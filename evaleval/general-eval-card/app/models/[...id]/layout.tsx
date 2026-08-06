import type { Metadata } from "next"

import { getModelSummaryById } from "@/lib/data-backend"
import { routeIdFromSegments, routeIdToPath } from "@/lib/utils"

/**
 * Server-side metadata for the model detail page. The page itself is a
 * client component so it can't export `generateMetadata` directly; this
 * sibling layout owns the OpenGraph payload so social/chat unfurls
 * carry the model's name + a per-model thumbnail (rendered by
 * /api/og/models/<id>) instead of the site-wide card.
 */
export async function generateMetadata(props: {
  params: Promise<{ id: string | string[] }>
}): Promise<Metadata> {
  const { id } = await props.params
  const routeId = routeIdFromSegments(id)
  let modelName = "Model"
  let developer: string | null = null

  try {
    const summary = await getModelSummaryById(routeId)
    if (summary) {
      modelName = summary.model_info?.name ?? modelName
      developer = summary.model_info?.developer ?? null
    }
  } catch {
    // Fall through to generic copy.
  }

  const idSlug = routeIdToPath(routeId)
  const title = developer ? `${modelName} — ${developer}` : modelName
  const description = developer
    ? `${modelName} (${developer}) — every reported model–benchmark result, organized under Evaluation Cards' five-level hierarchy and four interpretive signals.`
    : `${modelName} — every reported model–benchmark result on Evaluation Cards.`
  const imageUrl = `/api/og/models/${idSlug}`

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
          alt: `${modelName} — Evaluation Cards`,
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

export default function ModelDetailLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return children
}
