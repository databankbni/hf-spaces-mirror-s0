import base64
import datetime
import re
from typing import Optional

import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

OUTPUT_FILE = "playlist.m3u"

REFERER = "https://cdnlivetv.tv/"
ORIGIN = "https://cdnlivetv.tv"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/148.0.0.0 Safari/537.36"
)

SPORT_KEYWORDS = {
    "sport", "sports", "sport+", "sporttv", "sportsnet",
    "espn", "bein", "sky", "arena", "supersport",
    "dazn", "fox", "tnt", "eurosport",

    "premier", "laliga", "la liga", "bundesliga",
    "serie a", "ligue", "liga", "champions",
    "football", "soccer", "match",
    "canal foot", "real madrid",
    "benfica", "goltv", "gol play",

    "nba", "wnba",
    "nfl", "nhl", "mlb", "baseball",

    "orioles", "yankees", "mets", "dodgers",
    "padres", "giants", "guardians",
    "astros", "braves", "reds",
    "cubs", "white sox", "blue jays",
    "rangers", "marlins", "brewers",
    "twins", "athletics", "diamondbacks",
    "phillies", "pirates", "mariners",
    "angels", "cardinals", "royals",
    "rays", "red sox",

    "nascar", "f1", "formula", "indycar",

    "tennis", "atp", "wta",
    "sony ten",

    "golf", "golftv",
    "cricket", "willow",

    "ufc", "boxing", "fight",
    "combate", "wwe",

    "tsn", "tudn", "nesn",
    "masn", "msg", "sec",
    "btn", "acc", "altitude",

    "teledeporte",
    "deportes",
    "movistar deportes",
    "trt spor",
    "spor",
    "astro cricket",
}

session = requests.Session()

session.headers.update({
    "User-Agent": USER_AGENT,
    "Accept": "*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Origin": ORIGIN,
    "Referer": REFERER,
    "Connection": "keep-alive",
})


def http_get(url: str, referer: str = REFERER) -> Optional[str]:
    headers = {
        "Referer": referer,
    }

    try:
        r = session.get(
            url,
            headers=headers,
            timeout=15,
            verify=False,
        )
        r.raise_for_status()
        return r.text
    except Exception as e:
        print(e)
        return None


def decode_b64(s: str) -> Optional[str]:
    try:
        s = s.replace("-", "+").replace("_", "/")
        while len(s) % 4:
            s += "="
        return base64.b64decode(s).decode("utf-8")
    except Exception:
        return None


def extract_m3u8(html: str) -> Optional[str]:

    decoded = set()

    for b64_val in re.findall(
        r"var\s+\w+\s*=\s*['\"]([A-Za-z0-9+/=_-]+)['\"]",
        html,
    ):
        v = decode_b64(b64_val)
        if v:
            decoded.add(v)

    channel_id = next(
        (v for v in decoded if re.fullmatch(r"[0-9a-f]{24}", v)),
        None,
    )

    token_qs = next(
        (v for v in decoded if v.startswith("?token=")),
        None,
    )

    if channel_id and token_qs:
        return (
            f"https://cdnlivetv.tv/secure/api/v1/"
            f"{channel_id}/playlist.m3u8{token_qs}"
        )

    m = re.search(
        r"https://[^\s\"']+playlist\.m3u8[^\s\"']*",
        html,
    )

    if m:
        return m.group(0)

    return None


def get_m3u8_url(url: str, referer: str = REFERER) -> Optional[str]:
    html = http_get(url, referer)

    if not html:
        return None

    return extract_m3u8(html)


def get_group(name):

    name = name.lower()

    if any(k in name for k in SPORT_KEYWORDS):
        return "🏎|TV SPORT"

    return "🎞|TV ENTERTAIN"

def get_online_channels(referer: str = REFERER):
    try:
        r = session.get(
            "https://api.cdnlivetv.tv/api/v1/channels/?user=cdnlivetv&plan=free",
            headers={"Referer": referer},
            timeout=15,
            verify=False,
        )

        r.raise_for_status()

        data = r.json().get("channels", [])

        channels = [
            ch
            for ch in data
            if ch.get("status", "").lower() == "online"
        ]

        print(f"Total API     : {len(data)}")
        print(f"Online        : {len(channels)}")

        return channels

    except Exception as e:
        print(e)
        return []

def fix_logo_url(url: str) -> str:
    if not url:
        return ""

    url = url.strip()

    if url.startswith("https://cdnlivetv.tv/api/"):
        return url.replace(
            "https://cdnlivetv.tv/api/",
            "https://api.cdnlivetv.tv/api/",
            1,
        )

    if url.startswith("http://cdnlivetv.tv/api/"):
        return url.replace(
            "http://cdnlivetv.tv/api/",
            "https://api.cdnlivetv.tv/api/",
            1,
        )

    if url.startswith("/api/"):
        return "https://api.cdnlivetv.tv" + url

    if url.startswith("api/"):
        return "https://api.cdnlivetv.tv/" + url

    return url

# ================= MAIN =================

channels = get_online_channels()

with open(OUTPUT_FILE, "w", encoding="utf-8") as f:

    f.write("#EXTM3U\n")
    f.write(f"# Updated: {datetime.datetime.now()}\n\n")

    for ch in channels:

        name = ch.get("name", "")
        code = ch.get("code", "")
        url = ch.get("url", "")
        logo = fix_logo_url(ch.get("image", ""))

        print("[+]", name)

        m3u8 = get_m3u8_url(url)

        if not m3u8:
            print("   ❌ gagal ambil stream")
            continue
            
        title = f"{name} {code}".strip()
        
        group = get_group(name)

        f.write(
            f'#EXTINF:-1 '
            f'tvg-id="{code}" '
            f'tvg-name="{name}" '
            f'tvg-logo="{logo}" '
            f'group-title="{group}",{title}\n'
        )

        f.write(f"#EXTVLCOPT:http-user-agent={USER_AGENT}\n")
        f.write(f"#EXTVLCOPT:http-referrer={REFERER}\n")
        f.write(f"#EXTVLCOPT:http-origin={ORIGIN}\n")
        f.write(f"{m3u8}\n\n")

print("Playlist updated.")