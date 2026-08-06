# ai_engine.py - OPTIMIZED with 2-stage classification
import os
import json
import time
from transformers import AutoTokenizer, AutoModelForCausalLM, AutoModelForSequenceClassification
from sentence_transformers import SentenceTransformer
from keybert import KeyBERT
import faiss
import torch
import numpy as np
from dotenv import load_dotenv
from constants import BANK_PRODUCTS, SIMILARITY_CONFIG
from issue_lookup import ISSUE_LOOKUP
from severity import BASE_SEVERITY
from typing import Dict, List, Tuple, Any, Optional
import re
from chatbot_engine import ConversationManager

load_dotenv()


class AIEngine:
    def __init__(self):
        print("Initializing AIEngine...")

        self.dimension = 384

        # Use CUDA when available
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        print(f"✅ Using device: {self.device}")

        # Initialize SentenceTransformer
        self.embedder = SentenceTransformer(
            SIMILARITY_CONFIG["embedding_model"],
            device=str(self.device),
        )

        print("Precomputing product embeddings...")
        self.product_names = BANK_PRODUCTS
        self.product_embeddings = self.embedder.encode(
            self.product_names,
            convert_to_numpy=True
        ).astype("float32")
        
        faiss.normalize_L2(self.product_embeddings)
        self.product_index = faiss.IndexFlatIP(self.dimension)
        self.product_index.add(self.product_embeddings)
        print("✅ Product embeddings ready!")
        
        # Initialize KeyBERT with existing embedder
        self.kw_model = KeyBERT(model=self.embedder)

        # Initialize FinBERT for sentiment analysis
        self.finbert_tokenizer = AutoTokenizer.from_pretrained("ProsusAI/finbert")
        self.finbert_model = AutoModelForSequenceClassification.from_pretrained("ProsusAI/finbert").to(self.device)
        self.finbert_model.eval()


        # Initialize Qwen
        MODEL_NAME = "Qwen/Qwen2.5-0.5B-Instruct"
        self.qwen_tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
        self.qwen_model = AutoModelForCausalLM.from_pretrained(
            MODEL_NAME,
            low_cpu_mem_usage=True,
            torch_dtype=torch.float32,
        )
        self.qwen_model.to(self.device)
        self.qwen_model.eval()


        # Initialize FAISS index
          # MiniLM-L6-v2
        self.index = faiss.IndexFlatL2(self.dimension)
        self.complaint_ids = []

        # Precompute embeddings for all issue subtypes for every product!
        self.issue_embeddings: Dict[str, List[Dict]] = {}
        print("Precomputing issue subtype embeddings...")
        for product in ISSUE_LOOKUP.keys():
            self._get_subtype_embeddings(product)
        print("✅ Issue subtype embeddings ready!")

        self._sessions: Dict[str, Any] = {}
        print("✅ AIEngine initialized successfully!")

    
    def _build_product_list_str(self) -> str:
        """
        Render BANK_PRODUCTS as a numbered list for injection into prompts.
        Generated dynamically from the single source of truth — no manual maintenance.
        Adding a product to BANK_PRODUCTS automatically appears here.
        """
        return "\n".join(f"{i+1}. {p}" for i, p in enumerate(self.product_names))


    


    def _classify_product_llm(self, complaint_for_classification: str) -> str:
        """
        Classify banking product using a two-pass approach:
        Pass 1 — embedding search produces a GENEROUS shortlist (top 10 of 25).
                The shortlist is never used as a hard filter — it only re-ranks
                candidates so the LLM sees the most plausible ones first.
                k=10 ensures the correct product is almost always present even
                when embedding similarity is imperfect (e.g. "credit card" vs
                "Wallet / Prepaid Card" surface overlap on the word "card").
        Pass 2 — Qwen receives the shortlist and is prompted as a NAMED-ENTITY
                MATCHING task, not a reasoning task.
                Frame: "find the product whose name appears in or is directly
                implied by the complaint" — this plays to a 0.5B model's
                strength (token-level pattern matching) rather than its
                weakness (multi-option semantic reasoning).

        WHY k=10 INSTEAD OF k=5:
        With k=5, a complaint like "I lost my credit card" may receive a shortlist
        of [Wallet/Prepaid Card, Debit Card, ATM, Credit Card, ...] where
        "Credit Card" is ranked 4th or 5th — or excluded entirely — because
        MiniLM matches on token overlap and "card" appears in multiple product
        labels. The LLM then picks the wrong product from a wrong shortlist.
        k=10 costs nothing at inference time (FAISS search is O(n) regardless)
        and makes exclusion of the correct product extremely unlikely.

        WHY PATTERN-MATCHING FRAME INSTEAD OF SELECTION FRAME:
        "Choose the most relevant product" is a reasoning task — the model must
        evaluate all options simultaneously and rank them. At 0.5B parameters
        this degrades across more than ~5 options.
        "Find the product whose name is mentioned or implied" is a matching task —
        the model scans the list for a name that appears in the complaint text.
        Token-level matching is reliable at 0.5B. The model does not need to
        understand banking to match "credit card" → "Credit Card".

        WHY TWO FEW-SHOT EXAMPLES:
        One example anchors the output format (a number).
        The second example covers the ambiguous "card" case specifically —
        showing the model that "credit card" maps to "Credit Card" and not
        "Debit Card" or "Wallet / Prepaid Card". This is the exact failure
        mode we are fixing. Two examples is the minimum to cover it without
        overfitting the prompt to specific products.
        """

        # ── Pass 1: generous embedding shortlist ────────────────────────────
        # k=10 — large enough that the correct product is almost always present.
        # FAISS search cost is negligible; this is not a performance concern.
        embedding = self.embedder.encode(
            complaint_for_classification, convert_to_numpy=True
        ).astype("float32").reshape(1, -1)
        faiss.normalize_L2(embedding)

        k = min(8, len(self.product_names))
        scores, indices = self.product_index.search(embedding, k)

        candidates = []
        for score, idx in zip(scores[0], indices[0]):
            if idx != -1:
                candidates.append(self.product_names[idx])

        if not candidates:
            return self.product_names[0]

        print(f"🔍 Embedding shortlist (k={k}): {candidates}")

        # ── Pass 2: LLM as named-entity matcher ─────────────────────────────
        candidate_list = "\n".join(f"- {p}" for p in candidates)
        n = len(candidates)
        prompt = (
    "You are a banking complaint classifier.\n\n"

    "Read the customer's complaint carefully.\n"
    "Choose the ONE banking product that the customer is mainly complaining about.\n\n"

    "Rules:\n"
    "- Choose ONLY ONE product from the list.\n"
    "- Use only the customer's complaint.\n"
    "- If multiple products are mentioned, choose the primary product.\n"
    "- Return ONLY the product name exactly as it appears in the list.\n"
    "- Do not explain your answer.\n"
    "- Do not return anything except the product name.\n\n"

    f"Customer complaint:\n"
    f"{complaint_for_classification[:300]}\n\n"

    f"Products:\n"
    f"{candidate_list}\n\n"

    "Answer:"
)
       
    

        try:
            print("\n" + "=" * 80)
            print("TEXT SENT TO PRODUCT CLASSIFIER")
            print("=" * 80)
            print(repr(complaint_for_classification))
            print("=" * 80)
            messages = [{"role": "user", "content": prompt}]
            formatted = self.qwen_tokenizer.apply_chat_template(
                messages, tokenize=False, add_generation_prompt=True, enable_thinking=False
            )
            inputs = self.qwen_tokenizer([formatted], return_tensors="pt").to(self.qwen_model.device)
            with torch.inference_mode():
                print("=" * 80)
                print(prompt)
                print("=" * 80)
                outputs = self.qwen_model.generate(
                    **inputs,
                    max_new_tokens=15,
                    do_sample=False,
                    temperature=0.0,
                    use_cache=True,
                    eos_token_id=self.qwen_tokenizer.eos_token_id,
                    pad_token_id=self.qwen_tokenizer.eos_token_id,
                )
            generated_ids = outputs[0][len(inputs.input_ids[0]):]
            raw = self.qwen_tokenizer.decode(generated_ids, skip_special_tokens=True).strip()
            print(f"🧠 Product classification raw output: '{raw}'")
            
            raw_lower = raw.lower().strip()
            for product in candidates:
                if product.lower() in raw_lower:
                    print(f"✅ LLM classified product: {product}")
                    return product
                # Handle partial outputs like "Credit"
            for product in candidates:
                words = product.lower().split()
                if all(word in raw_lower for word in words):
                    print(f"✅ Partial product match: {product}")
                    return product

        except Exception as e:
            print(f"⚠️ LLM product classification failed: {e}")

        # Fallback: top embedding candidate
        print(f"⚠️ Falling back to top embedding candidate: '{candidates[0]}'")
        return candidates[0]


    def _check_vagueness_llm(self, complaint: str) -> bool:
        """
        Returns True if the complaint is too vague to classify.

        Why YES/NO instead of JSON:
        At max_new_tokens=5, JSON generation is unreliable. A YES/NO completion
        after a few-shot pattern is stable and requires only 1-2 tokens.
        """
        prompt = (
            "Is this banking complaint specific enough to act on, or is it too vague?\n\n"
            "Complaint: help\n"
            "Answer: TOO VAGUE\n\n"
            "Complaint: I have a problem\n"
            "Answer: TOO VAGUE\n\n"
            "Complaint: something is wrong\n"
            "Answer: TOO VAGUE\n\n"
            "Complaint: UPI payment failed, money deducted\n"
            "Answer: SPECIFIC\n\n"
            "Complaint: loan EMI deducted twice this month\n"
            "Answer: SPECIFIC\n\n"
            "Complaint: ATM card blocked after wrong PIN\n"
            "Answer: SPECIFIC\n\n"
            f"Complaint: {complaint[:200]}\n"
            "Answer:"
        )
        try:
            messages = [{"role": "user", "content": prompt}]
            formatted = self.qwen_tokenizer.apply_chat_template(
                messages, tokenize=False, add_generation_prompt=True, enable_thinking=False
            )
            inputs = self.qwen_tokenizer([formatted], return_tensors="pt").to(self.qwen_model.device)
            with torch.inference_mode():
                outputs = self.qwen_model.generate(
                    **inputs,
                    max_new_tokens=5,
                    do_sample=False,
                    temperature=0.0,
                    use_cache=True,
                    eos_token_id=self.qwen_tokenizer.eos_token_id,
                    pad_token_id=self.qwen_tokenizer.eos_token_id,
                )
            generated_ids = outputs[0][len(inputs.input_ids[0]):]
            raw = self.qwen_tokenizer.decode(generated_ids, skip_special_tokens=True).strip().upper()
            print(f"🔍 Vagueness check: '{complaint[:60]}' → {raw}")
            return "VAGUE" in raw
        except Exception as e:
            print(f"⚠️ Vagueness check failed: {e}")
            return False  # Safe default: treat as specific, let classification proceed


    def categorize_complaint(self, text: str):
        """
        CHANGE FROM ORIGINAL:
        - Product classification now uses the ORIGINAL complaint text (not reformulated).
        - Reformulation is still performed, but only feeds the subtype embedding search.
        - Added skip_reformulation parameter for the correction path, where the
        combined text is already clean enough for subtype search.
        """
        if not text or len(text.strip()) < 5:
            return {
                "specific": True,
                "product": "General",
                "issue_type": "General Inquiry",
                "issue_subtype": "General Inquiry",
                "sentiment": "Neutral",
                "sentiment_score": 0.5,
                "severity": 5,
                "keywords": ["complaint", "banking"],
            }

        start_time = time.time()
        full_text = text  # Keep full text for storage/embeddings
        # Truncate for FinBERT (max 512 tokens ~ 2000 chars) and LLM prompts (keep manageable)
        safe_text = text[:2000]
        print("\n" + "=" * 80)
        print("RAW TEXT RECEIVED BY CATEGORIZER")
        print("=" * 80)
        print(repr(safe_text))
        print("=" * 80)

        try:
            # ── Step 1: Reformulate — for subtype search ONLY ─────────────────
            # The original text is preserved separately for product classification.
           

            # ── Step 2: Vagueness check ───────────────────────────────────────
            if len(safe_text.split()) <= 8:
                if self._check_vagueness_llm(safe_text):
                    return {
                        "specific": False,
                        "reply": (
                            "Could you tell me a bit more about the issue you're facing? "
                            "For example, is it related to a payment, your card, account, or loan?"
                        ),
                    }

            # ── Step 3: Product classification — uses ORIGINAL text ───────────
            # Original text preserves product-anchoring nouns that reformulation
            # may strip. This is the most important change from the prior version.
            product = self._classify_product_llm(safe_text)

            # ── Step 4: Issue subtype — uses REFORMULATED text ────────────────
            # Reformulated text is a cleaner problem statement, which improves
            # cosine similarity against the issue subtype labels.
            issue_subtype = self._find_best_subtype_embedding(full_text, product)
            print(f"📌 Subtype: {issue_subtype}")

            # Normalize product key against ISSUE_LOOKUP
            product_subtypes = []
            for key in ISSUE_LOOKUP:
                if key.lower() == product.lower():
                    product_subtypes = ISSUE_LOOKUP[key]
                    product = key
                    break

            selected_issue_type = product if product_subtypes else "Other"
            if not issue_subtype or issue_subtype == "General Inquiry":
                issue_subtype = "General Inquiry"

            # ── Step 5: Sentiment, keywords, severity ────────────────────────
            sentiment, sentiment_score = self.analyze_sentiment(safe_text)
            keywords = self.extract_keywords(full_text)
            if not keywords or len(keywords) < 2:
                keywords = ["complaint", "banking"]
            severity = BASE_SEVERITY.get(issue_subtype, 5)

            print(f"📊 Categorization complete in {time.time() - start_time:.2f}s")

            return {
                "specific": True,
                "product": product,
                "issue_type": selected_issue_type,
                "issue_subtype": issue_subtype,
                "sentiment": sentiment,
                "sentiment_score": sentiment_score,
                "severity": severity,
                "keywords": keywords,
            }

        except Exception as e:
            print(f"Categorization error: {e}")
            import traceback
            traceback.print_exc()
            try:
                product, _ = self.find_best_product_embedding(full_text)
                issue_subtype = self._find_best_subtype_embedding(full_text, product)
                sentiment, sentiment_score = self.analyze_sentiment(safe_text)
                return {
                    "specific": True,
                    "product": product,
                    "issue_type": product,
                    "issue_subtype": issue_subtype,
                    "sentiment": sentiment,
                    "sentiment_score": sentiment_score,
                    "severity": BASE_SEVERITY.get(issue_subtype, 5),
                    "keywords": self.extract_keywords(safe_text),
                }
            except Exception:
                return {
                    "specific": False,
                    "reply": "Sorry, I couldn't process your request. Could you describe the issue again?",
                }

        

    def _precompute_issue_embeddings(self):
        """
        No longer precomputes anything at startup.
        Subtype embeddings are computed on first use per product
        and cached in self.issue_embeddings for reuse.
        Startup time is now unaffected by ISSUE_LOOKUP size.
        """
        # Initialize empty — populated lazily on first use per product
        self.issue_embeddings: Dict[str, List[Dict]] = {}
        print("✅ Subtype embeddings will load on first use per product.")
    
    def _get_subtype_embeddings(self, product: str) -> List[Dict]:
        """
        Return cached subtype embeddings for a product, computing them
        on first access if not yet cached.

        This is the only place subtype embeddings are ever computed.
        Cost is paid once per product per server session, not at startup.
        """
        if product in self.issue_embeddings:
            return self.issue_embeddings[product]

        subtypes = ISSUE_LOOKUP.get(product, [])
        if not subtypes:
            self.issue_embeddings[product] = []
            return []

        print(f"🔄 Computing subtype embeddings for '{product}' ({len(subtypes)} subtypes)...")

        expanded_texts = [
            f"{product} complaint: {subtype}"
            for subtype in subtypes
        ]

        embeddings = self.embedder.encode(
            expanded_texts,
            convert_to_numpy=True,
            show_progress_bar=False,
            batch_size=32,
        )

        self.issue_embeddings[product] = [
            {"text": subtype, "embedding": embedding}
            for subtype, embedding in zip(subtypes, embeddings)
        ]

        print(f"✅ '{product}' subtype embeddings cached.")
        return self.issue_embeddings[product]
    def extract_name(self, text: str):
        """Extract customer name — used by chatbot engine opportunistic extractor."""
        _NOT_A_NAME = {
            "atm", "upi", "neft", "rtgs", "imps", "otp", "emi", "pin",
            "loan", "card", "account", "bank", "payment", "transaction",
            "credit", "debit", "balance", "transfer", "fraud", "issue",
            "problem", "error", "unable", "blocked", "failed", "stolen",
            "lost", "wrong", "incorrect", "pending", "declined", "refund",
            "general", "inquiry", "unknown", "help", "support",
        }
        patterns = [
            r"my\s+name\s+is\s+([A-Za-z][A-Za-z\s]{1,30})",
            r"this\s+is\s+([A-Za-z][A-Za-z\s]{1,30})",
            r"name[:\-]?\s*([A-Za-z][A-Za-z\s]{1,30})",
            r"call\s+me\s+([A-Za-z][A-Za-z\s]{1,20})",
        ]
        text = text.strip()
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                name = match.group(1).strip()
                name = re.sub(
                    r"\s+(and|is|my|the|a|i|im|to|for|about|with)$",
                    "", name, flags=re.IGNORECASE
                ).strip()
                if len(name) < 2 or len(name) > 50:
                    continue
                name_words = {w.lower() for w in name.split()}
                if name_words & _NOT_A_NAME:
                    continue
                if any(ch.isdigit() for ch in name):
                    continue
                return name.title()
        return None

    @staticmethod
    def extract_customer_id(text: str) -> Optional[str]:
        """Extract a numeric customer / account ID from message."""
        match = re.search(r"\b(\d{5,16})\b", text)
        return match.group(1) if match else None


    def _generate_json(self, prompt: str, max_tokens: int, temperature: float = 0.1) -> Dict[str, Any]:
        total_start = time.time()
        try:
            t1_start = time.time()
            messages = [{"role": "user", "content": prompt}]
            formatted_prompt = self.qwen_tokenizer.apply_chat_template(
                messages, tokenize=False, add_generation_prompt=True, enable_thinking=False
            )
            template_time = time.time() - t1_start

            t2_start = time.time()
            inputs = self.qwen_tokenizer([formatted_prompt], return_tensors="pt").to(self.qwen_model.device)
            tokenization_time = time.time() - t2_start

            t3_start = time.time()
            with torch.inference_mode():
                outputs = self.qwen_model.generate(
                    **inputs,
                    max_new_tokens=max_tokens,
                    do_sample=False,
                    temperature=0.0,
                    use_cache=True,
                    
                    eos_token_id=self.qwen_tokenizer.eos_token_id,
                    pad_token_id=self.qwen_tokenizer.eos_token_id
                    )
            generate_time = time.time() - t3_start

            t4_start = time.time()
            generated_ids = outputs[0][len(inputs.input_ids[0]):]
            raw_response = self.qwen_tokenizer.decode(generated_ids, skip_special_tokens=True)
            decode_time = time.time() - t4_start
            generated_token_count = len(generated_ids)

            t5_start = time.time()
            json_start = raw_response.find('{')
            json_end = raw_response.rfind('}') + 1
            result = None
            
            print("\n" + "=" * 60)
            print("RAW MODEL OUTPUT:")
            print(raw_response)
            print("=" * 60)
            
            if json_start == -1 or json_end == 0:
                raise ValueError("No JSON found in model output")
            
            json_string = raw_response[json_start:json_end]
            print("\nJSON STRING:")
            print(json_string)
            
            try:
                result = json.loads(json_string)
            except json.JSONDecodeError as e:
                print(f"\nJSON Error: {e}")
                print("Invalid JSON:")
                print(json_string)
                raise
           

            json_parse_time = time.time() - t5_start
            total_time = time.time() - total_start

            print(f"⏱️ Generation Profile:")
            print(f"Template: {template_time:.2f}s")
            print(f"Tokenization: {tokenization_time:.2f}s")
            print(f"Generate: {generate_time:.2f}s")
            print(f"Decode: {decode_time:.2f}s")
            print(f"JSON Parse: {json_parse_time:.2f}s")
            print(f"Generated Tokens: {generated_token_count}")
            print(f"Total: {total_time:.2f}s")

            if result is not None:
                return result
            else:
                raise ValueError("No valid JSON found in response")
        except Exception as e:
            elapsed = time.time() - total_start
            print(f"❌ Generation failed after {elapsed:.2f}s: {e}")
            raise

    def _find_best_subtype_embedding(self, complaint: str, product: str) -> str:
        """
        Find the best matching subtype using lazy-loaded embeddings.
        First call for a product triggers embedding computation.
        All subsequent calls for the same product use the cache.
        """
        subtype_list = self._get_subtype_embeddings(product)

        if not subtype_list:
            return "General Inquiry"

        subtype_embeddings = np.array(
            [s["embedding"] for s in subtype_list]
        ).astype("float32")

        normed_subtypes = subtype_embeddings.copy()
        faiss.normalize_L2(normed_subtypes)

        faiss_index = faiss.IndexFlatIP(self.dimension)
        faiss_index.add(normed_subtypes)

        lines = [l.strip() for l in complaint.split("\n") if l.strip()]
        if not lines:
            lines = [complaint]

        best_score = -1.0
        best_subtype = "General Inquiry"
        k = min(3, len(subtype_list))

        for line in lines:
            contextualized = f"{product} complaint: {line}"

            line_embedding = self.embedder.encode(
                contextualized,
                convert_to_numpy=True,
                show_progress_bar=False,
            ).reshape(1, -1).astype("float32")
            faiss.normalize_L2(line_embedding)

            D, I = faiss_index.search(line_embedding, k)

            for score, idx in zip(D[0], I[0]):
                score = float(score)
                candidate = subtype_list[idx]["text"]
                print(f"  📎 '{line[:50]}' → '{candidate}' (score={score:.3f})")

                if score > best_score:
                    best_score = score
                    best_subtype = candidate

        print(f"  ✅ Best subtype: '{best_subtype}' (score={best_score:.3f})")
        return best_subtype


    def analyze_sentiment(self, text: str) -> Tuple[str, float]:
        inputs = self.finbert_tokenizer(
            text[:512],
            return_tensors="pt",
            truncation=True,
            padding=True,
        ).to(self.device)
        with torch.inference_mode():
            outputs = self.finbert_model(**inputs)

            logits = outputs.logits
            probabilities = torch.softmax(logits, dim=-1)
            predicted_class = torch.argmax(probabilities, dim=-1).item()
            confidence = probabilities[0][predicted_class].item()
        
        label_map = {0: "Positive", 1: "Negative", 2: "Neutral"}
        sentiment = label_map.get(predicted_class, "Neutral")
        # Convert confidence to a score 0-1, with Negative=1.0, Neutral=0.5, Positive=0.0
        if sentiment == "Negative":
            sentiment_score = confidence
        elif sentiment == "Neutral":
            sentiment_score = 0.5 * confidence
        else:
            sentiment_score = 0.0
        
        return sentiment, sentiment_score

    def extract_keywords(self, text: str) -> List[str]:
        keywords = self.kw_model.extract_keywords(
            text[:1000], 
            keyphrase_ngram_range=(1, 2), 
            stop_words='english', 
            top_n=5
        )
        return [kw[0] for kw in keywords]
    
    

    def find_best_product_embedding(self, complaint: str) -> Tuple[str, float]:
        """Emergency fallback — used only when LLM classification fails entirely."""
        embedding = self.embedder.encode(
            complaint, convert_to_numpy=True
        ).astype("float32").reshape(1, -1)
        faiss.normalize_L2(embedding)
        scores, indices = self.product_index.search(embedding, 1)
        if indices[0][0] != -1:
            return self.product_names[indices[0][0]], float(scores[0][0])
        return "General", 0.0
   
                
    def get_embedding(self, text: str) -> np.ndarray:
        return self.embedder.encode([text])[0]

    def find_similar_complaints(self, embedding: np.ndarray, threshold: float = 0.78) -> List[Tuple[str, float]]:
        if self.index.ntotal == 0:
            return []
        D, I = self.index.search(np.array([embedding]).astype('float32'), 5)
        results = []
        for dist, idx in zip(D[0], I[0]):
            if idx != -1:
                similarity = 1 / (1 + dist)
                if similarity >= threshold:
                    results.append((self.complaint_ids[idx], similarity))
        return results

    def add_to_index(self, complaint_id: str, embedding: np.ndarray):
        self.index.add(np.array([embedding]).astype('float32'))
        self.complaint_ids.append(complaint_id)

    def generate_acknowledgement(self, product: str, issue: str, sla_deadline: str, complaint_id: str, complaint_text: str) -> str:
        safe_text = complaint_text[:500]
        return f"We have received your complaint regarding {issue} on {product}. The complaint has been registered and is under review by the concerned team. The resolution is expected by {sla_deadline} without committing to an outcome. Your complaint reference ID is {complaint_id}; please contact us if needed."
    
    def get_or_create_session(self, session_id: str) -> "ConversationManager":
        if session_id not in self._sessions:
            self._sessions[session_id] = ConversationManager(self)
            print(f"🆕 New session created: {session_id}")
        return self._sessions[session_id]

    def clear_session(self, session_id: str):
        self._sessions.pop(session_id, None)
        print(f"🗑️ Session cleared: {session_id}")

    async def get_chatbot_response(
            self,
            message: str,
            history,
            existing_fields=None,
            session_id: str = "default",
    ):
        chatbot = self.get_or_create_session(session_id)
        return await chatbot.respond(message, history, existing_fields)

    async def identify_root_cause(self, narratives: List[str], product: str) -> dict:
        if not narratives:
            return {
                "current_issues": "No data available for analysis.",
                "recommendation": "No data available for analysis."
            }
        
        # Step 1: Batch the complaints and create combined context
        batch_size = 5
        batches = [narratives[i:i+batch_size] for i in range(0, len(narratives), batch_size)]
        
        batch_summaries = []
        for batch_num, batch in enumerate(batches, 1):
            print(f"📄 Processing batch {batch_num}/{len(batches)}...")
            batch_text = "\n\n---\n\n".join([f"Complaint {i+1}:\n{text}" for i, text in enumerate(batch)])
            
            prompt = f"""PRODUCT: {product}

BATCH OF COMPLAINTS:
{batch_text}

ABSTRACT THIS BATCH INTO CONCISE TRENDS ONLY.
- DO NOT INCLUDE ANY INDIVIDUAL COMPLAINT DETAILS.
- LIST ONLY THE BROAD ISSUE PATTERNS AND THEMES.
- MAX 100 WORDS."""
            
            try:
                messages = [{"role": "user", "content": prompt}]
                formatted = self.qwen_tokenizer.apply_chat_template(
                    messages,
                    tokenize=False,
                    add_generation_prompt=True,
                    enable_thinking=False
                )
                inputs = self.qwen_tokenizer([formatted], return_tensors="pt").to(self.qwen_model.device)
                with torch.inference_mode():
                    outputs = self.qwen_model.generate(
                        **inputs,
                        max_new_tokens=100,
                        temperature=0.3,
                        top_p=0.9,
                        use_cache=True,
                        eos_token_id=self.qwen_tokenizer.eos_token_id,
                        pad_token_id=self.qwen_tokenizer.eos_token_id,
                    )
                generated_ids = outputs[0][len(inputs.input_ids[0]):]
                batch_summary = self.qwen_tokenizer.decode(generated_ids, skip_special_tokens=True).strip()
                batch_summaries.append(batch_summary)
            except Exception as e:
                print(f"⚠️ Failed to summarize batch {batch_num}: {e}")
                continue
        
        if not batch_summaries:
            return {
                "current_issues": "Could not analyze complaints due to errors.",
                "recommendation": "Could not analyze complaints due to errors."
            }
        
        combined_summaries = "\n\n---\n\n".join(batch_summaries)

        # Helper function to generate sections
        async def generate_section(section_prompt: str, max_tokens: int) -> str:
            try:
                messages = [{"role": "user", "content": section_prompt}]
                formatted = self.qwen_tokenizer.apply_chat_template(
                    messages,
                    tokenize=False,
                    add_generation_prompt=True,
                    enable_thinking=False
                )
                inputs = self.qwen_tokenizer([formatted], return_tensors="pt").to(self.qwen_model.device)
                with torch.inference_mode():
                    outputs = self.qwen_model.generate(
                        **inputs,
                        max_new_tokens=max_tokens,
                        temperature=0.4,
                        top_p=0.9,
                        use_cache=True,
                        eos_token_id=self.qwen_tokenizer.eos_token_id,
                        pad_token_id=self.qwen_tokenizer.eos_token_id,
                    )
                generated_ids = outputs[0][len(inputs.input_ids[0]):]
                return self.qwen_tokenizer.decode(generated_ids, skip_special_tokens=True).strip()
            except Exception as e:
                return f"Generation failed: {str(e)}"

        # First, generate CURRENT ISSUES SPOTTED (Product Risk Manager internal report)
        issues_prompt = f"""You are a Product Risk Manager at a major bank, preparing an internal report for senior management.

You are given summaries of multiple complaint batches for the product: "{product}".

REQUIREMENTS (OUTPUT MUST BE A SHORT PARAGRAPH, NOT BULLETS):
- Return ONLY 3-6 issue themes as a single paragraph.
- Each theme must be a complete sentence.
- Professional, formal language for senior management.
- No customer names/identifiers.
- No customer-facing language, apologies, or sympathy.
- Focus on systemic patterns across the entire product.
- 160 words MAX.

STRICT OUTPUT RULE:
- Output ONLY the paragraph text and stop. No headings.
"""

        current_issues = await generate_section(issues_prompt, 160)

        # Finally, generate SYSTEMIC RECOMMENDATIONS (Product Risk Manager internal report)
        rec_prompt = f"""You are a Product Risk Manager at a major bank, preparing an internal report for senior management.

You are given summaries of multiple complaint batches for the product: "{product}".

Current Issues Identified:
{current_issues}

REQUIREMENTS (OUTPUT MUST BE A SHORT PARAGRAPH, NOT BULLETS):
- Return ONLY 3-4 recommendations as a single paragraph.
- Each recommendation must be a complete sentence.
- Focus on systemic root-cause solutions preventing recurrence.
- No customer-facing language, issue-by-issue fixes, or "we'll help you" language.
- No references to individual customers or complaints.
- 100 words MAX.

STRICT OUTPUT RULE:
- Output ONLY the paragraph text and stop. No headings.
"""

        recommendation = await generate_section(rec_prompt, 160)

        
        return {
            "current_issues": current_issues,
            "recommendation": recommendation
        }
