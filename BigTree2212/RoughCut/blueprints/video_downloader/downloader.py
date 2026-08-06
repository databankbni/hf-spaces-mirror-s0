"""yt-dlp helpers: domain validation, metadata extraction (no download), and
download-command building for video and audio-only (MP3) modes.

No subprocess execution happens for the actual download here -- app.py owns
the Popen/cancel lifecycle itself (mirrors youtube_fetcher.py in ai-clipper),
so this module only builds argv lists, parses output, and does the one quick
synchronous --dump-json call for metadata lookup.
"""
import os
import re
import sys
import json
import shutil
import subprocess
from urllib.parse import urlparse

# Base domains this tool accepts. A netloc matches if it equals one of these
# (after stripping a leading "www.") or ends with "." + one of these, so
# m.youtube.com, music.youtube.com, vm.tiktok.com, vt.tiktok.com etc. all
# resolve correctly without listing every subdomain by hand.
BASE_DOMAINS = {
    "youtube.com": "YouTube",
    "youtu.be": "YouTube",
    "tiktok.com": "TikTok",
    "instagram.com": "Instagram",
}

# Substrings (checked lowercase) that indicate YouTube's anti-bot check
# rejected the request outright -- "Sign in to confirm you're not a bot".
# Checked *before* _AUTH_KEYWORDS below since that message contains "sign
# in" too: this is a distinct failure mode (the server's IP/session got
# flagged as a bot, not that the video itself needs a login) and deserves
# its own message so users don't think the video is actually private.
_BOT_DETECTION_KEYWORDS = [
    "not a bot", "confirm you're not a bot", "confirm you are not a bot",
]

# Substrings (checked lowercase) that indicate yt-dlp failed because the
# content requires being logged in -- a private video/account, an
# age-restricted video yt-dlp can't verify without cookies, a subscriber- or
# members-only post, etc. Not exhaustive, but covers the common phrasing
# across YouTube/TikTok/Instagram's yt-dlp extractors.
_AUTH_KEYWORDS = [
    "sign in", "log in", "login required", "requires you to be signed in",
    "private video", "private account", "this account is private",
    "age-restricted", "age restricted", "confirm your age",
    "members-only", "subscriber", "not available, try logging in",
    "use --cookies", "requested content is not available",
]

_yt_dlp_bin = None


def _yt_dlp_path():
    """Resolve the yt-dlp executable without relying on the parent process's
    PATH -- when app.py is launched via a venv's python directly (rather
    than after `source venv/bin/activate`), PATH may not include the venv's
    bin/ even though pip installed yt-dlp's console script right there next
    to the running Python interpreter."""
    global _yt_dlp_bin
    if _yt_dlp_bin is None:
        candidate = shutil.which("yt-dlp")
        if not candidate:
            sibling = os.path.join(os.path.dirname(os.path.abspath(sys.executable)), "yt-dlp")
            candidate = sibling if os.path.exists(sibling) else "yt-dlp"
        _yt_dlp_bin = candidate
    return _yt_dlp_bin


class VideoFetchError(Exception):
    """Raised when a URL can't be resolved or downloaded (invalid link,
    unsupported domain, removed video, network failure, etc.)."""


class UnsupportedDomainError(VideoFetchError):
    """Raised when the URL isn't from YouTube, TikTok, or Instagram."""


class AuthRequiredError(VideoFetchError):
    """Raised when the content is private/age-gated/members-only and can't
    be accessed without logging in -- this tool only handles public content."""


class BotDetectedError(VideoFetchError):
    """Raised when YouTube's anti-bot check rejects the request outright
    ("Sign in to confirm you're not a bot") -- unlike AuthRequiredError,
    this is about the *server's* IP/session being flagged, not the video's
    own access level. The video itself is very likely public."""


def detect_platform(url):
    """Return "YouTube"/"TikTok"/"Instagram" for a recognized URL, else None."""
    netloc = (urlparse(url).netloc or "").lower()
    if netloc.startswith("www."):
        netloc = netloc[4:]
    for domain, label in BASE_DOMAINS.items():
        if netloc == domain or netloc.endswith("." + domain):
            return label
    return None


def validate_url(url):
    """Return the detected platform label, or raise UnsupportedDomainError
    with a message safe to show directly to the user."""
    if not (url.startswith("http://") or url.startswith("https://")):
        raise UnsupportedDomainError("Link tidak valid. Pastikan link diawali dengan http:// atau https://.")
    platform = detect_platform(url)
    if platform is None:
        raise UnsupportedDomainError(
            "Link tidak didukung. Tool ini hanya menerima link dari YouTube, TikTok, atau Instagram."
        )
    return platform


def _error_tail(text):
    lines = [
        line for line in (text or "").splitlines()
        if line.strip() and not line.strip().startswith("WARNING")
    ]
    if not lines:
        return "yt-dlp keluar tanpa pesan error."
    # yt-dlp occasionally crashes with an unhandled internal Python traceback
    # instead of exiting with its usual clean one-line error message -- e.g.
    # a networking exception its own top-level handler doesn't catch cleanly.
    # Blindly taking "the last 5 lines" in that case lands squarely inside
    # the traceback dump (a stray "File ..., line N, in ..." fragment), which
    # is worse to show a user than a short generic message.
    if any(line.strip().startswith(("File \"", "Traceback ")) for line in lines):
        return "Terjadi error internal yang tidak terduga saat memproses video. Coba lagi."
    return "\n".join(lines[-5:])


# Substrings indicating a transient connectivity failure (timeout, reset,
# DNS hiccup) rather than a bot-detection/auth rejection -- worth its own
# short, retry-friendly message instead of falling through to a raw error
# tail, since these are usually gone on the next attempt.
_NETWORK_ERROR_KEYWORDS = [
    "read timed out", "connection reset", "connection aborted",
    "unexpected_eof_while_reading", "transporterror", "max retries exceeded",
    "connection refused", "name or service not known",
    "temporary failure in name resolution",
]


def classify_error(raw_output):
    """Turn yt-dlp's raw stderr/stdout tail into a VideoFetchError (or the
    more specific BotDetectedError/AuthRequiredError) with an Indonesian,
    user-facing message. Returned (not raised) so callers can
    `raise classify_error(...)`."""
    lowered = (raw_output or "").lower()
    if any(kw in lowered for kw in _BOT_DETECTION_KEYWORDS):
        return BotDetectedError(
            "YouTube menolak permintaan ini karena mendeteksinya sebagai bot "
            "(bukan berarti videonya privat). Server sedang mencoba mengatasi "
            "ini otomatis -- kalau masih gagal, coba lagi dalam beberapa menit "
            "atau pakai link TikTok/Instagram untuk sementara."
        )
    if any(kw in lowered for kw in _AUTH_KEYWORDS):
        return AuthRequiredError(
            "Video atau akun ini bersifat privat / butuh login untuk diakses. "
            "Tool ini hanya bisa memproses konten publik."
        )
    if any(kw in lowered for kw in _NETWORK_ERROR_KEYWORDS):
        return VideoFetchError(
            "Koneksi ke server video terputus atau timeout saat mengambil datanya. "
            "Biasanya ini sementara -- coba lagi dalam beberapa saat."
        )
    return VideoFetchError(_error_tail(raw_output))


def _infer_width(fmt, fallback_ratio):
    """Best-effort width for a format that omits it -- yt-dlp's Instagram
    extractor in particular often reports "height" on a format without a
    matching "width". Try the format's own aspect_ratio first, then the
    overall video's width/height ratio (from the top-level info dict, which
    is virtually always populated), before giving up."""
    width = fmt.get("width")
    if width:
        return width
    height = fmt.get("height")
    ratio = fmt.get("aspect_ratio") or fallback_ratio
    return round(height * ratio) if height and ratio else None


def _extract_resolutions(info):
    """Build a deduped, sorted-descending list of genuinely available video
    resolutions from yt-dlp's format list -- never hardcoded. For each
    distinct height, keep the variant with the largest known filesize (a
    reasonable proxy for "best encode at this height")."""
    info_w, info_h = info.get("width"), info.get("height")
    fallback_ratio = (info_w / info_h) if info_w and info_h else None

    best_by_height = {}
    for fmt in info.get("formats") or []:
        height = fmt.get("height")
        vcodec = fmt.get("vcodec")
        if not height or vcodec in (None, "none"):
            continue
        filesize = fmt.get("filesize") or fmt.get("filesize_approx")
        existing = best_by_height.get(height)
        if existing is None or (filesize or 0) > (existing.get("filesize") or 0):
            best_by_height[height] = {
                "height": height,
                "width": _infer_width(fmt, fallback_ratio),
                "fps": fmt.get("fps"),
                "filesize": filesize,
            }

    resolutions = []
    for entry in sorted(best_by_height.values(), key=lambda r: r["height"], reverse=True):
        fps = entry["fps"]
        # Label by the shorter side, not the raw pixel height. Portrait clips
        # (Instagram/TikTok Reels & Stories are typically 1080x1920) would
        # otherwise show as the non-standard "1920p" instead of the familiar
        # "1080p" everyone actually means by that term. The download command
        # still filters by the real pixel height (see build_video_download_
        # command), so this only changes what's displayed.
        quality = min(entry["width"], entry["height"]) if entry.get("width") else entry["height"]
        label = f"{quality}p"
        if fps and fps >= 50:
            label += str(round(fps))
        filesize_mb = round(entry["filesize"] / (1024 * 1024), 1) if entry["filesize"] else None
        resolutions.append({"height": entry["height"], "label": label, "fps": fps, "filesize_mb": filesize_mb})
    return resolutions


# YouTube player-client override, applied to every yt-dlp call (metadata
# *and* download) so the two stay consistent. yt-dlp's default client set
# can fail outright against YouTube from a datacenter IP (Hugging Face
# Spaces included) -- "Sign in to confirm you're not a bot" -- because most
# clients now require a valid PO Token to prove the request isn't
# automated; android is the one client that has historically kept working
# without one. Ignored for non-YouTube URLs -- extractor-args are
# namespaced per-extractor, so TikTok/Instagram runs are unaffected.
#
# The second --extractor-args points at bgutil-pot, a PO-Token provider
# sidecar started by start.sh and reachable only over loopback (see
# Dockerfile). It supplies a real token so the "web" client -- which
# exposes the full DASH format range, unlike android's single 360p
# progressive stream -- has a real shot at working too, without dropping
# the android fallback that already works without any token at all.
_POT_ARGS = ["--extractor-args", "youtubepot-bgutilhttp:base_url=http://127.0.0.1:4416"]
_YOUTUBE_CLIENT_ARGS = ["--extractor-args", "youtube:player_client=android,web", *_POT_ARGS]
# A verbose debug run showed every single request to youtube.com (webpage,
# then the API JSON call) hitting "SSL: UNEXPECTED_EOF_WHILE_READING" -- a
# connection that completes the TCP handshake and then gets reset mid-TLS,
# rather than a clean HTTP-level bot rejection. A follow-up run with
# --extractor-retries bumped to 5 confirmed this is 100% deterministic. not
# a flaky connection: every one of 6 consecutive attempts (1 + 5 retries) hit
# the identical reset, all the way to yt-dlp's own "Giving up after 5
# retries". That rules out "just retry more" as a mitigation -- it only makes
# a guaranteed failure take longer -- so these are back to lean budgets.
# Real fix candidates from here: YOUTUBE_COOKIES_B64 (an authenticated
# session may get treated differently by whatever is resetting these), or
# this being specific to YouTube's servers rather than this host's network
# stack in general (confirm by checking whether TikTok/Instagram still work
# on the same deployment).
_FAST_TIMEOUT = 15
_FULL_TIMEOUT = 25


def _cookies_args():
    """Returns ["--cookies", <path>] if start.sh decoded a YOUTUBE_COOKIES_B64
    secret into a real file, else []. Safe to include unconditionally on
    every call regardless of platform -- yt-dlp's cookie jar honors each
    cookie's own Domain column from the Netscape file, so a youtube.com-
    scoped cookie is never sent on a tiktok.com/instagram.com request even
    though the same file is loaded globally. Absent locally (no env var set),
    which just means yt-dlp runs unauthenticated like it always has."""
    path = os.environ.get("YOUTUBE_COOKIES_FILE")
    return ["--cookies", path] if path and os.path.isfile(path) else []


def _dump_json(url, extra_args, timeout):
    cmd = [
        _yt_dlp_path(), "--dump-json", "--no-download", "--no-playlist",
        # TEMPORARY DEBUG: --verbose (instead of --no-warnings) so a hung
        # attempt's captured stderr shows which phase yt-dlp actually got
        # stuck in (DNS, TCP connect, PO-Token fetch, waiting on a response,
        # ...) instead of nothing at all. A prior deploy showed both the fast
        # and fallback attempts timing out with completely empty stderr,
        # which --no-warnings was largely responsible for -- revert this back
        # to --no-warnings once the real hang point is identified.
        "--verbose",
        # Bound every individual network call instead of relying solely on
        # the outer subprocess timeout -- a single stalled connection would
        # otherwise eat the whole budget before yt-dlp's own retries do.
        # Kept modest (not the 5/2 tried during debugging) since the SSL-reset
        # failure mode turned out to be 100% deterministic -- more retries
        # there just delayed a guaranteed failure instead of ever clearing it.
        "--socket-timeout", "10", "--extractor-retries", "2", "--retry-sleep", "1",
        # No-op on hosts where IPv6 already works fine; cheap insurance
        # against a separate, unrelated IPv6-blackhole failure mode on some
        # cloud hosts (a connection that hangs completely rather than
        # resetting) in case this container ever hits that instead.
        "--force-ipv4",
        *extra_args, url,
    ]
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def fetch_metadata(url):
    """Return video metadata without downloading it:
    {"title", "thumbnail", "duration", "platform", "resolutions": [...]}.
    Raises VideoFetchError / UnsupportedDomainError / AuthRequiredError."""
    platform = validate_url(url)

    proc = None
    try:
        proc = _dump_json(url, [*_YOUTUBE_CLIENT_ARGS, *_cookies_args()], _FAST_TIMEOUT)
    except subprocess.TimeoutExpired as e:
        # Swallowed here on purpose (the fallback below gets a fresh
        # attempt) -- but still worth a line in the container's own logs
        # (visible in HF Spaces' "Logs" tab) since a *complete* hang on the
        # fast path, repeated on the fallback too, is the main diagnostic
        # signal for the IPv6-blackhole failure mode described above.
        print(f"[video_downloader] fast metadata attempt timed out after {_FAST_TIMEOUT}s "
              f"for {url}; partial stderr: {(e.stderr or '')[-3000:]}", file=sys.stderr)

    # Fall back to yt-dlp's unrestricted client set only when the fast path
    # genuinely couldn't resolve the video -- not when it cleanly reported a
    # terminal error like a private/age-gated video (AuthRequiredError) or a
    # bot-detection rejection despite already having a PO Token
    # (BotDetectedError) -- both would just fail the same way again after
    # burning another ~35s for nothing.
    needs_fallback = proc is None or (
        proc.returncode != 0
        and not isinstance(classify_error(proc.stderr), (AuthRequiredError, BotDetectedError))
    )
    if needs_fallback:
        try:
            # Still pass the PO Token args (but not the client restriction)
            # so whatever client yt-dlp's own defaults pick can use the
            # token too -- only the android/web narrowing is dropped here.
            proc = _dump_json(url, [*_POT_ARGS, *_cookies_args()], _FULL_TIMEOUT)
        except subprocess.TimeoutExpired as e:
            print(f"[video_downloader] fallback metadata attempt also timed out after "
                  f"{_FULL_TIMEOUT}s for {url}; partial stderr: {(e.stderr or '')[-3000:]}",
                  file=sys.stderr)
            raise VideoFetchError("Server terlalu lama merespons saat mengambil info video. Coba lagi.")

    if proc.returncode != 0:
        raise classify_error(proc.stderr)

    try:
        info = json.loads(proc.stdout)
    except Exception as e:
        raise VideoFetchError(f"Gagal membaca info video: {e}") from e

    if info.get("availability") in ("private", "needs_auth", "premium_only", "subscriber_only"):
        raise AuthRequiredError(
            "Video atau akun ini bersifat privat / butuh login untuk diakses. "
            "Tool ini hanya bisa memproses konten publik."
        )

    return {
        "title": info.get("title") or "video",
        "thumbnail": info.get("thumbnail"),
        "duration": info.get("duration"),
        "platform": platform,
        "resolutions": _extract_resolutions(info),
    }


def build_video_download_command(url, height, output_template):
    """Return the yt-dlp argv (a plain list, never a shell string) that
    downloads a single video (no playlists) at the given height, falling
    back to the best available quality at or below it. height=None means no
    cap -- use the overall best.

    Prefers H.264 video + AAC audio first. yt-dlp's --merge-output-format
    only picks a container -- it does not transcode, so merging a VP9/AV1
    video or Opus audio stream (common on Instagram/TikTok/YouTube's higher
    -quality formats) into an ".mp4" produces a file whose codecs standard
    players like QuickTime/iOS don't actually support, even though the
    extension says mp4. Falling back through progressively looser selectors
    means a video that's only available in a non-H.264 encode still
    downloads (just without the compatibility guarantee) rather than
    failing outright.
    """
    hcap = f"[height<={height}]" if height else ""
    fmt = (
        f"bestvideo[vcodec^=avc1]{hcap}+bestaudio[acodec^=mp4a]/"
        f"best[vcodec^=avc1][ext=mp4]{hcap}/"
        f"bestvideo{hcap}+bestaudio/best{hcap}/best"
    )
    return [
        _yt_dlp_path(),
        "-f", fmt,
        "--merge-output-format", "mp4",
        "--no-playlist",
        "--newline",
        "--force-ipv4",  # see the matching comment in _dump_json
        *_YOUTUBE_CLIENT_ARGS,
        *_cookies_args(),
        "-o", output_template,
        url,
    ]


def build_audio_download_command(url, output_template):
    """Return the yt-dlp argv that extracts the best audio stream and
    converts it to MP3 via ffmpeg (yt-dlp's built-in postprocessor)."""
    return [
        _yt_dlp_path(),
        "-f", "bestaudio/best",
        "-x", "--audio-format", "mp3", "--audio-quality", "0",
        "--no-playlist",
        "--newline",
        "--force-ipv4",  # see the matching comment in _dump_json
        *_YOUTUBE_CLIENT_ARGS,
        *_cookies_args(),
        "-o", output_template,
        url,
    ]


_PROGRESS_RE = re.compile(r"\[download\]\s+([\d.]+)%")
_PROCESSING_MARKERS = ("[Merger]", "[ExtractAudio]", "[ffmpeg]", "[VideoRemuxer]", "[FixupM3u8]", "[Metadata]")


def parse_progress_percent(line):
    """Extract a 0-100 float from a yt-dlp --newline download-progress line,
    or None if the line isn't one."""
    match = _PROGRESS_RE.search(line)
    if not match:
        return None
    try:
        return max(0.0, min(100.0, float(match.group(1))))
    except ValueError:
        return None


def is_processing_line(line):
    """True for post-download lines (merging streams, extracting/converting
    audio) -- these have no percentage, just a change of phase worth
    reflecting in the UI."""
    return any(marker in line for marker in _PROCESSING_MARKERS)


_ILLEGAL_FILENAME_RE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def sanitize_filename(name, max_len=150):
    """Strip filesystem-illegal characters while keeping the title otherwise
    readable (spaces, punctuation, unicode all preserved)."""
    cleaned = _ILLEGAL_FILENAME_RE.sub("", name or "").strip()
    cleaned = re.sub(r"\s+", " ", cleaned)
    if len(cleaned) > max_len:
        cleaned = cleaned[:max_len].rstrip()
    return cleaned or "video"


def build_output_filename(title, mode, resolution_label, ext):
    """User-facing download filename: "{Judul Video}_{resolusi}.ext" for
    video (e.g. "Judul Video_1080p.mp4") or "{Judul Video}_audio.ext" for
    the MP3 mode -- keeps repeated downloads of the same video at different
    quality/format from colliding on disk. `resolution_label` must be the
    exact label already shown to the user in the resolution picker (e.g.
    "1080p") -- NOT the raw yt-dlp pixel height, which for a portrait video
    (Instagram/TikTok Reels & Stories) is the taller dimension and would
    read as a confusing, non-standard "1920p"."""
    safe_title = sanitize_filename(title)
    if mode == "audio":
        suffix = "audio"
    else:
        suffix = sanitize_filename(resolution_label, max_len=20) if resolution_label else "best"
    return f"{safe_title}_{suffix}.{ext}"


_QUICKTIME_SAFE_VIDEO_CODECS = {"h264", "hevc"}


def probe_video_codec(path):
    """Return ffprobe's codec_name for the first video stream in `path`
    (e.g. "h264", "vp9", "av1"), or None if it can't be determined."""
    cmd = [
        "ffprobe", "-v", "error", "-select_streams", "v:0",
        "-show_entries", "stream=codec_name", "-of", "json", path,
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        streams = json.loads(proc.stdout).get("streams") or []
        return streams[0].get("codec_name") if streams else None
    except Exception:
        return None


def needs_transcode(codec_name):
    """True when the downloaded video's codec isn't one QuickTime/iOS/most
    standard players actually support -- e.g. Instagram frequently only
    offers VP9 DASH streams with no H.264 alternative at all, so preferring
    avc1 in the format selector (see build_video_download_command) isn't
    enough on its own; the file needs an actual re-encode, not just a
    container remux, to be reliably playable."""
    return bool(codec_name) and codec_name not in _QUICKTIME_SAFE_VIDEO_CODECS


def build_transcode_command(input_path, output_path):
    """ffmpeg argv that re-encodes a video to H.264/AAC. Used only when
    probe_video_codec() finds a non-H.264/HEVC stream -- re-encoding every
    download unconditionally would waste time/CPU on sources (like most
    YouTube videos) that are already H.264. veryfast trades some file size
    for speed since this runs synchronously in the job's single worker slot."""
    return [
        "ffmpeg", "-y", "-i", input_path,
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
        "-c:a", "aac", "-b:a", "160k",
        "-movflags", "+faststart",
        output_path,
    ]
