"""Harvest REAL human businesses/services from OpenStreetMap (free Overpass API).
Only imports entries that carry a real website tag -> no fabricated contacts.
This is the human-services side of the index. Run: python seeders/harvest_osm.py"""
import json, time, urllib.request, urllib.parse
from _common import slugify, merge

OVERPASS = "https://overpass-api.de/api/interpreter"

# (city label, country, bbox south,west,north,east)
CITIES = [
    ("kampala",      "uganda",       (0.24, 32.50, 0.42, 32.68)),
    ("nairobi",      "kenya",        (-1.37, 36.72, -1.16, 36.95)),
    ("lagos",        "nigeria",      (6.40, 3.30, 6.65, 3.55)),
    ("kigali",       "rwanda",       (-1.99, 30.02, -1.90, 30.14)),
    ("addis",        "ethiopia",     (8.90, 38.68, 9.05, 38.85)),
    ("accra",        "ghana",        (5.52, -0.28, 5.66, -0.10)),
    ("dar",          "tanzania",     (-6.90, 39.20, -6.75, 39.32)),
    ("johannesburg", "southafrica",  (-26.28, 27.95, -26.10, 28.12)),
]
SLEEP = 12  # Overpass rate-limits hard; be patient between cities

SKILL = {
    "pharmacy": "healthcare", "hospital": "healthcare", "clinic": "healthcare",
    "doctors": "healthcare", "dentist": "healthcare",
    "bank": "bank", "restaurant": "restaurant", "cafe": "restaurant",
    "fast_food": "restaurant", "fuel": "transport", "car_repair": "mechanic",
    "hotel": "hotel_lodging", "guest_house": "hotel_lodging",
    "lawyer": "legal", "school": "education", "university": "education",
}

def q(bbox):
    s, w, n, e = bbox
    b = f"({s},{w},{n},{e})"
    return f"""[out:json][timeout:60];
(
  nwr["amenity"~"pharmacy|hospital|clinic|doctors|dentist|bank|restaurant|cafe|fast_food|fuel|car_repair"]["website"]{b};
  nwr["tourism"~"hotel|guest_house"]["website"]{b};
  nwr["office"="lawyer"]["website"]{b};
  nwr["amenity"~"school|university"]["website"]{b};
);
out center 200;"""

def fetch(ql):
    data = urllib.parse.urlencode({"data": ql}).encode()
    req = urllib.request.Request(OVERPASS, data=data, headers={"User-Agent": "godena-harvester"})
    with urllib.request.urlopen(req, timeout=90) as r:
        return json.load(r)

def harvest():
    out = []
    for label, country, bbox in CITIES:
        try:
            data = fetch(q(bbox))
        except Exception as ex:
            print(f"  osm {label}: {ex}")
            time.sleep(5)
            continue
        for el in data.get("elements", []):
            t = el.get("tags", {})
            name = t.get("name")
            web = (t.get("website") or t.get("contact:website") or "").strip()
            if not name or not web.startswith("http"):
                continue
            cat = t.get("amenity") or t.get("tourism") or t.get("office") or ""
            skill = SKILL.get(cat, "")
            if not skill:
                continue
            out.append({
                "name": name.replace(" ", "_")[:60],
                "slug": slugify(f"{name}-{label}"),
                "skill_primary": skill,
                "skill_tags": [skill, cat, label, country],
                "location": label, "country": country,
                "website": web,
                "phone": t.get("phone") or t.get("contact:phone") or None,
                "source": "osm_scraped",
                "reputation_score": 9,
            })
        print(f"  osm {label}: {len(out)} cumulative")
        time.sleep(SLEEP)
    return out

if __name__ == "__main__":
    cands = harvest()
    added, total = merge(cands)
    print(f"OSM: {len(cands)} real businesses, {added} added, snapshot now {total}")
