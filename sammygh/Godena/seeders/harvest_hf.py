"""Harvest real AI agents/tools/services from the Hugging Face Hub (keyless).
- Spaces (AI apps/agents) sorted by likes
- Models (AI services) sorted by downloads
Every entry has a real https://huggingface.co/... URL. Run: python seeders/harvest_hf.py"""
import json, sys, urllib.request
from _common import slugify, merge

def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "godena-harvester"})
    with urllib.request.urlopen(req, timeout=45) as r:
        return json.load(r)

SKILL_HINTS = {
    "image": "design", "diffusion": "design", "art": "design", "logo": "design",
    "text-to-image": "design", "img": "design", "sdxl": "design", "flux": "design",
    "video": "media_production", "audio": "media_production", "music": "media_production",
    "voice": "media_production", "speech": "media_production", "tts": "media_production",
    "asr": "media_production", "whisper": "media_production", "text-to-speech": "media_production",
    "text-to-video": "media_production",
    "translate": "translation", "translation": "translation",
    "chat": "coding", "agent": "coding", "code": "coding", "llm": "coding",
    "research": "coding", "search": "coding", "rag": "coding", "text-generation": "coding",
    "embedding": "coding", "classification": "coding", "detection": "coding",
}

def skill_for(text):
    t = (text or "").lower()
    for k, v in SKILL_HINTS.items():
        if k in t:
            return v
    return "coding"

def words(s):
    return [w for w in s.lower().replace("-", " ").replace("_", " ").split() if len(w) > 2][:5]

def harvest_spaces(limit):
    out = []
    for a in fetch(f"https://huggingface.co/api/spaces?sort=likes&direction=-1&limit={limit}"):
        sid = a.get("id") or ""
        if "/" not in sid:
            continue
        likes = int(a.get("likes") or 0)
        if likes < 3:
            continue
        sp = sid.split("/", 1)[1]
        tags = [str(t).lower() for t in (a.get("tags") or [])][:5]
        out.append({
            "name": sp.replace("-", " ").replace("_", " ").strip().title().replace(" ", "_")[:60],
            "slug": slugify(sid),
            "skill_primary": skill_for(sp + " " + " ".join(tags)),
            "skill_tags": ["ai", "huggingface", "tool"] + words(sp) + tags[:2],
            "website": f"https://huggingface.co/spaces/{sid}",
            "source": "huggingface_v3",
            "reputation_score": min(6 + likes // 50, 12),
        })
    return out

PIPELINES = [
    "text-generation", "text-to-image", "automatic-speech-recognition",
    "text-to-speech", "translation", "image-classification", "object-detection",
    "image-to-text", "text-classification", "summarization", "question-answering",
    "image-to-image", "text-to-video", "sentence-similarity", "image-segmentation",
    "audio-classification", "zero-shot-classification", "fill-mask",
]

def harvest_models(per_tag=700):
    out, seen = [], set()
    for tag in PIPELINES:
        try:
            data = fetch(f"https://huggingface.co/api/models?pipeline_tag={tag}&sort=downloads&direction=-1&limit={per_tag}")
        except Exception as e:
            print(f"  models {tag}: {e}")
            continue
        for m in data:
            mid = m.get("id") or ""
            if "/" not in mid or mid in seen:
                continue
            seen.add(mid)
            dl = int(m.get("downloads") or 0)
            if dl < 1000:
                continue
            name = mid.split("/", 1)[1]
            out.append({
                "name": name.replace("-", " ").replace("_", " ").strip().title().replace(" ", "_")[:60],
                "slug": slugify("model-" + mid),
                "skill_primary": skill_for(tag + " " + name),
                "skill_tags": ["ai", "model", "huggingface", tag] + words(name),
                "website": f"https://huggingface.co/{mid}",
                "source": "huggingface_v2",
                "reputation_score": min(6 + dl // 500000, 12),
            })
    return out

if __name__ == "__main__":
    per_tag = int(sys.argv[1]) if len(sys.argv) > 1 else 800
    cands = harvest_spaces(1000) + harvest_models(per_tag)
    added, total = merge(cands)
    print(f"HF: {len(cands)} candidates, {added} added, snapshot now {total}")
