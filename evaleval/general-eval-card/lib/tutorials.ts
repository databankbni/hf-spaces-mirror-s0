import "server-only"

import fs from "node:fs"
import path from "node:path"

const TUTORIALS_DIR = path.join(process.cwd(), "content", "tutorials")
const SCREENSHOTS_DIR = path.join(process.cwd(), "public", "tutorials", "screenshots")

export type TutorialCategory = "guide" | "doc"

export interface TutorialMeta {
  slug: string
  title: string
  category: TutorialCategory
  /** Short "who it's for" (guides) or topic (docs) line. */
  audience: string
  /** One-sentence description of the focus. */
  blurb: string
}

/**
 * Ordered guide catalogue. Quickstart is stakeholder-agnostic and listed
 * first; the rest are the per-stakeholder guides. Copy mirrors the table in
 * the source tutorials README so the hub reads consistently with the guides.
 */
export const TUTORIALS: TutorialMeta[] = [
  {
    slug: "quickstart",
    title: "Quickstart",
    category: "guide",
    audience: "Stakeholder-agnostic · ~6 min",
    blurb:
      "The four signals, the five-level hierarchy, and your first five minutes on the site.",
  },
  {
    slug: "evaluation-researchers",
    title: "Evaluation researchers",
    category: "guide",
    audience: "Researchers auditing or comparing evaluations",
    blurb:
      "Researcher View, a per-section card walkthrough, rigorous signal reading, and comparability caveats.",
  },
  {
    slug: "policymakers",
    title: "Policymakers",
    category: "guide",
    audience: "Governance & policy",
    blurb:
      "What the evidence supports versus what it doesn't, independence checks, and responsible claims.",
  },
  {
    slug: "model-developers",
    title: "Model developers",
    category: "guide",
    audience: "Teams publishing models",
    blurb:
      "How your model is carded, what's documented versus missing, and a checklist to raise your signals.",
  },
  {
    slug: "general-public",
    title: "General public",
    category: "guide",
    audience: "Everyone",
    blurb: "Plain-language: what a benchmark score means and how to read a card.",
  },
  {
    slug: "journalists",
    title: "Journalists",
    category: "guide",
    audience: "Reporters",
    blurb: "The three-minute fact-check, sourcing, citation, and overclaiming traps.",
  },
]

/**
 * Technical documentation — deeper than the stakeholder guides. Rendered from
 * the same markdown pipeline and routed under /help/<slug>.
 */
export const DOCS: TutorialMeta[] = [
  {
    slug: "what-its-built-on",
    title: "What Evaluation Cards is built on",
    category: "doc",
    audience: "Data sources & structure",
    blurb:
      "The infrastructure behind the corpus: Auto-BenchmarkCards, Every Eval Ever, IBM Risk Atlas, and the five-level hierarchy.",
  },
  {
    slug: "how-signals-are-computed",
    title: "How the four signals are computed",
    category: "doc",
    audience: "Signal definitions",
    blurb:
      "The exact computation behind reproducibility, completeness, provenance, and comparability: fields, formulas, and corpus aggregation.",
  },
  {
    slug: "cross-post-to-hugging-face",
    title: "Cross-post EEE results to Hugging Face",
    category: "doc",
    audience: "Contributing evaluation data",
    blurb:
      "Send your Every Eval Ever results to Hugging Face Community Evals: the YAML schema, the converter, and the backlink to the full EEE record.",
  },
  {
    slug: "get-verified",
    title: "Get a verified checkmark",
    category: "doc",
    audience: "Verification",
    blurb:
      "Submit your data through your organisation's Hugging Face account to have your results show up verified — our call for apples-to-apples comparison.",
  },
]

const ALL_ENTRIES = [...TUTORIALS, ...DOCS]

export function getTutorialSlugs(): string[] {
  return ALL_ENTRIES.map((t) => t.slug)
}

export function getTutorialMeta(slug: string): TutorialMeta | undefined {
  return ALL_ENTRIES.find((t) => t.slug === slug)
}

function listExistingScreenshots(): Set<string> {
  try {
    return new Set(fs.readdirSync(SCREENSHOTS_DIR))
  } catch {
    return new Set()
  }
}

/**
 * Reads a tutorial markdown file and returns it ready for rendering:
 * screenshot placeholder blocks are converted into image references. Where a
 * matching PNG exists in public/tutorials/screenshots it becomes a real image;
 * otherwise it becomes a `placeholder:<file>` reference the renderer styles as
 * a "screenshot coming" callout. Returns null if the slug has no file.
 */
export function readTutorial(slug: string): string | null {
  if (!getTutorialMeta(slug)) return null
  const filePath = path.join(TUTORIALS_DIR, `${slug}.md`)
  let raw: string
  try {
    raw = fs.readFileSync(filePath, "utf8")
  } catch {
    return null
  }
  return transformScreenshotBlocks(raw, listExistingScreenshots())
}

/**
 * Rewrites the `> 🖼️ **Screenshot — \`file.png\`** / *What to capture:* …`
 * blockquotes into markdown images (`.png` or `.gif`). Real screenshots resolve
 * to a public path; missing ones become `placeholder:` images so the renderer
 * can style them.
 */
function transformScreenshotBlocks(raw: string, existing: Set<string>): string {
  const lines = raw.split("\n")
  const out: string[] = []

  for (let i = 0; i < lines.length; i++) {
    // Allow leading whitespace: screenshot blocks nested under a list item are
    // indented (e.g. "  > 🖼️ …") and must still be matched.
    if (!/^\s*>\s*🖼️/.test(lines[i])) {
      out.push(lines[i])
      continue
    }

    // Collect the contiguous blockquote that starts with the screenshot marker.
    const block: string[] = []
    while (i < lines.length && /^\s*>/.test(lines[i])) {
      block.push(lines[i])
      i++
    }
    i-- // the outer loop will advance past the last consumed line

    const inner = block.map((l) => l.replace(/^\s*>\s?/, "")).join("\n")
    const file = inner.match(/`([^`]+\.(?:png|gif))`/)?.[1]
    if (!file) continue // malformed marker — drop it rather than render noise

    const rawCaption = inner.match(/\*What to capture:\*\s*([\s\S]+)$/)?.[1] ?? ""
    const caption = rawCaption
      .replace(/[*`<>]/g, "") // strip markdown emphasis / autolink / code markers
      .replace(/\s+/g, " ")
      .replace(/[[\]()]/g, "") // keep markdown image alt syntax intact
      .trim()
    const alt = caption || `Screenshot: ${file}`
    const src = existing.has(file) ? `/tutorials/screenshots/${file}` : `placeholder:${file}`

    out.push("", `![${alt}](${src})`, "")
  }

  return out.join("\n")
}
