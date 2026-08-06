import Link from "next/link"
import type { Metadata } from "next"
import { ArrowRight, ExternalLink, FileText } from "lucide-react"

import { CiteSection, PAPER_URL } from "@/components/cite-section"
import { ContributeSection } from "@/components/contribute-section"
import { Navigation } from "@/components/navigation"
import { ReplayIntroButton } from "@/components/replay-intro-button"
import { DOCS, TUTORIALS } from "@/lib/tutorials"

export const metadata: Metadata = {
  title: "Help",
  description:
    "Learn how to read Evaluation Cards: a quickstart, stakeholder guides, documentation, and how to contribute.",
}

const quickstart = TUTORIALS.find((t) => t.slug === "quickstart")!
const stakeholderGuides = TUTORIALS.filter((t) => t.slug !== "quickstart")

export default function HelpPage() {
  return (
    <div className="min-h-screen bg-background">
      <Navigation />

      <main className="mx-auto w-full max-w-[64rem] px-4 pb-24 pt-12 sm:px-8">
        {/* HEADER --------------------------------------------------------- */}
        <div className="kicker">Help</div>
        <h1
          className="mt-2 mb-7"
          style={{
            fontSize: "clamp(40px, 5.2vw, 56px)",
            fontWeight: 700,
            letterSpacing: "-0.03em",
            lineHeight: 1.05,
            color: "var(--fg)",
          }}
        >
          How to use Evaluation Cards.
        </h1>
        <p className="mb-8 text-[19px] leading-[1.6] text-[color:var(--fg-muted)]">
          New here? Start with the quickstart, then dive into a guide written for your role.
          You can replay the intro tour at any time.
        </p>
        <ReplayIntroButton />

        {/* QUICKSTART ----------------------------------------------------- */}
        <section className="mt-14 mb-14">
          <div className="section-head">
            <h2>Quickstart</h2>
          </div>
          <Link
            href={`/help/${quickstart.slug}`}
            className="group flex flex-col gap-3 border border-[color:var(--border-soft)] bg-[color:var(--fg)] p-7 text-[color:var(--bg)] sm:flex-row sm:items-center sm:justify-between"
          >
            <div>
              <div className="kicker mb-2" style={{ color: "var(--accent)" }}>
                {quickstart.audience}
              </div>
              <h3 className="m-0 mb-1.5 text-xl font-semibold">{quickstart.title}</h3>
              <p
                className="m-0 max-w-[44ch] text-[14px] leading-[1.6]"
                style={{ color: "color-mix(in srgb, var(--bg) 78%, transparent)" }}
              >
                {quickstart.blurb}
              </p>
            </div>
            <span className="inline-flex shrink-0 items-center gap-2 font-mono text-[11px] uppercase tracking-[0.12em]">
              Start reading
              <ArrowRight className="h-4 w-4 transition-transform group-hover:translate-x-0.5" aria-hidden />
            </span>
          </Link>
        </section>

        {/* TUTORIALS BY STAKEHOLDER --------------------------------------- */}
        <section className="mb-14">
          <div className="section-head">
            <h2>Tutorials by stakeholder</h2>
          </div>
          <p className="mb-5 max-w-[700px] text-[15px] leading-[1.7] text-[color:var(--fg-muted)]">
            Each guide reads the same record through a different lens. Pick the one closest to
            how you'll use Evaluation Cards.
          </p>
          <div className="grid gap-5 sm:grid-cols-2">
            {stakeholderGuides.map((guide) => (
              <Link
                key={guide.slug}
                href={`/help/${guide.slug}`}
                className="group flex flex-col border border-[color:var(--border-soft)] bg-[color:var(--bg-warm)] p-[22px] transition-colors hover:border-[color:var(--border-strong)]"
              >
                <div className="kicker mb-2">{guide.audience}</div>
                <h3 className="m-0 mb-2 flex items-center gap-2 text-base font-semibold tracking-[-0.005em] text-[color:var(--fg)]">
                  {guide.title}
                  <ArrowRight
                    className="h-3.5 w-3.5 text-[color:var(--fg-subtle)] transition-transform group-hover:translate-x-0.5"
                    aria-hidden
                  />
                </h3>
                <p className="m-0 text-[13.5px] leading-[1.6] text-[color:var(--fg-muted)]">
                  {guide.blurb}
                </p>
              </Link>
            ))}
          </div>
        </section>

        {/* DOCUMENTATION -------------------------------------------------- */}
        <section className="mb-14">
          <div className="section-head">
            <h2>Documentation</h2>
          </div>
          <p className="mb-5 max-w-[700px] text-[15px] leading-[1.7] text-[color:var(--fg-muted)]">
            Deeper, more technical references for contributing to and working with the data
            behind Evaluation Cards.
          </p>
          <div className="grid gap-5 sm:grid-cols-2">
            {DOCS.map((doc) => (
              <Link
                key={doc.slug}
                href={`/help/${doc.slug}`}
                className="group flex flex-col border border-[color:var(--border-soft)] bg-[color:var(--bg-warm)] p-[22px] transition-colors hover:border-[color:var(--border-strong)]"
              >
                <div className="kicker mb-2 flex items-center gap-1.5">
                  <FileText className="h-3 w-3" aria-hidden />
                  {doc.audience}
                </div>
                <h3 className="m-0 mb-2 flex items-center gap-2 text-base font-semibold tracking-[-0.005em] text-[color:var(--fg)]">
                  {doc.title}
                  <ArrowRight
                    className="h-3.5 w-3.5 text-[color:var(--fg-subtle)] transition-transform group-hover:translate-x-0.5"
                    aria-hidden
                  />
                </h3>
                <p className="m-0 text-[13.5px] leading-[1.6] text-[color:var(--fg-muted)]">
                  {doc.blurb}
                </p>
              </Link>
            ))}

            {/* External: how to contribute evaluation results to EEE */}
            <a
              href="https://evalevalai.com/every_eval_ever/"
              target="_blank"
              rel="noreferrer"
              className="group flex flex-col border border-[color:var(--border-soft)] bg-[color:var(--bg-warm)] p-[22px] transition-colors hover:border-[color:var(--border-strong)]"
            >
              <div className="kicker mb-2 flex items-center gap-1.5">
                <ExternalLink className="h-3 w-3" aria-hidden />
                External · EvalEval
              </div>
              <h3 className="m-0 mb-2 flex items-center gap-2 text-base font-semibold tracking-[-0.005em] text-[color:var(--fg)]">
                Add results to Every Eval Ever
                <ExternalLink
                  className="h-3.5 w-3.5 text-[color:var(--fg-subtle)] transition-transform group-hover:-translate-y-0.5"
                  aria-hidden
                />
              </h3>
              <p className="m-0 text-[13.5px] leading-[1.6] text-[color:var(--fg-muted)]">
                The Every Eval Ever contributor site explains how to add evaluation results to the
                datastore that powers Evaluation Cards.
              </p>
            </a>
          </div>
          <p className="mt-4 text-[13px] leading-[1.6] text-[color:var(--fg-subtle)]">
            Suggest missing documentation on our{" "}
            <a
              href="https://changemap.co/evaleval/evalcards/"
              target="_blank"
              rel="noreferrer"
              className="underline underline-offset-2 hover:text-[color:var(--fg)]"
            >
              public roadmap
            </a>{" "}
            and we'll make sure to add it!
          </p>
        </section>

        {/* HOW TO CONTRIBUTE ---------------------------------------------- */}
        <section id="how-to-contribute" className="mb-8 scroll-mt-24">
          <div className="section-head">
            <h2>How to contribute</h2>
          </div>
          <ContributeSection />
        </section>

        {/* HOW TO CITE ---------------------------------------------------- */}
        <section id="how-to-cite" className="mb-8 scroll-mt-24">
          <div className="section-head">
            <h2>How to cite</h2>
          </div>
          <CiteSection />
        </section>

        {/* CTA ROW -------------------------------------------------------- */}
        <section className="mt-12 flex flex-wrap gap-3 border-t border-[color:var(--border-soft)] pt-10">
          <ReplayIntroButton />
          <Link href="/" className="btn-ec outline">
            Back to home
          </Link>
          <Link href="/about" className="btn-ec outline">
            About Evaluation Cards
          </Link>
          <a href={PAPER_URL} target="_blank" rel="noreferrer" className="btn-ec outline">
            Read the paper
            <ExternalLink className="h-3.5 w-3.5" aria-hidden />
          </a>
        </section>
      </main>
    </div>
  )
}
