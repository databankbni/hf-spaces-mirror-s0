import os
import re
import sys

MAIN_PY_PATH = "main.py"

def extract_drive_id(share_url):
    """
    Extracts the unique file ID from various Google Drive sharing link formats.
    """
    # Regex patterns for standard Google Drive share links
    patterns = [
        r"/file/d/([a-zA-Z0-9_-]+)",
        r"id=([a-zA-Z0-9_-]+)",
        r"srcid=([a-zA-Z0-9_-]+)"
    ]
    
    for pattern in patterns:
        match = re.search(pattern, share_url)
        if match:
            return match.group(1)
            
    return None

def update_video_url_in_main(video_id, direct_url):
    """
    Updates the video_url for the specified video_id inside main.py using regular expressions.
    """
    if not os.path.exists(MAIN_PY_PATH):
        print(f"Error: Could not find '{MAIN_PY_PATH}' in the current directory.")
        return False
        
    with open(MAIN_PY_PATH, "r", encoding="utf-8") as file:
        content = file.read()
        
    # Regex to find the dictionary block containing the specific video ID and capture its contents
    # up to the video_url property, then replace the URL.
    # Matches: "id": "vid_001", ..., "video_url": "..."
    pattern = rf'({{\s*"id":\s*"{video_id}",(?:[^{}}]*?)"video_url":\s*")[^"]*(")'
    
    # Check if the video ID exists in the file
    if not re.search(pattern, content):
        print(f"Error: Video ID '{video_id}' not found in '{MAIN_PY_PATH}'.")
        return False
        
    # Replace the matching video URL with the new direct URL
    new_content = re.sub(pattern, rf'\g<1>{direct_url}\g<2>', content)
    
    with open(MAIN_PY_PATH, "w", encoding="utf-8") as file:
        file.write(new_content)
        
    return True

def main():
    print("=========================================")
    print(" Google Drive Direct Link Automator")
    print("=========================================")
    
    # 1. Get Google Drive Share Link
    share_url = input("\nPaste your Google Drive share link: ").strip()
    if not share_url:
        print("Error: Link cannot be empty.")
        return
        
    file_id = extract_drive_id(share_url)
    if not file_id:
        print("Error: Could not extract File ID from link. Make sure it is a valid Google Drive sharing URL.")
        return
        
    # Generate the direct streamable URL
    direct_url = f"https://docs.google.com/uc?export=download&id={file_id}"
    print(f"\n[✓] Extracted File ID: {file_id}")
    print(f"[✓] Generated Direct URL: {direct_url}")
    
    # 2. Select Video ID to update in backend
    print("\nSelect a Video ID to update in your mock backend:")
    print("Options: vid_001 to vid_010")
    video_id = input("Enter Video ID (default: vid_001): ").strip() or "vid_001"
    
    # Validate format (vid_001 to vid_010)
    if not re.match(r"^vid_\d{3}$", video_id):
        print("Error: Invalid Video ID format. Example format: vid_001")
        return
        
    # 3. Update main.py
    print(f"\nUpdating {MAIN_PY_PATH}...")
    if update_video_url_in_main(video_id, direct_url):
        print(f"[✓] Successfully updated '{video_id}' with your Google Drive video URL!")
        print("\nNote: Remember to restart your backend server (python main.py) for changes to take effect.")
    else:
        print("[✗] Failed to update backend file.")

if __name__ == "__main__":
    main()
