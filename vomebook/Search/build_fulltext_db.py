from __future__ import annotations
import gzip
import hashlib
import json
import re
import sqlite3
import unicodedata
from collections import defaultdict
from pathlib import Path
BASE_DIR = Path(__file__).resolve().parent
DATA_PATH = BASE_DIR / "data/search_data.json.gz"
FULLTEXT_DIR = BASE_DIR / "data/fulltext"
STATUS_PATH = FULLTEXT_DIR / "build-status.json"
TOKEN_RE = re.compile(r"[a-z0-9]+|[\u4e00-\u9fff\u3400-\u4dbf]+")
SUMMARY_CHARS = 700
TOKENIZER_VERSION = "cjk-bigram-boundary-fts5-v6-snippet-anchors"
LITERAL_PREFIX = "\0literal:"

def load_json_gz(path: Path):
    return json.loads(gzip.decompress(path.read_bytes()).decode("utf-8"))

def index_tokens(text: str) -> set[str]:
    tokens = set()
    normalized = unicodedata.normalize("NFKC", text or "").casefold()
    for part in TOKEN_RE.findall(normalized):
        if re.fullmatch(r"[\u4e00-\u9fff\u3400-\u4dbf]+", part):
            tokens.update(part)
            tokens.update(part[index:index + 2] for index in range(len(part) - 1))
        else:
            tokens.add(part)
    return tokens

def literal_tokens(text: str) -> set[str]:
    normalized = normalize_literal(text)
    return {
        LITERAL_PREFIX + normalized[index:index + 3]
        for index in range(len(normalized) - 2)
        if not TOKEN_RE.fullmatch(normalized[index + 1])
    }

def token_hashes(text: str) -> set[bytes]:
    normalized = unicodedata.normalize("NFKC", text or "").casefold()
    hashes: set[bytes] = set()
    for part in TOKEN_RE.findall(normalized):
        if re.fullmatch(r"[\u4e00-\u9fff\u3400-\u4dbf]+", part):
            for token in part:
                hashes.add(hashlib.sha256(token.encode("utf-8")).digest()[:16])
            for index in range(len(part) - 1):
                hashes.add(hashlib.sha256(part[index:index + 2].encode("utf-8")).digest()[:16])
        else:
            hashes.add(hashlib.sha256(part.encode("utf-8")).digest()[:16])
    for index in range(len(normalized) - 2):
        if not TOKEN_RE.fullmatch(normalized[index + 1]):
            token = LITERAL_PREFIX + normalized[index:index + 3]
            hashes.add(hashlib.sha256(token.encode("utf-8")).digest()[:16])
    return hashes

def normalize_literal(text: str) -> str:
    return unicodedata.normalize("NFKC", text or "").casefold()

def encode_doc_ids(doc_numbers: list[int]) -> bytes:
    previous = 0
    output = bytearray()
    for doc_number in sorted(doc_numbers):
        delta = doc_number - previous
        previous = doc_number
        while delta >= 0x80:
            output.append((delta & 0x7F) | 0x80)
            delta >>= 7
        output.append(delta)
    return bytes(output)

def doc_number(doc_id: str) -> int:
    try:
        return int(doc_id.rsplit(":", 1)[1])
    except (IndexError, ValueError) as exc:
        raise ValueError(f"doc_id must end with ':<number>': {doc_id}") from exc

def get_doc_storage_path(record: dict) -> Path:
    return BASE_DIR / record["storage_root"] / record["storage_rel_path"]

def build_summary(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()[:SUMMARY_CHARS]

def fts_content(text: str) -> str:
    return unicodedata.normalize("NFKC", text or "").casefold().replace("\0", " ")

def snippet_anchors(text: str) -> dict[bytes, int]:
    """Return the earliest normalized-character offset for every indexed token."""
    normalized = fts_content(text)
    anchors: dict[bytes, int] = {}

    def add(token: str, offset: int) -> None:
        anchors.setdefault(hashlib.sha256(token.encode("utf-8")).digest()[:16], offset)

    for match in TOKEN_RE.finditer(normalized):
        part = match.group()
        start = match.start()
        if re.fullmatch(r"[\u4e00-\u9fff\u3400-\u4dbf]+", part):
            for index, character in enumerate(part):
                add(character, start + index)
            for index in range(len(part) - 1):
                add(part[index:index + 2], start + index)
        else:
            add(part, start)
    for index in range(len(normalized) - 2):
        if not TOKEN_RE.fullmatch(normalized[index + 1]):
            add(LITERAL_PREFIX + normalized[index:index + 3], index)
    return anchors

def database_ready(path: Path, expected_documents: int) -> bool:
    if not path.exists():
        return False
    try:
        uri = f"file:{path.resolve()}?mode=ro&immutable=1"
        with sqlite3.connect(uri, uri=True) as connection:
            version = connection.execute("SELECT value FROM metadata WHERE key = 'tokenizer_version'").fetchone()
            documents = int(connection.execute("SELECT COUNT(*) FROM documents").fetchone()[0])
            fts_rows = int(connection.execute("SELECT COUNT(*) FROM content_fts").fetchone()[0])
            anchor_columns = {
                row[1] for row in connection.execute("PRAGMA table_info(snippet_anchors)")
            }
            has_anchors = {"token_hash", "doc_number", "char_offset"} <= anchor_columns
        return bool(version and version[0] == TOKENIZER_VERSION and documents == expected_documents and fts_rows == expected_documents and has_anchors)
    except Exception:
        return False

def build_source_db(source: str, source_records: list[dict]) -> None:
    db_path = FULLTEXT_DIR / f"{source}.sqlite3"
    if database_ready(db_path, len(source_records)):
        print(f"{source}: current index already ready", flush=True)
        return
    tmp_path = db_path.with_suffix(".sqlite3.tmp")
    postings: dict[bytes, set[int]] = defaultdict(set)
    missing = 0
    if tmp_path.exists():
        tmp_path.unlink()
    document_count = 0
    with sqlite3.connect(tmp_path) as connection:
        connection.execute("PRAGMA journal_mode = OFF")
        connection.execute("PRAGMA synchronous = OFF")
        connection.execute("PRAGMA temp_store = MEMORY")
        connection.execute("CREATE TABLE documents (doc_id TEXT PRIMARY KEY, summary TEXT NOT NULL)")
        connection.execute("CREATE TABLE postings (token_hash BLOB PRIMARY KEY, docs BLOB NOT NULL, doc_count INTEGER NOT NULL)")
        connection.execute("CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        connection.execute("INSERT INTO metadata (key, value) VALUES ('tokenizer_version', ?)", (TOKENIZER_VERSION,))
        connection.execute("CREATE VIRTUAL TABLE content_fts USING fts5(content, tokenize='trigram', detail='full')")
        connection.execute(
            "CREATE TABLE snippet_anchors (token_hash BLOB NOT NULL, doc_number INTEGER NOT NULL, char_offset INTEGER NOT NULL, PRIMARY KEY (token_hash, doc_number)) WITHOUT ROWID"
        )
        for index, record in enumerate(source_records, 1):
            doc_id = record["doc_id"]
            file_path = get_doc_storage_path(record)
            if not file_path.exists():
                missing += 1
                continue
            text = file_path.read_text(encoding="utf-8", errors="ignore")
            number = doc_number(doc_id)
            connection.execute("INSERT INTO documents (doc_id, summary) VALUES (?, ?)", (doc_id, build_summary(text)))
            connection.execute("INSERT INTO content_fts (rowid, content) VALUES (?, ?)", (number, fts_content(text)))
            connection.executemany(
                "INSERT INTO snippet_anchors (token_hash, doc_number, char_offset) VALUES (?, ?, ?)",
                ((token_hash, number, char_offset) for token_hash, char_offset in snippet_anchors(text).items()),
            )
            document_count += 1
            for token_hash in token_hashes(text):
                postings[token_hash].add(number)
            if index % 100 == 0:
                connection.commit()
            if index % 1000 == 0:
                print(f"{source}: indexed {index}/{len(source_records)} records", flush=True)
        connection.executemany(
            "INSERT INTO postings (token_hash, docs, doc_count) VALUES (?, ?, ?)",
            ((token_hash, encode_doc_ids(list(numbers)), len(numbers)) for token_hash, numbers in postings.items()),
        )
        connection.execute("CREATE INDEX idx_documents_doc_id ON documents(doc_id)")
    if missing:
        tmp_path.unlink(missing_ok=True)
        raise RuntimeError(f"{source}: refusing to publish index with {missing} missing files")
    tmp_path.replace(db_path)
    try:
        display_path = db_path.relative_to(BASE_DIR)
    except ValueError:
        display_path = db_path
    print(
        f"{source}: wrote {display_path} "
        f"with {document_count} documents, {len(postings)} tokens, {missing} missing files",
        flush=True,
    )

def main() -> None:
    payload = load_json_gz(DATA_PATH)
    records = payload.get("records", [])
    FULLTEXT_DIR.mkdir(parents=True, exist_ok=True)
    records_by_source: dict[str, list[dict]] = defaultdict(list)
    for record in records:
        records_by_source[record["source"]].append(record)
    STATUS_PATH.write_text(json.dumps({"state": "building"}), encoding="utf-8")
    try:
        for source in sorted(records_by_source):
            build_source_db(source, records_by_source[source])
    except Exception as exc:
        STATUS_PATH.write_text(json.dumps({"state": "failed", "error": type(exc).__name__}), encoding="utf-8")
        raise
    STATUS_PATH.write_text(json.dumps({"state": "ready"}), encoding="utf-8")

if __name__ == "__main__":
    main()
