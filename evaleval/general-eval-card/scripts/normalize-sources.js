#!/usr/bin/env node
const fs = require('fs')
const path = require('path')

const EVAL_DIR = path.join(__dirname, '..', 'public', 'evaluations')

const benchmarkFields = [
  'id',
  'url',
  'description',
  'sourceType',
  'benchmarkName',
  'metrics',
  'score',
  'version',
  'taskVariants',
  'customFields',
]

const processFields = [
  'id',
  'url',
  'description',
  'sourceType',
  'documentType',
  'customFields',
]

function ensureId(prefix = 's') {
  return `${prefix}-${Date.now().toString(36)}-${Math.random().toString(36).slice(2,8)}`
}

function normalizeSource(obj, isProcess = false) {
  if (typeof obj === 'string') {
    obj = { description: obj }
  }

  if (obj == null || typeof obj !== 'object') obj = {}

  const out = {}
  const fields = isProcess ? processFields : benchmarkFields
  for (const f of fields) {
    if (f === 'id') {
      out.id = obj.id || ensureId(isProcess ? 'proc' : 'bench')
      continue
    }
    if (f === 'customFields') {
      out.customFields = obj.customFields && typeof obj.customFields === 'object' ? obj.customFields : {}
      continue
    }

    out[f] = obj[f] != null ? obj[f] : ''
  }

  return out
}

function normalizeFile(filePath) {
  const content = fs.readFileSync(filePath, 'utf8')
  let data
  try {
    data = JSON.parse(content)
  } catch (e) {
    console.error(`Skipping ${filePath}: invalid JSON`)
    return false
  }

  let changed = false

  if (data.categoryEvaluations && typeof data.categoryEvaluations === 'object') {
    for (const [catId, catData] of Object.entries(data.categoryEvaluations)) {
      if (!catData || typeof catData !== 'object') continue

      // benchmarkSources: object mapping questionId -> array
      catData.benchmarkSources = catData.benchmarkSources || {}
      for (const [qid, arr] of Object.entries(catData.benchmarkSources)) {
        const list = Array.isArray(arr) ? arr : arr ? [arr] : []
        const normalized = list.map((s) => normalizeSource(s, false))
        // compare lengths/ids to detect change
        if (JSON.stringify(list) !== JSON.stringify(normalized)) changed = true
        catData.benchmarkSources[qid] = normalized
      }

      catData.processSources = catData.processSources || {}
      for (const [qid, arr] of Object.entries(catData.processSources)) {
        const list = Array.isArray(arr) ? arr : arr ? [arr] : []
        const normalized = list.map((s) => normalizeSource(s, true))
        if (JSON.stringify(list) !== JSON.stringify(normalized)) changed = true
        catData.processSources[qid] = normalized
      }

      // ensure answers exist as objects but don't alter existing answers
      catData.benchmarkAnswers = catData.benchmarkAnswers || {}
      catData.processAnswers = catData.processAnswers || {}
    }
  }

  if (changed) {
    fs.writeFileSync(filePath, JSON.stringify(data, null, 2) + '\n')
    console.log(`Updated: ${path.basename(filePath)}`)
    return true
  }

  console.log(`Unchanged: ${path.basename(filePath)}`)
  return false
}

function main() {
  const files = fs.readdirSync(EVAL_DIR).filter((f) => f.endsWith('.json'))
  for (const f of files) {
    const fp = path.join(EVAL_DIR, f)
    try {
      normalizeFile(fp)
    } catch (e) {
      console.error(`Error processing ${f}:`, e.message)
    }
  }
}

main()
