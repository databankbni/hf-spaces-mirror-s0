import json

# Play Store validation
ps = json.load(open('data/raw/play_store/page_1.json', encoding='utf-8'))
print(f"Play Store: {len(ps)} reviews")
print(f"  First review keys: {list(ps[0].keys())}")
print(f"  Sample text: {ps[0]['content'][:80]}")
print(f"  Score: {ps[0]['score']}, Date: {ps[0]['at']}")
print()

# App Store validation
ap = json.load(open('data/raw/app_store/page_us_1.json', encoding='utf-8'))
entries = ap['feed']['entry']
if isinstance(entries, dict):
    entries = [entries]
print(f"App Store: {len(entries)} reviews")
print(f"  First entry keys: {list(entries[0].keys())}")
text = entries[0].get('content', {}).get('label', 'N/A')
print(f"  Sample text: {text[:80]}")
rating = entries[0].get('im:rating', {}).get('label', 'N/A')
date = entries[0].get('updated', {}).get('label', 'N/A')
print(f"  Rating: {rating}, Date: {date}")
