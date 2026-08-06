const fs = require('fs')
const path = require('path')

const EVAL_DIR = path.join(__dirname, '..', 'public', 'evaluations')
const BENCH = ['A1','A2','A3','A4','A5','A6']
const PROC = ['B1','B2','B3','B4','B5','B6']

function reasonForBenchmark(evalObj, catId, qid) {
  const modality = (evalObj.modality || '').toLowerCase()
  if (modality.includes('text') && (catId.includes('vision') || catId.includes('physical') || catId.includes('robotic') || catId.includes('perception'))) {
    return `${qid}: Not applicable — this evaluation/sample is for a text-only model; visual or physical benchmarks are not relevant.`
  }
  // default
  return `${qid}: Not applicable — benchmark data not provided or not run for this evaluation.`
}

function reasonForProcess(evalObj, catId, qid) {
  // give more specific reasons for some questions
  if (qid === 'B2') return `${qid}: Not applicable — replication package or reproducible artifacts were not published for this sample.`
  if (qid === 'B4') return `${qid}: Not applicable — figures/uncertainty plots are not included in this report.`
  if (qid === 'B5') return `${qid}: Not applicable — standards mapping or regulatory alignment not performed for this sample.`
  if (evalObj.modality && evalObj.modality.toLowerCase().includes('text') && (catId.includes('physical') || catId.includes('robotic'))) {
    return `${qid}: Not applicable — process documentation for physical/robotic systems not relevant to text-only model.`
  }
  return `${qid}: Not applicable — documentation or process evidence not captured for this evaluation.`
}

function populateFile(filePath) {
  const raw = fs.readFileSync(filePath, 'utf8')
  const obj = JSON.parse(raw)
  let changed = false

  for (const catId of obj.selectedCategories || []) {
    obj.categoryEvaluations = obj.categoryEvaluations || {}
    obj.categoryEvaluations[catId] = obj.categoryEvaluations[catId] || {}
    const ce = obj.categoryEvaluations[catId]
    ce.benchmarkAnswers = ce.benchmarkAnswers || {}
    ce.processAnswers = ce.processAnswers || {}
    ce.benchmarkSources = ce.benchmarkSources || {}
    ce.processSources = ce.processSources || {}

    // Benchmarks
    for (const q of BENCH) {
      if (ce.benchmarkAnswers[q] === 'N/A') {
        const sources = ce.benchmarkSources[q] || []
        if (!sources || sources.length === 0 || (sources[0] && (sources[0].description === 'N/A' || sources[0].description === 'Not applicable'))) {
          ce.benchmarkSources[q] = [
            {
              url: '',
              description: reasonForBenchmark(obj, catId, q),
              sourceType: 'N/A'
            }
          ]
          changed = true
        }
      }
    }

    // Process
    for (const q of PROC) {
      if (ce.processAnswers[q] === 'N/A') {
        const sources = ce.processSources[q] || []
        if (!sources || sources.length === 0 || (sources[0] && (sources[0].description === 'N/A' || sources[0].description === 'Not applicable'))) {
          ce.processSources[q] = [
            {
              url: '',
              description: reasonForProcess(obj, catId, q),
              documentType: 'N/A',
              scope: reasonForProcess(obj, catId, q)
            }
          ]
          changed = true
        }
      }
    }
  }

  if (changed) {
    fs.writeFileSync(filePath, JSON.stringify(obj, null, 2) + '\n')
  }
  return changed
}

const results = []
fs.readdirSync(EVAL_DIR).forEach((file) => {
  if (!file.endsWith('.json')) return
  const p = path.join(EVAL_DIR, file)
  try {
    const updated = populateFile(p)
    results.push({ file, updated })
  } catch (e) {
    results.push({ file, error: e.message })
  }
})

console.table(results)
