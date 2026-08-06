# language_utils.py
# ─────────────────────────────────────────────────────────────────────────────
# Language detection and display-name resolution.
#
# To add a new language: add its word set below, update detect_language(),
# and add a branch in get_display_name().
#
# Current display rule (by design decision):
#   bisaya input  → Tagalog display name  (CANONICAL_DISPLAY)
#   tagalog input → Tagalog display name  (CANONICAL_DISPLAY)
#   english input → English display name  (ENGLISH_DISPLAY)
# ─────────────────────────────────────────────────────────────────────────────

from crop_aliases import CANONICAL_DISPLAY, ENGLISH_DISPLAY


# ══════════════════════════════════════════════════════════════════════════════
# WORD SETS — used by detect_language() only, not for display output
# ══════════════════════════════════════════════════════════════════════════════

ENGLISH_CROP_WORDS = {
    "rice", "corn", "maize", "tomato", "tomatoes", "eggplant", "cucumber",
    "ginger", "garlic", "onion", "onions", "carrot", "carrots", "potato",
    "potatoes", "cabbage", "lettuce", "radish", "chili", "chilli", "chilly",
    "pepper", "peanut", "peanuts", "basil", "mint", "oregano", "rosemary",
    "chives", "turmeric", "cassava", "manioc", "yuca", "yucca", "luffa",
    "loofah", "chayote", "jicama", "moringa", "lemongrass", "sweet potato",
    "pandan", "bitter melon", "bitter gourd", "mung bean", "mung beans",
    "string bean", "string beans", "winged bean", "winged beans",
    "green bean", "green beans", "green onion", "green onions",
    "scallion", "scallions", "spring onion", "bok choy", "napa cabbage",
    "bottle gourd", "winter melon", "wax gourd", "sponge gourd",
    "vegetable fern", "fern", "yam", "purple yam", "malabar spinach",
    "water spinach", "river spinach", "aubergine", "brinjal",
    "pawpaw", "papaya", "turnip",
    # phonetic English misspellings still count as English
    "muringa", "muringga", "moringo", "morenga", "moringah",
    "igplant", "egplant", "eggplnat", "egplnat", "eggplan",
    "eggplnt", "egplnt", "eggpant", "eggplat", "egglant",
    "tomatoe", "tometo", "tomatto", "tomto",
    "cucmber", "cuccumber", "cucuumber", "cucumbr", "cucumbe",
    "cucumbber", "cuucumber", "cucmbre", "cuecumber", "cucumbar",
    "gingger", "gingr", "giner", "ginjer", "genger",
    "aubergene", "aubergin", "bringal", "brinjel",
    "penut", "peanat", "peanett", "peenut",
    "lemongras", "lemongrss", "lemograss",
    "tumeric", "termeric", "tumerik", "turmerik",
    "chayoti", "chayotee", "hikama",
    "lufa", "lufah", "loofa",
    "sweetpotato", "sweet patato", "sweat potato",
    "maniok", "mannioc", "yukka",
    "drumstic", "drumstick",
    "scallian", "scallins",
    "bittergourd", "biter melon",
    "bottlegourd", "wintermelon", "waxgourd",
    "vegfern", "veg fern",
    "purpleyam",
    "peppermint", "spearmint", "pepermint",
    "rosemarry", "rosmary", "rosemerry",
    "bazil", "bassil",
    "garlik", "garlicc", "garlick", "galic",
    "raddish", "radis", "radiss", "radich",
    "letuce", "lettuse", "letius",
    "cabagge", "cabbge", "kabbage",
    "carot", "carots", "karrot", "karrots", "carrt",
    "potatoe", "poteto", "patato",
}

# Bisaya-specific words — NOT shared with Tagalog
BISAYA_CROP_WORDS = {
    "humay", "bugas", "buggas", "kanon", "kanen",
    "tarong", "taroong", "tarung", "tarond", "taroung",
    "tangkong", "tangkon", "tangkung", "tinangkong", "tinangkon",
    "kamuti", "kamute", "tamus", "tamis", "tammus",
    "balinghoy", "balinghoi", "balingoy", "balinhoy",
    "bumbay", "bombay", "bumbai", "bombai",
    "ahos", "ahus", "ajos", "aho", "ahoss", "ajus",
    "parya", "paria", "pariya", "paryah",
    "libato", "libatu", "dundula", "dundola",
    "batong", "batoong", "batung", "battong", "batongan", "batungg",
    "hantak", "hantag",
    "lada", "ladda",
    "lemonsito", "lemonsitu", "lemoncito",
    "limon", "limun",
    "kamunggay", "kamunggai", "kamungay", "kamunggey",
    "kamunggoy", "kamungai", "kamungey",
    "salai", "salay", "sallai",
    "kasaba", "kasabba",
    "lasona", "lasuna",
    "kapaya", "tapaya", "kapaiya", "tapaiya",
    "labanu", "labanus",
    "kalawag", "kalawog", "kunig", "kuning",
    "gatas gatas", "gatas-gatas", "gatasgatas",
    "dangla", "danggla",
    "solasi", "solasin",
    "pangdan", "pandang",
    "ubi", "ubii",
    "pitsay",
    "ukra",
    "loya", "luia", "loy a",
    "kuchai",
    "kutchay", "kutchey",
    "hierba buena",
    "sengkamas",
    "sitau", "sitao",
}


# ══════════════════════════════════════════════════════════════════════════════
# LANGUAGE DETECTION
# ══════════════════════════════════════════════════════════════════════════════

def detect_language(raw_input: str) -> str:
    """
    Returns 'english', 'bisaya', or 'tagalog'.
    Tagalog is the default fallback.
    """
    cleaned = raw_input.strip().lower()

    if cleaned in ENGLISH_CROP_WORDS:
        return "english"

    if cleaned in BISAYA_CROP_WORDS:
        return "bisaya"

    # multi-word heuristic: if most words are English, call it English
    words = cleaned.split()
    english_count = sum(1 for w in words if w in ENGLISH_CROP_WORDS)
    if english_count >= len(words) / 2 and len(words) > 1:
        return "english"

    return "tagalog"


# ══════════════════════════════════════════════════════════════════════════════
# DISPLAY NAME RESOLVER
# ══════════════════════════════════════════════════════════════════════════════

def get_display_name(matched_key: str, lang: str) -> str:
    """
    Returns the display name for the frontend based on detected language.

    Display rule (by design):
      english → ENGLISH_DISPLAY
      bisaya  → CANONICAL_DISPLAY  (Tagalog shown, not Bisaya)
      tagalog → CANONICAL_DISPLAY

    Fallback chain if a key is missing from the primary dict:
      CANONICAL_DISPLAY → ENGLISH_DISPLAY → title-cased key
    """
    if lang == "english":
        return (
            ENGLISH_DISPLAY.get(matched_key)
            or CANONICAL_DISPLAY.get(matched_key)
            or matched_key.replace("_", " ").title()
        )

    # bisaya and tagalog both show Tagalog name
    return (
        CANONICAL_DISPLAY.get(matched_key)
        or ENGLISH_DISPLAY.get(matched_key)
        or matched_key.replace("_", " ").title()
    )