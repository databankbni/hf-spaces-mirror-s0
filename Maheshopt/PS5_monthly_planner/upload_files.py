#!/usr/bin/env python3
"""Upload PS5 planner files to Hugging Face Space."""
import sys
from huggingface_hub import upload_file
from pathlib import Path
import getpass

def main():
    # Get token from argument or environment
    if len(sys.argv) > 1:
        HF_TOKEN = sys.argv[1]
    else:
        HF_TOKEN = getpass.getpass("Enter your HF API token: ")
    
    if not HF_TOKEN:
        print("Error: No token provided")
        sys.exit(1)
    
    REPO_ID = "Maheshopt/PS5_monthly_planner"
    REPO_TYPE = "space"
    
    # Files to upload
    files_to_upload = [
        "PS5MonthlyPlanner.py",
        "requirements.txt",
        "HF_DEPLOY.md",
        "PS5MonthlyPlanner_report.html",
        ".gitignore",
    ]
    
    print(f"Uploading files to {REPO_ID}...")
    base_dir = Path(__file__).parent
    
    success_count = 0
    for file_name in files_to_upload:
        file_path = base_dir / file_name
        if file_path.exists():
            print(f"Uploading {file_name}...")
            try:
                upload_file(
                    path_or_fileobj=str(file_path),
                    path_in_repo=file_name,
                    repo_id=REPO_ID,
                    repo_type=REPO_TYPE,
                    token=HF_TOKEN,
                )
                print(f"  ✓ {file_name} uploaded successfully")
                success_count += 1
            except Exception as e:
                print(f"  ✗ Error uploading {file_name}: {e}")
        else:
            print(f"  - {file_name} not found (skipping)")
    
    print(f"\nUpload complete! ({success_count}/{len(files_to_upload)} files uploaded)")

if __name__ == "__main__":
    main()
