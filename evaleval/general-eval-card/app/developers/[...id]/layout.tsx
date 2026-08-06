import type { Metadata } from "next"

import { getDeveloperSummaryById } from "@/lib/data-backend"
import { routeIdFromSegments, routeIdToPath } from "@/lib/utils"

/**
 * Server-side metadata for the developer detail page. The page itself is a
 * client component, so this sibling layout owns the OpenGraph payload so
 * social/chat unfurls carry the developer's name + a per-developer
 * thumbnail (rendered by /api/og/developers/<id>) instead of the
 * site-wide card. Mirrors app/models/[...id]/layout.tsx.
 */
export async function generateMetadata(props: {
  params: Promise<{ id: string | string[] }>
}): Promise<Metadata> {
  const { id } = await props.params
  const routeId = routeIdFromSegments(id)
  let developerName = "Developer"
  let modelCount: number | null = null

  try {
    const summary = await getDeveloperSummaryById(routeId)
    if (summary) {
      developerName = summary.developer ?? developerName
      modelCount = summary.model_count ?? summary.models?.length ?? null
    }
  } catch {
    // Fall through to generic copy.
  }

  const idSlug = routeIdToPath(routeId)
  const title = developerName
  const description =
    modelCount != null
      ? `${developerName} — evaluation coverage across ${modelCount.toLocaleString("en-US")} ${modelCount === 1 ? "model" : "models"}, organized under Evaluation Cards' five-level hierarchy and four interpretive signals.`
      : `${developerName} — model evaluation coverage on Evaluation Cards.`
  const imageUrl = `/api/og/developers/${idSlug}`

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
          alt: `${developerName} — Evaluation Cards`,
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

export default function DeveloperDetailLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return children
}
