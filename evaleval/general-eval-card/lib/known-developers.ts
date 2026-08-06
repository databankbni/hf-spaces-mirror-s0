// Canonical-name helpers for model developers. Lives in a neutral module
// (no `server-only`) so client components can call `isOfficialDeveloper`.

export const KNOWN_DEVELOPER_NAMES: Record<string, string> = {
  openai: "OpenAI",
  google: "Google",
  anthropic: "Anthropic",
  meta: "Meta",
  microsoft: "Microsoft",
  mistralai: "Mistral AI",
  deepseek: "DeepSeek",
  "deepseek-ai": "DeepSeek",
  cohere: "Cohere",
  nvidia: "NVIDIA",
  alibaba: "Alibaba",
  amazon: "Amazon",
  apple: "Apple",
  ibm: "IBM",
  xai: "xAI",
  "x-ai": "xAI",
}

// Canonical display names treated as "official" model-developer organisations.
// MIRRORS the registry's `canonical_orgs.kind == 'lab'` set — the `developer`
// string the backend emits is already the org's canonical display_name, so we
// match on it directly. Keep in sync when curated labs are added to the registry
// (eval-card-registry/seed/orgs.yaml). Durable follow-up: have the producer emit
// an `is_official` flag on the developer list so this hand-maintained set can be
// retired. (KNOWN_DEVELOPER_NAMES values are a subset, included via the spread.)
export const OFFICIAL_DEVELOPER_NAMES: Set<string> = new Set([
  ...Object.values(KNOWN_DEVELOPER_NAMES),
  "01.AI",
  "AI21 Labs",
  "Allen Institute for AI",
  "BigScience",
  "ByteDance",
  "Databricks",
  "EleutherAI",
  "Google DeepMind",
  "Hugging Face",
  "Inception Labs",
  "MiniMax",
  "Moonshot AI",
  "Nous Research",
  "Perplexity AI",
  "Sarvam AI",
  "Stability AI",
  "Stanford CRFM",
  "Stanford University",
  "StepFun",
  "Technology Innovation Institute",
  "Upstage",
  "Writer",
  "Z.AI",
])

export function normalizeDeveloperName(name: string): string {
  const key = name.trim().toLowerCase()
  if (KNOWN_DEVELOPER_NAMES[key]) return KNOWN_DEVELOPER_NAMES[key]
  // Title-case if the name is all-lowercase and not a compound like "01-ai"
  if (name === name.toLowerCase() && /^[a-z]/.test(name)) {
    return name.charAt(0).toUpperCase() + name.slice(1)
  }
  return name
}

export function isOfficialDeveloper(name: string): boolean {
  return OFFICIAL_DEVELOPER_NAMES.has(normalizeDeveloperName(name))
}
