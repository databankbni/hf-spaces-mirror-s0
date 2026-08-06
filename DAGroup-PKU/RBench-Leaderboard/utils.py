import json
import os

def update_leaderboard(model_name, scores, path="leaderboard.json"):
    """
    Update leaderboard.json by inserting a new model entry.
    - model_name: string
    - scores: dict with the 9 metrics
    """

    # Load existing leaderboard
    if os.path.exists(path):
        with open(path, "r") as f:
            data = json.load(f)
    else:
        data = []

    # Build new record
    new_entry = {"model": model_name}
    new_entry.update(scores)

    # Remove old entries with the same model name (avoid duplicates)
    data = [entry for entry in data if entry["model"] != model_name]

    # Append new one
    data.append(new_entry)

    # Save back
    with open(path, "w") as f:
        json.dump(data, f, indent=2)

    print(f"[update_leaderboard] Added/Updated: {model_name}")
    return True
