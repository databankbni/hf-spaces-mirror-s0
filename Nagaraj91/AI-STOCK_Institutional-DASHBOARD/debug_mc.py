import json
from bs4 import BeautifulSoup
import re

with open(r"C:\Users\Nagar\.gemini\antigravity-ide\brain\1effdcab-9919-433c-8fb2-4c0946a8b62f\.system_generated\steps\345\content.md", 'r', encoding='utf-8') as f:
    html = f.read()

soup = BeautifulSoup(html, 'html.parser')
script = soup.find('script', id='__NEXT_DATA__')
if script:
    data = json.loads(script.string)
    
    with open("debug_next.json", "w", encoding="utf-8") as f2:
        f2.write(json.dumps(data, indent=2))
        
    print("Saved debug_next.json")
else:
    print("No __NEXT_DATA__ found")
