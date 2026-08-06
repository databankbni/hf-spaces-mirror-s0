import Link from "next/link"
import { ArrowRight, ExternalLink } from "lucide-react"

import { CiteSection, PAPER_URL } from "@/components/cite-section"
import { ContributeSection } from "@/components/contribute-section"
import { Navigation } from "@/components/navigation"

export default function AboutPage() {
  return (
    <div className="min-h-screen bg-background">
      <Navigation />

      <main className="mx-auto w-full max-w-[64rem] px-4 pb-24 pt-12 sm:px-8">
        {/* HEADER --------------------------------------------------------- */}
        <div className="kicker">About</div>
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
          A reporting layer for AI evaluations.
        </h1>
        <p className="mb-6 text-[19px] leading-[1.6] text-[color:var(--fg-muted)]">
          <strong className="text-[color:var(--fg)] font-semibold">Evaluation Cards</strong> is a
          structured collection of how AI models are evaluated — and, just as importantly, of
          what is left undocumented. It composes existing evaluation infrastructure into a
          single audience-agnostic reading surface. It is a research artifact of the{" "}
          <a
            href="https://evalevalai.com/"
            target="_blank"
            rel="noreferrer"
            className="font-semibold text-[color:var(--fg)] underline underline-offset-2"
          >
            EvalEval Coalition
          </a>
          , a cross-sector and interdisciplinary coalition community of 500+ individuals working
          on broader-impact evaluation of AI systems.
        </p>
        <p className="mb-5 text-base leading-[1.75] text-[color:var(--fg)]">
          Benchmark scores are routinely reported without the context required to interpret
          them: prompts, decoding parameters, evaluator identity, reproduction artifacts,
          scope of validity. Evaluation Cards treats every published evaluation as a{" "}
          <em>claim</em>, and every absent field as a claim <em>not made</em>. Neither is an
          error — the distinction is what makes the public record useful.
        </p>

        {/* PRINCIPLES ----------------------------------------------------- */}
        <section className="mb-14">
          <div className="section-head">
            <h2>Principles</h2>
          </div>
          <ol className="list-none p-0 m-0">
            {[
              [
                "We do not impute.",
                "If a developer did not publish a score, the cell is empty. We do not estimate, infer, or cross-fill.",
              ],
              [
                "Every number cites its source.",
                "Each reported score resolves to a specific document — paper, model card, blog post — with a line reference.",
              ],
              [
                "Evaluator identity matters.",
                "First-party and third-party results are visually distinct and never silently merged. When both have reported on the same (model, benchmark) pair, both rows are kept side by side.",
              ],
              [
                "Gaps are data.",
                "Undisclosed fields appear alongside disclosed ones. Silence about a safety benchmark is itself information.",
              ],
              [
                "Aggregates resolve to evidence.",
                "Every corpus-level claim drills down to the (model, benchmark, metric-path) records that support it. No black-box scores.",
              ],
              [
                "Corrections are welcome.",
                "Each record links a correction path. Evaluation Cards is a living artifact; coverage improves as developers publish.",
              ],
            ].map(([h, p], i) => (
              <li
                key={i}
                className="grid grid-cols-[60px_1fr] gap-6 border-b border-[color:var(--border-soft)] py-6"
              >
                <span
                  className="font-mono"
                  style={{
                    fontSize: 12,
                    color: "var(--accent)",
                    letterSpacing: "0.1em",
                  }}
                >
                  0{i + 1}
                </span>
                <div>
                  <h3 className="m-0 text-xl font-semibold text-[color:var(--fg)]">{h}</h3>
                  <p className="mt-2 m-0 text-[15px] leading-[1.65] text-[color:var(--fg-muted)]">
                    {p}
                  </p>
                </div>
              </li>
            ))}
          </ol>
        </section>

        {/* HOW TO CONTRIBUTE --------------------------------------------- */}
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
          <Link href="/" className="btn-ec">
            Back to home
            <ArrowRight className="h-3.5 w-3.5" aria-hidden />
          </Link>
          <Link href="/models" className="btn-ec outline">
            Browse models
          </Link>
          <Link href="/evals" className="btn-ec outline">
            Browse evaluations
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
