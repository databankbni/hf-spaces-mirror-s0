import re
import html
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import fitz
import gradio as gr
import pandas as pd


APP_TITLE = "TenderKompas AI"
APP_SUBTITLE = "PvE Navigator"
DEFAULT_PDF_FILENAME = "1.0 Inkoopdocument Wmo dienstverlening - v1.0(1).pdf"
DEFAULT_PDF_STEM = "1.0 Inkoopdocument Wmo dienstverlening - v1.0"

ATTENTION_TERMS = [
    "VOG", "ISO", "HKZ", "AVG", "privacy", "informatiebeveiliging",
    "social return", "accountantsverklaring", "jaarrekening",
    "verwerkersovereenkomst", "facturatie", "PEPPOL",
    "acceptatieplicht", "vervoer", "klachtenregeling"
]

CHECKLIST_MAP = {
    "VOG": ("VOG’s controleren en verzamelen", "HR"),
    "ISO": ("ISO-certificaat / gelijkwaardigheid controleren", "Kwaliteit"),
    "HKZ": ("HKZ/ISO-kwaliteitssysteem controleren", "Kwaliteit"),
    "AVG": ("AVG-verplichtingen beoordelen", "Juridisch"),
    "privacy": ("Privacyreglement controleren", "Juridisch"),
    "informatiebeveiliging": ("Informatiebeveiliging afstemmen", "ICT"),
    "social return": ("Social Return-verplichting beoordelen", "Directie"),
    "accountantsverklaring": ("Accountantsverklaring voorbereiden", "Finance"),
    "jaarrekening": ("Jaarrekening controleren", "Finance"),
    "verwerkersovereenkomst": ("Verwerkersovereenkomst beoordelen", "Juridisch"),
    "facturatie": ("Facturatie-eisen afstemmen", "Finance"),
    "PEPPOL": ("PEPPOL/e-facturatie controleren", "Finance"),
    "acceptatieplicht": ("Acceptatieplicht intern bespreken", "Team"),
    "vervoer": ("Vervoerseisen beoordelen", "Operatie"),
    "klachtenregeling": ("Klachtenregeling controleren", "Kwaliteit"),
}


def esc(value):
    return html.escape(str(value))


def short(text, n=180):
    text = re.sub(r"\s+", " ", str(text)).strip()
    return text if len(text) <= n else text[: n - 1].rstrip() + "…"


def clean_text(text):
    text = text.replace("\x0c", "\n").replace("\u00a0", " ").replace("￾", "-").replace("\uf0a7", "•")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def split_lines(text):
    return [line.strip() for line in text.splitlines() if line.strip()]


def sentence_split(text):
    parts = re.split(r"(?<=[.!?])\s+(?=[A-ZÁÉÍÓÚÄËÏÖÜ])", text)
    return [re.sub(r"\s+", " ", p).strip() for p in parts if len(p.strip()) > 35]


def extract_pdf(path):
    doc = fitz.open(path)
    text = "\n".join(page.get_text("text") for page in doc)
    return clean_text(text), len(doc)


def find_client(text):
    patterns = [
        r"gemeente\s+[A-ZÁÉÍÓÚÄËÏÖÜa-záéíóúäëïöü\- ]{2,45}",
        r"Gemeente\s+[A-ZÁÉÍÓÚÄËÏÖÜa-záéíóúäëïöü\- ]{2,45}",
        r"Voorne\s+aan\s+Zee",
        r"Rotterdam",
        r"Den Haag",
    ]
    for p in patterns:
        m = re.search(p, text, flags=re.IGNORECASE)
        if m:
            val = re.sub(r"\s+", " ", m.group(0)).strip()
            val = re.sub(r"\b\d+\b$", "", val).strip()
            return short(val, 80)
    return "Niet betrouwbaar herkend"


def find_subject(text):
    for line in split_lines(text)[:50]:
        low = line.lower()
        if "programma van eisen" in low:
            continue
        if 10 < len(line) < 120 and any(w in low for w in ["wmo", "dagbesteding", "begeleiding", "dienst", "perceel", "psycholog"]):
            return short(line, 95)
    return "Programma van Eisen"


def is_heading(line):
    line = line.strip()
    if not line or len(line) > 115:
        return False
    if line.lower() in {"eis", "eis nr.", "eis nr. eis", "programma van eisen"}:
        return False
    if re.match(r"^\d{1,2}\.\s+[A-ZÁÉÍÓÚÄËÏÖÜa-záéíóúäëïöü]", line):
        return True
    known = {
        "algemeen", "personeel", "privacy", "privacy en informatiebeveiliging",
        "social return", "juridische eisen", "controle en onderzoek",
        "registratie en overleg", "klachten, incidenten en calamiteiten",
        "algemene kwaliteitseisen", "invulling en einde opdracht",
        "administratie en facturatie", "prestatieverklaring", "e-ordering",
        "zero-emissie", "eisen aan de dienstverlening",
        "eisen aan de informatiebeveiliging", "eisen met betrekking tot privacy"
    }
    return line.lower() in known


def find_headings(lines):
    headings = []
    for i, line in enumerate(lines):
        if is_heading(line):
            title = re.sub(r"^\d{1,2}\.\s*", "", line).strip()
            headings.append({"line": i, "title": title})
    if not headings:
        headings = [{"line": 0, "title": "Algemeen"}]
    unique = []
    seen = set()
    for h in headings:
        key = h["title"].lower()
        if key not in seen:
            seen.add(key)
            unique.append(h)
    return unique


def current_heading(idx, headings):
    selected = headings[0]["title"] if headings else "Algemeen"
    for h in headings:
        if h["line"] <= idx:
            selected = h["title"]
        else:
            break
    return selected


def parse_requirements(lines, headings):
    reqs = []
    current = None
    start = re.compile(r"^(\d{1,3})[\.\)]\s+(.*)$")
    for i, line in enumerate(lines):
        raw = line.strip()
        low = raw.lower()
        if low in {"eis", "eis nr.", "eis nr. eis", "programma van eisen"}:
            continue
        if re.match(r"^gemeente\s+.+\s+\d+$", raw, flags=re.IGNORECASE) or re.match(r"^\d+$", raw):
            continue
        m = start.match(raw)
        if m:
            if current:
                reqs.append(current)
            current = {
                "eisnummer": m.group(1),
                "hoofdstuk": current_heading(i, headings),
                "tekst": m.group(2).strip(),
            }
        elif current and not is_heading(raw):
            current["tekst"] += " " + raw
    if current:
        reqs.append(current)
    for r in reqs:
        r["tekst"] = re.sub(r"\s+", " ", r["tekst"]).strip()
    return reqs


def find_attention_points(text):
    low = text.lower()
    return [term for term in ATTENTION_TERMS if term.lower() in low]


def find_obligations(text):
    patterns = [
        r"(?:De\s+)?Opdrachtnemer dient[^.?!]*(?:[.?!]|$)",
        r"(?:De\s+)?Opdrachtnemer zorgt[^.?!]*(?:[.?!]|$)",
        r"(?:De\s+)?Opdrachtnemer is verplicht[^.?!]*(?:[.?!]|$)",
        r"(?:De\s+)?Opdrachtnemer moet[^.?!]*(?:[.?!]|$)",
        r"(?:De\s+)?Opdrachtnemer verplicht zich[^.?!]*(?:[.?!]|$)",
        r"(?:De\s+)?Inschrijver dient[^.?!]*(?:[.?!]|$)",
    ]
    found = []
    for p in patterns:
        for m in re.finditer(p, text, flags=re.IGNORECASE):
            item = short(m.group(0), 175)
            if item not in found:
                found.append(item)
    return found[:10]


def find_deadlines(text):
    keys = [
        "binnen", "uiterlijk", "werkdagen", "kalenderdagen", "jaarlijks",
        "eenmaal per jaar", "kwartaal", "vóór", "voor ", "per jaar",
        "maanden", "weken", "dagen", "24 uur", "30 dagen"
    ]
    found = []
    for s in sentence_split(text):
        low = s.lower()
        if any(k in low for k in keys):
            item = short(s, 170)
            if item not in found:
                found.append(item)
    return found[:9]


def make_checklist(points):
    items = [CHECKLIST_MAP[p] for p in points if p in CHECKLIST_MAP]
    return items[:9] if items else [("Origineel PvE controleren op eisen, bijlagen en verplichtingen", "Team")]


def extractive_summary(text, points, reqs, headings):
    themes = [
        "personeel", "kwaliteit", "privacy", "informatiebeveiliging", "facturatie",
        "social return", "klachten", "registratie", "verantwoording", "continuïteit",
        "VOG", "HKZ", "ISO", "AVG"
    ]
    scored = []
    for s in sentence_split(text):
        low = s.lower()
        score = sum(2 for t in themes if t.lower() in low)
        score += sum(3 for p in points if p.lower() in low)
        if "opdrachtnemer" in low:
            score += 1
        if score > 0 and 50 <= len(s) <= 290:
            scored.append((score, s))
    scored.sort(key=lambda x: x[0], reverse=True)
    out = [f"In totaal zijn {len(reqs)} genummerde eisen geïdentificeerd, verdeeld over {len(headings)} hoofdstukken."] if reqs else []
    for _, s in scored:
        item = short(s, 205)
        if item not in out:
            out.append(item)
        if len(out) >= 4:
            break
    return out[:4]


def chapter_counts(reqs, headings):
    counts = defaultdict(int)
    for r in reqs:
        counts[r["hoofdstuk"]] += 1
    return [(h["title"], counts.get(h["title"], 0)) for h in headings]


def sidebar_html(filename="Geen bestand", pages="-", reqs="-", chapters="-", last="-"):
    nav = [
        ("⌂", "Dashboard", "active", "#dashboard-area"),
        ("☷", "Eisen overzicht", "", "#eisenbrowser"),
        ("▣", "Hoofdstukken", "", "#hoofdstukken"),
        ("◷", "Termijnen", "", "#termijnen"),
        ("⌕", "Zoeken", "", "#eisenbrowser"),
        ("☑", "Actielijst / Checklist", "", "#checklist"),
        ("☰", "Samenvatting", "", "#samenvatting"),
        ("✎", "NVI-assistent", "", "#nvi-assistent"),
        ("▤", "Bijlagen", "", "#bijlagen"),
        ("⚙", "Instellingen", "", "#instellingen"),
    ]
    items = "".join(
        f"<a class='nav-item {cls}' href='{href}'><span>{ic}</span><b>{esc(label)}</b></a>"
        for ic, label, cls, href in nav
    )
    return f"""
    <div class="brand">
        <div class="brand-logo">◇</div>
        <div><h1>{APP_TITLE}</h1><p>{APP_SUBTITLE}</p></div>
    </div>
    <nav>{items}</nav>
    <div class="analysis-info">
        <h3>Analyse info</h3>
        <div><span>Bestandsnaam</span><b>{esc(filename)}</b></div>
        <div><span>Pagina’s</span><b>{esc(pages)}</b></div>
        <div><span>Eisen gevonden</span><b>{esc(reqs)}</b></div>
        <div><span>Hoofdstukken</span><b>{esc(chapters)}</b></div>
        <div><span>Laatst geanalyseerd</span><b>{esc(last)}</b></div>
    </div>
    """


def top_intro_html():
    return f"""
    <div class="topbar">
        <div>
            <div class="page-title">{APP_TITLE}</div>
            <div class="page-subtitle">Upload één Programma van Eisen. De applicatie zet eisen, hoofdstukken, termijnen en verplichtingen om in een dashboard.</div>
        </div>
        <div class="top-pills">
            <a href="#upload-card">Upload</a>
            <a href="#dashboard-area">Dashboard</a>
            <a href="#eisenbrowser">Eisenbrowser</a>
        </div>
    </div>
    """


def empty_dashboard_html():
    return """
    <div class="empty-panel" id="dashboard-area">
        <h2>Upload één Programma van Eisen</h2>
        <p>Na analyse verschijnt hier het dashboard met documentgegevens, hoofdstukken, verplichtingen, termijnen, aandachtspunten, checklist en samenvatting.</p>
    </div>
    """



def kpi_cards(pages, req_count, heading_count, obligations_count):
    return f"""
    <section class="kpi-grid" id="dashboard-area">
        <div class="kpi-card"><span>Pagina’s</span><strong>{pages}</strong><p>uit PDF gelezen</p></div>
        <div class="kpi-card"><span>Hoofdstukken</span><strong>{heading_count}</strong><p>herkende onderdelen</p></div>
        <div class="kpi-card"><span>Eisen</span><strong>{req_count}</strong><p>genummerde eisen</p></div>
        <div class="kpi-card"><span>Verplichtingen</span><strong>{obligations_count}</strong><p>gevonden patronen</p></div>
    </section>
    """


def document_card(subject, client, filename):
    return f"""
    <section class="document-card">
        <div class="doc-head">
            <div class="pdf-icon"><span>PDF</span></div>
            <div>
                <h2>Programma van Eisen</h2>
                <p>{esc(subject)}</p>
                <strong>{esc(client)}</strong>
            </div>
        </div>
        <div class="doc-meta">
            <div><span>Bestand</span><b>{esc(short(filename, 45))}</b></div>
            <div><span>Perceel</span><b>n.v.t.</b></div>
            <div><span>Publicatiedatum</span><b>n.v.t.</b></div>
            <div><span>Sluitingsdatum</span><b>n.v.t.</b></div>
            <div><span>Procedure</span><b>n.v.t.</b></div>
            <div><span>Analyse status</span><b class="pill-ok">Voltooid</b></div>
        </div>
    </section>
    """


def chapters_card(chapters):
    rows = "".join(
        f"<div class='table-row'><span>{i}.</span><p>{esc(title)}</p><b>{count if count else '-'}</b></div>"
        for i, (title, count) in enumerate(chapters[:10], 1)
    )
    return f"<div class='dash-card' id='hoofdstukken'><h3>Hoofdstukken overzicht</h3>{rows or '<p class=muted>Geen hoofdstukken gevonden.</p>'}<a href='#eisenbrowser'>Bekijk in eisenbrowser →</a></div>"


def obligations_card(items):
    rows = "".join(f"<li><span class='check'>✓</span><p>{esc(i)}</p></li>" for i in items)
    content = f"<ul class='icon-list'>{rows}</ul>" if rows else "<p class='muted'>Geen verplichtingen gevonden.</p>"
    return f"<div class='dash-card' id='verplichtingen'><h3>Belangrijkste verplichtingen</h3>{content}<a href='#eisenbrowser'>Zoek verplichtingen →</a></div>"


def deadlines_card(items):
    rows = ""
    for item in items:
        m = re.search(r"(\d+\s*(?:werkdagen|kalenderdagen|dagen|weken|maanden|uur)|eenmaal per jaar|per kwartaal|kwartaal|jaarlijks)", item, flags=re.I)
        label = m.group(1) if m else "termijn"
        rows += f"<div class='deadline-row'><span>▣</span><p>{esc(item)}</p><b>{esc(label)}</b></div>"
    return f"<div class='dash-card' id='termijnen'><h3>Termijnen</h3>{rows or '<p class=muted>Geen termijnen gevonden.</p>'}<a href='#eisenbrowser'>Zoek termijnen →</a></div>"


def category_card(chapters, total):
    colors = ["#2f80ed", "#27ae60", "#f2b01e", "#7b61ff", "#20c997", "#ff7a45", "#b8beca"]
    top = [(t, c) for t, c in chapters if c > 0][:7]
    legend = "".join(
        f"<div><span style='background:{colors[i % len(colors)]}'></span>{esc(short(t, 24))}<b>{c}</b></div>"
        for i, (t, c) in enumerate(top)
    )
    bars = "".join(
        f"<i style='width:{max(int(c/total*100),4) if total else 4}%;background:{colors[i % len(colors)]}'></i>"
        for i, (_, c) in enumerate(top)
    )
    return f"""
    <div class='dash-card' id='categorieen'><h3>Eisen per categorie</h3>
        <div class='category-wrap'>
            <div class='donut'><div><strong>{total}</strong><span>totaal</span></div></div>
            <div class='legend'>{legend or '<p class=muted>Nog geen categorieën.</p>'}</div>
        </div>
        <div class='bar-stack'>{bars}</div><a href='#eisenbrowser'>Bekijk alle eisen →</a>
    </div>
    """


def attention_card(points):
    rows = "".join(f"<li><span class='warn'>△</span><p>{esc(p)} genoemd in het PvE</p></li>" for p in points[:8])
    content = f"<ul class='icon-list warn-list'>{rows}</ul>" if rows else "<p class='muted'>Geen aandachtspunten gevonden.</p>"
    return f"<div class='dash-card' id='aandachtspunten'><h3>Aandachtspunten</h3>{content}<a href='#eisenbrowser'>Zoek aandachtspunten →</a></div>"


def checklist_card(items):
    rows = "".join(f"<div class='check-row'><span></span><p>{esc(text)}</p><b>{esc(tag)}</b></div>" for text, tag in items)
    return f"<div class='dash-card' id='checklist'><h3>Snelle acties / Checklist</h3>{rows}<a href='#eisenbrowser'>Naar eisenbrowser →</a></div>"


def summary_card(items):
    body = "".join(f"<p>{esc(i)}</p>" for i in items)
    return f"""
    <div class='summary-card' id='samenvatting'>
        <div class='summary-icon'>▤</div>
        <div><h3>AI Samenvatting</h3>{body or '<p>Geen samenvatting beschikbaar.</p>'}</div>
        <div class='summary-action'><a href='#samenvatting'>Volledige samenvatting bekijken →</a><a class='download-link' href='#eisenbrowser'>Naar eisenbrowser</a></div>
    </div>
    """



def future_modules_card():
    return """
    <div class="future-grid">
        <div class="future-card" id="nvi-assistent">
            <h3>NVI-assistent</h3>
            <p>Voor een volgende sprint: nota’s van inlichtingen toevoegen, vragen bundelen en wijzigingen markeren.</p>
            <span>Module voorbereid</span>
        </div>
        <div class="future-card" id="bijlagen">
            <h3>Bijlagen</h3>
            <p>Voor een volgende sprint: conceptovereenkomst, tarievenblad en formulieren naast het PvE analyseren.</p>
            <span>Module voorbereid</span>
        </div>
        <div class="future-card" id="instellingen">
            <h3>Instellingen</h3>
            <p>Voor een volgende sprint: exportinstellingen, rapportage-opmaak en organisatiewoordenlijst beheren.</p>
            <span>Module voorbereid</span>
        </div>
    </div>
    """


def dashboard_html(filename, pages, reqs, headings, client, subject, obligations, deadlines, points, checklist, summary):
    chapters = chapter_counts(reqs, headings)
    return (
        kpi_cards(pages, len(reqs), len(headings), len(obligations))
        + document_card(subject, client, filename)
        + f"<div class='grid'>{chapters_card(chapters)}{obligations_card(obligations)}{deadlines_card(deadlines)}</div>"
        + f"<div class='grid'>{category_card(chapters, len(reqs))}{attention_card(points)}{checklist_card(checklist)}</div>"
        + summary_card(summary)
        + future_modules_card()
    )


def analyze(file):
    empty_df = pd.DataFrame(columns=["eisnummer", "hoofdstuk", "korte tekst"])
    if file is None:
        return (
            sidebar_html(),
            empty_dashboard_html(),
            empty_df,
            empty_df
        )
    try:
        path = file.name if hasattr(file, "name") else str(file)
        filename = path.split("/")[-1]
        text, pages = extract_pdf(path)
        lines = split_lines(text)
        headings = find_headings(lines)
        reqs = parse_requirements(lines, headings)
        client = find_client(text)
        subject = find_subject(text)
        points = find_attention_points(text)
        obligations = find_obligations(text)
        deadlines = find_deadlines(text)
        checklist = make_checklist(points)
        summary = extractive_summary(text, points, reqs, headings)
        df = pd.DataFrame([
            {"eisnummer": r["eisnummer"], "hoofdstuk": r["hoofdstuk"], "korte tekst": short(r["tekst"], 260)}
            for r in reqs
        ])
        side = sidebar_html(filename, pages, len(reqs), len(headings), datetime.now().strftime("%d-%m-%Y %H:%M"))
        dash = dashboard_html(filename, pages, reqs, headings, client, subject, obligations, deadlines, points, checklist, summary)
        return side, dash, df, df
    except Exception as e:
        error = f"<div class='empty-panel error'><h2>Analyse mislukt</h2><p>{esc(e)}</p><p>Controleer of de PDF een tekstlaag bevat.</p></div>"
        return sidebar_html(), error, empty_df, empty_df


def filter_table(df, q):
    if df is None or df.empty:
        return pd.DataFrame(columns=["eisnummer", "hoofdstuk", "korte tekst"])
    if not q:
        return df
    q = str(q).lower().strip()
    if not q:
        return df
    mask = (
        df["eisnummer"].astype(str).str.lower().str.contains(q, regex=False, na=False)
        | df["hoofdstuk"].astype(str).str.lower().str.contains(q, regex=False, na=False)
        | df["korte tekst"].astype(str).str.lower().str.contains(q, regex=False, na=False)
    )
    return df[mask]


CSS = """
:root{--green:#009f7a;--green-dark:#007a60;--soft:#eaf8f2;--ink:#111936;--muted:#667085;--line:#e6eaf0;--bg:#f7f9fc;--orange:#f97316}
body,.gradio-container{margin:0!important;padding:0!important;max-width:none!important;background:var(--bg)!important;color:var(--ink)!important;font-family:Inter,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif!important}
#shell{min-height:100vh;background:#fff}.sidebar-col{background:linear-gradient(180deg,#fff,#fbfdfc);border-right:1px solid var(--line);padding:20px 14px!important}.main-col{background:var(--bg);padding:0 20px 26px!important}
.brand{display:flex;align-items:center;gap:12px;padding:0 8px 18px}.brand-logo{width:44px;height:44px;border-radius:50%;border:3px solid var(--green);color:var(--green-dark);display:grid;place-items:center;font-size:22px;font-weight:900}.brand h1{font-size:20px;line-height:1;margin:0 0 6px;letter-spacing:-.03em}.brand p{margin:0;font-size:12px;color:var(--green-dark);font-weight:700}
nav{display:flex;flex-direction:column;gap:7px}.nav-item{display:flex;gap:12px;align-items:center;padding:12px 14px;border-radius:10px;color:#172044;font-size:13px}.nav-item span{width:18px;font-weight:900}.nav-item b{font-weight:750}.nav-item.active{background:linear-gradient(90deg,rgba(0,159,122,.14),rgba(0,159,122,.04));border-left:3px solid var(--green);color:var(--green-dark)}
.analysis-info{margin-top:26px;background:linear-gradient(135deg,#f0fbf7,#fff);border:1px solid #cdeee4;border-radius:14px;padding:16px}.analysis-info h3{margin:0 0 12px;color:var(--green-dark);font-size:14px}.analysis-info div{margin-bottom:10px}.analysis-info span{display:block;color:#36564f;font-size:11px;margin-bottom:3px}.analysis-info b{display:block;font-size:12px;color:#111936;word-break:break-word}
.topbar{min-height:70px;display:flex;align-items:center;justify-content:space-between;border-bottom:1px solid var(--line);margin:0 -20px 14px;padding:12px 20px;background:rgba(255,255,255,.88);backdrop-filter:blur(8px)}.page-title{font-size:20px;font-weight:900;letter-spacing:-.03em}.page-subtitle{font-size:13px;color:var(--muted);margin-top:4px}.top-pills{display:flex;gap:8px;flex-wrap:wrap}.top-pills span{background:#fff;border:1px solid var(--line);border-radius:999px;padding:8px 11px;font-size:12px;font-weight:800;color:#344054}
#upload-card{background:#fff;border:1px solid var(--line);border-radius:14px;padding:15px!important;box-shadow:0 8px 28px rgba(17,25,54,.06);margin-bottom:12px}.upload-title{font-weight:900;font-size:16px;margin-bottom:4px}.upload-sub{color:var(--muted);font-size:13px;margin-bottom:10px}button.primary,.gradio-button.primary{background:var(--green)!important;color:#fff!important;border:none!important;border-radius:12px!important;font-weight:800!important}
.document-card{background:#fff;border:1px solid var(--line);border-radius:14px;box-shadow:0 8px 28px rgba(17,25,54,.07);padding:18px;margin-bottom:12px}.doc-head{display:grid;grid-template-columns:92px 1fr;gap:18px;align-items:center}.pdf-icon{width:72px;height:72px;border-radius:50%;background:#fff;border:1px solid var(--line);box-shadow:0 6px 22px rgba(17,25,54,.08);display:grid;place-items:center;position:relative}.pdf-icon:before{content:"";width:39px;height:49px;border:5px solid #df2d2d;border-radius:4px}.pdf-icon span{position:absolute;bottom:12px;background:#df2d2d;color:#fff;font-size:11px;font-weight:900;border-radius:3px;padding:2px 5px}.doc-head h2{margin:6px 0 5px;font-size:18px}.doc-head p{margin:0 0 8px;font-size:13px}.doc-head strong{font-size:13px}
.doc-meta{border-top:1px solid var(--line);display:grid;grid-template-columns:repeat(6,1fr);margin-top:14px;padding-top:14px}.doc-meta div{border-right:1px solid var(--line);padding:0 16px}.doc-meta div:first-child{padding-left:0}.doc-meta div:last-child{border-right:0}.doc-meta span{display:block;font-size:11px;font-weight:800;margin-bottom:8px}.doc-meta b{font-size:13px}.pill-ok{display:inline-block;background:#dff7e9;color:var(--green-dark);border-radius:999px;padding:6px 12px}
.grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px;margin-bottom:12px}.dash-card,.summary-card,.empty-panel,.browser-card{background:#fff;border:1px solid var(--line);border-radius:14px;box-shadow:0 8px 28px rgba(17,25,54,.06);padding:16px}.dash-card h3,.summary-card h3{margin:0 0 16px;font-size:16px}.dash-card a,.summary-action a{display:inline-block;margin-top:13px;color:var(--green-dark);font-size:13px;font-weight:800;text-decoration:none}.muted{color:var(--muted);font-size:13px}
.table-row{display:grid;grid-template-columns:28px 1fr 42px;align-items:center;border-bottom:1px solid var(--line);min-height:28px;font-size:12px}.table-row p{margin:0}.table-row b{justify-self:end;background:#e5f7ec;color:var(--green-dark);border-radius:8px;padding:3px 10px}
.icon-list{list-style:none;padding:0;margin:0;display:flex;flex-direction:column;gap:10px}.icon-list li{display:grid;grid-template-columns:20px 1fr;gap:8px;align-items:start;font-size:12px}.icon-list p{margin:0;line-height:1.4}.check{width:14px;height:14px;border:1.8px solid var(--green);color:var(--green);display:grid;place-items:center;border-radius:50%;font-size:9px;font-weight:900}.warn{color:var(--orange);font-weight:900;font-size:16px}
.deadline-row{display:grid;grid-template-columns:20px 1fr auto;gap:8px;align-items:center;border-bottom:1px solid var(--line);padding-bottom:7px;margin-bottom:8px}.deadline-row p{margin:0;font-size:12px;line-height:1.35}.deadline-row b{background:#e5f7ec;color:var(--green-dark);border-radius:8px;padding:4px 10px;font-size:11px;white-space:nowrap}
.category-wrap{display:grid;grid-template-columns:150px 1fr;align-items:center;gap:15px}.donut{width:132px;height:132px;border-radius:50%;background:conic-gradient(#2f80ed 0 30%,#27ae60 30% 52%,#f2b01e 52% 70%,#7b61ff 70% 84%,#20c997 84% 93%,#ff7a45 93% 100%);display:grid;place-items:center}.donut div{width:82px;height:82px;background:#fff;border-radius:50%;display:grid;place-items:center;text-align:center}.donut strong{font-size:28px;line-height:1}.donut span{font-size:12px}.legend{display:flex;flex-direction:column;gap:10px}.legend div{display:grid;grid-template-columns:12px 1fr 28px;gap:9px;align-items:center;font-size:12px}.legend span{width:10px;height:10px;border-radius:3px}.legend b{justify-self:end}.bar-stack{display:flex;height:5px;border-radius:999px;overflow:hidden;margin-top:16px;background:#edf0f5}.bar-stack i{display:block}
.check-row{display:grid;grid-template-columns:18px 1fr auto;gap:8px;align-items:center;border-bottom:1px solid var(--line);padding:7px 0}.check-row span{width:12px;height:12px;border:1px solid #b8beca;border-radius:3px}.check-row p{margin:0;font-size:12px}.check-row b{background:#eaf8f2;color:var(--green-dark);border-radius:8px;padding:4px 9px;font-size:11px}
.summary-card{display:grid;grid-template-columns:50px 1fr 220px;gap:16px;align-items:start;margin-bottom:12px}.summary-icon{width:42px;height:42px;border-radius:14px;background:#eaf8f2;color:var(--green-dark);display:grid;place-items:center;font-size:24px;font-weight:900}.summary-card p{font-size:13px;line-height:1.55;margin:0 0 8px}.summary-action{text-align:right}.summary-action button{border:1px solid var(--green);color:var(--green-dark);background:#fff;border-radius:8px;padding:12px 14px;font-weight:800;margin-top:24px}.empty-panel{padding:38px}.empty-panel h2{margin-top:0}.error{color:#9b1c1c}
.browser-card h2{margin:0 0 6px;font-size:18px}.browser-card p{margin:0 0 12px;color:var(--muted);font-size:13px}.gradio-dataframe{border-radius:14px!important;overflow:hidden!important}.footer{color:#667085;font-size:12px;text-align:center;margin:18px 0}

.kpi-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px;margin-bottom:12px}
.kpi-card{background:#fff;border:1px solid var(--line);border-radius:14px;box-shadow:0 8px 28px rgba(17,25,54,.06);padding:16px}
.kpi-card span{display:block;color:var(--muted);font-size:12px;font-weight:900;text-transform:uppercase;letter-spacing:.04em}
.kpi-card strong{display:block;font-size:34px;line-height:1;margin:10px 0 6px;color:var(--ink);letter-spacing:-.04em}
.kpi-card p{margin:0;color:var(--muted);font-size:13px}
.top-pills a{background:#fff;border:1px solid var(--line);border-radius:999px;padding:8px 11px;font-size:12px;font-weight:800;color:#344054;text-decoration:none}
.download-link{display:inline-block;border:1px solid var(--green);color:var(--green-dark)!important;background:#fff;border-radius:8px;padding:12px 14px;font-weight:800;margin-top:24px;text-decoration:none}
@media(max-width:1180px){.kpi-grid{grid-template-columns:repeat(2,1fr)}}
@media(max-width:700px){.kpi-grid{grid-template-columns:1fr}}


html{scroll-behavior:smooth}
.nav-item{text-decoration:none!important}
.future-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px;margin-bottom:12px}
.future-card{background:#fff;border:1px dashed #cfd8e3;border-radius:14px;box-shadow:0 8px 28px rgba(17,25,54,.04);padding:16px}
.future-card h3{margin:0 0 10px;font-size:16px}
.future-card p{margin:0 0 12px;color:var(--muted);font-size:13px;line-height:1.45}
.future-card span{display:inline-block;background:#f2f4f7;color:#344054;border-radius:999px;padding:6px 10px;font-size:12px;font-weight:800}
@media(max-width:1180px){.future-grid{grid-template-columns:1fr}}

@media(max-width:1180px){.sidebar-col{display:none!important}.grid{grid-template-columns:1fr}.doc-meta{grid-template-columns:repeat(2,1fr)}.summary-card{grid-template-columns:1fr}.summary-action{text-align:left}.topbar{display:block}.top-pills{margin-top:10px}}
"""


def find_default_pdf():
    """Find the bundled demo PDF when it is placed next to app.py or in the working directory.

    Hugging Face Spaces normally starts the app from the repository/root folder.
    This helper is deliberately tolerant for local testing and for browser/OS
    filename suffixes such as (1), (2), etc.
    """
    search_dirs = []
    for folder in [Path.cwd(), Path(__file__).resolve().parent, Path("/mnt/data")]:
        if folder.exists() and folder not in search_dirs:
            search_dirs.append(folder)

    exact_names = [
        DEFAULT_PDF_FILENAME,
        f"{DEFAULT_PDF_STEM}(1).pdf",
        f"{DEFAULT_PDF_STEM}(2).pdf",
        f"{DEFAULT_PDF_STEM}.pdf",
    ]

    for folder in search_dirs:
        for name in exact_names:
            candidate = folder / name
            if candidate.exists() and candidate.is_file():
                return candidate

    for folder in search_dirs:
        matches = sorted(folder.glob(f"{DEFAULT_PDF_STEM}*.pdf"))
        if matches:
            return matches[0]

    return None


def load_startup_state():
    default_path = find_default_pdf()
    if default_path is not None:
        return analyze(str(default_path))

    empty_df = pd.DataFrame(columns=["eisnummer", "hoofdstuk", "korte tekst"])
    return sidebar_html(), empty_dashboard_html(), empty_df, empty_df


startup_sidebar, startup_dashboard, startup_table, startup_state = load_startup_state()


with gr.Blocks(title="TenderKompas AI – PvE Navigator") as demo:
    state = gr.State(startup_state)

    with gr.Row(elem_id="shell"):
        with gr.Column(scale=1, min_width=230, elem_classes=["sidebar-col"]):
            sidebar_component = gr.HTML(startup_sidebar)

        with gr.Column(scale=5, elem_classes=["main-col"]):
            gr.HTML(top_intro_html())

            with gr.Group(elem_id="upload-card"):
                gr.HTML("<div class='upload-title'>Upload & analyse</div><div class='upload-sub'>Upload één Programma van Eisen-PDF. De analyse draait lokaal met PyMuPDF en regex.</div>")
                with gr.Row():
                    pdf = gr.File(label="Programma van Eisen PDF", file_types=[".pdf"], scale=3)
                    button = gr.Button("Analyse uitvoeren", variant="primary", scale=1)

            dashboard_component = gr.HTML(startup_dashboard)

            with gr.Group(elem_classes=["browser-card"], elem_id="eisenbrowser"):
                gr.HTML("<h2>Eisenbrowser</h2><p>Zoek door alle gevonden eisen. De tabel wordt gevuld na analyse.</p>")
                search = gr.Textbox(label="Zoeken in eisen", placeholder="Bijvoorbeeld: privacy, VOG, facturatie, social return")
                table = gr.Dataframe(
                    value=startup_table,
                    headers=["eisnummer", "hoofdstuk", "korte tekst"],
                    datatype=["str", "str", "str"],
                    interactive=False,
                    wrap=True
                )

            gr.HTML("<div class='footer'>TenderKompas AI is een demonstratiemodel. Controleer altijd zelf de originele aanbestedingsstukken. De applicatie neemt geen besluit en beoordeelt niet automatisch of Reakt aan eisen voldoet.</div>")

    button.click(analyze, inputs=[pdf], outputs=[sidebar_component, dashboard_component, table, state])
    search.change(filter_table, inputs=[state, search], outputs=[table])
    search.submit(filter_table, inputs=[state, search], outputs=[table])


if __name__ == "__main__":
    demo.launch(css=CSS, theme=gr.themes.Soft())
