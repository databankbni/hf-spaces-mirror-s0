"""Storage layer: local files + optional sync to a Hugging Face Dataset repo.

On Hugging Face free Spaces the filesystem is wiped on every restart, so all
admin edits (content.json), guest data (rsvp.json, wishes.json) and uploaded
files are mirrored to a private Dataset repo when HF_TOKEN and DATASET_REPO
are set. On startup the latest copy is pulled back down.
"""
import json
import os
from pathlib import Path

DATA_DIR = Path(os.environ.get("DATA_DIR", Path(__file__).resolve().parent / "data"))
PHOTOS_DIR = DATA_DIR / "photos"

HF_TOKEN = os.environ.get("HF_TOKEN")
DATASET_REPO = os.environ.get("DATASET_REPO")

_api = None


def hf_enabled() -> bool:
    return bool(HF_TOKEN and DATASET_REPO)


def _get_api():
    global _api
    if _api is None:
        from huggingface_hub import HfApi
        _api = HfApi(token=HF_TOKEN)
    return _api


def init() -> None:
    """Create local dirs and pull the latest data from the dataset repo."""
    PHOTOS_DIR.mkdir(parents=True, exist_ok=True)
    if not hf_enabled():
        print("[storage] HF sync disabled (set HF_TOKEN and DATASET_REPO to enable). "
              "Data will NOT survive a Space restart.")
        return
    try:
        api = _get_api()
        api.create_repo(repo_id=DATASET_REPO, repo_type="dataset", private=True, exist_ok=True)
        from huggingface_hub import snapshot_download
        snapshot_download(
            repo_id=DATASET_REPO,
            repo_type="dataset",
            token=HF_TOKEN,
            local_dir=str(DATA_DIR),
        )
        print(f"[storage] Synced data from dataset repo {DATASET_REPO}")
    except Exception as e:
        print(f"[storage] Warning: could not sync from dataset repo: {e}")


def _push(local_path: Path, repo_path: str) -> None:
    if not hf_enabled():
        return
    try:
        _get_api().upload_file(
            path_or_fileobj=str(local_path),
            path_in_repo=repo_path,
            repo_id=DATASET_REPO,
            repo_type="dataset",
        )
    except Exception as e:
        print(f"[storage] Warning: failed to push {repo_path}: {e}")


# ---------- JSON documents (content, rsvp, wishes) ----------

def read_json(name: str):
    path = DATA_DIR / name
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            print(f"[storage] Warning: could not read {name}: {e}")
    return None


def write_json(name: str, data, push: bool = True) -> None:
    path = DATA_DIR / name
    path.parent.mkdir(parents=True, exist_ok=True)
    # Write-then-rename so a crash mid-write can't corrupt the file
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)
    if push:  # high-frequency writers (e.g. wish hearts) batch their pushes
        _push(path, name)


def read_content():
    return read_json("content.json")


def write_content(content: dict) -> None:
    write_json("content.json", content)


# ---------- Uploaded files (photos, QR codes, music) ----------

def save_photo(file_storage, filename: str) -> None:
    PHOTOS_DIR.mkdir(parents=True, exist_ok=True)
    dest = PHOTOS_DIR / filename
    file_storage.save(str(dest))
    _push(dest, f"photos/{filename}")


def save_bytes(data: bytes, filename: str) -> None:
    PHOTOS_DIR.mkdir(parents=True, exist_ok=True)
    dest = PHOTOS_DIR / filename
    dest.write_bytes(data)
    _push(dest, f"photos/{filename}")


def delete_photo(filename: str) -> None:
    target = PHOTOS_DIR / filename
    try:
        target.unlink(missing_ok=True)
    except OSError as e:
        # e.g. file locked on Windows — content.json is already updated, so a
        # stray leftover file is better than failing the whole admin request
        print(f"[storage] Warning: could not delete local file {filename}: {e}")
    if hf_enabled():
        try:
            _get_api().delete_file(
                path_in_repo=f"photos/{filename}",
                repo_id=DATASET_REPO,
                repo_type="dataset",
            )
        except Exception as e:
            print(f"[storage] Warning: failed to delete {filename} from repo: {e}")
