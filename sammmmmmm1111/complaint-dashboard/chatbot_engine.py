# chatbot_engine.py
# Hybrid AI chatbot for Banking Complaint Resolution System.
# Uses rule-based logic for simple interactions and LLM only when truly needed.
# Drop-in replacement for get_chatbot_response() in ai_engine.py.

import re
import time
import torch
from enum import Enum
from typing import Dict, List, Any, Optional, Tuple


# ─────────────────────────────────────────────
# Conversation stages
# ─────────────────────────────────────────────
class Stage(str, Enum):
    GREETING          = "GREETING"          # User just said hi / we haven't started yet
    WAITING_FOR_ISSUE = "WAITING_FOR_ISSUE" # We know who the user is but not the problem
    WAITING_FOR_NAME  = "WAITING_FOR_NAME"  # Problem known, need customer name
    WAITING_FOR_ID    = "WAITING_FOR_ID"    # Name known, need customer ID
    WAITING_CONFIRM   = "WAITING_CONFIRM"   # All fields collected, awaiting yes/no
    REGISTERED        = "REGISTERED"        # User confirmed → caller registers complaint
    COMPLETED         = "COMPLETED"         # End state


# ─────────────────────────────────────────────
# Intent labels
# ─────────────────────────────────────────────
class Intent(str, Enum):
    GREETING        = "GREETING"
    NEW_COMPLAINT   = "NEW_COMPLAINT"
    CORRECT_PRODUCT = "CORRECT_PRODUCT"   # ← add this
    PROVIDE_NAME    = "PROVIDE_NAME"
    PROVIDE_ID      = "PROVIDE_ID"
    CONFIRM_YES     = "CONFIRM_YES"
    CONFIRM_NO      = "CONFIRM_NO"
    UNKNOWN         = "UNKNOWN"


# ─────────────────────────────────────────────
# Lightweight, regex / keyword intent detector
# (No LLM cost for these simple cases)
# ─────────────────────────────────────────────

# Words that strongly signal a banking complaint
_COMPLAINT_SIGNALS = [
    "failed", "error", "stolen", "blocked", "fraud",
    "charged", "deducted", "not working", "unable", "can't", "cannot",
    "register", "lost", "unauthorised", "unauthorized",
    "declined", "pending", "stuck", "wrong", "incorrect", "delay", "late",
    "refund", "dispute", "transaction", "upi", "atm", "neft", "imps",
    "credit card", "debit card", "loan", "emi", "account", "balance",
    "transfer", "payment", "otp", "net banking", "mobile banking",
    # Product nouns — user mentioning these IS a complaint signal
    "card", "wallet", "cheque", "fd", "fixed deposit", "rd", "insurance",
    "passbook", "kyc", "forex", "locker", "pension", "mortgage",
]
_NOT_A_NAME = {
    "atm", "upi", "neft", "rtgs", "imps", "otp", "emi", "pin",
    "loan", "card", "account", "bank", "payment", "transaction",
    "credit", "debit", "balance", "transfer", "fraud", "issue",
    "problem", "error", "unable", "blocked", "failed", "stolen",
    "lost", "wrong", "incorrect", "pending", "declined", "refund",
    "general", "inquiry", "unknown", "help", "support",
}

_GREETING_WORDS = {"hi", "hello", "hey", "greetings", "good morning",
                   "good afternoon", "good evening", "howdy", "namaste"}

_YES_WORDS   = {"yes", "yeah", "yep", "yup", "sure", "confirm",
                "correct", "ok", "okay", "proceed", "go ahead",
                "please do", "please register", "that's right", "right"}

_NO_WORDS = {
    "no", "nope", "nah", "cancel", "stop", "don't", "do not",
    "incorrect", "wrong", "not right", "change", "edit", "modify",
    "wait", "hold", "not yet", "update", "correction", "mistake",
    "error", "redo", "restart",
}

# Messages that are clearly vague — warrant a canned "tell me more" response
# without any LLM call.
_VAGUE_SIGNALS = {
    "help", "issue", "problem", "complaint", "wrong", "trouble",
    "concern", "query", "support", "assist", "assistance", "question",
    "something", "anything", "everything", "nothing", "please help",
    "need help", "facing issue", "having problem", "i have a problem",
    "i have an issue", "i have a concern", "something is wrong",
    "something went wrong", "there is a problem",
}

def _is_vague(message: str) -> bool:
    """Returns True only if the message has no identifiable banking context."""
    msg = message.strip().lower()

    # If any complaint signal is present, it is NOT vague
    if any(sig in msg for sig in _COMPLAINT_SIGNALS):
        return False

    # Short message matching a known vague phrase
    if len(msg.split()) <= 6:
        for signal in _VAGUE_SIGNALS:
            if signal in msg:
                return True

    # Bare 1-2 word message with no banking context
    if len(msg.split()) <= 2:
        return True

    return False

def detect_intent(message: str, stage: Stage) -> Intent:
    msg = message.strip().lower()
    words = set(re.findall(r"\w+", msg))
    word_list = msg.split()
    stripped = msg.strip()

    has_greeting = bool(words & _GREETING_WORDS)
    has_complaint_signal = any(sig in msg for sig in _COMPLAINT_SIGNALS)

    if has_greeting and not has_complaint_signal and len(word_list) <= 6:
        return Intent.GREETING

    if stage == Stage.WAITING_CONFIRM:
        text = msg.lower()
        negative_patterns = [
            "don't", "do not", "dont", "not now", "no", "nope", "nah",
            "cancel", "stop", "not yet", "later", "don't register",
            "do not register", "i don't want", "i do not want"
        ]
        if any(p in text for p in negative_patterns):
            return Intent.CONFIRM_NO
        positive_patterns = [
            "yes", "yeah", "yep", "sure", "confirm", "go ahead",
            "please register", "register it", "proceed"
        ]
        if any(p in text for p in positive_patterns):
            return Intent.CONFIRM_YES

    # Standalone numeric ID
    if re.fullmatch(r"\d{5,16}", stripped):
        return Intent.PROVIDE_ID
    if re.search(r"\b(customer\s*id|cid|account\s*number|acc\s*no|my\s*id)\b", msg):
        if re.search(r"\b\d{5,16}\b", msg):
            return Intent.PROVIDE_ID

    # Name provision
    if re.search(r"\bmy\s+name\s+is\b|\bthis\s+is\b", msg):
        if not has_complaint_signal:
            return Intent.PROVIDE_NAME
    if stage == Stage.WAITING_FOR_NAME:
        if re.search(r"\bi\s+am\b", msg) and not has_complaint_signal:
            return Intent.PROVIDE_NAME
        if re.fullmatch(r"[a-z][a-z\s]{1,40}", stripped) and len(stripped.split()) <= 4:
            return Intent.PROVIDE_NAME

    if stage == Stage.WAITING_FOR_ID:
        if re.search(r"\b\d{5,16}\b", msg):
            return Intent.PROVIDE_ID

    if has_complaint_signal:
        return Intent.NEW_COMPLAINT

    if has_greeting:
        return Intent.GREETING

    return Intent.UNKNOWN


# ─────────────────────────────────────────────
# Field extractors (pure regex, zero LLM cost)
# ─────────────────────────────────────────────

def extract_name(text: str) -> Optional[str]:
    """Extract customer name from message."""
    patterns = [
        r"my\s+name\s+is\s+([A-Za-z][A-Za-z\s]{1,30})",
        r"i\s+am\s+([A-Za-z][A-Za-z\s]{1,30})",
        r"this\s+is\s+([A-Za-z][A-Za-z\s]{1,30})",
        r"name[:\-]?\s*([A-Za-z][A-Za-z\s]{1,30})",
        r"call\s+me\s+([A-Za-z][A-Za-z\s]{1,20})",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            name = match.group(1).strip()
            # Remove trailing filler words
            name = re.sub(r"\s+(and|is|my|the|a|i|im)$", "", name, flags=re.IGNORECASE)
            if 2 <= len(name) <= 50:
                return name.title()
    return None


def extract_customer_id(text: str) -> Optional[str]:
    """Extract a numeric customer / account ID from message."""
    match = re.search(r"\b(\d{5,12})\b", text)
    return match.group(1) if match else None


# ─────────────────────────────────────────────
# Confirmation summary builder (no LLM)
# ─────────────────────────────────────────────

def build_confirmation_summary(fields: Dict[str, Any]) -> str:
    lines = [
        "Here's a summary of your complaint:",
        f"  • Customer Name : {fields.get('customer_name', '—')}",
        f"  • Customer ID   : {fields.get('customer_id', '—')}",
        f"  • Product       : {fields.get('product', '—')}",
        f"  • Issue         : {fields.get('issue', '—')}",
        f"  • Details       : {str(fields.get('narrative', '—'))}",
        "",
        "Would you like me to register this complaint? (Yes / No)",
    ]
    return "\n".join(lines)


# ─────────────────────────────────────────────
# ConversationManager
# ─────────────────────────────────────────────

class ConversationManager:
    REQUIRED_FIELDS = ["customer_name", "customer_id", "product", "issue", "narrative"]

    _FIELD_QUESTIONS: Dict[str, str] = {
        "narrative":     (
            "Could you please describe the issue you're facing in detail? "
            "For example, what happened, when did it occur, and what was the amount involved?"
        ),
        "customer_name": "May I have your full name, please?",
        "customer_id":   (
            "Could you please share your Customer ID? "
            "It's the 5–12 digit number associated with your bank account."
        ),
        "product":       (
            "Which banking product or service does this concern? "
            "(e.g. Credit Card, UPI, Savings Account, Loan)"
        ),
        "issue":         (
            "Could you briefly describe the type of problem? "
            "(e.g. Failed transaction, Account blocked, Wrong charge)"
        ),
    }

    async def _is_correction(self, message: str) -> bool:
        """
        Detect whether the customer is correcting the chatbot's classification.

        Why few-shot YES/NO instead of JSON or reasoning:
        Qwen 0.5B completes demonstrated patterns reliably at minimal token cost.
        The examples show the format only — they contain no banking-specific rules.
        The same prompt works correctly for any product or issue type.

        Guard: only called when a non-General product is already set.
        This means the LLM call is skipped for the majority of turns.
        """
        current_product = self.fields.get("product", "")
        current_issue = self.fields.get("issue", "")

        if not current_product or current_product == "General":
            return False

        prompt = (
            "In a customer support chat, the chatbot stated a classification.\n"
            "Did the customer's reply disagree with or correct that classification?\n\n"
            "Classification: Credit Card / Billing Error\n"
            "Customer: No, this is about my loan account\n"
            "Answer: YES\n\n"
            "Classification: UPI / Failed Transaction\n"
            "Customer: Yes that is correct, please proceed\n"
            "Answer: NO\n\n"
            "Classification: Mobile Banking / App Login Issue\n"
            "Customer: Actually this is about my demat account\n"
            "Answer: YES\n\n"
            "Classification: Savings Account / Balance Discrepancy\n"
            "Customer: The amount was 5000 rupees and it was debited on Monday\n"
            "Answer: NO\n\n"
            "Classification: Internet Banking / Password Reset\n"
            "Customer: My name is Rahul Sharma\n"
            "Answer: NO\n\n"
            f"Classification: {current_product} / {current_issue}\n"
            f"Customer: {message[:200]}\n"
            "Answer:"
        )

        try:
            messages = [{"role": "user", "content": prompt}]
            formatted = self._ai.qwen_tokenizer.apply_chat_template(
                messages, tokenize=False, add_generation_prompt=True, enable_thinking=False
            )
            inputs = self._ai.qwen_tokenizer([formatted], return_tensors="pt").to(
                self._ai.qwen_model.device
            )
            with torch.inference_mode():
                outputs = self._ai.qwen_model.generate(
                    **inputs,
                    max_new_tokens=5,
                    do_sample=False,
                    temperature=0.0,
                    use_cache=True,
                    eos_token_id=self._ai.qwen_tokenizer.eos_token_id,
                    pad_token_id=self._ai.qwen_tokenizer.eos_token_id,
                )
            generated_ids = outputs[0][len(inputs.input_ids[0]):]
            raw = self._ai.qwen_tokenizer.decode(generated_ids, skip_special_tokens=True).strip().upper()
            print(f"🔍 Correction check → '{raw}' for: '{message[:60]}'")
            # "YES" must appear and must not be preceded by "NO"
            return "YES" in raw and not raw.startswith("NO")

        except Exception as e:
            print(f"⚠️ Correction detection failed: {e}")
            return False
    
    def _question_for(self, field: str) -> str:
        return self._FIELD_QUESTIONS.get(field, "Could you provide more details?")

    def __init__(self, ai_engine):
        self._ai = ai_engine
        self.stage   = Stage.GREETING
        self.fields: Dict[str, Any] = {}

    # ------------------------------------------------------------------
    # Public entry point – mirrors the old get_chatbot_response signature
    # ------------------------------------------------------------------
    async def respond(
        self,
        message: str,
        history: List[Dict[str, str]],
        existing_fields: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Process one user turn and return:
            {
                "answer": "<bot reply>",
                "metadata": {
                    "status": "<stage name>",
                    "fields": { … }
                }
            }
        """
        start = time.time()

        # Merge any externally tracked fields (e.g. from a previous session)
        if existing_fields:
            for k, v in existing_fields.items():
                if v and k not in self.fields:
                    self.fields[k] = v

        # Try to extract name / ID from every message opportunistically
        self._opportunistic_extract(message)

        # Detect intent cheaply
        intent = detect_intent(message, self.stage)

        # Route to the appropriate handler
        answer = await self._handle(message, intent, history)

        elapsed = time.time() - start
        print(f"🤖 Chatbot responded in {elapsed:.2f}s  [stage={self.stage}, intent={intent}]")

        return {
            "answer": answer,
            "metadata": {
                "status": self.stage.value,
                "fields": dict(self.fields),
            },
        }

    # ------------------------------------------------------------------
    # Intent → handler dispatch
    # ------------------------------------------------------------------
    async def _handle(
    self,
    message: str,
    intent: Intent,
    history: List[Dict[str, str]],
) -> str:

        # ── Terminal states ──────────────────────────────────────────────
        if self.stage in (Stage.REGISTERED, Stage.COMPLETED):
            self.stage = Stage.GREETING
            self.fields = {}
            intent = detect_intent(message, self.stage)

        # ── Greeting only (no complaint content) ─────────────────────────
        if intent == Intent.GREETING:
            self.stage = Stage.WAITING_FOR_ISSUE
            return (
                "Hello! Welcome to our Banking Support Centre. "
                "How can I assist you today? Please describe the issue you're facing."
            )

        # ── Correction detection ──────────────────────────────────────────
        # Only checked when a non-General product is already classified.
        # FIX: the correction path now bypasses categorize_complaint's reformulation.
        # Reformulation can strip the correcting noun ("loan", "demat") from a
        # meta-comment like "No, this is about my loan account", making reclassification
        # no better than the original. Instead we classify the correction directly.
        if self.fields.get("product") and self.fields["product"] != "General":
            if await self._is_correction(message):
                original_narrative = self.fields.get("narrative", "")

                # Clear stale classification, preserve identity fields
                for field in ["product", "issue", "narrative", "severity", "sentiment", "keywords"]:
                    self.fields.pop(field, None)

                # Classify product directly from correction text — no reformulation.
                # The correction phrase ("this is about my loan account") contains
                # the product noun explicitly; reformulation would likely lose it.
                try:
                    new_product = self._ai._classify_product_llm(message)
                    if new_product and new_product != "General":
                        self.fields["product"] = new_product

                    # For subtype, combine original narrative with correction for context.
                    combined = f"{original_narrative}. {message}".strip(". ")

                    # If we already have customer identity fields and only issue/subtype
                    # needs adjustment, avoid re-running full categorize_complaint.
                    # (This can be expensive due to LLM + sentiment/keyword passes.)
                    if self.fields.get("narrative") and self.fields.get("issue"):
                        # Recompute only issue/subtype from embedding similarity.
                        # This uses the current product label without forcing a reformulation.
                        product_for_lookup = self.fields.get("product", "")
                        issue_subtype = self._ai._find_best_subtype_embedding(combined, product_for_lookup)
                        self.fields["issue"] = issue_subtype if issue_subtype else "General Inquiry"
                        return await self._next_question(ack)

                    cat = self._ai.categorize_complaint(combined)


                    if cat.get("specific", True):
                        # Trust the subtype from combined context, but keep our
                        # directly-classified product (more reliable for corrections).
                        if new_product and new_product != "General":
                            cat["product"] = new_product
                        self.fields["issue"] = cat.get("issue_subtype", "General Inquiry")
                        self.fields["severity"] = cat.get("severity", 5)
                        self.fields["sentiment"] = cat.get("sentiment", "Neutral")
                        self.fields["keywords"] = cat.get("keywords", [])
                        self.fields["narrative"] = combined

                except Exception as e:
                    print(f"⚠️ Correction reclassification error: {e}")
                    # Leave fields cleared — _next_question will ask for the issue again

                product_label = self.fields.get("product", "")
                ack = (
                    f"Of course, I apologize for the confusion. "
                    f"I've updated that — this is regarding your {product_label}. "
                ) if product_label and product_label != "General" else (
                    "Of course, I apologize for that. Let me update the details. "
                )
                return await self._next_question(ack)

        # ── Greeting + complaint ──────────────────────────────────────────
        if intent == Intent.NEW_COMPLAINT:
            msg_lower = message.strip().lower()
            has_greeting = bool(set(re.findall(r"\w+", msg_lower)) & _GREETING_WORDS)
            if has_greeting and self.stage == Stage.GREETING:
                self.stage = Stage.WAITING_FOR_ISSUE
                complaint_response = await self._handle_complaint(message)
                return f"Hello! Welcome to our Banking Support Centre.\n\n{complaint_response}"
            return await self._handle_complaint(message)

        # ── Name provided ─────────────────────────────────────────────────
        if intent == Intent.PROVIDE_NAME:
            name = extract_name(message) or message.strip().title()
            if any(ch.isdigit() for ch in name) or len(name.split()) > 5:
                return await self._next_question("I didn't catch a valid name there.")
            self.fields["customer_name"] = name
            return await self._next_question(f"Thank you, {name}.")

        # ── Customer ID provided ──────────────────────────────────────────
        if intent == Intent.PROVIDE_ID:
            cid = extract_customer_id(message)
            if cid:
                self.fields["customer_id"] = cid
                return await self._next_question("Got it, thank you.")
            return "I couldn't find a valid Customer ID. Could you please share your 5–12 digit Customer ID?"

        # ── Confirmation Yes ──────────────────────────────────────────────
        if intent == Intent.CONFIRM_YES:
            self.stage = Stage.REGISTERED
            return (
                "Thank you for confirming. Your complaint has been registered successfully. "
                "You will receive updates via your registered contact details."
            )

        # ── Confirmation No ───────────────────────────────────────────────
        if intent == Intent.CONFIRM_NO:
            for field in ["product", "issue", "narrative", "severity", "sentiment", "keywords"]:
                self.fields.pop(field, None)
            self.stage = Stage.WAITING_FOR_ISSUE
            name = self.fields.get("customer_name", "")
            greeting = f"Of course, {name}." if name else "Of course."
            return (
                f"{greeting} No problem at all. "
                "Could you describe the issue again so I can make sure we get the details right?"
            )

        # ── Vague message ────────────────────────────────────────────────
        if _is_vague(message):
            self.stage = Stage.WAITING_FOR_ISSUE
            return (
                "I'd be happy to help. Could you describe the banking issue you're facing? "
                "For example, is it related to a payment, your card, account, or loan?"
            )

        # ── Ambiguous reply at confirmation stage ─────────────────────────
        if self.stage == Stage.WAITING_CONFIRM:
            return (
                "I didn't quite catch that. Would you like me to register this complaint? "
                "Please reply with Yes to confirm or No to make changes."
            )

        # ── Unknown — LLM as last resort ─────────────────────────────────
        # Hard guard: if all required fields are already complete, skip LLM fallback.
        missing_fields = [f for f in self.REQUIRED_FIELDS if not self.fields.get(f)]
        if not missing_fields:
            self.stage = Stage.WAITING_CONFIRM
            summary = build_confirmation_summary(self.fields)
            return summary
        return await self._llm_fallback(message, history)




    async def _handle_complaint(self, message: str) -> str:
        """
        Classify the complaint and advance to the next missing field.

        CHANGE FROM ORIGINAL:
        categorize_complaint is now called without skip_reformulation (default False),
        so it internally reformulates for subtype search but uses original text for
        product classification. No change to this function's interface — the fix
        lives in categorize_complaint and _classify_product_llm.
        """
        # Early-return: if product & issue are already specific enough,
        # don't re-run categorize_complaint.
        # (Especially avoid repeated embeddings when issue is already "General Inquiry".)
        if (
            self.fields.get("product")
            and self.fields.get("product") != "General"
            and self.fields.get("issue")
            and self.fields.get("issue") == "General Inquiry"
            and len(str(self.fields.get("narrative", "")).split()) > 5
        ):
            product_label = self.fields.get("product", "your banking service")
            issue_label = self.fields.get("issue", "banking issue")
            preamble = (
                f"I understand you're having an issue with your {product_label} "
                f"— specifically regarding '{issue_label}'. "
                "I'll help you register a complaint right away."
            )
            return await self._next_question(preamble)

        needs_classification = (
            not self.fields.get("product")
            or self.fields.get("product") == "General"
            or not self.fields.get("issue")
            or self.fields.get("issue") == "General Inquiry"
            or len(str(self.fields.get("narrative", "")).split()) <= 5
        )


        if needs_classification:
            try:
                cat = self._ai.categorize_complaint(message)

                if not cat.get("specific", True):
                    self.stage = Stage.WAITING_FOR_ISSUE
                    return cat.get(
                        "reply",
                        "Could you describe the banking issue in more detail? "
                        "For example, which service is affected — UPI, card, loan, account?",
                    )

                product = cat.get("product", "")
                if product and product != "General":
                    self.fields["product"] = product

                issue_subtype = cat.get("issue_subtype", "General Inquiry")

                if len(message.strip().split()) <= 4 and issue_subtype != "General Inquiry":
                    self.fields["narrative"] = message
                    self.stage = Stage.WAITING_FOR_ISSUE
                    product_label = self.fields.get("product", "your banking service")
                    return (
                        f"I can see this is regarding your {product_label}. "
                        "Could you briefly describe what the issue is?"
                    )

                self.fields["issue"] = issue_subtype
                self.fields["severity"] = cat.get("severity", 5)
                self.fields["sentiment"] = cat.get("sentiment", "Neutral")
                self.fields["keywords"] = cat.get("keywords", [])

                existing_narrative = str(self.fields.get("narrative", ""))
                if len(message.split()) > len(existing_narrative.split()):
                    self.fields["narrative"] = message

            except Exception as e:
                print(f"⚠️ categorize_complaint error: {e}")
                if not self.fields.get("product"):
                    self.fields["product"] = "General"
                if not self.fields.get("issue"):
                    self.fields["issue"] = "General Inquiry"
                if not self.fields.get("narrative"):
                    self.fields["narrative"] = message

        product_label = self.fields.get("product", "your banking service")
        issue_label = self.fields.get("issue", "banking issue")

        if product_label and product_label != "General":
            preamble = (
                f"I understand you're having an issue with your {product_label} "
                f"— specifically regarding '{issue_label}'. "
                "I'll help you register a complaint right away."
            )
        else:
            preamble = (
                "I understand you're facing a banking issue. "
                "I'll help you register a complaint."
            )

        return await self._next_question(preamble)
    # ------------------------------------------------------------------
    # Decide which field to ask for next
    # ------------------------------------------------------------------
    async def _next_question(self, preamble: str = "") -> str:
        missing = [f for f in self.REQUIRED_FIELDS if not self.fields.get(f)]

        if not missing:
            # All fields collected → go to confirmation
            self.stage = Stage.WAITING_CONFIRM
            summary = build_confirmation_summary(self.fields)
            return (f"{preamble}\n\n{summary}" if preamble else summary).strip()

        next_field = missing[0]

        # Update stage
        stage_map = {
            "narrative":      Stage.WAITING_FOR_ISSUE,
            "customer_name":  Stage.WAITING_FOR_NAME,
            "customer_id":    Stage.WAITING_FOR_ID,
            "product":        Stage.WAITING_FOR_ISSUE,
            "issue":          Stage.WAITING_FOR_ISSUE,
        }
        self.stage = stage_map.get(next_field, Stage.WAITING_FOR_ISSUE)

        question = self._question_for(next_field)
        return f"{preamble} {question}".strip() if preamble else question

    def _question_for(self, field: str) -> str:
        questions = {
            "narrative":     "Could you please describe the issue you are facing in detail?",
            "customer_name": "May I have your full name, please?",
            "customer_id":   "Could you please share your Customer ID (the 5–12 digit number on your bank account)?",
            "product":       "Which banking product or service does this concern? (e.g. Credit Card, UPI, Savings Account)",
            "issue":         "Could you briefly describe the type of issue? (e.g. Failed transaction, Account blocked)",
        }
        return questions.get(field, "Could you provide more details?")

    # ------------------------------------------------------------------
    # Opportunistic field extraction on every message
    # ------------------------------------------------------------------
    def _opportunistic_extract(self, message: str) -> None:
        """Passively extract name/ID from every message without explicit prompting."""

        # ── Name extraction (only when actively waiting for it) ──────────
        if self.stage == Stage.WAITING_FOR_NAME and not self.fields.get("customer_name"):
            # Try structured patterns first
            name = extract_name(message)

            # If no pattern matched, try accepting a bare name —
            # but be strict: short, alpha-only, not a yes/no/vague word.
            if not name:
                text = message.strip()
                text_lower = text.lower()
                # Reject common non-name short phrases
                _bare_name_rejects = {
                    "yes", "no", "ok", "okay", "sure", "thanks", "thank you",
                    "please", "correct", "right", "wrong", "nope", "yep",
                    "hello", "hi", "hey", "help", "stop", "cancel",
                }
                is_short_alpha = (
                    len(text.split()) <= 4
                    and not any(ch.isdigit() for ch in text)
                    and text.replace(" ", "").isalpha()
                )
                name_words_lower = {w.lower() for w in text.split()}
                is_not_reject = not (name_words_lower & (_bare_name_rejects | _NOT_A_NAME))

                if is_short_alpha and is_not_reject:
                    name = text

            if name:
                self.fields["customer_name"] = name.title()

        # ── Customer ID (any stage, if not already captured) ─────────────
        if not self.fields.get("customer_id"):
            cid = extract_customer_id(message)
            if cid:
                self.fields["customer_id"] = cid

    # ------------------------------------------------------------------
    # LLM fallback – only for genuinely ambiguous messages
    # ------------------------------------------------------------------
    async def _llm_fallback(self, message: str, history: List[Dict[str, str]]) -> str:
        """
        Called only when intent is UNKNOWN after all rule-based checks fail.
        Uses Qwen to generate a contextual reply and extract any recognisable fields.
        Kept as the absolute last resort — most conversations should not reach here.
        """
        missing = [f for f in self.REQUIRED_FIELDS if not self.fields.get(f)]
        known = {k: v for k, v in self.fields.items() if v}
        next_needed = missing[0] if missing else None

        # Minimal prompt — smaller = fewer hallucinations with a 0.5B model.
        # We fix the JSON schema so Qwen doesn't invent field names.
        prompt = (
            "Banking support assistant. Respond in JSON only.\n\n"
            f"Known: {known}\n"
            f"Next needed: {next_needed}\n"
            f"Customer: {message}\n\n"
            "Extract from message if present:\n"
            "- customer_name (string or null)\n"
            "- customer_id (digits 5-12 chars or null)\n\n"
            "Write a short, natural reply (max 30 words) asking only for the next needed field.\n\n"
            "JSON:\n"
            "{\"customer_name\": null, \"customer_id\": null, \"answer\": \"\"}"
        )

        try:
            result = self._ai._generate_json(prompt, max_tokens=55, temperature=0)


            # Only accept fields that match expected types
            extracted_name = result.get("customer_name")
            extracted_id = result.get("customer_id")

            if (
                extracted_name
                and isinstance(extracted_name, str)
                and not self.fields.get("customer_name")
            ):
                # Run through the same validation as the rule-based extractor
                name_words = {w.lower() for w in extracted_name.split()}
                if not (name_words & _NOT_A_NAME) and not any(ch.isdigit() for ch in extracted_name):
                    self.fields["customer_name"] = extracted_name.title()

            if (
                extracted_id
                and isinstance(extracted_id, str)
                and re.fullmatch(r"\d{5,16}", str(extracted_id).strip())
                and not self.fields.get("customer_id")
            ):
                self.fields["customer_id"] = str(extracted_id).strip()

            answer = result.get("answer", "").strip()

            # After field extraction, check if we can advance
            still_missing = [f for f in self.REQUIRED_FIELDS if not self.fields.get(f)]
            if not still_missing:
                self.stage = Stage.WAITING_CONFIRM
                summary = build_confirmation_summary(self.fields)
                return f"{answer}\n\n{summary}".strip() if answer else summary

            return answer if answer else await self._next_question()

        except Exception as e:
            print(f"⚠️ LLM fallback error: {e}")
            return await self._next_question("I'm sorry, I didn't quite catch that.")