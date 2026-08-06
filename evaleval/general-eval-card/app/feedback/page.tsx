import Link from "next/link"
import { ArrowRight } from "lucide-react"

import { Navigation } from "@/components/navigation"

const FEEDBACK_FORM_URL = "https://airtable.com/app1zVQBQ4ao1u2eT/pagEMueYiXMJy2PT1/form"
const ROADMAP_URL = "https://changemap.co/evaleval/evalcards/"

export default function FeedbackPage() {
  return (
    <div className="min-h-screen bg-background">
      <Navigation />

      <main className="mx-auto w-full max-w-[64rem] px-4 pb-24 pt-12 sm:px-8">
        {/* HEADER --------------------------------------------------------- */}
        <div className="kicker">Feedback</div>
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
          Help shape Evaluation Cards.
        </h1>
        <p className="mb-10 text-[19px] leading-[1.6] text-[color:var(--fg-muted)]">
          Evaluation Cards is a living research artifact, and your input directly steers where
          it goes next. There are two ways to get involved.
        </p>

        {/* TWO CHANNELS --------------------------------------------------- */}
        <div className="grid gap-5 sm:grid-cols-2">
          {/* ROADMAP */}
          <section className="border border-[color:var(--border-soft)] bg-[color:var(--bg-warm)] p-[26px]">
            <div className="kicker mb-2.5">Public roadmap</div>
            <h2 className="m-0 mb-3 text-xl font-semibold tracking-[-0.01em] text-[color:var(--fg)]">
              Suggest &amp; upvote features
            </h2>
            <p className="m-0 mb-6 text-[14.5px] leading-[1.7] text-[color:var(--fg-muted)]">
              We keep a public roadmap where you can propose new features, upvote existing
              suggestions, and see what we&apos;re planning. If there&apos;s something you want
              to see prioritized, this is the place to make the case.
            </p>
            <a
              href={ROADMAP_URL}
              target="_blank"
              rel="noreferrer"
              className="btn-ec"
            >
              Open the roadmap
              <ArrowRight className="h-3.5 w-3.5" aria-hidden />
            </a>
          </section>

          {/* GOOGLE FORM */}
          <section className="border border-[color:var(--border-soft)] bg-[color:var(--bg-warm)] p-[26px]">
            <div className="kicker mb-2.5">Feedback form</div>
            <h2 className="m-0 mb-3 text-xl font-semibold tracking-[-0.01em] text-[color:var(--fg)]">
              Share feedback directly
            </h2>
            <p className="m-0 mb-6 text-[14.5px] leading-[1.7] text-[color:var(--fg-muted)]">
              For feature requests, edits, bug reports, or any other comments, you can reach us
              through our feedback form. It only takes a moment, and every submission is read.
            </p>
            <a
              href={FEEDBACK_FORM_URL}
              target="_blank"
              rel="noreferrer"
              className="btn-ec"
            >
              Open the feedback form
              <ArrowRight className="h-3.5 w-3.5" aria-hidden />
            </a>
          </section>
        </div>

        {/* CTA ROW -------------------------------------------------------- */}
        <section className="mt-12 flex flex-wrap gap-3 border-t border-[color:var(--border-soft)] pt-10">
          <Link href="/" className="btn-ec outline">
            Back to home
          </Link>
          <Link href="/about" className="btn-ec outline">
            About Evaluation Cards
          </Link>
        </section>
      </main>
    </div>
  )
}
