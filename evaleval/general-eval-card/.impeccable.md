## Design Context

### Users
The interface serves two primary audiences: evaluation researchers and policymakers. Researchers use it to compare evaluations, understand methodological differences, and inspect evidence quality. Policymakers use it to understand what has been evaluated, how much supporting evidence exists, and which models have broader or thinner reporting coverage.

### Brand Personality
The product should feel editorial, premium, and vivid. It should communicate credibility and seriousness without becoming visually sterile. The emotional goal is confidence and clarity with a sense of polish, not hype.

### Aesthetic Direction
The interface should feel like a refined research publication with selective bursts of color. It should work in both light and dark mode. The visual direction should avoid oversized hero metrics, noisy card interiors, and overcrowded dashboards. Information density should be controlled carefully because the homepage presents many cards at once.

### Design Principles
1. Prefer compact, layered summaries over large isolated stat blocks.
2. Use color intentionally to create scanability and editorial hierarchy, not decoration.
3. Support both research and policy reading modes by shifting emphasis rather than duplicating content.
4. Keep card typography restrained so multiple cards remain legible in a grid.
5. Make evidence, breadth, and context feel trustworthy and easy to compare at a glance.

### Audience Surface Rules

#### Eval Researcher Mode
- Lead with methodology, reproducibility, and comparability.
- Surface inference settings, eval library/version, benchmark setup, generation config, and source relationships prominently.
- Preserve technical terminology when it helps precise comparison.
- Prefer tables, filters, exports, score distributions, config diffs, and sample-level inspection.
- Highlight missing reproducibility fields such as null generation configs as methodological warnings.
- Make apples-to-apples comparison affordances primary rather than secondary.

#### AI Policy Mode
- Lead with plain-language interpretation, governance relevance, and source accountability.
- Translate schema fields into reader-facing meaning rather than exposing raw jargon by default.
- Surface evaluator independence, reporting organization, test date, benchmark purpose, caveats, and comparability status prominently.
- Prefer narrative summaries, callouts, badges, and guided explanations over dense technical controls.
- Make limitations and confidence caveats highly visible to reduce score over-interpretation.
- Keep technical configuration available, but subordinate it behind clearer public-interest framing.

#### Field Translation Guidance
- `evaluator_relationship: third_party` should map to an independent verification signal in policy mode.
- Missing `generation_config` should be treated as a reproducibility gap, not merely an absent field.
- `retrieved_timestamp` should be surfaced as the date tested because timing matters for governance review.
- Large size/parameter differences should be surfaced as comparability caveats in policy mode.
- Instance-level or sample-level data should be a primary exploration tool in researcher mode and a selective illustration tool in policy mode.
