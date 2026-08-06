import base64
import json
import os
import re
import time
from typing import List, Optional
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query, File, UploadFile, Form
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import requests

# Load local environment variables from .env file
load_dotenv()

app = FastAPI(
    title="Video Recommendation Engine & GitHub CDN Upload",
    description="A recommendation engine backend with integrated automated GitHub uploads for a video-based social media application.",
    version="1.1.0"
)

# Enable CORS for frontend integration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins for local testing and cross-domain hosting
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

VIDEOS_FILE = "videos.json"

# Database Helper Functions
def load_videos() -> List[dict]:
    """Loads video records from the local videos.json file."""
    if os.path.exists(VIDEOS_FILE):
        try:
            with open(VIDEOS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except json.JSONDecodeError:
            print("Warning: videos.json was corrupted. Re-initializing.")
            return []
    return []

def save_videos(videos: List[dict]):
    """Saves video records back to the local videos.json file."""
    with open(VIDEOS_FILE, "w", encoding="utf-8") as f:
        json.dump(videos, f, indent=2)

# Mock user interaction profiles (history of liked video tags)
MOCK_USER_PROFILES = {
    "user_alice": ["tech", "coding", "webdev"],
    "user_bob": ["music", "gaming"],
    "user_charlie": ["lifestyle", "coffee"],
}

class RecommendationResponse(BaseModel):
    user_id: str
    recommendations: List[dict]

@app.get("/")
def read_root():
    return {
        "status": "online",
        "service": "Video Recommendation Engine API with GitHub CDN Upload",
        "message": "Send requests to /recommend or POST files to /upload."
    }

@app.get("/recommend", response_model=RecommendationResponse)
def get_recommendations(
    user_id: str = Query(..., description="ID of the user to generate recommendations for"),
    limit: int = Query(5, ge=1, le=20, description="Max number of recommendations to return")
):
    """
    Generates personalized video recommendations for a user based on their mock interest profile.
    If the user has no profile, it defaults to recommending the most liked videos overall.
    """
    videos = load_videos()
    user_interests = MOCK_USER_PROFILES.get(user_id, [])
    recommendations = []
    
    if user_interests:
        # 1. Score videos based on matching tags
        scored_videos = []
        for video in videos:
            matching_tags = set(video["tags"]).intersection(set(user_interests))
            score = len(matching_tags)
            
            if score > 0:
                # Add small weight based on popularity (likes)
                final_score = score + (video.get("likes", 0) / 10000.0)
                scored_videos.append((video, final_score))
        
        # Sort by score in descending order
        scored_videos.sort(key=lambda x: x[1], reverse=True)
        recommendations = [video for video, _ in scored_videos[:limit]]

    # 2. Fallback: If we don't have enough personalized recommendations, fill with top-liked videos
    if len(recommendations) < limit:
        remaining_slots = limit - len(recommendations)
        already_recommended_ids = {vid["id"] for vid in recommendations}
        popular_fallbacks = [
            vid for vid in videos 
            if vid["id"] not in already_recommended_ids
        ]
        # Sort by ID in descending order (newest first) so new uploads show up first
        popular_fallbacks.sort(key=lambda x: x.get("id", ""), reverse=True)
        recommendations.extend(popular_fallbacks[:remaining_slots])

    return RecommendationResponse(
        user_id=user_id,
        recommendations=recommendations[:limit]
    )

@app.post("/upload")
async def upload_video(
    file: UploadFile = File(..., description="The MP4 video file to upload"),
    title: str = Form(..., description="Title of the video"),
    creator: str = Form(..., description="Name of the creator"),
    tags: str = Form("", description="Comma-separated list of tags, e.g. 'coding,tech'")
):
    """
    Receives a video file, uploads it to a GitHub repository, gets the raw CDN link, 
    and saves the record in videos.json.
    """
    # 1. Validate file format
    if not file.filename.lower().endswith(".mp4"):
        raise HTTPException(status_code=400, detail="Only .mp4 video files are supported.")
        
    # 2. Validate file size (25 MB limit for GitHub Contents API)
    MAX_SIZE = 25 * 1024 * 1024  # 25 MB
    content = await file.read()
    if len(content) > MAX_SIZE:
        raise HTTPException(status_code=400, detail="File size exceeds maximum limit of 25MB.")
        
    # 3. Retrieve GitHub Secrets
    github_token = os.environ.get("GITHUB_TOKEN")
    github_username = os.environ.get("GITHUB_USERNAME")
    github_repo = os.environ.get("GITHUB_REPO")
    
    if not github_token or not github_username or not github_repo or "your_" in github_token:
        raise HTTPException(
            status_code=500,
            detail="GitHub configuration missing or placeholder detected. Please configure your .env file with GITHUB_TOKEN, GITHUB_USERNAME, and GITHUB_REPO."
        )
        
    # 4. Generate Safe & Unique Filename
    safe_filename = re.sub(r'[^a-zA-Z0-9_.-]', '-', file.filename)
    unique_filename = f"{int(time.time())}-{safe_filename}"
    
    # 5. Base64 encode the file contents
    content_b64 = base64.b64encode(content).decode("utf-8")
    
    # 6. Upload to GitHub Contents API
    github_url = f"https://api.github.com/repos/{github_username}/{github_repo}/contents/videos/{unique_filename}"
    headers = {
        "Authorization": f"Bearer {github_token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28"
    }
    payload = {
        "message": f"Upload {unique_filename} via VibeFeed Client App",
        "content": content_b64
    }
    
    try:
        response = requests.put(github_url, json=payload, headers=headers)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Request to GitHub failed: {str(e)}")
        
    if response.status_code not in [200, 201]:
        try:
            err_data = response.json()
            err_msg = err_data.get("message", response.text)
        except:
            err_msg = response.text
        raise HTTPException(status_code=500, detail=f"GitHub API Error: {err_msg}")
        
    # 7. Construct jsDelivr CDN URL (maps to GitHub repository under main branch)
    raw_cdn_url = f"https://cdn.jsdelivr.net/gh/{github_username}/{github_repo}@main/videos/{unique_filename}"
    
    # 8. Append to Local database
    videos = load_videos()
    
    # Process comma-separated tags
    tags_list = [t.strip().lower() for t in tags.split(",") if t.strip()]
    
    # Create new unique ID
    new_video_id = f"vid_{str(len(videos) + 1).zfill(3)}"
    
    new_video = {
        "id": new_video_id,
        "title": title,
        "creator": creator,
        "tags": tags_list,
        "likes": 0,
        "video_url": raw_cdn_url
    }
    
    videos.append(new_video)
    save_videos(videos)
    
    return {
        "message": "Video successfully uploaded and saved!",
        "video": new_video
    }

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 7860))
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)
