from huggingface_hub import hf_hub_download
import os
import shutil

REPO_ID = "sammmmmmm1111/complaint-dashboard-indices"

FILES = {
    "nba_index.faiss": "nba/vector_store/nba_index.faiss",
    "nba_metadata.pkl": "nba/vector_store/nba_metadata.pkl",
    "embeddings.pkl": "nba/vector_store/embeddings.pkl",
}

def download_assets():
    for filename, destination in FILES.items():

        print(f"Checking {filename}...")

        if os.path.exists(destination):
            print(f"{filename} already exists.")
            continue

        print(f"Downloading {filename}...")

        os.makedirs(os.path.dirname(destination), exist_ok=True)

        downloaded = hf_hub_download(
            repo_id=REPO_ID,
            filename=filename,
            repo_type="dataset",
        )

        shutil.copy(downloaded, destination)

        print(f"Downloaded {filename}")