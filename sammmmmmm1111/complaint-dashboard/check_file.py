import os
import time

action_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "action_lookup.py"

# Get file info
print("Checking action_lookup.py info:")
print(f"  Path: {action_path}")
print(f"  Exists: {os.path.exists(action_path)}")
if os.path.exists(action_path):
    print(f"  Size (bytes): {os.path.getsize(action_path)}")
    print(f"  Modified: {time.ctime(os.path.getmtime(action_path))}")
    print("\n=== FULL FILE CONTENTS ===")
    with open(action_path, 'r') as f:
        print(f.read())
