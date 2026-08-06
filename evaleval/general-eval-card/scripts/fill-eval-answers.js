const fs = require('fs')
const path = require('path')

const EVAL_DIR = path.join(__dirname, '..', 'public', 'evaluations')
const BENCH = ['A1','A2','A3','A4','A5','A6']
const PROC = ['B1','B2','B3','B4','B5','B6']

function fillAnswers(obj) {
  if (!obj.selectedCategories || !Array.isArray(obj.selectedCategories)) return obj
  obj.categoryEvaluations = obj.categoryEvaluations || {}

  for (const cat of obj.selectedCategories) {
    obj.categoryEvaluations[cat] = obj.categoryEvaluations[cat] || {}
    const catEval = obj.categoryEvaluations[cat]

    catEval.benchmarkAnswers = catEval.benchmarkAnswers || {}
    for (const q of BENCH) {
      if (catEval.benchmarkAnswers[q] === undefined || catEval.benchmarkAnswers[q] === null) {
        catEval.benchmarkAnswers[q] = 'N/A'
      }
    }

    catEval.processAnswers = catEval.processAnswers || {}
    for (const q of PROC) {
      if (catEval.processAnswers[q] === undefined || catEval.processAnswers[q] === null) {
        catEval.processAnswers[q] = 'N/A'
      }
    }

    catEval.benchmarkSources = catEval.benchmarkSources || {}
    catEval.processSources = catEval.processSources || {}
    catEval.additionalAspects = catEval.additionalAspects || ''
  }

  return obj
}

fs.readdirSync(EVAL_DIR).forEach((file) => {
  if (!file.endsWith('.json')) return
  const p = path.join(EVAL_DIR, file)
  try {
    const raw = fs.readFileSync(p, 'utf8')
    const obj = JSON.parse(raw)
    const updated = fillAnswers(obj)
    fs.writeFileSync(p, JSON.stringify(updated, null, 2) + '\n')
    console.log('Updated', file)
  } catch (e) {
    console.error('Failed', file, e.message)
  }
})
