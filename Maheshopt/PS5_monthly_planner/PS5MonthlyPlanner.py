import gradio as gr
import datetime
import json
import os
try:
    import requests
    _HAS_REQUESTS = True
except Exception:
    requests = None
    _HAS_REQUESTS = False
import urllib.request
import urllib.error
import time
import re
import io

# (The full Blocks-based `demo` is defined later in this file.)
# simple in-memory cache for fetched pages to avoid repeated requests and 429s
from urllib.parse import urljoin, urldefrag, quote
_URL_CACHE = {}
_CACHE_TTL = 600  # seconds
_LAST_SCRAPE_SUCCESS = True
import sys
import subprocess
import importlib

def ensure_package_import(package_name, import_name=None):
    """Ensure a package is importable; install via pip into the current interpreter if missing."""
    import_name = import_name or package_name
    try:
        return importlib.import_module(import_name)
    except Exception:
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", package_name])
            return importlib.import_module(import_name)
        except Exception as e:
            raise ImportError(f"Could not install or import {package_name}: {e}")

# Ensure BeautifulSoup (bs4) is available
_bs4 = ensure_package_import("beautifulsoup4", "bs4")
from bs4 import BeautifulSoup
_pil = ensure_package_import("Pillow", "PIL")
from PIL import Image

def fetch_url_text(url, timeout=10, headers=None, max_retries=2, backoff=0.5):
    """Fetch URL and return text. Use requests if available, otherwise urllib.
    Uses realistic browser-like headers and retry/backoff to reduce 429s.
    """
    headers = headers or {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
        "Accept-Language": "en-GB,en-US;q=0.9,en;q=0.8",
        "Referer": "https://www.google.com/",
    }
    # return cached copy if still fresh
    now = time.time()
    cached = _URL_CACHE.get(url)
    if cached and now - cached[0] < _CACHE_TTL:
        return cached[1]
    # retry/backoff for transient 429 responses
    retry_backoff = backoff
    for attempt in range(max_retries):
        if _HAS_REQUESTS:
            try:
                resp = requests.get(url, timeout=timeout, headers=headers)
                if resp.status_code == 429:
                    raise urllib.error.HTTPError(url, 429, "Too Many Requests", hdrs=None, fp=None)
                resp.raise_for_status()
                text = resp.text
                _URL_CACHE[url] = (time.time(), text)
                return text
            except Exception as e:
                # if 429, backoff and retry; otherwise fall through to urllib fallback
                if isinstance(e, urllib.error.HTTPError) and e.code == 429:
                    time.sleep(retry_backoff)
                    retry_backoff *= 2
                    continue
        # urllib fallback
        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                raw = r.read()
                try:
                    text = raw.decode(r.headers.get_content_charset(failobj="utf-8"))
                except Exception:
                    text = raw.decode("utf-8", errors="replace")
                _URL_CACHE[url] = (time.time(), text)
                return text
        except urllib.error.HTTPError as e:
            if e.code == 429:
                time.sleep(retry_backoff)
                retry_backoff *= 2
                continue
            raise
        except Exception:
            # final fallback - raise after retries
            if attempt == max_retries - 1:
                raise
            time.sleep(retry_backoff)
            retry_backoff *= 2
            continue


def fetch_cover_image_obj(image_url, timeout=10):
    """Download a remote image and return a PIL Image for reliable Gradio rendering."""
    if not image_url:
        return None
    try:
        if _HAS_REQUESTS:
            resp = requests.get(image_url, timeout=timeout)
            resp.raise_for_status()
            return Image.open(io.BytesIO(resp.content)).convert("RGB")
        req = urllib.request.Request(image_url)
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read()
            return Image.open(io.BytesIO(raw)).convert("RGB")
    except Exception:
        return None


def build_placeholder_cover_data_uri(title):
    safe_title = (title or "PS5 Game").strip() or "PS5 Game"
    svg = (
        "<svg xmlns='http://www.w3.org/2000/svg' width='640' height='360' viewBox='0 0 640 360'>"
        "<defs><linearGradient id='g' x1='0' y1='0' x2='1' y2='1'>"
        "<stop offset='0%' stop-color='#1f3b73'/><stop offset='100%' stop-color='#4f85ff'/></linearGradient></defs>"
        "<rect width='640' height='360' fill='url(#g)'/>"
        "<rect x='16' y='16' width='608' height='328' rx='18' fill='none' stroke='rgba(255,255,255,0.35)'/>"
        "<text x='32' y='70' fill='white' font-size='22' font-family='Segoe UI, Arial, sans-serif' opacity='0.85'>PS5 Monthly Planner</text>"
        f"<text x='32' y='185' fill='white' font-size='34' font-family='Segoe UI, Arial, sans-serif' font-weight='700'>{safe_title}</text>"
        "</svg>"
    )
    return "data:image/svg+xml;utf8," + quote(svg)

MEMORY_FILE = "planner_memory.json"
GAMES_CACHE_FILE = "monthly_games_cache.json"
CURRENT_GAME_URLS = []
LAST_GAMES = []

# --- Memory Helpers ---
def load_memory():
    if os.path.exists(MEMORY_FILE):
        try:
            with open(MEMORY_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except json.JSONDecodeError as e:
            print(f"Warning: could not parse {MEMORY_FILE}: {e}. Resetting saved history.")
            try:
                with open(MEMORY_FILE, "r", encoding="utf-8", errors="replace") as f:
                    bad_data = f.read()
                with open(MEMORY_FILE + ".backup", "w", encoding="utf-8") as backup:
                    backup.write(bad_data)
            except Exception:
                pass
            return []
        except Exception as e:
            print(f"Warning: unexpected error loading {MEMORY_FILE}: {e}")
            return []
    return []

def save_memory(history):
    with open(MEMORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, indent=2, default=str)


def games_cache_key(month_name, year):
    return f"{year}-{month_name}"


def load_games_cache():
    if not os.path.exists(GAMES_CACHE_FILE):
        return {}
    try:
        with open(GAMES_CACHE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def save_games_cache(cache):
    with open(GAMES_CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(cache, f, indent=2, default=str)


def save_month_games_to_cache(month_name, year, games):
    cache = load_games_cache()
    key = games_cache_key(month_name, year)
    serializable_games = []
    for g in games:
        item = dict(g)
        rd = item.get("release_date")
        if isinstance(rd, datetime.date):
            item["release_date"] = rd.isoformat()
        serializable_games.append(item)
    cache[key] = serializable_games
    save_games_cache(cache)


def deserialize_cached_games(games):
    out = []
    for g in games:
        item = dict(g)
        rd = item.get("release_date")
        if isinstance(rd, str):
            try:
                item["release_date"] = datetime.date.fromisoformat(rd)
            except Exception:
                item["release_date"] = datetime.date.max
        out.append(item)
    return out


def load_month_games_from_cache(month_name, year):
    cache = load_games_cache()
    key = games_cache_key(month_name, year)
    games = cache.get(key, [])
    return deserialize_cached_games(games)

chat_history = load_memory()

# --- Fetch PS5 Releases dynamically from PS Index ---
def parse_release_date(date_str, default_year):
    if not date_str:
        return datetime.date.max
    normalized = date_str.strip()
    if normalized.upper() in {"TBA", "TBD", "UNKNOWN"}:
        return datetime.date.max
    try:
        if re.match(r"^\d{4}-\d{2}-\d{2}$", normalized):
            return datetime.datetime.strptime(normalized, "%Y-%m-%d").date()
        if re.match(r"^\d{1,2}\s+[A-Za-z]+\s+\d{4}$", normalized):
            return datetime.datetime.strptime(normalized, "%d %B %Y").date()
        if re.match(r"^\d{1,2}\s+[A-Za-z]+$", normalized):
            return datetime.datetime.strptime(f"{normalized} {default_year}", "%d %B %Y").date()
    except Exception:
        return datetime.date.max
    return datetime.date.max


def fetch_games(month, year):
    games = []
    month_num = datetime.datetime.strptime(month, "%B").month
    month_name_lower = month.lower()
    url_primary = f"https://www.psindex.co.uk/releases/{year}/{month_num:02d}"
    url_calendar = f"https://www.psindex.co.uk/releases/{year}/{month_num:02d}/calendar"
    urls = [url_primary, url_calendar]
    base = "https://www.psindex.co.uk"
    seen = set()
    months = r"January|February|March|April|May|June|July|August|September|October|November|December"
    date_pattern = re.compile(rf"\b(\d{{1,2}}\s+(?:{months})(?:\s+\d{{4}})?)\b", re.IGNORECASE)

    for url in urls:
        try:
            html = fetch_url_text(url, timeout=10)
            soup = BeautifulSoup(html, "html.parser")
            entries = soup.select("div.min-w-0.space-y-2") or soup.select("div.space-y-2") or soup.select("article")

            for entry in entries:
                title_link = None
                for a in entry.find_all("a", href=re.compile(r"^/games/")):
                    text = a.get_text(strip=True)
                    label = a.get("aria-label", "").strip()
                    title_candidate = text or label
                    if not title_candidate:
                        continue
                    title_candidate = title_candidate.replace("View ", "").strip()
                    if title_candidate.lower() in ("view game", "view editions", "view edition"):
                        continue
                    title_link = a
                    title = title_candidate
                    break

                if not title_link:
                    continue

                href = title_link.get("href")
                if not href:
                    continue
                clean_href, _ = urldefrag(urljoin(base, href))
                if clean_href in seen:
                    continue
                seen.add(clean_href)

                date_tag = entry.find("p")
                surrounding = entry.get_text(" ", strip=True)
                if date_tag:
                    date_text = date_tag.get_text(strip=True)
                else:
                    date_text = ""
                    for nested in entry.find_all(["span", "div"]):
                        candidate = nested.get_text(strip=True)
                        if date_pattern.search(candidate):
                            date_text = candidate
                            break
                date_match = date_pattern.search(date_text or surrounding)
                date = date_match.group(1) if date_match else "TBA"
                release_date = parse_release_date(date, year)

                cover = None


            def build_placeholder_cover_data_uri(title):
                safe_title = (title or "PS5 Game").strip() or "PS5 Game"
                svg = (
                    "<svg xmlns='http://www.w3.org/2000/svg' width='640' height='360' viewBox='0 0 640 360'>"
                    "<defs><linearGradient id='g' x1='0' y1='0' x2='1' y2='1'>"
                    "<stop offset='0%' stop-color='#1f3b73'/><stop offset='100%' stop-color='#4f85ff'/></linearGradient></defs>"
                    "<rect width='640' height='360' fill='url(#g)'/>"
                    "<rect x='16' y='16' width='608' height='328' rx='18' fill='none' stroke='rgba(255,255,255,0.35)'/>"
                    "<text x='32' y='70' fill='white' font-size='22' font-family='Segoe UI, Arial, sans-serif' opacity='0.85'>PS5 Monthly Planner</text>"
                    f"<text x='32' y='185' fill='white' font-size='34' font-family='Segoe UI, Arial, sans-serif' font-weight='700'>{safe_title}</text>"
                    "</svg>"
                )
                return "data:image/svg+xml;utf8," + quote(svg)
                img_tag = entry.find("img")
                if img_tag:
                    for attr in ("src", "data-src", "data-lazy-src"):
                        candidate = img_tag.get(attr)
                        if candidate:
                            cover = candidate.strip()
                            break
                if cover:
                    if cover.startswith("//"):
                        cover = "https:" + cover
                    elif cover.startswith("/"):
                        cover = urljoin(base, cover)

                hours = 10 + (len(games) % 5) * 10
                games.append({
                    "title": title,
                    "popularity": 80,
                    "hours": hours,
                    "cover": cover,
                    "date": date,
                    "release_date": release_date,
                    "url": clean_href,
                })

            if games:
                break
        except Exception as e:
            print("Error fetching games from", url, e)
            continue

    # Keep only games that truly belong to the requested month/year.
    # This prevents cache pollution if an upstream page returns wrong-month results.
    filtered_games = []
    for g in games:
        rd = g.get("release_date")
        if isinstance(rd, datetime.date) and rd != datetime.date.max:
            if rd.year == year and rd.month == month_num:
                filtered_games.append(g)
            continue

        # Fallback for non-parseable dates (e.g., "TBA"): rely on date text.
        date_text = (g.get("date") or "").strip().lower()
        if month_name_lower not in date_text:
            continue
        year_match = re.search(r"\b(20\d{2})\b", date_text)
        if year_match and int(year_match.group(1)) != year:
            continue
        filtered_games.append(g)

    games = filtered_games
    games.sort(key=lambda g: (g.get("release_date", datetime.date.max), g.get("title", "").lower()))

    # Debug: report how many games were found
    print(f"Fetched {len(games)} titles for {month} {year}")

    global _LAST_SCRAPE_SUCCESS, CURRENT_GAME_URLS
    if not games:
        print("No titles found — site may be rate-limiting or structure has changed.")
        _LAST_SCRAPE_SUCCESS = False
        CURRENT_GAME_URLS = []
    else:
        _LAST_SCRAPE_SUCCESS = True
        CURRENT_GAME_URLS = [g.get("url") for g in games]

    return games


# removed bulk cover fetching to avoid rate-limits and generic images

# --- Planner Logic ---
def generate_planner(month_name, year, selected_game, games):
    if not selected_game:
        return "<div style='padding:12px; background:#ffe0e0; color:#821515; border-radius:8px;'>Please choose a game before generating the planner.</div>", gr.update()

    if not games:
        games = LAST_GAMES or []

    game = next((g for g in games if g.get("title") == selected_game), None)
    if not game:
        return f"<div style='padding:12px; background:#ffe0e0; color:#821515; border-radius:8px;'>Game '{selected_game}' not found in the currently loaded list.</div>", gr.update()

    month_num = datetime.datetime.strptime(month_name, "%B").month
    if month_num == 12:
        next_month = 1
        next_year = year + 1
    else:
        next_month = month_num + 1
        next_year = year
    days = (datetime.date(next_year, next_month, 1) - datetime.date(year, month_num, 1)).days
    daily_hours = round(game.get("hours", 40) / days, 2) if days else 0

    planner_html = f"<h3>🎯 Planner for {selected_game} ({month_name} {year})</h3>"
    planner_html += f"<p>Selected game release date: {game.get('date')}.</p>"
    planner_html += f"<p>Estimated daily play: <strong>{daily_hours}</strong> hrs/day to complete in the month.</p>"
    planner_html += "<table style='width:100%; border-collapse: collapse;'>"
    planner_html += "<tr style='background-color:#2a5298; color:white;'><th>Title</th><th>Release Date</th><th>Daily Hours</th><th>Game URL</th></tr>"
    planner_html += f"<tr style='background-color:#f0f8ff;'><td>{game['title']}</td><td>{game['date']}</td><td>{daily_hours}</td><td><a href='{game['url']}' target='_blank'>View</a></td></tr>"
    planner_html += "</table>"

    chat_history.append({
        "month": month_name,
        "year": year,
        "planner": planner_html,
        "covers": [game.get("cover")],
        "games": games,
        "selected_game": selected_game
    })
    save_memory(chat_history)

    if chat_history:
        last_choice = f"{chat_history[-1]['month']} {chat_history[-1]['year']}"
        past_update = gr.update(choices=[last_choice], value=last_choice)
    else:
        past_update = gr.update(choices=[], value=None)

    return planner_html, past_update

def load_past_planner(selection):
    for entry in chat_history:
        if f"{entry['month']} {entry['year']}" == selection:
            planner = entry.get("planner", "No planner found")
            games = entry.get("games", [])
            game_choices = [g.get("title") for g in games]
            game_update = gr.update(choices=game_choices, value=game_choices[0] if game_choices else None)
            return planner, game_update
    return "No planner found", gr.update(choices=[], value=None)


def show_game_details(selection, month_name, year):
    if not selection:
        return "", ""
    game = None
    for g in LAST_GAMES:
        if g.get("title") == selection:
            game = g
            break
    if not game:
        return "<div style='padding:8px; color:#6b7280;'>No cover available.</div>", "Game not found"

    try:
        month_num = datetime.datetime.strptime(month_name, "%B").month
        if month_num == 12:
            next_month = 1
            next_year = year + 1
        else:
            next_month = month_num + 1
            next_year = year
        days = (datetime.date(next_year, next_month, 1) - datetime.date(year, month_num, 1)).days
    except Exception:
        days = 30

    daily_hours = round(game.get("hours", 40) / days, 2) if days else 0

    cover = game.get("cover")
    if not cover and game.get("url"):
        try:
            page = fetch_url_text(game.get("url"), timeout=8, max_retries=4, backoff=1)
            gs = BeautifulSoup(page, "html.parser")
            og = gs.find("meta", property="og:image") or gs.find("meta", attrs={"name": "og:image"})
            tw = gs.find("meta", attrs={"name": "twitter:image"})
            if og and og.get("content"):
                cover = og.get("content")
            elif tw and tw.get("content"):
                cover = tw.get("content")
            else:
                for script in gs.find_all("script", attrs={"type": "application/ld+json"}):
                    raw = script.string or script.get_text("", strip=True)
                    if not raw:
                        continue
                    try:
                        data = json.loads(raw)
                    except Exception:
                        continue

                    candidates = data if isinstance(data, list) else [data]
                    found = None
                    for item in candidates:
                        if not isinstance(item, dict):
                            continue
                        image_value = item.get("image")
                        if isinstance(image_value, str) and image_value.strip():
                            found = image_value.strip()
                            break
                        if isinstance(image_value, list) and image_value:
                            first = image_value[0]
                            if isinstance(first, str) and first.strip():
                                found = first.strip()
                                break
                        if isinstance(image_value, dict):
                            url_value = image_value.get("url")
                            if isinstance(url_value, str) and url_value.strip():
                                found = url_value.strip()
                                break
                    if found:
                        cover = found
                        break

            if not cover:
                img = gs.find("img")
                if img and img.get("src"):
                    cover = img.get("src")
            if cover:
                if cover.startswith("//"):
                    cover = "https:" + cover
                elif cover.startswith("/"):
                    cover = urljoin("https://www.psindex.co.uk", cover)
        except Exception:
            cover = None

    if cover:
        game["cover"] = cover
        try:
            save_month_games_to_cache(month_name, year, LAST_GAMES)
        except Exception:
            pass
        safe_cover = cover.replace('"', '%22')
    else:
        safe_cover = build_placeholder_cover_data_uri(game.get("title"))

    cover_obj = (
        f"<div style='display:flex; justify-content:center; align-items:center; min-height:220px;'>"
        f"<img src=\"{safe_cover}\" alt=\"{game.get('title', 'Game')} cover\" "
        f"style='max-width:100%; max-height:320px; border-radius:14px; border:1px solid rgba(31,42,61,0.12); box-shadow:0 8px 24px rgba(31,42,61,0.12);' "
        f"loading='lazy' referrerpolicy='no-referrer' />"
        f"</div>"
    )
    info_html = f"<strong>{game.get('title')}</strong><br>Release: {game.get('date')}<br>Daily hours to finish in month: {daily_hours} hrs/day"
    return cover_obj, info_html

PAGE_SIZE = 12

def render_games_page(games, page=1):
    total = len(games)
    if total == 0:
        return "<p>No games found for this month.</p>"
    start = (page - 1) * PAGE_SIZE
    end = start + PAGE_SIZE
    page_games = games[start:end]
    html = f"<h3>🎮 PS5 Releases for page {page} of {((total - 1) // PAGE_SIZE) + 1}</h3>"
    html += f"<p>Showing {start + 1}-{min(end, total)} of {total} games.</p>"
    html += "<table style='width:100%; border-collapse: collapse;'>"
    html += "<tr style='background-color:#2a5298; color:white;'><th>Title</th><th>Release Date</th><th>URL</th></tr>"
    for g in page_games:
        html += f"<tr style='background-color:#f0f8ff;'><td>{g['title']}</td><td>{g['date']}</td><td><a href='{g['url']}' target='_blank'>View</a></td></tr>"
    html += "</table>"
    return html

def load_monthly_games(month_name, year):
    # Use month-specific cache first for fast/consistent UX on Spaces.
    games = load_month_games_from_cache(month_name, year)
    used_cached_fallback = bool(games)

    # If cache is missing, fetch from live source and persist for future loads.
    if not games:
        games = fetch_games(month_name, year)
        if games:
            save_month_games_to_cache(month_name, year, games)
            used_cached_fallback = False
    global LAST_GAMES
    LAST_GAMES = games
    game_choices = [g.get("title") for g in games]
    game_update = gr.update(choices=game_choices, value=game_choices[0] if game_choices else None)
    games_html = render_games_page(games, page=1)
    page_state = 1
    if games and not used_cached_fallback:
        info_text = f"Loaded {len(games)} games for {month_name} {year}. Choose a game and click Generate Planner."
    elif games and used_cached_fallback:
        info_text = f"Loaded {len(games)} cached games for {month_name} {year} (live source temporarily unavailable)."
    else:
        info_text = "No verified games could be loaded for this month right now. Please retry in a moment."
    return games_html, game_update, page_state, info_text, games, gr.update(value="")

def change_games_page(direction, games, current_page):
    if not games:
        return "<p>No games loaded yet.</p>", current_page
    total_pages = ((len(games) - 1) // PAGE_SIZE) + 1
    if direction == "next":
        current_page = min(total_pages, current_page + 1)
    elif direction == "prev":
        current_page = max(1, current_page - 1)
    return render_games_page(games, page=current_page), current_page


def prev_games_page(games, current_page):
    return change_games_page("prev", games, current_page)


def next_games_page(games, current_page):
    return change_games_page("next", games, current_page)


def filter_game_choices(search_text, games):
    if not games:
        return gr.update(choices=[], value=None)
    query = (search_text or "").strip().lower()
    if not query:
        filtered = [g.get("title") for g in games]
    else:
        filtered = [g.get("title") for g in games if query in g.get("title", "").lower()]
    if not filtered:
        filtered = [g.get("title") for g in games]
    return gr.update(choices=filtered, value=filtered[0] if filtered else None)

months = [datetime.date(2000, m, 1).strftime("%B") for m in range(1, 13)]
years = list(range(2024, 2030))

APP_CSS = """
            html, body {
                min-height: 100%;
                margin: 0;
                padding: 0;
                background: linear-gradient(180deg, #dbeeff 0%, #c3ddff 55%, #b2d4ff 100%);
                color: #1f2a3d;
                font-family: 'Segoe UI', sans-serif;
            }
            body, .gradio-container {
                background: transparent !important;
            }
            .gradio-container {
            background: rgba(235, 244, 255, 0.98);
            border: 1px solid rgba(31, 42, 61, 0.12);
            border-radius: 24px;
            padding: 28px;
            box-shadow: 0 20px 50px rgba(31, 42, 61, 0.12);
        }
        .gradio-row, .gradio-column {
            gap: 18px;
        }
        .gr-button, .gradio-button {
            border-radius: 999px;
            border: none;
            box-shadow: 0 10px 22px rgba(31, 42, 61, 0.15);
            transition: transform 0.18s ease, box-shadow 0.18s ease;
        }
        .gr-button:hover, .gradio-button:hover {
            transform: translateY(-2px);
            box-shadow: 0 14px 28px rgba(31, 42, 61, 0.2);
        }
        .gr-button.primary, .gradio-button.primary {
            background: linear-gradient(135deg, #ff7a18, #ffb71b);
            color: #17212e;
        }
        .gr-dropdown, .gr-input, .gr-html, .gradio-textbox, .gradio-dropdown {
            background: rgba(248,249,252,0.98) !important;
            color: #1f2a3d !important;
            border: 1px solid rgba(31, 42, 61, 0.14) !important;
            box-shadow: inset 0 0 0 1px rgba(255,255,255,0.8);
            border-radius: 18px;
        }
        .gr-dropdown select, .gr-input input, .gradio-textbox textarea {
            background: transparent !important;
            color: #1f2a3d !important;
        }
        .gr-html {
            padding: 18px;
            border-radius: 18px;
            background: rgba(248,249,252,0.98) !important;
        }
        .gr-html > * {
            color: #1f2a3d;
        }
        .gradio-gallery, .gradio-block {
            background: rgba(255,255,255,0.82);
        }
        .gr-image img {
            border-radius: 18px;
            border: 1px solid rgba(31, 42, 61, 0.12);
            box-shadow: 0 10px 30px rgba(31, 42, 61, 0.08);
        }
        a {
            color: #1f2a3d;
        }
        """

with gr.Blocks(css=APP_CSS) as demo:
    gr.Markdown("## 🕹️ PS5 Monthly Game Planner (Dynamic + Memory)")
    
    with gr.Row():
        current_month = datetime.date.today().strftime("%B")
        current_year = datetime.date.today().year
        month_dropdown = gr.Dropdown(choices=months, label="Month", value=current_month, interactive=True)
        year_dropdown = gr.Dropdown(choices=years, label="Year", value=current_year, interactive=True)
    load_btn = gr.Button("Load Games", variant="primary")
    output_status = gr.HTML("<p>Select a month and year, then click <strong>Load Games</strong> to fetch the full list.</p>")

    with gr.Row():
        with gr.Column(scale=2):
            games_html = gr.HTML(label="Game List")
            with gr.Row():
                prev_page_btn = gr.Button("Previous Page")
                next_page_btn = gr.Button("Next Page")
        with gr.Column(scale=1):
            game_search = gr.Textbox(label="Search games", placeholder="Type to filter the game list...", interactive=True)
            game_dropdown = gr.Dropdown(choices=[], label="Select Game")
            generate_btn = gr.Button("Generate Planner", variant="primary")
            output_cover = gr.HTML(label="Cover")
            output_info = gr.HTML(label="Game Info")

    planner_html = gr.HTML(label="Planner")
    games_state = gr.State([])
    page_state = gr.State(1)
    
    # show only the most recent saved planner in the past dropdown
    if chat_history:
        last_choice = f"{chat_history[-1]['month']} {chat_history[-1]['year']}"
        past_dropdown = gr.Dropdown(choices=[last_choice], label="View Past Planner", value=last_choice)
    else:
        past_dropdown = gr.Dropdown(choices=[], label="View Past Planner")
    past_btn = gr.Button("Load Past Planner")
    
    load_btn.click(load_monthly_games, inputs=[month_dropdown, year_dropdown], outputs=[games_html, game_dropdown, page_state, output_status, games_state, game_search])
    prev_page_btn.click(prev_games_page, inputs=[games_state, page_state], outputs=[games_html, page_state])
    next_page_btn.click(next_games_page, inputs=[games_state, page_state], outputs=[games_html, page_state])
    generate_btn.click(generate_planner, inputs=[month_dropdown, year_dropdown, game_dropdown, games_state], outputs=[planner_html, past_dropdown])
    # load past planner from saved history
    past_btn.click(load_past_planner, inputs=[past_dropdown], outputs=[planner_html, game_dropdown])
    game_search.change(filter_game_choices, inputs=[game_search, games_state], outputs=[game_dropdown])
    game_dropdown.change(show_game_details, inputs=[game_dropdown, month_dropdown, year_dropdown], outputs=[output_cover, output_info])

if __name__ == "__main__":
    demo.launch()
