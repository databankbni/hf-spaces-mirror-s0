import fs from 'fs/promises'
import path from 'path'

const root = path.resolve(new URL(import.meta.url).pathname, '..', '..')
const publicDir = path.join(root, 'public', 'evaluations')
const dataDir = path.join(root, 'data', 'evaluations')

const allowed = new Set([
  'A1','A2','A3','A4','A5','A6',
  'B1','B2','B3','B4','B5','B6'
])

async function listFiles(dir){
  try{
    const files = await fs.readdir(dir)
    return files.filter(f=>f.endsWith('.json')).map(f=>path.join(dir,f))
  }catch(e){
    return []
  }
}

async function analyze(file){
  const txt = await fs.readFile(file,'utf8')
  let json
  try{ json = JSON.parse(txt) }catch(e){ return {file, error: 'invalid json'} }
  const unexpected = {}
  const categories = json.categoryEvaluations || {}
  for(const [cat, obj] of Object.entries(categories)){
    const ua = []
    const pa = Object.keys(obj.benchmarkAnswers||{})
    const pproc = Object.keys(obj.processAnswers||{})
    const ps = Object.keys(obj.processSources||{})
    const keys = [...pa, ...pproc, ...ps]
    const bad = keys.filter(k=>!allowed.has(k))
    if(bad.length) unexpected[cat]=Array.from(new Set(bad))
  }
  return {file, unexpected}
}

async function main(){
  const files = [ ...(await listFiles(publicDir)), ...(await listFiles(dataDir)) ]
  const results = []
  for(const f of files){
    const r = await analyze(f)
    results.push(r)
  }
  console.log(JSON.stringify(results, null, 2))
}

main().catch(err=>{ console.error(err); process.exit(1) })
