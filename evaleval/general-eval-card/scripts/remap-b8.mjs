import fs from 'fs/promises'
import path from 'path'

const root = path.resolve(new URL(import.meta.url).pathname, '..', '..')
const publicDir = path.join(root, 'public', 'evaluations')
const dataDir = path.join(root, 'data', 'evaluations')

async function listFiles(dir){
  try{ const files = await fs.readdir(dir); return files.filter(f=>f.endsWith('.json')).map(f=>path.join(dir,f)) }catch(e){ return [] }
}

function chooseTarget(obj){
  // prefer B6, then B5
  if(!Object.prototype.hasOwnProperty.call(obj, 'B6')) return 'B6'
  if(!Object.prototype.hasOwnProperty.call(obj, 'B5')) return 'B5'
  // If both exist, choose B6 (we will try to merge by leaving existing and moving into B5)
  return 'B5'
}

async function processFile(file){
  const txt = await fs.readFile(file,'utf8')
  let json
  try{ json = JSON.parse(txt) }catch(e){ return {file, error: 'invalid json'} }
  const cats = json.categoryEvaluations || {}
  let changed = false
  const changes = []
  for(const [cat, obj] of Object.entries(cats)){
    // handle processAnswers
    if(obj.processAnswers && Object.prototype.hasOwnProperty.call(obj.processAnswers, 'B8')){
      const target = chooseTarget(obj.processAnswers)
      // if target exists, don't overwrite: move B8 value into an array / or leave both under target with suffix
      if(!Object.prototype.hasOwnProperty.call(obj.processAnswers, target)){
        obj.processAnswers[target] = obj.processAnswers['B8']
      }else{
        // merge: if values differ, create array of unique
        const existing = obj.processAnswers[target]
        const incoming = obj.processAnswers['B8']
        if(Array.isArray(existing)){
          const arr = Array.from(new Set([...existing, ...(Array.isArray(incoming)?incoming:[incoming])]))
          obj.processAnswers[target] = arr
        }else{
          const arr = Array.from(new Set([existing, ...(Array.isArray(incoming)?incoming:[incoming])]))
          obj.processAnswers[target] = arr
        }
      }
      delete obj.processAnswers['B8']
      changed = true
      changes.push({category:cat, section:'processAnswers', from:'B8', to:target})
    }
    // handle processSources
    if(obj.processSources && Object.prototype.hasOwnProperty.call(obj.processSources, 'B8')){
      const target = chooseTarget(obj.processSources)
      if(!Object.prototype.hasOwnProperty.call(obj.processSources, target)){
        obj.processSources[target] = obj.processSources['B8']
      }else{
        // merge arrays
        const existing = obj.processSources[target]
        const incoming = obj.processSources['B8']
        const merged = Array.isArray(existing)? existing.concat(incoming || []) : [existing].concat(incoming || [])
        // dedupe by JSON
        const seen = new Map()
        const dedup = []
        for(const item of merged){
          const key = JSON.stringify(item)
          if(!seen.has(key)){ seen.set(key,true); dedup.push(item) }
        }
        obj.processSources[target] = dedup
      }
      delete obj.processSources['B8']
      changed = true
      changes.push({category:cat, section:'processSources', from:'B8', to:target})
    }
  }
  if(changed){
    await fs.writeFile(file, JSON.stringify(json, null, 2), 'utf8')
  }
  return {file, changed, changes}
}

async function main(){
  const files = [ ...(await listFiles(publicDir)), ...(await listFiles(dataDir)) ]
  const results = []
  for(const f of files){
    const r = await processFile(f)
    results.push(r)
  }
  console.log(JSON.stringify(results, null, 2))
}

main().catch(err=>{ console.error(err); process.exit(1) })
