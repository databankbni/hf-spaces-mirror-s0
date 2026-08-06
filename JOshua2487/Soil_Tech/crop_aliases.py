# crop_aliases.py
# ─────────────────────────────────────────────────────────────────────────────
# PURE DATA FILE — no imports, no logic, no functions.
#
# To update aliases: add entries to CROP_ALIASES only.
# Format: "alias_or_misspelling": "canonical_key"
# canonical_key must exactly match a key in crop_requirements.json
#
# To add a new crop: add entries to ALL FOUR dicts below.
# ─────────────────────────────────────────────────────────────────────────────


# ══════════════════════════════════════════════════════════════════════════════
# CROP_ALIASES
# Every possible user input → canonical crop_requirements.json key
# Covers: Bisaya/Cebuano, Tagalog, English, vowel shifts, consonant swaps,
#         doubled/missing letters, mobile fat-finger errors
# ══════════════════════════════════════════════════════════════════════════════

CROP_ALIASES = {

    # ── Rice ──────────────────────────────────────────────────────────────────
    "humay": "rice", "humay rice": "rice",
    "palay": "rice", "palai": "rice", "pallay": "rice", "palaay": "rice",
    "bigas": "rice", "bugas": "rice", "buggas": "rice",
    "kanin": "rice", "kanen": "rice", "kanon": "rice",
    "rice": "rice", "rais": "rice", "rays": "rice", "ris": "rice",
    "ryce": "rice", "ricee": "rice", "ryse": "rice", "riss": "rice",
    "rise": "rice", "rce": "rice",

    # ── Corn ──────────────────────────────────────────────────────────────────
    "mais": "corn", "mays": "corn", "maes": "corn", "maais": "corn",
    "maiss": "corn", "maize": "corn", "maiz": "corn", "maise": "corn",
    "corn": "corn", "korn": "corn", "corm": "corn", "cornn": "corn",
    "cron": "corn", "conr": "corn", "coen": "corn",

    # ── Tomato ────────────────────────────────────────────────────────────────
    "kamatis": "tomato", "kamatiz": "tomato", "kamates": "tomato",
    "kamutes": "tomato", "komatis": "tomato",
    "camatis": "tomato", "camatiz": "tomato", "kamatys": "tomato",
    "kametes": "tomato", "kamotis": "tomato",
    "tomato": "tomato", "tomatis": "tomato", "tomatoe": "tomato",
    "tomatoes": "tomato", "tomat": "tomato", "tomatoo": "tomato",
    "tometo": "tomato", "tomatto": "tomato", "tomaeto": "tomato",
    "tomto": "tomato", "tamoto": "tomato", "tamato": "tomato",
    "tomatos": "tomato",

    # ── Eggplant ──────────────────────────────────────────────────────────────
    "talong": "eggplant", "taloong": "eggplant", "tallong": "eggplant",
    "talung": "eggplant", "talungg": "eggplant", "taloung": "eggplant",
    "tarong": "eggplant", "taroong": "eggplant", "tarung": "eggplant",
    "talond": "eggplant", "tarond": "eggplant", "taroung": "eggplant",
    "talungs": "eggplant",
    "eggplant": "eggplant", "egplant": "eggplant", "eggplnat": "eggplant",
    "igplant": "eggplant", "egplnat": "eggplant", "eggplan": "eggplant",
    "egg plant": "eggplant", "egg plnt": "eggplant",
    "eggplnt": "eggplant", "egplnt": "eggplant",
    "eggpant": "eggplant", "eggplat": "eggplant", "egplannt": "eggplant",
    "egglant": "eggplant", "eggpland": "eggplant",
    "aubergine": "eggplant", "aubergene": "eggplant", "aubergin": "eggplant",
    "brinjal": "eggplant", "bringal": "eggplant", "brinjel": "eggplant",

    # ── Kangkong ──────────────────────────────────────────────────────────────
    "kangkong": "kangkong", "kangkon": "kangkong", "kangkung": "kangkong",
    "kang kong": "kangkong",
    "tangkong": "kangkong", "tangkon": "kangkong", "tangkung": "kangkong",
    "tinangkong": "kangkong", "tinangkon": "kangkong",
    "kangong": "kangkong",
    "water spinach": "kangkong", "waterspinach": "kangkong",
    "river spinach": "kangkong", "riverspinach": "kangkong",
    "water spinch": "kangkong", "wtr spinach": "kangkong",

    # ── Camote ────────────────────────────────────────────────────────────────
    "camote": "camote", "kamote": "camote", "kamoti": "camote",
    "kamute": "camote", "kamuti": "camote", "camuote": "camote",
    "kamotee": "camote", "camoti": "camote", "kamotey": "camote",
    "camotie": "camote", "kamuote": "camote", "kamotii": "camote",
    "tamus": "camote", "tamis": "camote", "tammus": "camote",
    "sweet potato": "camote", "sweetpotato": "camote",
    "sweet patato": "camote", "sweat potato": "camote",
    "swt potato": "camote", "sweet potatoe": "camote",
    "sweet pottato": "camote", "swet potato": "camote",
    "camoteng kahoy": "camote", "kamoteng kahoy": "camote",

    # ── Cassava ───────────────────────────────────────────────────────────────
    "cassava": "cassava", "kasava": "cassava", "cassaba": "cassava",
    "casava": "cassava", "kasaba": "cassava", "kasabba": "cassava",
    "cassavva": "cassava", "cassaava": "cassava", "casssava": "cassava",
    "kassava": "cassava",
    "balinghoy": "cassava", "balinghoi": "cassava", "balingoy": "cassava",
    "balinhoy": "cassava",
    "manioc": "cassava", "maniok": "cassava", "mannioc": "cassava",
    "yuca": "cassava", "yucca": "cassava", "yukka": "cassava",

    # ── Onion ─────────────────────────────────────────────────────────────────
    "sibuyas": "onion", "sibyas": "onion", "sibuas": "onion",
    "sibuias": "onion", "sibuyaz": "onion", "sibias": "onion",
    "sivuyas": "onion",
    "bumbay": "onion", "bombay": "onion", "bumbai": "onion", "bombai": "onion",
    "lasona": "onion", "lasuna": "onion",
    "onion": "onion", "oniun": "onion", "onyon": "onion",
    "onyun": "onion", "unyon": "onion", "unyun": "onion",
    "onions": "onion", "onian": "onion", "onin": "onion",
    "onyons": "onion", "onins": "onion",

    # ── Garlic ────────────────────────────────────────────────────────────────
    "bawang": "garlic", "bawng": "garlic", "bawwang": "garlic",
    "dawang": "garlic", "bawangg": "garlic", "bavang": "garlic",
    "bawamg": "garlic",
    "ahos": "garlic", "ahus": "garlic", "ajos": "garlic", "aho": "garlic",
    "ahoss": "garlic", "ajus": "garlic",
    "garlic": "garlic", "garlik": "garlic", "garlicc": "garlic",
    "garlick": "garlic", "garlc": "garlic",
    "garliic": "garlic", "galic": "garlic",
    "bawang putih": "garlic", "garlic bulb": "garlic",

    # ── Mustasa ───────────────────────────────────────────────────────────────
    "mustasa": "mustasa", "mustaza": "mustasa", "mustassa": "mustasa",
    "mustasaa": "mustasa", "mustaasa": "mustasa", "mustsa": "mustasa",
    "mustasya": "mustasa",
    "mustard": "mustasa", "mustard greens": "mustasa",
    "mustasa greens": "mustasa", "mustasa leaf": "mustasa",
    "mustart": "mustasa", "mustad": "mustasa", "mustrd": "mustasa",
    "mustard green": "mustasa",

    # ── Ampalaya ──────────────────────────────────────────────────────────────
    "ampalaya": "ampalaya", "amplaya": "ampalaya", "ampalaia": "ampalaya",
    "ampalay": "ampalaya", "ampalya": "ampalaya", "ampalaiya": "ampalaya",
    "amplaaya": "ampalaya", "ampalaaya": "ampalaya",
    "parya": "ampalaya", "paria": "ampalaya", "pariya": "ampalaya",
    "paryah": "ampalaya",
    "bitter gourd": "ampalaya", "bittergourd": "ampalaya",
    "bitter melon": "ampalaya", "bittermelon": "ampalaya",
    "bitter gord": "ampalaya", "bitter melun": "ampalaya",
    "biter melon": "ampalaya",

    # ── Alugbati ──────────────────────────────────────────────────────────────
    "alugbati": "alugbati", "alugbate": "alugbati", "alugbat": "alugbati",
    "alugbatti": "alugbati", "alogbati": "alugbati",
    "alugboti": "alugbati",
    "libato": "alugbati", "libatu": "alugbati",
    "dundula": "alugbati", "dundola": "alugbati",
    "malabar spinach": "alugbati", "malabarspinach": "alugbati",
    "malabar spinch": "alugbati", "malabar spinash": "alugbati",

    # ── Sitaw ─────────────────────────────────────────────────────────────────
    "sitaw": "sitaw", "sitao": "sitaw", "sitau": "sitaw",
    "sitaaw": "sitaw", "sitaow": "sitaw",
    "batong": "sitaw", "batoong": "sitaw", "batung": "sitaw",
    "battong": "sitaw", "batongan": "sitaw",
    "batungg": "sitaw", "battoong": "sitaw",
    "hantak": "sitaw", "hantag": "sitaw", "hanntag": "sitaw",
    "string beans": "sitaw", "string bean": "sitaw", "stringbeans": "sitaw",
    "yardlong beans": "sitaw", "yard long beans": "sitaw",
    "long beans": "sitaw", "longbeans": "sitaw",
    "string bens": "sitaw", "strig beans": "sitaw",
    "yard long bean": "sitaw", "yardlong bean": "sitaw",
    "stringbean": "sitaw", "string ban": "sitaw",

    # ── Sili ──────────────────────────────────────────────────────────────────
    "sili": "sili", "silli": "sili", "sily": "sili",
    "silii": "sili", "siliy": "sili",
    "chili": "sili", "chilli": "sili", "chilly": "sili",
    "chili pepper": "sili", "chile": "sili", "chille": "sili",
    "chilli pepper": "sili",
    "pepper": "sili", "hot pepper": "sili",
    "lada": "sili", "ladda": "sili",
    "siling labuyo": "sili", "siling haba": "sili",
    "siling labuio": "sili", "siling labyo": "sili",

    # ── Kalamansi ─────────────────────────────────────────────────────────────
    "kalamansi": "kalamansi", "calamansi": "kalamansi",
    "calamansee": "kalamansi", "kalamansy": "kalamansi",
    "kalamansee": "kalamansi", "kalamansei": "kalamansi",
    "calamansii": "kalamansi", "kalamannsi": "kalamansi",
    "calamondin": "kalamansi", "calamonding": "kalamansi",
    "kalamunding": "kalamansi", "kalamansi lime": "kalamansi",
    "lemonsito": "kalamansi", "lemonsitu": "kalamansi",
    "lemoncito": "kalamansi", "lemonsitoo": "kalamansi",
    "limon": "kalamansi", "limun": "kalamansi",
    "lemon": "kalamansi",

    # ── Malunggay ─────────────────────────────────────────────────────────────
    "malunggay": "malunggay", "malungay": "malunggay",
    "malunggai": "malunggay", "malungai": "malunggay",
    "malunggey": "malunggay", "malunggei": "malunggay",
    "malunggoy": "malunggay", "malungey": "malunggay",
    "malunggays": "malunggay",
    "kamunggay": "malunggay", "kamunggai": "malunggay",
    "kamungay": "malunggay", "kamunggey": "malunggay",
    "kamunggoy": "malunggay", "kamungai": "malunggay",
    "kamungey": "malunggay",
    "moringa": "malunggay", "muringa": "malunggay",
    "moringga": "malunggay", "moringo": "malunggay",
    "morings": "malunggay", "muringga": "malunggay",
    "morenga": "malunggay", "moringah": "malunggay",
    "drumstick tree": "malunggay", "drumstick": "malunggay",
    "drumstic": "malunggay",

    # ── Tanglad ───────────────────────────────────────────────────────────────
    "tanglad": "tanglad", "tanglads": "tanglad", "tagland": "tanglad",
    "tangad": "tanglad", "tangland": "tanglad", "tanngad": "tanglad",
    "salai": "tanglad", "salay": "tanglad", "sallai": "tanglad",
    "lemongrass": "tanglad", "lemon grass": "tanglad",
    "lemograss": "tanglad", "lemon gras": "tanglad",
    "lemon grss": "tanglad", "lemongras": "tanglad",
    "lemongrss": "tanglad",

    # ── Sayote ────────────────────────────────────────────────────────────────
    "sayote": "sayote", "sayoti": "sayote", "saiote": "sayote",
    "sayor": "sayote", "sayotee": "sayote",
    "chayote": "sayote", "chayoti": "sayote", "chayotee": "sayote",
    "choko": "sayote",
    "vegetable pear": "sayote", "veg pear": "sayote",

    # ── Singkamas ─────────────────────────────────────────────────────────────
    "singkamas": "singkamas", "sengkamas": "singkamas",
    "singkamaz": "singkamas", "singkamas tuber": "singkamas",
    "singkammas": "singkamas", "sengkamaz": "singkamas",
    "jicama": "singkamas", "hikama": "singkamas",
    "jicamma": "singkamas", "hikamma": "singkamas",
    "turnip": "singkamas", "turnips": "singkamas",

    # ── Sigarilyas ────────────────────────────────────────────────────────────
    "sigarilyas": "sigarilyas", "sigarilya": "sigarilyas",
    "sigarillas": "sigarilyas", "sigarilias": "sigarilyas",
    "sigarillyas": "sigarilyas",
    "winged beans": "sigarilyas", "winged bean": "sigarilyas",
    "wingedbeans": "sigarilyas", "winged bens": "sigarilyas",
    "four angled bean": "sigarilyas", "4 angled bean": "sigarilyas",
    "4-angled bean": "sigarilyas",

    # ── Mani ──────────────────────────────────────────────────────────────────
    "mani": "mani", "manies": "mani", "manny": "mani",
    "maani": "mani", "manni": "mani",
    "peanut": "mani", "peanuts": "mani", "peanat": "mani",
    "penut": "mani", "peanett": "mani", "peenut": "mani",
    "groundnut": "mani", "ground nut": "mani", "groundnuts": "mani",

    # ── Kundol ────────────────────────────────────────────────────────────────
    "kundol": "kundol", "kondol": "kundol", "kundoll": "kundol",
    "wax gourd": "kundol", "waxgourd": "kundol",
    "winter melon": "kundol", "wintermelon": "kundol",
    "white gourd": "kundol", "whitegourd": "kundol",

    # ── Patola ────────────────────────────────────────────────────────────────
    "patola": "patola", "patula": "patola", "pattola": "patola",
    "patolla": "patola",
    "sponge gourd": "patola", "spongegourd": "patola",
    "luffa": "patola", "lufa": "patola",
    "loofah": "patola", "loofa": "patola", "lufah": "patola",

    # ── Upo ───────────────────────────────────────────────────────────────────
    "upo": "upo", "upo squash": "upo", "upoo": "upo", "uppo": "upo",
    "bottle gourd": "upo", "bottlegourd": "upo",
    "calabash": "upo", "calabahs": "upo", "bottle gord": "upo",

    # ── Pipino ────────────────────────────────────────────────────────────────
    "pipino": "pipino", "pepino": "pipino", "pepeno": "pipino",
    "pipinu": "pipino", "piipino": "pipino", "ppino": "pipino",
    "pepinu": "pipino", "piepino": "pipino",
    "cucumber": "pipino", "cucmber": "pipino", "cuccumber": "pipino",
    "cucuumber": "pipino", "cucumbr": "pipino", "cucumbe": "pipino",
    "cucumbber": "pipino", "cuucumber": "pipino", "cucmbre": "pipino",
    "cuecumber": "pipino", "cucumbar": "pipino",

    # ── Luya ──────────────────────────────────────────────────────────────────
    "luya": "luya", "loya": "luya", "luia": "luya",
    "luy a": "luya", "loy a": "luya", "luiya": "luya",
    "loyya": "luya", "luyya": "luya", "luiia": "luya",
    "ginger": "luya", "gingger": "luya", "gingr": "luya",
    "giner": "luya", "ginggr": "luya", "ginjer": "luya",
    "genger": "luya",

    # ── Pako ──────────────────────────────────────────────────────────────────
    "pako": "pako", "pakis": "pako", "pakko": "pako", "pakiss": "pako",
    "fern": "pako", "vegetable fern": "pako", "vegfern": "pako",
    "veg fern": "pako",

    # ── Carrots ───────────────────────────────────────────────────────────────
    "carrots": "carrots", "carrot": "carrots", "karot": "carrots",
    "karots": "carrots", "carot": "carrots", "carots": "carrots",
    "karrot": "carrots", "karrots": "carrots", "carrt": "carrots",
    "karoot": "carrots", "carroot": "carrots", "carrrot": "carrots",

    # ── Potato ────────────────────────────────────────────────────────────────
    "potato": "potato", "potatoes": "potato", "patatas": "potato",
    "patata": "potato", "potatoe": "potato", "poteto": "potato",
    "patato": "potato", "potatos": "potato",
    "potaato": "potato", "pottato": "potato", "potatto": "potato",

    # ── Chinese Petchay ───────────────────────────────────────────────────────
    "chinese_petchay": "chinese_petchay",
    "chinese petchay": "chinese_petchay",
    "chinese pechay": "chinese_petchay",
    "petsay": "chinese_petchay", "petsai": "chinese_petchay",
    "petchay baguio": "chinese_petchay", "pechay baguio": "chinese_petchay",
    "napa cabbage": "chinese_petchay", "napa": "chinese_petchay",
    "chinese cabbage": "chinese_petchay",
    "chinise cabbage": "chinese_petchay",
    "chines petchay": "chinese_petchay",
    "china cabbage": "chinese_petchay",
    "chinese petsay": "chinese_petchay",

    # ── Green Onions ──────────────────────────────────────────────────────────
    "green_onions": "green_onions",
    "green onions": "green_onions", "green onion": "green_onions",
    "greenonion": "green_onions", "green onyun": "green_onions",
    "grn onion": "green_onions", "gren onion": "green_onions",
    "scallion": "green_onions", "scallions": "green_onions",
    "scallian": "green_onions", "scallins": "green_onions",
    "spring onion": "green_onions", "spring onions": "green_onions",
    "sibuyas dahon": "green_onions", "sibuyas na dahon": "green_onions",
    "dahon ng sibuyas": "green_onions",
    "kutchay": "green_onions", "kuchay": "green_onions",
    "kutchey": "green_onions", "kuchai": "green_onions",

    # ── Repolyo ───────────────────────────────────────────────────────────────
    "repolyo": "repolyo", "repollo": "repolyo", "repullo": "repolyo",
    "repolio": "repolyo", "repulyo": "repolyo",
    "repollyo": "repolyo", "repollio": "repolyo",
    "cabbage": "repolyo", "cabbge": "repolyo", "kabbage": "repolyo",
    "cabagge": "repolyo", "cabbagge": "repolyo",
    "cabbege": "repolyo", "cabage": "repolyo",

    # ── Bokchoy ───────────────────────────────────────────────────────────────
    "bokchoy": "bokchoy", "bok choy": "bokchoy", "bokchoi": "bokchoy",
    "bok choi": "bokchoy", "pak choi": "bokchoy", "pok choy": "bokchoy",
    "bochoy": "bokchoy", "bokhoy": "bokchoy",

    # ── Papaya ────────────────────────────────────────────────────────────────
    "papaya": "papaya", "papaia": "papaya", "papaiya": "papaya",
    "kapaya": "papaya", "tapaya": "papaya", "papayya": "papaya",
    "papya": "papaya", "kapaiya": "papaya", "tapaiya": "papaya",
    "papaay": "papaya",
    "pawpaw": "papaya",

    # ── Baguio Beans ──────────────────────────────────────────────────────────
    "baguio_beans": "baguio_beans",
    "baguio beans": "baguio_beans", "baguio bean": "baguio_beans",
    "green beans": "baguio_beans", "green bean": "baguio_beans",
    "french beans": "baguio_beans", "french bean": "baguio_beans",
    "snap beans": "baguio_beans", "snap bean": "baguio_beans",
    "habitchuelas": "baguio_beans", "habichuelas": "baguio_beans",
    "bagyo beans": "baguio_beans", "baguio bens": "baguio_beans",
    "bagueo beans": "baguio_beans", "bagyo bean": "baguio_beans",

    # ── Monggo ────────────────────────────────────────────────────────────────
    "monggo": "monggo", "munggo": "monggo", "mongo": "monggo",
    "mungo": "monggo", "monggoo": "monggo", "mongggo": "monggo",
    "mung bean": "monggo", "mung beans": "monggo", "mungbean": "monggo",
    "green gram": "monggo", "greengram": "monggo",
    "mung bens": "monggo",

    # ── Radish ────────────────────────────────────────────────────────────────
    "radish": "radish", "raddish": "radish", "radis": "radish",
    "labanos": "radish", "labanu": "radish",
    "rabanos": "radish", "labbanoss": "radish",
    "labanus": "radish", "labanoss": "radish",
    "raddis": "radish", "radich": "radish", "radiss": "radish",

    # ── Turmeric ──────────────────────────────────────────────────────────────
    "turmeric": "turmeric", "termeric": "turmeric", "tumeric": "turmeric",
    "tumerik": "turmeric", "turmerik": "turmeric",
    "luyang dilaw": "turmeric", "luyang dilau": "turmeric",
    "luyang dila": "turmeric",
    "dilaw": "turmeric", "dilau": "turmeric",
    "kalawag": "turmeric", "kalawog": "turmeric",
    "kunig": "turmeric", "kuning": "turmeric",

    # ── Asthma Plant ──────────────────────────────────────────────────────────
    "asthma_plant": "asthma_plant", "asthma plant": "asthma_plant",
    "tawa tawa": "asthma_plant", "tawa-tawa": "asthma_plant",
    "tawatawa": "asthma_plant", "tawa": "asthma_plant",
    "gatas gatas": "asthma_plant", "gatas-gatas": "asthma_plant",
    "gatasgatas": "asthma_plant",

    # ── Lagundi ───────────────────────────────────────────────────────────────
    "lagundi": "lagundi", "lagunde": "lagundi", "lagunti": "lagundi",
    "lagundy": "lagundi", "lagundii": "lagundi",
    "dangla": "lagundi", "danggla": "lagundi",
    "five leaved chaste tree": "lagundi",
    "five-leaved chaste tree": "lagundi",

    # ── Basil ─────────────────────────────────────────────────────────────────
    "basil": "basil", "bazil": "basil", "bassil": "basil",
    "basill": "basil", "bazill": "basil",
    "sweet basil": "basil", "sweet bazil": "basil",
    "balanoy": "basil", "balanoi": "basil", "balanuy": "basil",
    "solasi": "basil", "solasin": "basil",

    # ── Pandan ────────────────────────────────────────────────────────────────
    "pandan": "pandan", "pandaan": "pandan", "pandan leaf": "pandan",
    "pandan leaves": "pandan", "pandann": "pandan",
    "screwpine": "pandan", "screw pine": "pandan",
    "pangdan": "pandan", "pandang": "pandan",

    # ── Mint ──────────────────────────────────────────────────────────────────
    "mint": "mint", "mnt": "mint", "minnt": "mint",
    "mintt": "mint", "mints": "mint",
    "hierba buena": "mint", "yerba buena": "mint",
    "herba buena": "mint", "yerbas buena": "mint",
    "peppermint": "mint", "spearmint": "mint",
    "pepermint": "mint", "spearemint": "mint",

    # ── Ube ───────────────────────────────────────────────────────────────────
    "ube": "ube", "ubi": "ube", "ubbe": "ube", "ubee": "ube", "ubii": "ube",
    "purple yam": "ube", "violet yam": "ube", "yam": "ube",
    "purpleyam": "ube",

    # ── Pechay ────────────────────────────────────────────────────────────────
    "pechay": "pechay", "pitsay": "pechay", "pechey": "pechay",
    "pechai": "pechay", "petchay": "pechay",
    "petsay pechay": "pechay", "baby pechay": "pechay",
    "baby petsay": "pechay",
    "chinese mustard": "pechay", "chinese mustad": "pechay",

    # ── Okra ──────────────────────────────────────────────────────────────────
    "okra": "okra", "ukra": "okra", "okraa": "okra",
    "okras": "okra", "okka": "okra",
    "okrra": "okra", "okkra": "okra", "okrah": "okra",
    "ladies finger": "okra", "lady finger": "okra",
    "ladyfinger": "okra", "ladies fingers": "okra",
    "ladys finger": "okra", "ladiesfinger": "okra",

    # ── Lettuce ───────────────────────────────────────────────────────────────
    "lettuce": "lettuce", "letuce": "lettuce", "lettuse": "lettuce",
    "lettuces": "lettuce", "lettucee": "lettuce",
    "lletuce": "lettuce", "lettcue": "lettuce",
    "litsugas": "lettuce", "litsugad": "lettuce",
    "letius": "lettuce", "litsuga": "lettuce",
    "salad": "lettuce",

    # ── Oregano ───────────────────────────────────────────────────────────────
    "oregano": "oregano", "oregono": "oregano", "oreganno": "oregano",
    "origano": "oregano", "oregnao": "oregano",
    "oreganoo": "oregano",
    "suganda": "oregano", "wild oregano": "oregano",
    "oregano leaf": "oregano",

    # ── Rosemary ──────────────────────────────────────────────────────────────
    "rosemary": "rosemary", "rosmary": "rosemary", "rosemerry": "rosemary",
    "rozzmarry": "rosemary", "rosemarry": "rosemary",
    "roseemary": "rosemary", "rosmarry": "rosemary",
    "romero": "rosemary", "romero herb": "rosemary",

    # ── Chives ────────────────────────────────────────────────────────────────
    "chives": "chives", "chive": "chives", "chivs": "chives",
    "chivves": "chives",
    "kuchai": "chives", "chinese chives": "chives",
    "garlic chives": "chives",
}


# ══════════════════════════════════════════════════════════════════════════════
# CANONICAL_DISPLAY  — Tagalog names (default Filipino display)
# Bisaya input → falls back here (shows Tagalog, not Bisaya)
# Tagalog input → uses this directly
# ══════════════════════════════════════════════════════════════════════════════

CANONICAL_DISPLAY = {
    "rice":            "Palay",
    "corn":            "Mais",
    "tomato":          "Kamatis",
    "eggplant":        "Talong",
    "kangkong":        "Kangkong",
    "camote":          "Kamote",
    "cassava":         "Cassava",
    "onion":           "Sibuyas",
    "garlic":          "Bawang",
    "mustasa":         "Mustasa",
    "ampalaya":        "Ampalaya",
    "alugbati":        "Alugbati",
    "sitaw":           "Sitaw",
    "sili":            "Sili",
    "kalamansi":       "Kalamansi",
    "malunggay":       "Malunggay",
    "tanglad":         "Tanglad",
    "sayote":          "Sayote",
    "singkamas":       "Singkamas",
    "sigarilyas":      "Sigarilyas",
    "mani":            "Mani",
    "kundol":          "Kundol",
    "patola":          "Patola",
    "upo":             "Upo",
    "pipino":          "Pipino",
    "luya":            "Luya",
    "pako":            "Pako",
    "carrots":         "Karot",
    "potato":          "Patatas",
    "chinese_petchay": "Petsay",
    "green_onions":    "Sibuyas Dahon",
    "repolyo":         "Repolyo",
    "bokchoy":         "Bokchoy",
    "baguio_beans":    "Baguio Beans",
    "monggo":          "Monggo",
    "turmeric":        "Luyang Dilaw",
    "asthma_plant":    "Tawa-Tawa",
    "lagundi":         "Lagundi",
    "pandan":          "Pandan",
    "ube":             "Ube",
    "pechay":          "Pechay",
    "okra":            "Okra",
    "lettuce":         "Lettuce",
    "papaya":          "Papaya",
    "radish":          "Labanos",
    "oregano":         "Oregano",
    "basil":           "Basil",
    "mint":            "Yerba Buena",
    "rosemary":        "Rosemary",
    "chives":          "Kutchay",
}


# ══════════════════════════════════════════════════════════════════════════════
# BISAYA_DISPLAY — kept for reference / future use
# NOT used as frontend output currently.
# get_display_name() maps bisaya input → CANONICAL_DISPLAY (Tagalog) instead.
# ══════════════════════════════════════════════════════════════════════════════

BISAYA_DISPLAY = {
    "rice":            "Humay",
    "corn":            "Mais",
    "tomato":          "Kamatis",
    "eggplant":        "Tarong",
    "kangkong":        "Tangkong",
    "camote":          "Kamote",
    "cassava":         "Balinghoy",
    "onion":           "Bumbay",
    "garlic":          "Ahos",
    "mustasa":         "Mustasa",
    "ampalaya":        "Parya",
    "alugbati":        "Libato",
    "sitaw":           "Sitaw",
    "sili":            "Sili",
    "kalamansi":       "Lemonsito",
    "malunggay":       "Kamunggay",
    "tanglad":         "Salai",
    "sayote":          "Sayote",
    "singkamas":       "Singkamas",
    "sigarilyas":      "Sigarilyas",
    "mani":            "Mani",
    "kundol":          "Kundol",
    "patola":          "Patola",
    "upo":             "Upo",
    "pipino":          "Pipino",
    "luya":            "Luya",
    "pako":            "Pakis",
    "carrots":         "Karot",
    "potato":          "Patatas",
    "chinese_petchay": "Petsay",
    "green_onions":    "Kutchay",
    "repolyo":         "Repolyo",
    "bokchoy":         "Bokchoy",
    "baguio_beans":    "Baguio Beans",
    "monggo":          "Monggo",
    "turmeric":        "Kalawag",
    "asthma_plant":    "Gatas-Gatas",
    "lagundi":         "Dangla",
    "pandan":          "Pandang",
    "ube":             "Ube",
    "pechay":          "Pechay",
    "okra":            "Okra",
    "lettuce":         "Lettuce",
    "papaya":          "Kapaya",
    "radish":          "Labanos",
    "oregano":         "Oregano",
    "basil":           "Solasi",
    "mint":            "Hierba Buena",
    "rosemary":        "Rosemary",
    "chives":          "Kuchai",
}


# ══════════════════════════════════════════════════════════════════════════════
# ENGLISH_DISPLAY — English names
# English input → uses this directly
# Also used as final fallback for any language if CANONICAL_DISPLAY is missing
# ══════════════════════════════════════════════════════════════════════════════

ENGLISH_DISPLAY = {
    "rice":            "Rice",
    "corn":            "Corn",
    "tomato":          "Tomato",
    "eggplant":        "Eggplant",
    "kangkong":        "Kangkong",
    "camote":          "Sweet Potato",
    "cassava":         "Cassava",
    "onion":           "Onion",
    "garlic":          "Garlic",
    "mustasa":         "Mustasa",
    "ampalaya":        "Bitter Melon",
    "alugbati":        "Malabar Spinach",
    "sitaw":           "String Beans",
    "sili":            "Chili",
    "kalamansi":       "Kalamansi",
    "malunggay":       "Moringa",
    "tanglad":         "Lemongrass",
    "sayote":          "Chayote",
    "singkamas":       "Jicama",
    "sigarilyas":      "Winged Beans",
    "mani":            "Peanut",
    "kundol":          "Winter Melon",
    "patola":          "Luffa",
    "upo":             "Bottle Gourd",
    "pipino":          "Cucumber",
    "luya":            "Ginger",
    "pako":            "Vegetable Fern",
    "carrots":         "Carrots",
    "potato":          "Potato",
    "chinese_petchay": "Chinese Cabbage",
    "green_onions":    "Green Onions",
    "repolyo":         "Cabbage",
    "bokchoy":         "Bok Choy",
    "baguio_beans":    "Green Beans",
    "monggo":          "Mung Beans",
    "turmeric":        "Turmeric",
    "asthma_plant":    "Tawa-Tawa",
    "lagundi":         "Lagundi",
    "pandan":          "Pandan",
    "ube":             "Ube",
    "pechay":          "Pechay",
    "okra":            "Okra",
    "lettuce":         "Lettuce",
    "papaya":          "Papaya",
    "radish":          "Radish",
    "oregano":         "Oregano",
    "basil":           "Basil",
    "mint":            "Mint",
    "rosemary":        "Rosemary",
    "chives":          "Chives",
}