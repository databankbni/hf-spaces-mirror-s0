"""
Evaluation module for RAG accuracy measurement.
Tests retrieval precision, recall, and answer quality.
"""

import time
from typing import List, Dict, Tuple
from dataclasses import dataclass

from retriever import HybridRetriever, RetrievedChunk
from query import IFODAQueryEngine


@dataclass
class EvalResult:
    query: str
    expected_answer_contains: List[str]  # keywords that should appear
    expected_products: List[str]         # product names that should appear
    actual_products: List[str]
    recall_hit: bool                     # at least one expected product found
    precision_at_5: float
    mrr: float
    latency_ms: float


class RAGEvaluator:
    """Evaluates retrieval accuracy for IFODA RAG."""

    def __init__(self):
        self.retriever = HybridRetriever()

        # Test queries with expected results (ground truth from IFODA catalog)
        self.test_cases = [
            {
                "query": "Какой инсектицид использовать против тли на хлопчатнике?",
                "expected_products": ["Акарагольд", "Акара Голд", "Энтоспилан", "Имидаклоприд", "Эквадор"],
                "keywords": ["тли", "трипсы", "хлопчатник", "л/га", "0.4"]
            },
            {
                "query": "Дозировка Далатэ для пшеницы против клопов",
                "expected_products": ["Далатэ", "DALATE", "Лямбда-цигалотрин"],
                "keywords": ["пшеница", "wheat", "черепашка", "0.07", "л/га"]
            },
            {
                "query": "What fungicide against powdery mildew on wheat?",
                "expected_products": ["ТОПКРОП", "Флутрифул", "FLUTRIFUL", "Топкроп"],
                "keywords": ["powdery mildew", "wheat", "rust", "fungicide", "propiconazole", "tebuconazole"]
            },
            {
                "query": "Норма расхода удобрения SMARTFERT NPK для хлопчатника",
                "expected_products": ["SMARTFERT", "Смартферт"],
                "keywords": ["хлопчатник", "cotton", "300", "400", "кг/га", "NPK"]
            },
            {
                "query": "Протравитель семян пшеницы против твердой головни",
                "expected_products": ["Ифотебу", "IFOTEBU", "Энтовакс", "ENTOVAKS"],
                "keywords": ["протрав", "семян", "wheat", "smut", "tebuconazole", "кг/т"]
            },
            {
                "query": "Дефолиант для хлопчатника когда открыто 60% коробочек",
                "expected_products": ["Сиклодефол", "SIKLODEFOL", "Энто-Дефол", "ENTO-DEFOL"],
                "keywords": ["дефолиация", "хлопчатник", "коробочек", "капсул", "60%"]
            },
            {
                "query": "Удобрение для томатов в закрытом грунте",
                "expected_products": ["HOSIL", "Хосил", "SMARTFERT", "Вуксал", "WUKSAL"],
                "keywords": ["томат", "закрыт", "greenhouse", "удобрен", "fertigation"]
            },
            {
                "query": "Препарат против паутинного клеща на яблоне",
                "expected_products": ["Флур", "FLUR", "Энтосоран", "ENTOSORAN", "Демофос"],
                "keywords": ["паутинный клещ", "яблон", "apple", "mite", "клещ"]
            },
        ]

    def evaluate_retrieval(self, query: str, expected_products: List[str],
                          top_k: int = 5) -> Tuple[int, float, float, float]:
        """
        Evaluate retrieval quality.
        Returns: (hits, precision@k, MRR, latency_ms)
        """
        start = time.time()
        results = self.retriever.retrieve(query, top_k=top_k)
        latency = (time.time() - start) * 1000

        expected_lower = [e.lower() for e in expected_products]
        found_products = []

        # Check which expected products are found
        hits = 0
        for r in results:
            # Search in text and metadata
            search_in = (r.text + " " +
                        r.metadata.get("product_name", "") + " " +
                        r.metadata.get("product_name_ru", "")).lower()

            for exp in expected_lower:
                if exp.lower() in search_in:
                    if exp not in found_products:
                        found_products.append(exp)
                        hits += 1

        recall_hit = 1 if hits > 0 else 0
        precision_at_k = hits / top_k if top_k > 0 else 0

        # MRR (Mean Reciprocal Rank)
        mrr = 0.0
        for rank, r in enumerate(results):
            search_in = (r.text + " " + r.metadata.get("product_name", "")).lower()
            for exp in expected_lower:
                if exp.lower() in search_in:
                    mrr = 1.0 / (rank + 1)
                    break
            if mrr > 0:
                break

        return recall_hit, precision_at_k, mrr, latency

    def run_full_eval(self, verbose: bool = True) -> Dict:
        """Run full evaluation suite."""
        print("=" * 60)
        print("IFODA RAG SYSTEM — ACCURACY EVALUATION")
        print("=" * 60)

        results = []
        total_latency = 0

        for tc in self.test_cases:
            recall_hit, p_at_5, mrr, latency = self.evaluate_retrieval(
                tc["query"], tc["expected_products"]
            )

            results.append({
                "query": tc["query"],
                "recall_hit": bool(recall_hit),
                "precision@5": round(p_at_5, 3),
                "mrr": round(mrr, 3),
                "latency_ms": round(latency, 1),
            })

            total_latency += latency

            if verbose:
                status = "✅" if recall_hit else "❌"
                print(f"\n{status} Query: {tc['query'][:80]}...")
                print(f"   Recall@Hit: {bool(recall_hit)}, P@5: {p_at_5:.3f}, MRR: {mrr:.3f}, Latency: {latency:.0f}ms")

        # Summary metrics
        avg_recall = sum(r["recall_hit"] for r in results) / len(results)
        avg_p5 = sum(r["precision@5"] for r in results) / len(results)
        avg_mrr = sum(r["mrr"] for r in results) / len(results)
        avg_latency = total_latency / len(results)

        # Custom accuracy score (weighted)
        accuracy_score = (
            0.40 * avg_recall +    # 40% weight on recall (found expected product?)
            0.30 * avg_p5 +        # 30% weight on precision
            0.20 * avg_mrr +       # 20% weight on MRR
            0.10 * min(1.0, 200.0 / max(avg_latency, 1))  # 10% weight on speed
        )

        print(f"\n{'='*60}")
        print("SUMMARY METRICS:")
        print(f"  Recall@Hit:   {avg_recall:.1%}")
        print(f"  Precision@5:  {avg_p5:.3f}")
        print(f"  MRR:          {avg_mrr:.3f}")
        print(f"  Avg Latency:  {avg_latency:.0f}ms")
        print(f"  ACCURACY:     {accuracy_score:.1%}")
        print(f"{'='*60}")

        return {
            "per_query": results,
            "summary": {
                "recall_hit": round(avg_recall, 3),
                "precision_at_5": round(avg_p5, 3),
                "mrr": round(avg_mrr, 3),
                "avg_latency_ms": round(avg_latency, 1),
                "accuracy_score": round(accuracy_score, 3),
            }
        }


if __name__ == "__main__":
    evaluator = RAGEvaluator()
    results = evaluator.run_full_eval()
