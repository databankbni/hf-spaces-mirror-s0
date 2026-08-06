// Lightweight helper to determine whether a category should be considered fully Not Applicable.
// It intentionally only treats the category as NA when the category-level field
// `additionalAspects` explicitly marks it as not applicable. Question-level/source
// markers are ignored for category selectability (they are relevant to question details).
//
// TODO: check if deprecated. Only consumer is tests/na-utils.test.ts;
// no production callers — possibly intended for an unshipped UI feature.
export function naReasonForCategoryFromEval(
  catEval: any,
  benchmarkQuestionIds: string[] = [],
  processQuestionIds: string[] = []
): string | undefined {
  if (!catEval) return undefined

  const isNonNAAnswer = (ans: any) => {
    if (ans === undefined || ans === null) return false
    if (Array.isArray(ans)) {
      return ans.some((a) => {
        const s = String(a || "").trim().toLowerCase()
        return s !== "n/a" && !/not applicable/i.test(s) && s.length > 0
      })
    }
    const s = String(ans).trim().toLowerCase()
    return s !== "n/a" && !/not applicable/i.test(s) && s.length > 0
  }

  let anyNonNA = false
  if (catEval.benchmarkAnswers) {
    for (const k of benchmarkQuestionIds) {
      if (isNonNAAnswer(catEval.benchmarkAnswers[k])) {
        anyNonNA = true
        break
      }
    }
  }
  if (!anyNonNA && catEval.processAnswers) {
    for (const k of processQuestionIds) {
      if (isNonNAAnswer(catEval.processAnswers[k])) {
        anyNonNA = true
        break
      }
    }
  }

  if (anyNonNA) return undefined

  if (typeof catEval.additionalAspects === "string" && /not applicable/i.test(catEval.additionalAspects)) {
    return catEval.additionalAspects
  }

  return undefined
}
