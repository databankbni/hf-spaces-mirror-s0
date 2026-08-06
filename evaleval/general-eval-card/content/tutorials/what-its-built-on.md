# What Evaluation Cards is built on

*Evaluation Cards doesn't run evaluations; it composes existing evaluation infrastructure into a single reading surface. Here's what powers it.*

---

## Auto-BenchmarkCards

A schema for benchmark-level metadata: what a benchmark measures, its splits, intended use, validity scope, and known limitations. Each benchmark family has an Auto-BenchmarkCard at the family root and a Policy Note compressed for plain-language reading.

## Every Eval Ever

A run-level corpus of public evaluation results: `(model, benchmark, metric-path, value, source)` tuples extracted from papers, model cards, and leaderboards. It provides the raw rows that Evaluation Cards canonicalizes and joins. [Every Eval Ever](https://evalevalai.com/every_eval_ever/) is a sister [EvalEval](https://evalevalai.com/) project.

## IBM Risk Atlas alignment

Risk-domain annotations on benchmarks (capability, robustness, safety, agentic risk, fairness) so policy readers can locate which deployment-relevant property a number speaks to.

## The five-level hierarchy

```
Family  →  Composite  →  Single benchmark  →  Split  →  Metric
```

Every score resolves to an explicit path, so aggregate claims drill down to the evidence supporting them.
