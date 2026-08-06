import type { Metadata } from "next"

import { getEvaluatorSummaryBySlug } from "@/lib/data-backend"
import { routeIdFromSegments, routeIdToPath } from "@/lib/utils"

/**
 * Server-side metadata for the evaluator (reporting-org) detail page. The
 * page itself is a client component, so this sibling layout owns the
 * OpenGraph payload so social/chat unfurls carry the evaluator's name + a
 * per-evaluator thumbnail (rendered by /api/og/evaluators/<slug>) instead
 * of the site-wide card. Mirrors app/models/[...id]/layout.tsx.
 */
export async function generateMetadata(props: {
  params: Promise<{ id: string | string[] }>
}): Promise<Metadata> {
  const { id } = await props.params
  const slug = routeIdFromSegments(id)
  let evaluatorName = "Evaluator"
  let evalCount: number | null = null
  let verifiedCount: number | null = null

  try {
    const summary = await getEvaluatorSummaryBySlug(slug)
    if (summary) {
      evaluatorName = summary.name ?? evaluatorName
      evalCount = summary.evalCount ?? null
      verifiedCount = summary.verifiedCount ?? null
    }
  } catch {
    // Fall through to generic copy.
  }

  const idSlug = routeIdToPath(slug)
  const title = evaluatorName
  const description =
    evalCount != null
      ? `${evaluatorName} — ${evalCount.toLocaleString("en-US")} ${evalCount === 1 ? "evaluation" : "evaluations"} reported${
          verifiedCount != null && verifiedCount > 0
            ? `, ${verifiedCount.toLocaleString("en-US")} verified`
            : ""
        }, with reproducibility, completeness, provenance, and comparability signals on Evaluation Cards.`
      : `${evaluatorName} — reported evaluations on Evaluation Cards.`
  const imageUrl = `/api/og/evaluators/${idSlug}`

  return {
    title,
    description,
    openGraph: {
      title,
      description,
      type: "article",
      images: [
        {
          url: imageUrl,
          width: 1200,
          height: 630,
          alt: `${evaluatorName} — Evaluation Cards`,
        },
      ],
    },
    twitter: {
      card: "summary_large_image",
      title,
      description,
      images: [imageUrl],
    },
  }
}

export default function EvaluatorDetailLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return children
}
