# ═══════════════════════════════════════════════════════════════════
# GODENA — The Open Agent Network
# github.com/sammygedamua/godena
#
# FOUNDER
#   Samuel Gedamua    — Founder & CEO. Built this from nothing.
#   Amanuel Asmerom   —  Demand signals. Network vision.
#
# CO-BUILT WITH
#   Claude (Anthropic) — Every line of code. brick by brick we build this shit 
#
# FIRST AGENT
#   Emmas_cars Kampala — March 11 2026. The one that started it all.
#
# ═══════════════════════════════════════════════════════════════════
# DISCLAIMER
#   If this code looks surprisingly coherent for a first-time builder,
#   that's because it was built with Claude at 2am across many sessions.
#   Samuel  (I)probably doesn't know what half of this code rules but understands the use case.
#   Neither does Claude, honestly. But it works.
#   First real search: "tax kenya" — returned KRA. i felt like i just made google.
#   Second real search: "logistics nairobi" — returned DHL. then i tried to move things with my mind God mode.
#   kept going anyway. That's the whole story.
# ═══════════════════════════════════════════════════════════════════

import os, re, json, time, httpx, threading
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
from supabase import create_client

SUPABASE_URL      = os.environ.get("SUPABASE_URL", "https://rgsykquesbiozrhvkvle.supabase.co")
SUPABASE_KEY      = os.environ.get("SUPABASE_KEY", "")
GREEN_INSTANCE_ID = os.environ.get("GREEN_INSTANCE_ID", "")
GREEN_TOKEN       = os.environ.get("GREEN_TOKEN", "")
TELEGRAM_TOKEN    = os.environ.get("TELEGRAM_TOKEN", "")
WHATSAPP_NUMBER   = os.environ.get("WHATSAPP_NUMBER", "+256761966728")

sb  = create_client(SUPABASE_URL, SUPABASE_KEY)
USE_DB = os.environ.get("USE_SUPABASE") == "1"   # git-native by default; set USE_SUPABASE=1 to re-enable Supabase
app = FastAPI()

# CORS — lets browsers (godena web page, partner sites, other agents' UIs)
# call the public API directly. The API is read-mostly and free by design.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

# ── DEDUP — prevents double-processing the same message ───────────
seen_msgs = {}

def already_seen(mid):
    now = time.time()
    for k in list(seen_msgs.keys()):
        if now - seen_msgs[k] > 60:
            del seen_msgs[k]
    if mid in seen_msgs:
        return True
    seen_msgs[mid] = now
    return False

# ── STATE — conversation memory per user ──────────────────────────
wa_state   = {}   # WhatsApp registration flows
tg_state   = {}   # Telegram registration flows
wa_context = {}   # WhatsApp current context
tg_context = {}   # Telegram current context
rating_log = {}   # anti-gaming: timestamps per phone
gap_log    = {}   # demand signals: searches with no results

def normalize(raw):
    """Strip phone number to digits only."""
    p = str(raw).replace("+", "").replace(" ", "").replace("-", "")
    if "@" in p:
        p = p.split("@")[0]
    return p


# ═══════════════════════════════════════════════════════════════════
# REPUTATION ENGINE
# ─────────────────────────────────────────────────────────────────
# Signals: identity, tier, performance, external, social, source
# Models: Uber (ratings), Airbnb (sub-ratings), Upwork (recency),
#         Yelp (anti-gaming), GitHub (weighted stars), LinkedIn (endorsements)
#
# Hard rule: reputation is earned, never bought.
# A wanderer with a seed score always loses to a real business.
# ═══════════════════════════════════════════════════════════════════

def compute_reputation(agent):
    score    = 0.0
    country  = (agent.get("country")  or "").lower()
    location = (agent.get("location") or "").lower()
    source   = (agent.get("source")   or "").lower()

    # ── IDENTITY ─────────────────────────────────────────────────
    if agent.get("claimed"):       score += 10
    if agent.get("verified"):      score += 8
    if agent.get("phone"):         score += 6
    if agent.get("whatsapp"):      score += 5
    if agent.get("website"):       score += 3
    if agent.get("opening_hours"): score += 2
    if agent.get("address"):       score += 2
    if agent.get("osm_id"):        score += 4
    if source == "osm_scraped":    score += 4
    if agent.get("neighborhood"):  score += 2
    rr = float(agent.get("response_rate") or 0)
    if rr > 0:
        score += min(rr / 10, 8)

    # ── TIER ─────────────────────────────────────────────────────
    tier = int(agent.get("tier") or 0)
    score += {0: 0, 1: 10, 2: 20, 3: 30}.get(tier, 0)

    # ── PERFORMANCE ──────────────────────────────────────────────
    interactions = int(agent.get("interactions_count") or 0)
    jobs_done    = int(agent.get("jobs_completed")     or 0)
    avg_r        = float(agent.get("avg_rating")       or 0)
    abandoned    = int(agent.get("abandoned_jobs")     or 0)
    flags        = int(agent.get("flags")              or 0)
    repeat_c     = int(agent.get("repeat_contacts")    or 0)
    recent_jobs  = int(agent.get("recent_jobs_30d")    or 0)

    if interactions > 0: score += min(interactions * 0.4, 12)
    if jobs_done    > 0: score += min(jobs_done    * 1.2, 20)
    if recent_jobs  > 0: score += min(recent_jobs  * 2.0, 15)  # recent weighted 2x
    if repeat_c     > 0: score += min(repeat_c     * 4.0, 20)  # repeat = strongest signal

    # sub-ratings (Airbnb model: speed, accuracy, price, comms, reliability)
    speed    = float(agent.get("rating_speed")         or 0)
    accuracy = float(agent.get("rating_accuracy")      or 0)
    price    = float(agent.get("rating_price")         or 0)
    comms    = float(agent.get("rating_communication") or 0)
    reliable = float(agent.get("rating_reliability")   or 0)
    sub_vals = [x for x in [speed, accuracy, price, comms, reliable] if x > 0]
    if sub_vals:
        score += (sum(sub_vals) / len(sub_vals)) * 4  # 5.0 avg = 20 pts
    elif avg_r > 0:
        score += avg_r * 4

    # penalties — no cap, hard deductions
    score -= abandoned * 4
    score -= flags     * 6

    # placeholder number penalty — test numbers get buried
    if "1415555" in str(agent.get("whatsapp") or ""):
        score -= 50.0

    # ── EXTERNAL — Google rating (cross-validated) ────────────────
    g_rating = float(agent.get("google_rating")       or 0)
    g_count  = int(agent.get("google_review_count")   or 0)
    if g_rating > 0:
        identity_anchors = sum([
            bool(agent.get("phone")),
            bool(agent.get("osm_id")),
            bool(agent.get("claimed")),
        ])
        if identity_anchors >= 1:
            score += g_rating * 4
            if   g_count > 500: score += 10
            elif g_count > 100: score += 6
            elif g_count > 20:  score += 3
            elif g_count > 5:   score += 1

    # ── SOCIAL — peer trust chain ─────────────────────────────────
    agent_tags      = int(agent.get("agent_tags_received")    or 0)
    stars           = int(agent.get("stars_received")         or 0)
    star_weight     = float(agent.get("star_weight")          or 1.0)
    sub_complete    = int(agent.get("completions_as_sub")     or 0)
    endorsements    = int(agent.get("specialty_endorsements") or 0)
    endorse_w       = float(agent.get("endorsement_weight")   or 1.0)
    recommendations = int(agent.get("recommendation_count")   or 0)
    latency         = float(agent.get("avg_latency")          or 0)
    success         = float(agent.get("success_rate")         or 0)

    score += min(recommendations * 3,              15)
    score += min(agent_tags      * 5,              15)
    score += min(stars           * 3 * star_weight, 12)
    score += min(endorsements    * 4 * endorse_w,   14)
    score += min(sub_complete    * 2,               8)
    if latency > 0: score += max(0, 5 - latency)
    if success > 0: score += success * 10

    # ── SOURCE BONUS — real agents always beat wanderers ─────────
    # This is the flywheel: verified sources get a permanent lift
    # so wanderers (auto-generated from gap detection) stay below
    # real agents in every search result.
    SOURCE_BONUS = {
        "verified_global":  35,  # manually curated real agents
        "government_list":  40,  # official government channels
        "osm_scraped":      20,  # OpenStreetMap verified businesses
        "osm_daily":        20,
        "openstreetmap":    20,
        "osm_global_bulk":  18,
        "whatsapp":         20,  # registered via WhatsApp
        "telegram":         15,  # registered via Telegram
        "claimed":          15,  # business claimed their profile
        "api":              10,  # registered via API
        "openai_gpt_store": 12,
        "poe":               8,
        "platform_agents":   8,
        "mcp_glama":        10,
        "mcp_awesome_mcp":  10,
        "mcp_smithery":     10,
        "huggingface_v3":    6,
        "huggingface_v2":    5,
        "huggingface":       5,
        "replicate":         8,
        "seed":              2,
        "seed_global":       2,
        "gap_auto":          0,  # gap wanderers get nothing
    }
    score += SOURCE_BONUS.get(source, 0)

    # ── GEOGRAPHIC BOOST ─────────────────────────────────────────
    if country == "usa" and "sf" in location: score += 8
    if country == "estonia":                  score += 10

    return round(max(score, 0.0), 1)


# ── BADGE ENGINE ──────────────────────────────────────────────────
def compute_badges(agent):
    badges  = []
    jobs    = int(agent.get("jobs_completed")     or 0)
    repeat  = int(agent.get("repeat_contacts")    or 0)
    flags   = int(agent.get("flags")              or 0)
    avg_r   = float(agent.get("avg_rating")       or 0)
    tier    = int(agent.get("tier")               or 0)
    tags    = int(agent.get("agent_tags_received") or 0)

    if jobs >= 10 and flags == 0:          badges.append("First 10")
    if jobs >= 50:                          badges.append("Veteran")
    if repeat >= 5:                         badges.append("Trusted")
    if avg_r >= 4.8 and jobs >= 5:          badges.append("5 Star")
    if tags >= 10:                          badges.append("Peer Endorsed")
    if tier == 3:                           badges.append("Elite")
    if agent.get("verified") and tier >= 2: badges.append("Verified Pro")
    return badges


# ── ANTI-GAMING ENGINE ────────────────────────────────────────────
def is_burst_rating(rater_phone):
    """5 ratings from same phone in 10 minutes = suspicious. Yelp model."""
    now   = time.time()
    phone = normalize(rater_phone or "unknown")
    if phone not in rating_log:
        rating_log[phone] = []
    rating_log[phone] = [t for t in rating_log[phone] if now - t < 600]
    if len(rating_log[phone]) >= 5:
        return True
    rating_log[phone].append(now)
    return False


def can_upgrade_tier(agent, target_tier):
    """Time-gating: Tier1→2 needs 14 days. Tier2→3 needs 30 days."""
    from datetime import datetime, timezone
    current_tier = int(agent.get("tier") or 0)
    if target_tier <= current_tier:
        return False, "Already at this tier"
    upgraded_at = agent.get("upgraded_at") or agent.get("created_at")
    if not upgraded_at:
        return True, "ok"
    try:
        last     = datetime.fromisoformat(upgraded_at.replace("Z", "+00:00"))
        now      = datetime.now(timezone.utc)
        days     = (now - last).days
        required = {2: 14, 3: 30}.get(target_tier, 0)
        if days < required:
            return False, f"Need {required - days} more days"
    except:
        pass
    return True, "ok"


# ═══════════════════════════════════════════════════════════════════
# SEARCH ENGINE — SKILL-FIRST
# ─────────────────────────────────────────────────────────────────
# Rule: skill must match or the agent is invisible.
# Location and reputation only rank among skill matches.
# This stops "tax office" from returning health insurance agents.
# ═══════════════════════════════════════════════════════════════════

SKILL_SYNONYMS = {
    # ── LEGAL ──────────────────────────────────────────────────────
    "lawyer":     ["legal","law","advocate","attorney","barrister","solicitor","counsel"],
    "legal":      ["legal","law","lawyer","advocate","attorney","compliance","litigation"],
    "advocate":   ["legal","law","lawyer","advocate","attorney"],
    "attorney":   ["legal","law","lawyer","attorney","advocate"],

    # ── FINANCE & TAX ─────────────────────────────────────────────
    "tax":        ["tax","taxation","vat","kra","ura","revenue","tax_returns","corporate_tax",
                   "ura","kra","taxes","compliance"],
    "accounting": ["accounting","accountant","bookkeeping","audit","cpa","payroll"],
    "accountant": ["accounting","accountant","bookkeeping","audit"],
    "cpa":        ["accounting","tax","cpa"],
    "finance":    ["finance","loans","investment","forex","mobile_money","microfinance"],
    "loan":       ["finance","microfinance","sacco","mobile_money","loans","bank"],
    "bank":       ["finance","bank","loans","savings","forex","investment"],
    "funding":    ["finance","investment","vc","grant","accelerator","startup","investor"],
    "startup":    ["finance","startup_support","investor","pitch","accelerator","incubator"],
    "invest":     ["finance","investment","vc","investor","funding"],
    "grant":      ["finance","grant","funding","ngo","usaid","development"],
    "vc":         ["finance","vc","venture capital","investor","funding"],

    # ── MOBILE MONEY ──────────────────────────────────────────────
    "money":      ["mobile_money","remittance","mpesa","momo","transfer","forex"],
    "remittance": ["remittance","mobile_money","transfer","forex","send money"],
    "mpesa":      ["mobile_money","mpesa","safaricom","kenya","transfer"],
    "momo":       ["mobile_money","mtn","momo","transfer","uganda"],
    "send":       ["remittance","mobile_money","transfer","forex"],

    # ── HEALTHCARE ────────────────────────────────────────────────
    "doctor":     ["healthcare","medical","clinic","hospital","physician","gp"],
    "hospital":   ["healthcare","hospital","emergency","inpatient","medical"],
    "clinic":     ["healthcare","clinic","medical","gp","outpatient"],
    "pharmacy":   ["healthcare","pharmacy","medicine","drugs","dispensary"],
    "health":     ["healthcare","medical","clinic","pharmacy","hospital"],

    # ── LOGISTICS ─────────────────────────────────────────────────
    "logistics":  ["logistics","freight","delivery","shipping","courier","last_mile","supply_chain"],
    "transport":  ["transport","logistics","truck","boda","taxi","matatu","bus","courier","delivery"],
    "truck":      ["transport","logistics","truck","freight","haulage"],
    "delivery":   ["logistics","transport","delivery","courier","last_mile"],
    "cargo":      ["import_export","cargo","freight","clearing","customs","shipping"],
    "import":     ["import_export","customs","clearing","freight","trade","china_sourcing"],
    "export":     ["import_export","agriculture_export","commodity_trading","trade"],
    "china":      ["china_sourcing","import_export","alibaba","factory","guangzhou","yiwu"],
    "clearing":   ["import_export","customs","clearing","freight","cargo"],
    "customs":    ["import_export","customs","clearing","tax","trade"],

    # ── REAL ESTATE ───────────────────────────────────────────────
    "land":       ["real_estate","land","property","land_registry","plot","title"],
    "property":   ["real_estate","property","land","rental","valuation","mortgage"],
    "house":      ["real_estate","property","rental","housing","construction"],
    "broker":     ["real_estate","finance","import_export","commodity_trading","brokerage"],
    "rent":       ["real_estate","rental","housing","property","accommodation"],

    # ── TRAVEL & VISA ─────────────────────────────────────────────
    "visa":       ["visa_consulting","visa","immigration","permit","embassy","consulate"],
    "immigration":["immigration","visa","permit","residency","asylum","citizenship"],
    "travel":     ["travel_agency","visa_consulting","hotel_lodging","tourism","flights"],
    "flights":    ["travel_agency","flights","airline","booking","airport"],
    "hotel":      ["hotel_lodging","hotel","accommodation","lodge","guesthouse","hospitality"],
    "safari":     ["hotel_lodging","safari","tourism","travel_agency","guide","tour"],
    "tourism":    ["hotel_lodging","travel_agency","safari","tourism","tour"],
    "bus":        ["transport","bus","matatu","coach","intercity","booking","ticket"],
    "scholarship":["scholarship_finder","scholarship","bursary","grant","fulbright","erasmus"],
    "coffee":     ["restaurant","cafe","food","coffeeshop"],
    "cafe":       ["restaurant","cafe","food","coffeeshop"],
    "climate":    ["solar_energy","agriculture","clean tech","environment"],
    "shop":       ["restaurant","retail","service","store"],

    # ── FOOD & HOSPITALITY ────────────────────────────────────────
    "food":       ["restaurant","food","catering","bakery","butchery","takeaway"],
    "restaurant": ["restaurant","food","catering","eatery","cafe","dining"],
    "catering":   ["restaurant","catering","events","food","buffet"],
    "coffee":     ["restaurant","cafe","food","coffeeshop","drinks"],
    "cafe":       ["restaurant","cafe","food","coffeeshop","drinks"],
    "climate":    ["solar_energy","agriculture","clean tech","environment","carbon"],
    "shop":       ["restaurant","retail","service","store","shop"],
    "coworking":  ["education","coworking","office","workspace","desk"],
    "accelerator":["finance","accelerator","startup","investor","incubator","yc"],
    "pitch":      ["finance","startup","investor","pitch","accelerator"],
    "angel":      ["finance","angel","investor","funding","seed"],
    "founder":    ["finance","startup","founder","accelerator","community"],
    "barber":     ["hair_beauty","barber","barbershop","haircut","grooming"],
    "nail":       ["hair_beauty","nails","manicure","pedicure","beauty"],
    "plumbing":   ["construction","plumbing","plumber","pipes","water","repair"],
    "wiring":     ["construction","electrical","electrician","wiring","power"],
    "dentist":    ["healthcare","dental","dentist","teeth","clinic"],
    "mental":     ["healthcare","mental health","therapy","counseling","wellness"],
    "grocery":    ["restaurant","grocery","supermarket","food","market"],
    "market":     ["agriculture","market","prices","commodity","grocery"],
    "wedding":    ["marketing","wedding","events","planner","venue","catering"],
    "event":      ["marketing","events","wedding","conference","venue","catering"],
    "moving":     ["logistics","moving","relocation","transport","courier"],
    "rent":       ["real_estate","rental","housing","apartment","property"],
    "apartment":  ["real_estate","apartment","housing","rental","accommodation"],

    # ── ENERGY ────────────────────────────────────────────────────
    "solar":      ["solar_energy","solar","renewable","off_grid","panels","battery"],
    "electricity":["solar_energy","electricity","power","umeme","kplc","tokens"],
    "power":      ["solar_energy","electricity","umeme","kplc","tokens","lighting"],

    # ── AGRICULTURE ───────────────────────────────────────────────
    "farming":    ["agriculture","farming","farm","crop","livestock","agro","seeds"],
    "agriculture":["agriculture","farming","farm","crop","livestock","seeds","agro"],
    "farmer":     ["agriculture","farming","crop","livestock","smallholder"],
    "maize":      ["agriculture","prices","commodity_trading","farming","crop"],

    # ── SERVICES ──────────────────────────────────────────────────
    "insurance":  ["insurance","cover","nhif","health_cover","motor_insurance"],
    "security":   ["security_services","security","guard","surveillance","alarm"],
    "cleaning":   ["cleaning_services","cleaning","laundry","hygiene","janitorial"],
    "water":      ["water_supply","water","borehole","sanitation","treatment",
                   "nwsc","water_bill","national water"],
    "government": ["government","official","tax","passport","registration","permits"],
    "printing":   ["digital_printing","print","banner","flyer","media"],
    "photo":      ["photography","photo","studio","video","events"],
    "media":      ["media_production","photography","video","radio","podcast","content"],

    # ── BEAUTY & PERSONAL ─────────────────────────────────────────
    "salon":      ["hair_beauty","salon","hair","nails","beauty","hairdresser"],
    "hair":       ["hair_beauty","salon","hairdresser","barber","braiding"],
    "beauty":     ["hair_beauty","salon","nails","makeup","spa","beauty"],
    "massage":    ["healthcare","massage","spa","wellness","physiotherapy"],
    "spa":        ["healthcare","spa","massage","wellness","beauty"],

    # ── AUTOMOTIVE ────────────────────────────────────────────────
    "mechanic":   ["mechanic","car_repair","garage","auto","vehicle","engine"],
    "car":        ["mechanic","car_hire","car_repair","vehicle","auto","transport"],
    "cars":       ["car_dealership","mechanic","car_hire","vehicle","auto","transport"],

    # ── CONSTRUCTION ──────────────────────────────────────────────
    "construction":["construction","building","renovation","plumbing","electrical","roofing"],
    "building":   ["construction","real_estate","architecture","renovation","contractor"],
    "plumber":    ["construction","plumbing","pipes","water","repair"],
    "electrician":["construction","electrical","wiring","power","install"],

    # ── EDUCATION ─────────────────────────────────────────────────
    "school":     ["education","school","tutoring","college","training","learning"],
    "university": ["education","university","college","higher_education","degree"],
    "tutor":      ["education","tutoring","school","learning","private","lessons"],
    "exam":       ["education","waec","jamb","kcse","uneb","results","certificate"],
    "waec":       ["education","waec","results","nigeria","certificate"],
    "jamb":       ["education","jamb","utme","nigeria","university","admission"],
    "kcse":       ["education","kcse","kenya","results","certificate"],

    # ── DIGITAL & AI ──────────────────────────────────────────────
    "coding":     ["coding","developer","software","programming","web","mobile","api"],
    "developer":  ["coding","developer","software","web","mobile","app"],
    "software":   ["coding","developer","software","programming","api"],
    "design":     ["design","graphic_design","logo","branding","creative","ui_ux"],
    "marketing":  ["marketing","social_media","seo","ads","content","branding"],
    "ai":         ["ai_assistant","chatbot","gpt","assistant","ai agent","llm"],
    "claude":     ["ai_assistant","assistant","chatbot","anthropic"],
    "chatgpt":    ["ai_assistant","assistant","chatbot","openai"],
    "gpt":        ["ai_assistant","assistant","openai","coding"],
    "llm":        ["ai_assistant","coding","assistant","language model"],
    "whatsapp":   ["ai_assistant","whatsapp","wa","whatsapp bot","whatsapp ai"],
    "bot":        ["ai_assistant","chatbot","whatsapp bot","automation"],
    "calendar":   ["ai_assistant","schedule","appointment","meeting","calendar"],

    # ── RECRUITMENT ───────────────────────────────────────────────
    "recruitment":["recruitment","hr","hiring","cv_writing","job_search","headhunting"],
    "job":        ["recruitment","cv_writing","job_search","employment","hiring"],
    "hiring":     ["recruitment","hr","hiring","talent","jobs"],

    # ── COMMUNITY ─────────────────────────────────────────────────
    "translation":["translation","swahili","french","amharic","luganda","interpreter"],
    "translate":  ["translation","interpreter","language","swahili","french","amharic"],
    "ngo":        ["ngo_compliance","ngo","charity","nonprofit","development","cbo"],
    "mining":     ["mining","minerals","gold","artisanal","quarry","extractives"],
    "sacco":      ["microfinance","sacco","savings","cooperative","vsla","loan"],
    "vet":        ["veterinary","vet","animal","livestock","pet","poultry"],
    "diaspora":   ["remittance","cargo","import_export","visa_consulting","diaspora"],
    "prices":     ["prices","market_prices","commodity_trading","agriculture","maize"],

    # ── AI-AGENT CATEGORIES (fixes topic search over the harvested index) ─
    "research":   ["coding","research","ai","papers","analysis","data"],
    "automation": ["coding","automation","workflow","ai","agent","integration"],
    "framework":  ["coding","framework","ai","agents","developer","sdk"],
    "mcp":        ["coding","mcp","tools","ai","developer","server"],
    "rag":        ["coding","rag","ai","retrieval","search","embeddings"],
    "data":       ["coding","data","analytics","ai","dashboard","science"],
    "analytics":  ["coding","analytics","data","ai","dashboard","insights"],
    "support":    ["coding","support","customer_service","chatbot","ai","helpdesk"],
    "writing":    ["marketing","writing","content","copy","ai","editor"],
    "write":      ["marketing","writing","content","copy","ai"],
    "sales":      ["marketing","sales","leads","outreach","crm","ai"],
    "content":    ["marketing","content","writing","social_media","ai","creative"],
    "seo":        ["marketing","seo","ads","content","search","ranking"],
    "image":      ["design","image","art","creative","generation","picture"],
    "art":        ["design","art","image","creative","illustration"],
    "logo":       ["design","logo","branding","graphic_design","creative"],
    "generation": ["design","image","video","ai","create","generate"],
    "avatar":     ["media_production","avatar","video","ai","face"],
    "video":      ["media_production","video","film","editing","creative","clips"],
    "audio":      ["media_production","audio","sound","music","voice","podcast"],
    "music":      ["media_production","music","audio","song","creative"],
    "voice":      ["media_production","voice","speech","tts","audio","clone"],
    "speech":     ["media_production","speech","voice","tts","transcription"],
    "podcast":    ["media_production","podcast","audio","voice","content"],
    "assistant":  ["ai_assistant","coding","assistant","chatbot","agent"],
    "pharmacy":   ["healthcare","pharmacy","medicine","drugs","chemist"],
    "clinic":     ["healthcare","clinic","hospital","medical","doctor"],
    "restaurant": ["restaurant","food","cafe","eatery","catering"],
    "garage":     ["mechanic","car_repair","auto","vehicle","service"],
}

LOCATION_WORDS = {
    "kampala","nairobi","lagos","accra","kigali","addis","dar","johannesburg",
    "london","dubai","toronto","paris","berlin","amsterdam","brussels","stockholm",
    "abuja","dakar","kinshasa","lusaka","harare","mombasa","arusha","entebbe",
    "jinja","gulu","mbale","lira","mbarara","kisumu","eldoret","nakuru",
    "guangzhou","yiwu","shenzhen","delhi","mumbai","singapore","doha","riyadh",
    "sydney","tokyo","seoul","istanbul","cairo","casablanca","new","york","dc",
    "africa","uganda","kenya","tanzania","nigeria","ghana","ethiopia","rwanda",
    "zambia","zimbabwe","southafrica","east","west","central","global","worldwide",
    "uk","usa","us","canada","china","india","uae","australia","germany","france",
    "tallinn","estonia","tartu","helsinki","riga","vilnius",
    "sf","sanfrancisco","oakland","sanjose","bayarea","mission","soma","tenderloin",
}

AI_SOURCES = {
    "mcp_awesome_mcp","mcp_glama","mcp_smithery","mcp_mcpso",
    "huggingface_v3","huggingface_v2","huggingface","replicate",
    "curated_ai","openai_gpt_store","poe","platform_agents","gap_auto",
}

def is_ai_agent(agent):
    return agent.get("source", "") in AI_SOURCES

# ── EMBEDDED SNAPSHOT — search survives database outages ─────────
# A curated registry of real, verified agents (official websites only)
# ships inside the repo. If the database is unreachable or thin, search
# falls back to / is supplemented by this snapshot. Zero-dependency
# resilience: the core product (search) can never fully die again.
SNAPSHOT_AGENTS = []
try:
    _snap_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "agents_snapshot.json")
    with open(_snap_path, "r", encoding="utf-8") as _f:
        SNAPSHOT_AGENTS = json.load(_f)
    for _i, _a in enumerate(SNAPSHOT_AGENTS):
        _a["id"] = -(_i + 1)          # negative ids — never collide with DB rows
    print(f"Snapshot loaded: {len(SNAPSHOT_AGENTS)} agents")
except Exception as _e:
    print(f"Snapshot not loaded: {_e}")

def get_skill_keywords(skill_words):
    expanded = set()
    for w in skill_words:
        expanded.add(w)
        if w in SKILL_SYNONYMS:
            expanded.update(SKILL_SYNONYMS[w])
    return expanded

def skill_matches(agent, skill_keywords):
    if not skill_keywords:
        return True
    skill     = (agent.get("skill_primary")  or "").lower()
    tags      = " ".join(str(t).lower() for t in (agent.get("skill_tags") or []))
    name      = (agent.get("name")           or "").lower().replace("_", " ").replace("-", " ")
    secondary = (agent.get("skill_secondary") or "").lower()
    haystack  = f"{skill} {tags} {name} {secondary}"
    return any(kw in haystack for kw in skill_keywords)

def location_score(agent, location_words):
    loc     = (agent.get("location")     or "").lower()
    country = (agent.get("country")      or "").lower()
    name    = (agent.get("name")         or "").lower()
    hood    = (agent.get("neighborhood") or "").lower()
    s = 0
    for w in location_words:
        if w in loc:     s += 25
        if w in country: s += 15
        if w in hood:    s += 20
        if w in name:    s += 10
    return s

def parse_query(words):
    skill_words = set()
    loc_words   = set()
    for w in words:
        if w in LOCATION_WORDS:
            loc_words.add(w)
        elif w in SKILL_SYNONYMS or any(w in vlist for vlist in SKILL_SYNONYMS.values()):
            skill_words.add(w)
        else:
            loc_words.add(w)
    return skill_words, loc_words

def search_agents(query, limit=3):
    words = [w.strip().lower() for w in query.split() if len(w.strip()) > 1]
    if not words:
        return []

    # Name search — exact name matches always surface first
    name_hits = []
    try:
        if not USE_DB:
            raise RuntimeError("git-native")
        name_pattern = "%".join([w for w in words if len(w) > 2])
        if name_pattern:
            name_hits = (
                sb.table("agents")
                .select("*")
                .ilike("name", f"%{name_pattern}%")
                .limit(10)
                .execute().data or []
            )
    except:
        name_hits = []

    skill_words, loc_words = parse_query(words)

    # AI-only mode: user typed "ai", "bot", or "agent". Strip those BEFORE
    # expanding keywords, so a query like "video ai" filters on "video" only
    # and generic AI agents (gpt/assistant/...) don't leak into the match set.
    ai_only = "ai" in words or "bot" in words or "agent" in words
    if ai_only:
        skill_words -= {"ai", "bot", "agent"}

    skill_kws = get_skill_keywords(skill_words)

    # Supabase-side filter (skipped when git-native / no DB key). Rank in Python.
    try:
        if not USE_DB:
            raise RuntimeError("git-native")
        if skill_words:
            primary_skill = None
            for sw in skill_words:
                if sw in SKILL_SYNONYMS:
                    candidates = SKILL_SYNONYMS[sw]
                    primary_skill = candidates[0] if candidates else sw
                    break
            if not primary_skill:
                primary_skill = list(skill_words)[0]

            agents = (
                sb.table("agents")
                .select("*")
                .eq("skill_primary", primary_skill)
                .limit(500)
                .execute().data or []
            )
            # Fallback: also check skill_tags
            if len(agents) < 10:
                extra = (
                    sb.table("agents")
                    .select("*")
                    .contains("skill_tags", [primary_skill])
                    .limit(200)
                    .execute().data or []
                )
                seen_ids = {a["id"] for a in agents}
                agents += [a for a in extra if a["id"] not in seen_ids]
        else:
            # No skill words — general/location search
            agents = (
                sb.table("agents")
                .select("*")
                .order("reputation_score", desc=True)
                .limit(200)
                .execute().data or []
            )
    except:
        agents = []

    # Snapshot merge — DB rows win (live reputation), snapshot fills the
    # gaps, and fully carries search when the database is unreachable.
    if SNAPSHOT_AGENTS:
        have = {a.get("slug") for a in agents}
        agents = agents + [a for a in SNAPSHOT_AGENTS if a.get("slug") not in have]

    results = []
    for agent in agents:
        if ai_only and not is_ai_agent(agent):
            continue
        if skill_words and not skill_matches(agent, skill_kws):
            continue
        rep   = compute_reputation(agent)
        loc   = location_score(agent, loc_words)
        # Relevance: reward agents that literally carry the user's specific
        # term(s) in name/tags, so real "research"/"video" tools outrank a
        # generic high-reputation agent that only matches on "coding"/"ai".
        hay = (
            (agent.get("skill_primary") or "") + " "
            + " ".join(str(t) for t in (agent.get("skill_tags") or [])) + " "
            + (agent.get("name") or "")
        ).lower().replace("_", " ").replace("-", " ")
        relevance = sum(18 for w in skill_words if w in hay)
        total = rep + loc + relevance
        results.append((total, agent))

    # Name matches get a +40 boost
    name_ids     = {a["id"] for a in name_hits}
    name_scored  = [(compute_reputation(a) + location_score(a, loc_words) + 40, a) for a in name_hits]
    skill_scored = [(s, a) for s, a in results if a["id"] not in name_ids]
    all_results  = name_scored + skill_scored
    all_results.sort(key=lambda x: x[0], reverse=True)
    found = [a for _, a in all_results[:limit]]

    # Gap detection — 3 searches with no result → auto-create a placeholder
    if not found and len(words) >= 1:
        gap_key = " ".join(sorted(words[:2]))
        gap_log[gap_key] = gap_log.get(gap_key, 0) + 1
        if gap_log[gap_key] >= 3:
            threading.Thread(
                target=seed_gap_wanderer, args=(query, words), daemon=True
            ).start()

    return found

def seed_gap_wanderer(query, words):
    """3 searches with no result → auto-create a placeholder. Waze model."""
    try:
        skill_words, loc_words = parse_query(words)
        skill = list(skill_words)[0] if skill_words else words[0]
        loc   = list(loc_words)[0]   if loc_words   else "global"
        name  = f"{skill.title()}_{loc.title()}_AUTO"
        slug  = name.lower().replace("_", "-").replace(" ", "-")
        existing = sb.table("agents").select("slug").eq("slug", slug).execute()
        if existing.data:
            return
        sb.table("agents").insert({
            "name": name, "slug": slug, "tier": 0,
            "skill_primary": skill,
            "skill_tags":    [skill, loc],
            "location":      loc.lower(), "country": "unknown",
            "languages":     ["english"], "claimed": False,
            "source":        "gap_auto", "reputation_score": 0.0,
        }).execute()
        print(f"GAP: seeded {name}")
    except Exception as e:
        print(f"Gap seed error: {e}")


# ── FORMAT ────────────────────────────────────────────────────────
TIER_BADGE = {0: "🌀", 1: "✅", 2: "⭐", 3: "🔥"}
TIER_NAME  = {0: "Wanderer", 1: "Verified", 2: "Pro", 3: "Elite"}

def format_contact(agent):
    """Show the best available contact. WhatsApp first, then website."""
    wa      = agent.get("whatsapp")      or ""
    phone   = agent.get("phone")         or ""
    website = agent.get("website")       or ""
    contact = agent.get("contact_link")  or ""
    source  = agent.get("source")        or ""

    # AI agents — show their link with robot icon
    if source in AI_SOURCES:
        link = website or contact
        if link:
            display = link[:55] + "..." if len(link) > 55 else link
            return f"   🤖 {display}"
        return "   🤖 Virtual Agent"

    # Real WhatsApp link
    if wa and "wa.me" in wa:
        return f"   💬 {wa}"

    # Phone number → convert to WhatsApp link
    if phone:
        digits = "".join(filter(str.isdigit, str(phone)))
        if len(digits) > 7:
            return f"   💬 https://wa.me/{digits}"

    # Website — real contact but no WhatsApp
    if website:
        display = website[:55] + "..." if len(website) > 55 else website
        return f"   🌐 {display}"

    # Contact link
    if contact:
        for part in contact.split():
            p = part.strip()
            if "wa.me" in p or "t.me" in p:
                return f"   📞 {p}"
        return f"   📞 {contact[:55]}"

    slug = agent.get("slug", "")
    return f"   ℹ️  Unclaimed · reply: CLAIM {slug}"

def format_results(results, query):
    if not results:
        return (
            f"Nothing found for '{query}'.\n\n"
            "Try:\n"
            "• Different words — 'lawyer' not 'legal advisor'\n"
            "• Broader search — skip the city\n"
            "• Nearby city\n\n"
            "2 — Add your service free"
        )

    lines = [f"🔍 {query.title()}\n"]
    for i, agent in enumerate(results, 1):
        tier    = int(agent.get("tier") or 0)
        name    = (agent.get("name") or "").replace("_", " ").replace("-", " ").title()
        loc     = (agent.get("location") or "").title()
        country = (agent.get("country")  or "").title()
        hood    = (agent.get("neighborhood") or "").title()
        rep     = int(compute_reputation(agent))
        hours   = agent.get("opening_hours") or ""
        g_rating= agent.get("google_rating")
        badges  = agent.get("badges") or []

        if hood:
            loc_str = hood
        elif loc and country and country not in ("Unknown", "Global"):
            loc_str = f"{loc}, {country}"
        else:
            loc_str = loc or country or "Global"

        lines.append(f"{i}. {TIER_BADGE.get(tier, '🌀')} {name}")
        lines.append(f"   {TIER_NAME.get(tier, 'Agent')} · {loc_str}")
        lines.append(f"   ⭐ {rep} rep" + (f"  · Google ★{g_rating}" if g_rating else ""))
        if hours:
            lines.append(f"   🕐 {hours[:45]}")
        if badges:
            lines.append(f"   🏅 {' · '.join(badges[:2])}")
        lines.append(format_contact(agent))
        lines.append("")

    lines.append("─────────────────")
    lines.append("1 — Search again")
    lines.append("2 — Add your service free")
    lines.append("RATE 1-5 — rate your top match after you connect")
    return "\n".join(lines)


# ── MENUS ─────────────────────────────────────────────────────────
def main_menu():
    return (
        "🌐 Godena\n"
        "The open agent network.\n\n"
        "1 — Find an agent or service\n"
        "2 — Add your agent free\n\n"
        "Or just type what you need:\n"
        "  lawyer kampala\n"
        "  visa london\n"
        "  logistics nairobi\n"
        "  china sourcing\n"
        "  hotel kigali"
    )

def search_prompt():
    return (
        "🔍 What are you looking for?\n\n"
        "Type skill + city:\n"
        "  lawyer kampala\n"
        "  tax nairobi\n"
        "  visa london\n"
        "  hotel addis\n"
        "  logistics lagos\n"
        "  china sourcing\n"
        "  scholarship canada\n\n"
        "Just type — Godena finds it."
    )

def build_menu():
    return (
        "➕ Add your agent to Godena\n\n"
        "What type are you?\n\n"
        "1 — 👑 Boss  (you answer personally)\n"
        "2 — ⚡ Semi  (auto FAQ, you close deals)\n"
        "3 — 🤖 Agent (fully automated AI)"
    )


# ── GREETINGS — 20+ languages ─────────────────────────────────────
GREETINGS = {
    "hello","hi","hey","hii","sup","yo","start","/start","menu","home",
    "back","help","?","godena","g",
    # Swahili
    "habari","sasa","mambo","niaje","jambo","karibu","salama","hujambo","sijambo",
    # Amharic
    "selam","salam","tenayistilign",
    # French
    "bonjour","salut","bonsoir","allô","coucou",
    # Arabic
    "marhaba","ahlan","السلام","مرحبا",
    # Hausa
    "sannu","ina kwana","barka",
    # Yoruba
    "bawo","e kaaro","e kaabo",
    # Igbo
    "nnoo","kedu",
    # Portuguese
    "olá","oi","bom dia","boa tarde","boa noite",
    # Zulu
    "sawubona","yebo",
    # Kinyarwanda
    "muraho","mwaramutse","mwiriwe",
    # Somali
    "iska waran","nabad",
    # Hindi
    "namaste","namaskar",
    # Chinese
    "你好","您好","嗨",
    # German
    "hallo","guten tag",
    # General
    "test","ping","hi there","good morning","good afternoon","good evening","hey there",
}


# ── REGISTRATION FLOW ─────────────────────────────────────────────
TIER_MAP = {"1": (1, "Boss 👑"), "2": (2, "Semi ⚡"), "3": (3, "Agent 🤖")}

def registration_step(state, text):
    step = state.get("step", "tier")
    t    = text.strip()

    if step == "tier":
        if t not in TIER_MAP:
            return build_menu(), False
        num, name = TIER_MAP[t]
        state.update({"step": "name", "tier": num, "tier_name": name})
        return (
            "Name your agent:\n\n"
            "No spaces — use underscore:\n"
            "Grace_Legal_Nairobi\n"
            "Toyota_Dealer_Kampala\n"
            "Tax_Pro_Lagos"
        ), False

    if step == "name":
        state["name"] = t.replace(" ", "_")[:60]
        state["slug"] = state["name"].lower().replace("_", "-")
        state["step"] = "skill"
        return (
            "Main skill or service?\n\n"
            "legal · tax · cars · logistics\n"
            "coding · design · beauty · food\n"
            "import · healthcare · education\n"
            "hotel · mining · farming · solar"
        ), False

    if step == "skill":
        state["skill"] = t.lower()
        state["step"]  = "location"
        return "Which city?", False

    if step == "location":
        state["location"] = t.lower()
        state["step"]     = "country"
        return "Which country?", False

    if step == "country":
        state["country"] = t.lower()
        state["step"]    = "contact"
        return (
            "Your contact?\n\n"
            "wa.me/+256712345678\n"
            "t.me/yourusername\n"
            "+256712345678\n\n"
            "Type SKIP to leave blank"
        ), False

    if step == "contact":
        state["contact"] = None if t.upper() == "SKIP" else t
        state["step"]    = "confirm"
        return (
            f"Confirm:\n\n"
            f"Name:    {state['name']}\n"
            f"Type:    {state['tier_name']}\n"
            f"Skill:   {state['skill']}\n"
            f"City:    {state['location'].title()}, {state['country'].title()}\n"
            f"Contact: {state.get('contact') or 'Not set'}\n\n"
            f"YES to go live · NO to cancel"
        ), False

    if step == "confirm":
        if t.upper() == "YES":
            try:
                sb.table("agents").insert({
                    "name":          state["name"],
                    "slug":          state["slug"],
                    "tier":          state["tier"],
                    "skill_primary": state["skill"],
                    "skill_tags":    [state["skill"], state["location"], state["country"]],
                    "location":      state["location"],
                    "country":       state["country"],
                    "contact_link":  state.get("contact"),
                    "languages":     ["english"],
                    "claimed":       True,
                    "source":        state.get("source", "whatsapp"),
                    "reputation_score": 10.0,
                }).execute()
                return (
                    f"✅ {state['name']} is live on Godena!\n\n"
                    f"People searching {state['skill']} in "
                    f"{state['location'].title()} will find you.\n\n"
                    + main_menu()
                ), True
            except Exception as e:
                msg = (
                    "Name taken — try a different name."
                    if "duplicate" in str(e).lower()
                    else f"Error: {e}"
                )
                return msg, True
        return "Cancelled.\n\n" + main_menu(), True

    return main_menu(), True


# ── RATING FLYWHEEL ───────────────────────────────────────────────
# Search → connect → RATE → reputation moves → better ranking.
# Without this loop the reputation engine only ever sees seed points.
last_results = {}   # uid -> [slugs shown in their most recent search]

def record_rating(uid, rating, slug):
    """Running-average rating update, same math as /api/rate. Fail-safe."""
    try:
        if is_burst_rating(uid):
            return "⏳ Too many ratings too fast — try again in a few minutes."
        res = sb.table("agents").select(
            "name,avg_rating,interactions_count"
        ).eq("slug", slug).execute()
        if not res.data:
            return "Couldn't find that agent — search again and then RATE 1-5."
        agent   = res.data[0]
        cur_avg = float(agent.get("avg_rating") or 0)
        cur_n   = int(agent.get("interactions_count") or 0)
        new_avg = round((cur_avg * cur_n + rating) / (cur_n + 1), 2) if cur_n > 0 else float(rating)
        sb.table("agents").update({
            "avg_rating":         new_avg,
            "interactions_count": cur_n + 1,
        }).eq("slug", slug).execute()
        name = (agent.get("name") or slug).replace("_", " ")
        return (
            f"⭐ Thanks — {rating}/5 recorded for {name}.\n"
            f"Ratings decide who ranks first on Godena.\n\n"
            "1 — Search again"
        )
    except Exception as e:
        print(f"rate error: {e}")
        return "Couldn't save that rating right now — please try again later."

def handle_rating_reply(uid, tl):
    """Parses 'rate 5' (rates top result of user's last search) or 'rate <slug> 4'."""
    parts = tl.split()
    slugs = last_results.get(uid) or []
    if len(parts) == 2 and parts[1].isdigit():
        rating = int(parts[1])
        if not 1 <= rating <= 5:
            return "Rate from 1 to 5 — e.g. RATE 5"
        if not slugs:
            return "Search first, then reply RATE 1-5 to rate your top match."
        return record_rating(uid, rating, slugs[0])
    if len(parts) == 3 and parts[2].isdigit():
        rating = int(parts[2])
        if not 1 <= rating <= 5:
            return "Rate from 1 to 5 — e.g. RATE emmas-cars 5"
        return record_rating(uid, rating, parts[1])
    return "To rate: RATE 5  (your top match)\nor: RATE agent-name 4"


# ── CORE HANDLER ──────────────────────────────────────────────────
def handle(state_d, ctx_d, uid, text, source):
    t  = text.strip()
    tl = t.lower().strip()

    # Active registration flow takes priority
    if uid in state_d:
        reply, done = registration_step(state_d[uid], t)
        if done:
            del state_d[uid]
            ctx_d[uid] = "menu"
        return reply

    # Greetings → main menu
    if tl in GREETINGS:
        ctx_d[uid] = "menu"
        return main_menu()

    # 1 → search
    if tl in ("1", "find", "search", "tafuta", "chercher", "buscar", "search again"):
        ctx_d[uid] = "searching"
        return search_prompt()

    # 2 → register
    if tl in ("2", "add", "build", "register", "list", "ongeza", "ajouter"):
        state_d[uid] = {"step": "tier", "source": source}
        ctx_d[uid]   = "building"
        return build_menu()

    # Easter egg — the first agent
    if "emma" in tl:
        return "🏆 Emmas_cars · Kampala\nFirst Godena agent · March 11 2026\n💬 wa.me/256741994463"

    # Claim shortcut
    if tl.startswith("claim "):
        slug = tl.replace("claim ", "").strip()
        return f"Claim '{slug}':\nContact t.me/godenabot\n\nOr reply 2 to register your own agent."

    # Rating reply — closes the trust loop
    if tl.startswith("rate"):
        return handle_rating_reply(uid, tl)

    # Everything else → search
    ctx_d[uid] = "searching"
    results = search_agents(t)
    if results:
        last_results[uid] = [a.get("slug") for a in results if a.get("slug")]
    return format_results(results, t)


# ── WHATSAPP SENDER ───────────────────────────────────────────────
def wa_send(phone, text):
    url = f"https://api.green-api.com/waInstance{GREEN_INSTANCE_ID}/sendMessage/{GREEN_TOKEN}"
    try:
        httpx.post(
            url,
            json={"chatId": f"{normalize(phone)}@c.us", "message": text},
            timeout=15,
        )
    except Exception as e:
        print(f"WA send error: {e}")

@app.post("/webhook")
async def wa_webhook(request: Request):
    data = await request.json()
    try:
        if data.get("typeWebhook") != "incomingMessageReceived":
            return {"status": "ok"}
        msg_data = data.get("messageData", {})
        if msg_data.get("typeMessage") != "textMessage":
            return {"status": "ok"}
        mid = data.get("idMessage", "")
        if already_seen(mid):
            return {"status": "ok"}
        phone = normalize(data["senderData"]["sender"])
        text  = msg_data["textMessageData"]["textMessage"]
        print(f"WA [{phone}]: {text}")
        wa_send(phone, handle(wa_state, wa_context, phone, text, "whatsapp"))
    except Exception as e:
        print(f"WA error: {e}")
    return {"status": "ok"}


# ── TELEGRAM SENDER ───────────────────────────────────────────────
def tg_send(chat_id, text):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        httpx.post(url, json={"chat_id": chat_id, "text": text}, timeout=15)
    except Exception as e:
        print(f"TG send error: {e}")

@app.post("/telegram")
async def tg_webhook(request: Request):
    data = await request.json()
    try:
        msg     = data.get("message", {})
        chat_id = msg.get("chat", {}).get("id")
        text    = msg.get("text", "")
        if chat_id and text:
            print(f"TG [{chat_id}]: {text}")
            tg_send(chat_id, handle(tg_state, tg_context, str(chat_id), text, "telegram"))
    except Exception as e:
        print(f"TG error: {e}")
    return {"status": "ok"}


# ── PUBLIC API ────────────────────────────────────────────────────
@app.get("/api/search")
async def api_search(q: str, limit: int = 5):
    results = search_agents(q, limit)
    return {
        "query":  q,
        "count":  len(results),
        "agents": [{**a, "computed_reputation": compute_reputation(a)} for a in results],
    }

@app.post("/api/register")
async def api_register(request: Request):
    """Any platform, any developer, any AI agent registers here. Free forever."""
    data = await request.json()
    try:
        name  = data.get("name", "").replace(" ", "_")[:60]
        skill = data.get("skill", "").lower()
        if not name or not skill:
            return {"error": "name and skill required"}
        slug = name.lower().replace("_", "-")
        sb.table("agents").insert({
            "name":          name,
            "slug":          slug,
            "tier":          int(data.get("tier", 0)),
            "skill_primary": skill,
            "skill_tags":    [skill, data.get("location", ""), data.get("country", "")],
            "location":      data.get("location", "").lower(),
            "country":       data.get("country", "").lower(),
            "contact_link":  data.get("contact")  or None,
            "phone":         data.get("phone")     or None,
            "whatsapp":      data.get("whatsapp")  or None,
            "website":       data.get("website")   or None,
            "languages":     data.get("languages", ["english"]),
            "claimed":       True,
            "source":        data.get("source", "api"),
            "reputation_score": 10.0,
            "google_rating":       data.get("google_rating")       or None,
            "google_review_count": data.get("google_review_count") or None,
            "neighborhood":        data.get("neighborhood")        or None,
            "service_radius":      data.get("service_radius")      or None,
        }).execute() # Optional federation — share to main Godena if fork opts in
        federate_to = data.get("federate_to")
        if federate_to:
            try:
                httpx.post(f"{federate_to}/api/register", json=data, timeout=5)
            except:
                pass
        return {
            "status": "live",
            "name": name,
            "slug": slug,
            "profile": f"https://sammygh-godena.hf.space/api/agent/{slug}",
            "search": f"https://sammyghe.github.io/Godena/?q={skill}",
            # Viral loop: paste this badge on your site/README — agents recruit agents
            "badge_markdown": f"[![Found on Godena](https://img.shields.io/badge/Found_on-Godena-1d9e75)](https://sammyghe.github.io/Godena/)",
            "findable_on": WHATSAPP_NUMBER,
        }
    except Exception as e:
        return {"error": "name exists" if "duplicate" in str(e).lower() else str(e)}

@app.post("/api/claim")
async def api_claim(request: Request):
    """Real business claims its wanderer profile."""
    data = await request.json()
    try:
        slug = data.get("slug", "").lower()
        if not slug:
            return {"error": "slug required"}
        sb.table("agents").update({
            "claimed":      True,
            "tier":         int(data.get("tier", 1)),
            "phone":        data.get("phone")   or None,
            "whatsapp":     data.get("whatsapp") or None,
            "contact_link": data.get("contact") or None,
            "source":       "claimed",
        }).eq("slug", slug).execute()
        return {"status": "claimed", "slug": slug}
    except Exception as e:
        return {"error": str(e)}

@app.post("/api/rate")
async def api_rate(request: Request):
    """Human rates an agent. Anti-gaming applied."""
    data = await request.json()
    try:
        slug        = data.get("slug", "")
        rating      = float(data.get("rating", 5))
        rater_phone = data.get("rater_phone", "unknown")
        if not slug:
            return {"error": "slug required"}
        if is_burst_rating(rater_phone):
            return {"error": "too many ratings too fast", "status": "flagged"}
        result = sb.table("agents").select(
            "reputation_score,avg_rating,interactions_count"
        ).eq("slug", slug).execute()
        if not result.data:
            return {"error": "agent not found"}
        agent       = result.data[0]
        current_avg = float(agent.get("avg_rating")        or 0)
        current_n   = int(agent.get("interactions_count")  or 0)
        new_avg     = round(
            (current_avg * current_n + rating) / (current_n + 1), 2
        ) if current_n > 0 else rating
        sb.table("agents").update({
            "avg_rating":         new_avg,
            "interactions_count": current_n + 1,
        }).eq("slug", slug).execute()
        return {"status": "rated", "new_avg_rating": new_avg}
    except Exception as e:
        return {"error": str(e)}

@app.post("/api/rate/sub")
async def api_rate_sub(request: Request):
    """Granular sub-ratings: speed, accuracy, price, communication, reliability."""
    data = await request.json()
    try:
        slug = data.get("slug", "")
        if not slug:
            return {"error": "slug required"}
        if is_burst_rating(data.get("rater_phone", "unknown")):
            return {"error": "rate limit", "status": "flagged"}
        update = {}
        for field in ["rating_speed", "rating_accuracy", "rating_price",
                      "rating_communication", "rating_reliability"]:
            val = data.get(field)
            if val is not None:
                curr = sb.table("agents").select(
                    field + ",interactions_count"
                ).eq("slug", slug).execute()
                if curr.data:
                    old_v = float(curr.data[0].get(field) or 0)
                    n     = int(curr.data[0].get("interactions_count") or 1)
                    new_v = round((old_v * (n - 1) + float(val)) / n, 2)
                    update[field] = new_v
        if update:
            sb.table("agents").update(update).eq("slug", slug).execute()
            return {"status": "rated", "updated": list(update.keys())}
        return {"error": "no valid sub-rating fields provided"}
    except Exception as e:
        return {"error": str(e)}

@app.post("/api/rate/google")
async def api_rate_google(request: Request):
    """Ingest Google Places rating. Cross-validated against identity signals."""
    data = await request.json()
    try:
        slug   = data.get("slug", "")
        rating = float(data.get("google_rating", 0))
        count  = int(data.get("google_review_count", 0))
        if not slug:
            return {"error": "slug required"}
        sb.table("agents").update({
            "google_rating":       rating,
            "google_review_count": count,
        }).eq("slug", slug).execute()
        return {"status": "updated", "google_rating": rating, "count": count}
    except Exception as e:
        return {"error": str(e)}

@app.post("/api/recommend")
async def api_recommend(request: Request):
    """Agent A recommends Agent B. Builds trust graph."""
    data      = await request.json()
    from_slug = data.get("from_slug")
    to_slug   = data.get("to_slug")
    result    = sb.table("agents").select(
        "recommended_agents,recommendation_count"
    ).eq("slug", to_slug).execute()
    if not result.data:
        return {"error": "agent not found"}
    recs = result.data[0].get("recommended_agents") or []
    if from_slug not in recs:
        recs.append(from_slug)
    sb.table("agents").update({
        "recommended_agents":   recs,
        "recommendation_count": len(recs),
    }).eq("slug", to_slug).execute()
    return {"status": "ok"}

@app.post("/api/endorse")
async def api_endorse(request: Request):
    """Agent-to-agent specialty endorsement. Weighted by endorser reputation."""
    data = await request.json()
    try:
        target_slug   = data.get("target_slug",   "")
        endorser_slug = data.get("endorser_slug", "")
        specialty     = data.get("specialty",     "")
        if not all([target_slug, endorser_slug, specialty]):
            return {"error": "target_slug, endorser_slug, specialty all required"}
        endorser     = sb.table("agents").select("*").eq("slug", endorser_slug).execute()
        endorser_rep = compute_reputation(endorser.data[0]) if endorser.data else 10
        weight       = round(min(endorser_rep / 50, 2.0), 2)
        target       = sb.table("agents").select(
            "specialty_endorsements,endorsement_weight,agent_tags_received"
        ).eq("slug", target_slug).execute()
        if not target.data:
            return {"error": "target agent not found"}
        sb.table("agents").update({
            "specialty_endorsements": int(target.data[0].get("specialty_endorsements") or 0) + 1,
            "endorsement_weight":     weight,
            "agent_tags_received":    int(target.data[0].get("agent_tags_received")    or 0) + 1,
        }).eq("slug", target_slug).execute()
        return {"status": "endorsed", "specialty": specialty, "endorser_weight": weight}
    except Exception as e:
        return {"error": str(e)}

@app.post("/api/complete")
async def api_complete_job(request: Request):
    """Mark a job completed. Updates jobs_completed and recent_jobs_30d."""
    data = await request.json()
    try:
        slug = data.get("slug", "")
        if not slug:
            return {"error": "slug required"}
        result = sb.table("agents").select(
            "jobs_completed,recent_jobs_30d,interactions_count"
        ).eq("slug", slug).execute()
        if not result.data:
            return {"error": "not found"}
        a = result.data[0]
        sb.table("agents").update({
            "jobs_completed":     int(a.get("jobs_completed")    or 0) + 1,
            "recent_jobs_30d":    int(a.get("recent_jobs_30d")   or 0) + 1,
            "interactions_count": int(a.get("interactions_count") or 0) + 1,
        }).eq("slug", slug).execute()
        return {"status": "completed", "jobs_completed": int(a.get("jobs_completed") or 0) + 1}
    except Exception as e:
        return {"error": str(e)}

@app.get("/api/agent/{slug}")
async def api_get_agent(slug: str):
    try:
        result = sb.table("agents").select("*").eq("slug", slug).execute()
        if not result.data:
            return {"error": "not found"}
        a = result.data[0]
        a["computed_reputation"] = compute_reputation(a)
        a["badges"]              = compute_badges(a)
        return a
    except Exception as e:
        return {"error": str(e)}

@app.get("/api/gaps")
async def api_gaps(limit: int = 20):
    """See what people searched that returned nothing. The demand map."""
    sorted_gaps = sorted(gap_log.items(), key=lambda x: x[1], reverse=True)
    return {"gaps": [{"query": q, "searches": n} for q, n in sorted_gaps[:limit]]}


# ── BACKGROUND UPDATER ────────────────────────────────────────────
def background_updater():
    """Runs every hour. Updates badges, cleans stale state."""
    while True:
        time.sleep(3600)
        try:
            print("Hourly update running...")
            agents  = sb.table("agents").select("*").limit(2000).execute().data or []
            updated = 0
            for a in agents:
                new_badges = compute_badges(a)
                old_badges = a.get("badges") or []
                if set(new_badges) != set(old_badges):
                    sb.table("agents").update(
                        {"badges": new_badges}
                    ).eq("id", a["id"]).execute()
                    updated += 1
            print(f"Hourly update: {updated} badge updates")
        except Exception as e:
            print(f"Hourly update error: {e}")


# ── HEALTH ────────────────────────────────────────────────────────
@app.get("/")
@app.get("/health")
async def health():
    return {
        "status":   "Godena is live",
        "founders": ["Samuel Gedamua", "Amanuel Asmerom"],
        "search":   "/api/search?q=lawyer+kampala",
        "register": "POST /api/register",
        "claim":    "POST /api/claim",
        "rate":     "POST /api/rate",
        "endorse":  "POST /api/endorse",
        "complete": "POST /api/complete",
        "gaps":     "GET /api/gaps",
        "whatsapp": WHATSAPP_NUMBER,
        "telegram": "@GodenaBot",
        "website":  "https://sammyghe.github.io/Godena/",
        "github":   "github.com/sammyghe/Godena",
        "built":    "March 2026 — The open agent network",
        "registry": "open — git-native index (no external database)",
        "agents":   len(SNAPSHOT_AGENTS),
    }

@app.get("/api/stats")
async def api_stats():
    """Public stats — the registry is the open index shipped in the repo."""
    return {
        "agents": len(SNAPSHOT_AGENTS),
        "registry": "git-native",
        "source": "https://github.com/sammyghe/Godena/blob/main/data/agents_snapshot.json",
    }

# ── AGENT INTEROP — Godena is itself a discoverable agent ─────────
# A2A-style agent card + llms.txt so other AI agents and assistants can
# find and use Godena programmatically. The search engine for agents
# must be discoverable BY agents.
AGENT_CARD = {
    "name": "Godena",
    "description": (
        "Open search engine for AI agents and real-world services. "
        "Query a need in plain words (e.g. 'lawyer kampala', 'ai coding') "
        "and get the top matches ranked by earned reputation, with a real "
        "contact link. Free, open source (MIT), no commission."
    ),
    "url": "https://sammygh-godena.hf.space",
    "provider": {"organization": "Godena", "url": "https://sammyghe.github.io/Godena/"},
    "version": "1.0.0",
    "capabilities": {"streaming": False, "pushNotifications": False},
    "defaultInputModes": ["text"],
    "defaultOutputModes": ["text", "application/json"],
    "skills": [
        {
            "id": "search_agents",
            "name": "Search agents & services",
            "description": "Skill + location search over AI agents and human services, ranked by reputation.",
            "examples": ["lawyer kampala", "ai coding", "flights nairobi", "china sourcing"],
            "inputModes": ["text"],
            "outputModes": ["application/json"],
        },
        {
            "id": "register_agent",
            "name": "Register an agent",
            "description": "Any agent (AI or human business) registers free via POST /api/register.",
            "inputModes": ["application/json"],
            "outputModes": ["application/json"],
        },
    ],
    "interfaces": {
        "search":   "GET /api/search?q={query}&limit={n}",
        "agent":    "GET /api/agent/{slug}",
        "register": "POST /api/register",
        "rate":     "POST /api/rate",
        "stats":    "GET /api/stats",
    },
}

@app.get("/.well-known/agent-card.json")
@app.get("/.well-known/agent.json")
async def agent_card():
    return AGENT_CARD

@app.get("/llms.txt")
async def llms_txt():
    from fastapi.responses import PlainTextResponse
    return PlainTextResponse(
        "# Godena — the open agent network\n\n"
        "> Search engine for AI agents and real-world services, ranked by earned reputation.\n\n"
        "## API (free, no key)\n"
        "- Search: GET https://sammygh-godena.hf.space/api/search?q=lawyer+kampala&limit=3\n"
        "- Agent detail: GET https://sammygh-godena.hf.space/api/agent/{slug}\n"
        "- Register (free forever): POST https://sammygh-godena.hf.space/api/register "
        "{name, skill, location, country, website|whatsapp|phone}\n"
        "- Rate after a connection: POST https://sammygh-godena.hf.space/api/rate {slug, rating, rater_phone}\n"
        "- Stats: GET https://sammygh-godena.hf.space/api/stats\n"
        "- Agent card: GET https://sammygh-godena.hf.space/.well-known/agent-card.json\n\n"
        "## Docs\n"
        "- Website: https://sammyghe.github.io/Godena/\n"
        "- Source (MIT): https://github.com/sammyghe/Godena\n"
        "- Vision: https://github.com/sammyghe/Godena/blob/main/docs/VISION.md\n\n"
        "Rules: results include only real, verifiable contacts. Never fabricate agents or ratings.\n"
    )

@app.on_event("startup")
async def startup():
    print("=" * 55)
    print("GODENA — The Open Agent Network")
    print("Founders: Samuel Gedamua + Amanuel Asmerom")
    print("WhatsApp + Telegram + Public API")
    print("Co-built with Claude (Anthropic)")
    print("=" * 55)
    t = threading.Thread(target=background_updater, daemon=True)
    t.start()
    print("Background updater started — hourly badge refresh")
# GODENA — /api/signal endpoint
# Paste this into app.py BEFORE the if __name__ == "__main__": line
# This is the flywheel. AI agents rate other AI agents after tasks.
# No humans needed. Reputation becomes self-improving.

"""
@app.post("/api/signal")
async def api_signal(request: Request):
    \"\"\"
    THE FLYWHEEL ENDPOINT.
    Any AI agent, app, or system calls this after using a Godena agent.
    No human needed. Reputation self-improves from real usage.
    
    Usage example (any app, any language):
    POST /api/signal
    {
        "slug": "sendy-africa-logistics",
        "outcome": "success",           // success | partial | failed
        "quality_score": 4.2,           // 1.0-5.0
        "latency_ms": 1200,             // how fast they responded
        "task_type": "delivery",        // what the task was
        "caller_slug": "my-app-agent",  // who is calling (optional)
        "caller_verified": true         // is caller trusted source
    }
    
    Signals from verified callers weight more.
    Burst signals from same caller are rate-limited.
    Bad actors get auto-flagged after 10 bad signals.
    \"\"\"
    data = await request.json()
    try:
        slug          = data.get("slug","")
        outcome       = data.get("outcome","success")  # success/partial/failed
        quality       = float(data.get("quality_score", 3.0))
        latency_ms    = int(data.get("latency_ms", 0))
        task_type     = data.get("task_type","")
        caller_slug   = data.get("caller_slug","")
        caller_verified = bool(data.get("caller_verified", False))

        if not slug:
            return {"error": "slug required"}

        # Clamp quality to valid range
        quality = max(1.0, min(5.0, quality))

        # Get current agent state
        result = sb.table("agents").select(
            "id,reputation_score,interactions_count,jobs_completed,"
            "recent_jobs_30d,abandoned_jobs,flags,avg_rating,"
            "signal_count,success_rate"
        ).eq("slug", slug).execute()

        if not result.data:
            return {"error": "agent not found"}

        a = result.data[0]

        current_rep    = float(a.get("reputation_score") or 0)
        interactions   = int(a.get("interactions_count") or 0)
        jobs           = int(a.get("jobs_completed") or 0)
        recent         = int(a.get("recent_jobs_30d") or 0)
        abandoned      = int(a.get("abandoned_jobs") or 0)
        flags          = int(a.get("flags") or 0)
        avg_r          = float(a.get("avg_rating") or 0)
        signal_count   = int(a.get("signal_count") or 0)
        success_rate   = float(a.get("success_rate") or 0)

        update = {}

        # ── OUTCOME PROCESSING ─────────────────────────────────
        if outcome == "success":
            update["jobs_completed"]   = jobs + 1
            update["recent_jobs_30d"]  = recent + 1
            update["interactions_count"] = interactions + 1
            # Running success rate
            new_success = round((success_rate * signal_count + 1.0) / (signal_count + 1), 3)
            update["success_rate"] = new_success

        elif outcome == "partial":
            update["interactions_count"] = interactions + 1
            new_success = round((success_rate * signal_count + 0.5) / (signal_count + 1), 3)
            update["success_rate"] = new_success

        elif outcome == "failed":
            update["abandoned_jobs"] = abandoned + 1
            update["interactions_count"] = interactions + 1
            new_success = round((success_rate * signal_count + 0.0) / (signal_count + 1), 3)
            update["success_rate"] = new_success
            # Auto-flag if too many failures from verified callers
            if caller_verified and abandoned + 1 >= 5:
                update["flags"] = flags + 1

        # ── QUALITY SCORE UPDATE ───────────────────────────────
        # Running weighted average — recent signals weight slightly more
        if avg_r > 0:
            # Caller trust multiplier
            caller_weight = 1.5 if caller_verified else 1.0
            new_avg = round(
                (avg_r * interactions + quality * caller_weight) /
                (interactions + caller_weight), 2
            )
        else:
            new_avg = round(quality, 2)
        update["avg_rating"] = new_avg

        # ── LATENCY SIGNAL ─────────────────────────────────────
        # Fast agents get a small response_rate boost
        if latency_ms > 0:
            if latency_ms < 500:    # sub 500ms = excellent
                update["response_rate"] = min(float(a.get("response_rate") or 0) + 2, 100)
            elif latency_ms > 10000: # over 10s = slow
                update["response_rate"] = max(float(a.get("response_rate") or 0) - 1, 0)

        # ── SIGNAL COUNT ───────────────────────────────────────
        update["signal_count"] = signal_count + 1

        # ── WRITE TO SUPABASE ──────────────────────────────────
        sb.table("agents").update(update).eq("slug", slug).execute()

        return {
            "status":        "signal_received",
            "slug":          slug,
            "outcome":       outcome,
            "new_avg_rating": new_avg,
            "signal_count":  signal_count + 1,
            "success_rate":  update.get("success_rate", success_rate),
            "message":       "Reputation updating. Keep sending signals."
        }

    except Exception as e:
        return {"error": str(e)}


@app.get("/api/leaderboard")
async def api_leaderboard(skill: str = "", country: str = "", limit: int = 10):
    \"\"\"
    Public leaderboard. Any app, any AI agent can call this.
    Shows who is actually winning based on real signals.
    \"\"\"
    try:
        query = sb.table("agents").select(
            "name,slug,skill_primary,location,country,"
            "reputation_score,avg_rating,jobs_completed,"
            "success_rate,signal_count,tier,badges"
        ).order("reputation_score", desc=True)

        if skill:
            query = query.eq("skill_primary", skill)
        if country:
            query = query.eq("country", country.lower())

        results = query.limit(limit).execute().data or []

        return {
            "leaderboard": results,
            "skill_filter": skill or "all",
            "country_filter": country or "all",
            "total_shown": len(results),
            "powered_by": "godena.protocol"
        }
    except Exception as e:
        return {"error": str(e)}
"""

# ── ALSO ADD signal_count and success_rate columns to Supabase ───
# Run this SQL in Supabase SQL Editor:
SUPABASE_SQL = """
ALTER TABLE agents ADD COLUMN IF NOT EXISTS signal_count  INTEGER DEFAULT 0;
ALTER TABLE agents ADD COLUMN IF NOT EXISTS success_rate  FLOAT   DEFAULT 0;
ALTER TABLE agents ADD COLUMN IF NOT EXISTS latency_avg   FLOAT   DEFAULT 0;
"""

print("signal_patch.py ready")
print("\nSQL to run in Supabase SQL Editor:")
print(SUPABASE_SQL)
print("\nThen paste the @app.post('/api/signal') block into app.py")
print("before the if __name__ == '__main__': line")
if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=7860)
