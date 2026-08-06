import Link from "next/link"
import type { Metadata } from "next"
import { notFound } from "next/navigation"
import { ArrowLeft } from "lucide-react"
import "katex/dist/katex.min.css"

import { Navigation } from "@/components/navigation"
import { ReplayIntroButton } from "@/components/replay-intro-button"
import { TutorialMarkdown } from "@/components/tutorial-markdown"
import { getTutorialMeta, getTutorialSlugs, readTutorial } from "@/lib/tutorials"

export function generateStaticParams() {
  return getTutorialSlugs().map((slug) => ({ slug }))
}

export async function generateMetadata({
  params,
}: {
  params: Promise<{ slug: string }>
}): Promise<Metadata> {
  const { slug } = await params
  const meta = getTutorialMeta(slug)
  if (!meta) return {}
  return { title: `${meta.title} · Help`, description: meta.blurb }
}

export default async function TutorialPage({
  params,
}: {
  params: Promise<{ slug: string }>
}) {
  const { slug } = await params
  const meta = getTutorialMeta(slug)
  const source = readTutorial(slug)
  if (!meta || source === null) {
    notFound()
  }

  return (
    <div className="min-h-screen bg-background">
      <Navigation />

      <main className="mx-auto w-full max-w-[52rem] px-4 pb-24 pt-12 sm:px-8">
        <Link
          href="/help"
          className="inline-flex items-center gap-1.5 font-mono text-[11px] uppercase tracking-[0.12em] text-[color:var(--fg-muted)] transition-colors hover:text-[color:var(--fg)]"
        >
          <ArrowLeft className="h-3.5 w-3.5" aria-hidden />
          All guides
        </Link>

        <div className="kicker mt-6">{meta.audience}</div>

        <article className="mt-3">
          <TutorialMarkdown source={source} />
        </article>

        <section className="mt-14 flex flex-wrap gap-3 border-t border-[color:var(--border-soft)] pt-10">
          <Link href="/help" className="btn-ec outline">
            <ArrowLeft className="h-3.5 w-3.5" aria-hidden />
            Back to Help
          </Link>
          <ReplayIntroButton />
        </section>
      </main>
    </div>
  )
}
