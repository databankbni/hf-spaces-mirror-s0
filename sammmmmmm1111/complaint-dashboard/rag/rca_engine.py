import os
import json
import torch
import re
from rag.retriever import ComplaintRetriever
from dotenv import load_dotenv
load_dotenv()

ROOT_CAUSES = [
    "Transaction Timeout",
    "Amount Deducted Not Reversed",
    "Server Downtime",
    "Payment Gateway Failure",
    "Authentication Failure",
    "Duplicate Transaction",
    "Backend Processing Delay",
    "Settlement Delay",
    "Fraudulent Transaction",
    "Unknown"
]

class RCAEngine:
    def __init__(self, ai_engine):
        self.retriever = ComplaintRetriever()
        self.ai_engine = ai_engine

    def build_prompt(
        self,
        complaint,
        retrieved_cases
    ):
        context = ""

        for i, case in enumerate(
            retrieved_cases,
            1
        ):
            context += f"""
Case {i}
Product: {case['product']}
Issue: {case['issue']}
Sub Issue: {case['sub_issue']}
Similarity: {case['similarity']:.2f}

Complaint:
{case['text']}

"""

        root_cause_options = "\n".join(
            f"- {cause}"
            for cause in ROOT_CAUSES
        )
        prompt = f"""
        You are a banking root cause analyst.

        Current Complaint:
        {complaint}

        Historical Complaints:
        {context}

        Determine:

        1. Most probable root cause.
        2. Confidence score between 0 and 1.
        3. Evidence.
        4. Suggested resolution.
        5. Escalation recommendation.

        LENGTH CONSTRAINTS (to prevent mid-sentence truncation):
        - root_cause: <= 10 words.
        - evidence: return exactly 3 items; each item <= 22 words and must be a complete sentence.
        - resolution: <= 55 words total and must be a complete paragraph of complete sentences.
        - escalation: must be a boolean, no extra text.

        STRICT OUTPUT RULE:
        - Output ONLY the JSON object and then stop. Do not print any extra tokens.



        Choose the root cause ONLY from:

        {root_cause_options}

        Evidence must ONLY reference the historical complaints above.
        Do not invent sources.

        IMPORTANT WRITING RULES (to avoid mid-sentence truncation):
        - The model must output fully complete sentences only.
        - Do NOT output partial sentences. If unsure, finish the sentence naturally.
        - In "evidence" and "resolution":
          * each evidence item must be a complete sentence ending with punctuation.
          * "resolution" must be a complete paragraph of complete sentences ending with punctuation.
        - Never end any sentence with an em-dash, hyphen, colon, or unfinished clause.
        - Avoid starting a line with a bullet or dash in "evidence" unless the dash is followed by a complete sentence on the same line.


        Return ONLY valid JSON.
        Do not include markdown.
        Do not include explanations.
        Do not include text after the final JSON brace.

        Format:

        {{
            "root_cause": "",
            "confidence": 0.0,
            "evidence": [],
            "resolution": "",
            "escalation": false
        }}
        """


        return prompt

    def analyze(
        self,
        complaint_text,
        product=None,
        issue=None
    ):
        cases = self.retriever.search(
            complaint_text,
            top_k=5,
            product=product,
            issue=issue
        )

        prompt = self.build_prompt(
            complaint_text,
            cases
        )

        messages = [
            {
                "role": "user",
                "content": prompt
            }
        ]

        formatted = (
            self.ai_engine.qwen_tokenizer
            .apply_chat_template(
                messages,
                tokenize=False,
                add_generation_prompt=True,
                enable_thinking=False
            )
        )

        inputs = (
            self.ai_engine.qwen_tokenizer(
                [formatted],
                return_tensors="pt"
            )
            .to(
                self.ai_engine.qwen_model.device
            )
        )

        with torch.inference_mode():
            outputs = (
                self.ai_engine.qwen_model.generate(
                    **inputs,
                    max_new_tokens=300,
                    do_sample=False,
                    temperature=0.0,
                    use_cache=True,
                    eos_token_id=
                        self.ai_engine.qwen_tokenizer.eos_token_id,
                    pad_token_id=
                        self.ai_engine.qwen_tokenizer.eos_token_id,
                )
            )

        generated_ids = (
            outputs[0][
                len(inputs.input_ids[0]):
            ]
        )

        raw = (
            self.ai_engine.qwen_tokenizer
            .decode(
                generated_ids,
                skip_special_tokens=True
            )
            .strip()
        )

        print(raw)

        try:
            raw = (
                raw
                .replace("```json", "")
                .replace("```", "")
                .strip()
            )

            match = re.search(
                r'\{.*\}',
                raw,
                re.DOTALL
            )

            if not match:
                raise json.JSONDecodeError(
                    "No JSON found",
                    raw,
                    0
                )

            json_text = match.group(0)

            result = json.loads(
                json_text
            )

        except json.JSONDecodeError:
            result = {
                "root_cause": "Unknown",
                "confidence": 0.0,
                "evidence": [],
                "resolution": raw,
                "escalation": False
            }

        if cases:
            top_case = cases[0]

            if top_case["similarity"] >= 0.55:
                result["root_cause"] = (
                    top_case["sub_issue"]
                    or top_case["issue"]
                    or "Unknown"
                )

                result["confidence"] = round(
                    top_case["similarity"],
                    2
                )

        result["similar_cases"] = [
            c["complaint_id"]
            for c in cases
        ]

        result["evidence"] = [
            c["complaint_id"]
            for c in cases[:3]
        ]

        return result