import json
import os
import random
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
from urllib.parse import urljoin

import gradio as gr
import gspread
import pandas as pd
import requests
from anthropic import Anthropic
from bs4 import BeautifulSoup
from google.oauth2.service_account import Credentials
from zoneinfo import ZoneInfo


LINK_COLUMNS = [
    "id",
    "name",
    "url",
    "enabled",
    "interval_minutes",
    "last_run_utc",
    "next_run_utc",
    "last_status",
]

RESULT_COLUMNS = [
    "source_id",
    "source_name",
    "source_url",
    "scraped_at_utc",
    "product_name",
    "price",
    "producer_name",
    "location",
    "posted_date",
    "image_url",
    "listing_url",
    "raw_text",
    "claude_decision",
]

SHEET_ID = os.environ.get("GOOGLE_SHEET_ID", "").strip()
SERVICE_ACCOUNT_JSON = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON", "").strip()

LINKS_WORKSHEET = os.environ.get("LINKS_WORKSHEET", "links")
RESULTS_WORKSHEET = os.environ.get("RESULTS_WORKSHEET", "results")
SCHEDULER_TICK_SECONDS = int(os.environ.get("SCHEDULER_TICK_SECONDS", "60"))

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "").strip()
ANTHROPIC_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-6").strip()
CLAUDE_MAX_TOKENS = int(os.environ.get("CLAUDE_MAX_TOKENS", "160"))

REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    )
}

TORI_SESSION = requests.Session()
TORI_SESSION.headers.update({
    **REQUEST_HEADERS,
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,"
        "image/avif,image/webp,*/*;q=0.8"
    ),
    "Accept-Language": "fi-FI,fi;q=0.9,en-US;q=0.8,en;q=0.7",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
})


def get_tori_page(url, referer="https://www.tori.fi/", attempts=3):
    last_error = None

    for attempt in range(attempts):
        try:
            response = TORI_SESSION.get(
                url,
                headers={"Referer": referer},
                timeout=25,
                allow_redirects=True,
            )

            if response.status_code == 403:
                last_error = RuntimeError(
                    f"Tori returned 403 Forbidden for {url}"
                )
                if attempt < attempts - 1:
                    time.sleep(5 * (attempt + 1))
                    continue

            response.raise_for_status()
            return response

        except requests.RequestException as exc:
            last_error = exc
            if attempt < attempts - 1:
                time.sleep(3 * (attempt + 1))

    raise last_error or RuntimeError(f"Failed to fetch {url}")

SHEET_LOCK = threading.RLock()
RUN_LOCK = threading.Lock()


LOCAL_TZ = ZoneInfo("Europe/Berlin")

def utc_now():
    return datetime.now(LOCAL_TZ)

def iso_utc(dt):
    return dt.astimezone(LOCAL_TZ).replace(microsecond=0).isoformat()

def parse_utc(value):
    if value is None or str(value).strip() == "":
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except ValueError:
        return None


def google_client():
    if not SHEET_ID:
        raise RuntimeError("Missing GOOGLE_SHEET_ID Space variable.")
    if not SERVICE_ACCOUNT_JSON:
        raise RuntimeError("Missing GOOGLE_SERVICE_ACCOUNT_JSON Space secret.")

    info = json.loads(SERVICE_ACCOUNT_JSON)
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    credentials = Credentials.from_service_account_info(info, scopes=scopes)
    return gspread.authorize(credentials)


def spreadsheet():
    return google_client().open_by_key(SHEET_ID)


def ensure_worksheet(book, title, columns):
    try:
        ws = book.worksheet(title)
    except gspread.WorksheetNotFound:
        ws = book.add_worksheet(title=title, rows=1000, cols=max(20, len(columns)))

    first_row = ws.row_values(1)
    if first_row != columns:
        existing = ws.get_all_records() if first_row else []
        ws.clear()
        ws.update([columns], "A1")
        if existing:
            normalized = pd.DataFrame(existing).reindex(columns=columns).fillna("")
            ws.update([columns] + normalized.astype(str).values.tolist(), "A1")
    return ws


def initialize_sheets():
    with SHEET_LOCK:
        book = spreadsheet()
        ensure_worksheet(book, LINKS_WORKSHEET, LINK_COLUMNS)
        ensure_worksheet(book, RESULTS_WORKSHEET, RESULT_COLUMNS)


def read_table(worksheet_name, columns):
    with SHEET_LOCK:
        book = spreadsheet()
        ws = ensure_worksheet(book, worksheet_name, columns)
        records = ws.get_all_records()
    if not records:
        return pd.DataFrame(columns=columns)
    return pd.DataFrame(records).reindex(columns=columns).fillna("")


def write_table(worksheet_name, columns, df):
    clean = df.reindex(columns=columns).fillna("").astype(str)
    values = [columns] + clean.values.tolist()

    with SHEET_LOCK:
        book = spreadsheet()
        ws = ensure_worksheet(book, worksheet_name, columns)
        ws.clear()
        ws.update(values, "A1")


def read_links():
    df = read_table(LINKS_WORKSHEET, LINK_COLUMNS)
    if not df.empty:
        df["enabled"] = df["enabled"].astype(str).str.lower().isin(
            ["true", "1", "yes", "on"]
        )
        df["interval_minutes"] = pd.to_numeric(
            df["interval_minutes"], errors="coerce"
        ).fillna(60).astype(int)
    return df


def save_links(df):
    output = df.copy()
    if not output.empty:
        output["enabled"] = output["enabled"].map(
            lambda value: "TRUE" if bool(value) else "FALSE"
        )
    write_table(LINKS_WORKSHEET, LINK_COLUMNS, output)


def links_for_ui():
    try:
        df = read_links()
        return df, "Links loaded from Google Sheets."
    except Exception as exc:
        return pd.DataFrame(columns=LINK_COLUMNS), f"Error loading links: {exc}"


def add_link(name, url, enabled, interval_minutes):
    name = (name or "").strip()
    url = (url or "").strip()

    if not name:
        return *links_for_ui()[:1], "Name is required."
    if not url.startswith(("http://", "https://")):
        return *links_for_ui()[:1], "URL must start with http:// or https://."

    try:
        interval = max(1, int(interval_minutes))
        df = read_links()

        if not df.empty and url in df["url"].astype(str).tolist():
            return df, "That URL is already saved."

        now = utc_now()
        row = {
            "id": str(uuid.uuid4()),
            "name": name,
            "url": url,
            "enabled": bool(enabled),
            "interval_minutes": interval,
            "last_run_utc": "",
            "next_run_utc": iso_utc(now) if enabled else "",
            "last_status": "New",
        }

        df = pd.concat([df, pd.DataFrame([row])], ignore_index=True)
        save_links(df)
        return df, f"Added '{name}'."
    except Exception as exc:
        return pd.DataFrame(columns=LINK_COLUMNS), f"Error adding link: {exc}"


def update_link(link_id, name, url, enabled, interval_minutes):
    link_id = (link_id or "").strip()
    if not link_id:
        return *links_for_ui()[:1], "Enter or select a link ID."

    try:
        df = read_links()
        matches = df.index[df["id"].astype(str) == link_id].tolist()
        if not matches:
            return df, "Link ID was not found."

        idx = matches[0]
        interval = max(1, int(interval_minutes))
        previous_enabled = bool(df.at[idx, "enabled"])

        df.at[idx, "name"] = (name or "").strip()
        df.at[idx, "url"] = (url or "").strip()
        df.at[idx, "enabled"] = bool(enabled)
        df.at[idx, "interval_minutes"] = interval

        if enabled and not previous_enabled:
            df.at[idx, "next_run_utc"] = iso_utc(utc_now())
        elif not enabled:
            df.at[idx, "next_run_utc"] = ""

        save_links(df)
        return df, f"Updated '{df.at[idx, 'name']}'."
    except Exception as exc:
        return pd.DataFrame(columns=LINK_COLUMNS), f"Error updating link: {exc}"


def delete_link(link_id):
    link_id = (link_id or "").strip()
    if not link_id:
        return *links_for_ui()[:1], "Enter or select a link ID."

    try:
        links = read_links()
        if link_id not in links["id"].astype(str).tolist():
            return links, "Link ID was not found."

        links = links[links["id"].astype(str) != link_id].reset_index(drop=True)
        save_links(links)

        results = read_table(RESULTS_WORKSHEET, RESULT_COLUMNS)
        if not results.empty:
            results = results[
                results["source_id"].astype(str) != link_id
            ].reset_index(drop=True)
            write_table(RESULTS_WORKSHEET, RESULT_COLUMNS, results)

        return links, "Link and its stored results were deleted."
    except Exception as exc:
        return pd.DataFrame(columns=LINK_COLUMNS), f"Error deleting link: {exc}"


def dataframe_selection(evt: gr.SelectData):
    row = evt.row_value or []
    row = list(row) + [""] * max(0, len(LINK_COLUMNS) - len(row))
    values = dict(zip(LINK_COLUMNS, row))

    enabled = str(values["enabled"]).lower() in ["true", "1", "yes", "on"]
    try:
        interval = int(float(values["interval_minutes"]))
    except (TypeError, ValueError):
        interval = 60

    return (
        str(values["id"]),
        str(values["name"]),
        str(values["url"]),
        enabled,
        interval,
    )


def scrape_tori(url):
    # REPLACED WITH USER'S SCRAPER
    response = get_tori_page(url)
    soup = BeautifulSoup(response.text,'html.parser')
    listings=[]
    for card in soup.find_all('article')[:3]:
        title_tag=card.find(['h2','h3']); title=title_tag.get_text(' ',strip=True) if title_tag else ''
        price=next((t.strip() for t in card.stripped_strings if '€' in t),'')
        producer_name=''; bd=card.select_one('div.flex.flex-wrap.mt-4.text-xs')
        if bd:
            sp=bd.find('span'); producer_name=sp.get_text(strip=True) if sp else ''
        location=''; posted_date=''; meta=card.select_one('div.text-xs.s-text-subtle.flex.justify-between.flex-wrap.mt-4.sm\\:mt-8')
        if meta:
            s=meta.find_all('span');
            if len(s)>0: location=s[0].get_text(strip=True)
            if len(s)>1: posted_date=s[1].get_text(strip=True)
        img=card.select_one('img'); image_url=urljoin('https://www.tori.fi',img.get('src','')) if img else ''
        a=card.select_one('a.sf-search-ad-link'); product_link=urljoin('https://www.tori.fi',a.get('href','')) if a else ''
        description=''
        description_parts = []
        if product_link:
            try:
                time.sleep(random.uniform(1.5, 3.0))
                r = get_tori_page(product_link, referer=url)
                ps = BeautifulSoup(r.text, 'html.parser')
                d=ps.find('div',class_='whitespace-pre-wrap')
                p_tags = d.find_all("p")

                if d:
                    for p in p_tags:
                        clean_p = BeautifulSoup(str(p), "html.parser")
                        text = clean_p.get_text(" ", strip=True)
    
                        if text:
                            description_parts.append(text)

                description = "\n".join(description_parts)
                
            except requests.RequestException: pass
        listings.append({'product_name':title,'price':price,'producer_name':producer_name,'location':location,'posted_date':posted_date,'image_url':image_url,'listing_url':product_link,'raw_text':description})
    return pd.DataFrame(listings)

def claude_client():
    if not ANTHROPIC_API_KEY:
        raise RuntimeError("Missing ANTHROPIC_API_KEY Space secret.")
    return Anthropic(api_key=ANTHROPIC_API_KEY)


def evaluate_listing_with_claude(raw_text, price, product_name=""):
    raw_text = str(raw_text or "").strip()
    price = str(price or "").strip()
    product_name = str(product_name or "").strip()

    if not raw_text:
        return "REVIEW | No product description was available."

    prompt = f"""
Evaluate whether this second-hand product appears cost-effective to buy.

Product: {product_name or 'Unknown'}
Asking price: {price or 'Unknown'}
Description:
{raw_text[:8000]}

Consider the asking price, condition, defects, age, missing parts, included
accessories, repair risk, and missing information.

Return exactly one concise line in one of these formats:
BUY | brief reason
DO_NOT_BUY | brief reason
REVIEW | brief reason

Use REVIEW when the information is insufficient. Do not use markdown.
""".strip()

    try:
        message = claude_client().messages.create(
            model=ANTHROPIC_MODEL,
            max_tokens=CLAUDE_MAX_TOKENS,
            messages=[{"role": "user", "content": prompt}],
        )

        answer_parts = []
        for block in message.content:
            if getattr(block, "type", "") == "text":
                answer_parts.append(block.text)

        answer = " ".join(" ".join(answer_parts).split()).strip()
        return answer[:1000] if answer else "REVIEW | Claude returned no text."
    except Exception as exc:
        return f"AI_ERROR | {exc}"


def add_claude_decisions(scraped_df):
    evaluated = scraped_df.copy()
    if evaluated.empty:
        evaluated["claude_decision"] = pd.Series(dtype="object")
        return evaluated

    evaluated["claude_decision"] = evaluated.apply(
        lambda row: evaluate_listing_with_claude(
            raw_text=row.get("raw_text", ""),
            price=row.get("price", ""),
            product_name=row.get("product_name", ""),
        ),
        axis=1,
    )
    return evaluated


def replace_results_for_source(source, scraped_df):
    current = read_table(RESULTS_WORKSHEET, RESULT_COLUMNS)
    source_id = str(source["id"])

    if not current.empty:
        current = current[
            current["source_id"].astype(str) != source_id
        ].reset_index(drop=True)

    scraped_at = iso_utc(utc_now())
    new_rows = scraped_df.copy()
    new_rows.insert(0, "scraped_at_utc", scraped_at)
    new_rows.insert(0, "source_url", source["url"])
    new_rows.insert(0, "source_name", source["name"])
    new_rows.insert(0, "source_id", source_id)

    combined = pd.concat([current, new_rows], ignore_index=True)
    write_table(RESULTS_WORKSHEET, RESULT_COLUMNS, combined)


def run_one_source(source):
    started = utc_now()
    try:
        scraped = scrape_tori(str(source["url"]))
        scraped = add_claude_decisions(scraped)
        replace_results_for_source(source, scraped)
        status = f"OK: {len(scraped)} rows at {iso_utc(started)}"
    except Exception as exc:
        status = f"ERROR at {iso_utc(started)}: {exc}"

    links = read_links()
    matches = links.index[
        links["id"].astype(str) == str(source["id"])
    ].tolist()

    if matches:
        idx = matches[0]
        interval = max(1, int(links.at[idx, "interval_minutes"]))
        links.at[idx, "last_run_utc"] = iso_utc(started)
        links.at[idx, "next_run_utc"] = iso_utc(
            started + timedelta(minutes=interval)
        )
        links.at[idx, "last_status"] = status
        save_links(links)

    return status


def run_selected(link_id):
    link_id = (link_id or "").strip()
    if not link_id:
        return *links_for_ui()[:1], "Enter or select a link ID."

    if not RUN_LOCK.acquire(blocking=False):
        return *links_for_ui()[:1], "A scraping run is already active."

    try:
        links = read_links()
        selected = links[links["id"].astype(str) == link_id]
        if selected.empty:
            return links, "Link ID was not found."

        status = run_one_source(selected.iloc[0].to_dict())
        return read_links(), status
    finally:
        RUN_LOCK.release()


def run_all_enabled():
    if not RUN_LOCK.acquire(blocking=False):
        return *links_for_ui()[:1], "A scraping run is already active."

    try:
        links = read_links()
        enabled = links[links["enabled"] == True]  # noqa: E712
        statuses = []

        for _, row in enabled.iterrows():
            statuses.append(f"{row['name']}: {run_one_source(row.to_dict())}")

        message = "\n".join(statuses) if statuses else "No enabled links."
        return read_links(), message
    finally:
        RUN_LOCK.release()


def scheduler_tick():
    if not RUN_LOCK.acquire(blocking=False):
        return read_links(), "Scheduler skipped: another run is active."

    try:
        links = read_links()
        now = utc_now()
        due = []

        for _, row in links.iterrows():
            if not bool(row["enabled"]):
                continue
            next_run = parse_utc(row["next_run_utc"])
            if next_run is None or next_run <= now:
                due.append(row.to_dict())

        statuses = []
        for source in due:
            statuses.append(f"{source['name']}: {run_one_source(source)}")

        message = (
            "\n".join(statuses)
            if statuses
            else f"Scheduler checked at {iso_utc(now)}; nothing due."
        )
        return read_links(), message
    except Exception as exc:
        return pd.DataFrame(columns=LINK_COLUMNS), f"Scheduler error: {exc}"
    finally:
        RUN_LOCK.release()


def load_results():
    try:
        return (
            read_table(RESULTS_WORKSHEET, RESULT_COLUMNS),
            "Results loaded from Google Sheets.",
        )
    except Exception as exc:
        return pd.DataFrame(columns=RESULT_COLUMNS), f"Error loading results: {exc}"


try:
    initialize_sheets()
    startup_message = "Connected to Google Sheets."
except Exception as startup_exc:
    startup_message = f"Configuration error: {startup_exc}"


with gr.Blocks(title="Scheduled Tori Scraper") as demo:
    gr.Markdown(
        """
        # Scheduled Tori Scraper
        Save Tori search/category URLs, edit or delete them, run scraping manually,
        and refresh stored results automatically.
        """
    )

    status = gr.Textbox(
        label="Status",
        value=startup_message,
        lines=4,
        interactive=False,
    )

    with gr.Tab("Links"):
        links_table = gr.Dataframe(
            headers=LINK_COLUMNS,
            datatype=["str", "str", "str", "bool", "number", "str", "str", "str"],
            value=pd.DataFrame(columns=LINK_COLUMNS),
            interactive=False,
            label="Saved links",
        )

        with gr.Row():
            link_id = gr.Textbox(label="ID", interactive=False)
            name = gr.Textbox(label="Name")
            url = gr.Textbox(label="Tori URL")

        with gr.Row():
            enabled = gr.Checkbox(label="Enabled", value=True)
            interval_minutes = gr.Number(
                label="Interval in minutes",
                value=60,
                minimum=1,
                precision=0,
            )

        with gr.Row():
            add_btn = gr.Button("Add", variant="primary")
            update_btn = gr.Button("Update")
            delete_btn = gr.Button("Delete", variant="stop")
            refresh_links_btn = gr.Button("Refresh")

        with gr.Row():
            run_selected_btn = gr.Button("Scrape selected now")
            run_all_btn = gr.Button("Scrape all enabled now")

    with gr.Tab("Results"):
        results_table = gr.Dataframe(
            headers=RESULT_COLUMNS,
            value=pd.DataFrame(columns=RESULT_COLUMNS),
            interactive=False,
            label="Stored scraping results",
        )
        refresh_results_btn = gr.Button("Refresh results")

    links_table.select(
        dataframe_selection,
        outputs=[link_id, name, url, enabled, interval_minutes],
    )

    add_btn.click(
        add_link,
        inputs=[name, url, enabled, interval_minutes],
        outputs=[links_table, status],
    )
    update_btn.click(
        update_link,
        inputs=[link_id, name, url, enabled, interval_minutes],
        outputs=[links_table, status],
    )
    delete_btn.click(
        delete_link,
        inputs=[link_id],
        outputs=[links_table, status],
    )
    refresh_links_btn.click(
        links_for_ui,
        outputs=[links_table, status],
    )
    run_selected_btn.click(
        run_selected,
        inputs=[link_id],
        outputs=[links_table, status],
    )
    run_all_btn.click(
        run_all_enabled,
        outputs=[links_table, status],
    )
    refresh_results_btn.click(
        load_results,
        outputs=[results_table, status],
    )

    demo.load(links_for_ui, outputs=[links_table, status])
    scheduler = gr.Timer(value=SCHEDULER_TICK_SECONDS, active=True)
    scheduler.tick(
        scheduler_tick,
        outputs=[links_table, status],
        show_progress="hidden",
    )


if __name__ == "__main__":
    demo.queue(default_concurrency_limit=4).launch()