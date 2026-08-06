import { CiteBlock } from "@/components/cite-block"

export const PAPER_URL = "https://arxiv.org/abs/2606.09809"
export const PAPER_BIBTEX = `@article{ghosh2026evaluationcards,
  title        = {Evaluation Cards: An Interpretive Layer for AI Evaluation Reporting},
  author       = {Ghosh, Avijit and Reuel, Anka and Chim, Jenny and Kennedy, Wm. Matthew and Yadav, Srishti and Mickel, Jennifer and Long, Yanan and Tran, Andrew and Kornilova, Anastassia and Stachura, Damian and Klyman, Kevin and Friedrich, Felix and Sania, Jeba and Lamparth, Max and Batzner, Jan and Mishra, Anoop and Habba, Eliya and Hao, Yixiong and Heath, Nathan and Rismani, Shalaleh and Gohar, Usman and Loehr, Andrea and Manheim, David and Dhar, Ruchira and Nelaturu, Sree Harsha and Sinha, Aarush and Choshen, Leshem and Sharma, Drishti and Khire, Ishan and Saha, Amit and Sahoo, Subramanyam and Hardy, Michael and Riegler, Michael Alexander and Manghnani, Kabir and Lin, Michelle and Jiang, Yanan and Huang, Yilin and Yehudai, Asaf and Ji, Jessica and Hofmann, Aris and Akhtar, Mubashara and Moniz, Nuno and Jernite, Yacine and Biderman, Stella and Talat, Zeerak and Koyejo, Sanmi and Kochenderfer, Mykel and Solaiman, Irene},
  journal      = {arXiv preprint arXiv:2606.09809},
  year         = {2026},
  url          = {https://arxiv.org/abs/2606.09809}
}`

export const EEE_BIBTEX = `@misc{evaleval2026everyevalever,
  title   = {Every Eval Ever: Toward a Common Language for AI Eval Reporting},
  author  = {Jan Batzner and Leshem Choshen and Avijit Ghosh and Sree Harsha Nelaturu and Anastassia Kornilova and Damian Stachura and Yifan Mai and Asaf Yehudai and Anka Reuel and Irene Solaiman and Stella Biderman},
  year    = {2026},
  month   = {February},
  url     = {https://evalevalai.com/infrastructure/2026/02/17/everyevalever-launch/},
  note    = {Blog Post, EvalEval Coalition}
}`

/**
 * The "How to cite" body — share note, reference, copy-pasteable BibTeX. Shared
 * by the About and Help pages so the citation stays in one place.
 */
export function CiteSection() {
  return (
    <>
      <p className="mb-5 max-w-[700px] text-[15px] leading-[1.7] text-[color:var(--fg-muted)]">
        If you find this effort useful, please consider citing our paper and sharing our work on
        socials.
      </p>
      <div className="mb-5 border border-[color:var(--border-soft)] p-[22px]">
        <div className="kicker mb-2.5">Reference</div>
        <p className="m-0 text-[13.5px] leading-[1.7] text-[color:var(--fg)]">
          Ghosh, A., Reuel, A., Chim, J., Kennedy, W. M., et al. (2026). Evaluation Cards: An
          Interpretive Layer for AI Evaluation Reporting.{" "}
          <a
            href={PAPER_URL}
            target="_blank"
            rel="noreferrer"
            className="underline underline-offset-2"
          >
            arXiv:2606.09809
          </a>
          .
        </p>
      </div>
      <CiteBlock bibtex={PAPER_BIBTEX} label="BibTeX · Evaluation Cards" />

      <p className="mt-6 mb-3 max-w-[700px] text-[14px] leading-[1.7] text-[color:var(--fg-muted)]">
        <a
          href="https://evalevalai.com/every_eval_ever/"
          target="_blank"
          rel="noreferrer"
          className="text-[color:var(--fg)] underline underline-offset-2"
        >
          Every Eval Ever
        </a>{" "}
        (EEE) is a sister{" "}
        <a
          href="https://evalevalai.com/"
          target="_blank"
          rel="noreferrer"
          className="text-[color:var(--fg)] underline underline-offset-2"
        >
          EvalEval
        </a>{" "}
        project and one of the data sources that powers Evaluation Cards — please show it some
        love and cite it too. 💜
      </p>
      <CiteBlock bibtex={EEE_BIBTEX} label="BibTeX · Every Eval Ever" />
    </>
  )
}
