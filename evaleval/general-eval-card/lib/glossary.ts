export interface GlossaryEntry {
  short: string
  long?: string
}

const ENTRIES: Record<string, GlossaryEntry> = {
  "0-shot": {
    short: "Model answers without seeing any worked examples first.",
    long: "The benchmark gives the model only the question. Tests how the model performs cold, without in-context demonstrations.",
  },
  "zero-shot": {
    short: "Model answers without seeing any worked examples first.",
  },
  "1-shot": {
    short: "Model sees one worked example before answering.",
  },
  "5-shot": {
    short: "Model sees five worked examples before answering.",
    long: "The five examples are included in the prompt as demonstrations. More shots usually raise scores; comparing a 0-shot result to a 5-shot result is not apples-to-apples.",
  },
  "few-shot": {
    short: "Model sees a small number of worked examples before answering.",
  },
  "n-shot": {
    short: "Number of worked examples shown to the model in the prompt.",
  },
  "pass@1": {
    short: "The model gets one attempt; counted correct only if that single attempt passes.",
    long: "Common in code benchmarks. Stricter than pass@k for k>1, since the model cannot retry.",
  },
  "pass@16": {
    short: "The model gets 16 attempts; counted correct if any one of them passes.",
    long: "Higher numbers tend to be inflated relative to pass@1 because the model has many tries.",
  },
  "pass@k": {
    short: "The model gets k attempts; counted correct if any one of them passes.",
  },
  "majority voting": {
    short: "The model answers many times; the most common answer is taken as the final answer.",
    long: "Also called self-consistency. Tends to raise scores on reasoning tasks but costs more compute per question.",
  },
  "self-consistency": {
    short: "The model answers many times; the most common answer is taken as the final answer.",
  },
  "best-of-n": {
    short: "The model produces N answers; the best one (by a scorer or oracle) is reported.",
    long: "Inflates scores compared to a single attempt. Worth flagging when comparing models.",
  },
  "exact match": {
    short: "The model's answer is counted correct only if it matches the reference string exactly.",
    long: "Strict: small formatting differences fail. Often used for short-answer tasks.",
  },
  "llm-as-judge": {
    short: "Another language model grades the answers.",
    long: "Faster than human grading but the judge model can have biases (length, style, self-preference). Worth knowing the judge identity.",
  },
  "llm as judge": {
    short: "Another language model grades the answers.",
  },
  "human-in-the-loop": {
    short: "Human graders score or check the model's answers.",
  },
  temperature: {
    short: "Controls randomness in the model's output.",
    long: "Lower (e.g. 0) is deterministic; higher (e.g. 1) is more varied. Affects scores: different temperatures make scores hard to compare.",
  },
  "top-p": {
    short: "Limits the model to sampling from the most likely next tokens (nucleus sampling).",
  },
  "top-k": {
    short: "Limits the model to sampling from the K most likely next tokens.",
  },
  perplexity: {
    short: "How surprised the model is by the text. Lower is better.",
  },
  "average normalized score": {
    short: "Each benchmark's score is rescaled to a 0–1 range, then averaged.",
    long: "Lets you combine benchmarks that use different scales. The exact rescaling rule matters: check the methodology.",
  },
  agentic: {
    short: "The model uses tools, takes multiple steps, and acts on an environment to complete a task.",
  },
  "agent budget": {
    short: "The maximum compute, tokens, or steps the agent is allowed before it must stop.",
  },
  "f1 score": {
    short: "A single number combining precision and recall. Higher is better.",
  },
  bleu: {
    short: "A score for how close generated text is to a reference, by overlapping word sequences.",
  },
  rouge: {
    short: "A score for how much a generated summary overlaps with a reference summary.",
  },
  benchmark: {
    short: "A standardized test used to compare models on a specific capability.",
  },
}

const KEY_ALIASES: Record<string, string> = {
  "0 shot": "0-shot",
  "1 shot": "1-shot",
  "5 shot": "5-shot",
  "few shot": "few-shot",
  "n shot": "n-shot",
  "zero shot": "zero-shot",
  "best of n": "best-of-n",
  "best-of-N": "best-of-n",
  "LLM-as-judge": "llm-as-judge",
  "LLM as judge": "llm as judge",
  "self consistency": "self-consistency",
  "Pass@1": "pass@1",
  "Pass@16": "pass@16",
  "Pass@K": "pass@k",
  "F1": "f1 score",
  "F1 score": "f1 score",
  "BLEU": "bleu",
  "ROUGE": "rouge",
  "Agentic": "agentic",
  "Temperature": "temperature",
  "Perplexity": "perplexity",
}

export function lookupTerm(term: string): GlossaryEntry | undefined {
  const trimmed = term.trim()
  if (!trimmed) return undefined
  const direct = ENTRIES[trimmed] ?? ENTRIES[trimmed.toLowerCase()]
  if (direct) return direct
  const aliased = KEY_ALIASES[trimmed] ?? KEY_ALIASES[trimmed.toLowerCase()]
  if (aliased) return ENTRIES[aliased]
  return undefined
}

export function hasTerm(term: string): boolean {
  return lookupTerm(term) !== undefined
}
