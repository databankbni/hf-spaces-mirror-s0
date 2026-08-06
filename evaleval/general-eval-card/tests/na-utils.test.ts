import { describe, it, expect } from 'vitest'
import { naReasonForCategoryFromEval } from '../lib/na-utils'

const benchIds = ['Q1', 'Q2']
const procIds = ['P1']

describe('naReasonForCategoryFromEval', () => {
  it('returns reason when additionalAspects marks not applicable', () => {
    const cat = {
      additionalAspects: 'Not applicable: this category does not apply',
      benchmarkAnswers: { Q1: 'N/A', Q2: 'N/A' },
      processAnswers: { P1: 'N/A' }
    }
    const r = naReasonForCategoryFromEval(cat, benchIds, procIds)
    expect(r).toBe('Not applicable: this category does not apply')
  })

  it('returns undefined when any non-NA answer exists', () => {
    const cat = {
      additionalAspects: 'Not applicable: but answers exist',
      benchmarkAnswers: { Q1: 'yes', Q2: 'N/A' },
      processAnswers: { P1: 'N/A' }
    }
    const r = naReasonForCategoryFromEval(cat, benchIds, procIds)
    expect(r).toBeUndefined()
  })

  it('ignores question-level source NA markers for category selectability', () => {
    const cat = {
      additionalAspects: '',
      benchmarkAnswers: { Q1: 'N/A', Q2: 'N/A' },
      processAnswers: { P1: 'N/A' },
      benchmarkSources: {
        Q1: [ { description: 'Not applicable for this question' } ]
      }
    }
    const r = naReasonForCategoryFromEval(cat, benchIds, procIds)
    expect(r).toBeUndefined()
  })
})
