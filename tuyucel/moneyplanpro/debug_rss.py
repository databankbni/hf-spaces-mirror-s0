import requests
from bs4 import BeautifulSoup

url = "https://www.bloomberght.com/rss"
headers = {"User-Agent": "Mozilla/5.0"}
resp = requests.get(url, headers=headers)
soup = BeautifulSoup(resp.content, 'xml')
item = soup.find('item')
print(f"Item found: {item is not None}")
if item:
    print("Tags in item:")
    for tag in item.find_all(True):
        print(f"Tag: {tag.name}, Attributes: {tag.attrs}, Text length: {len(tag.text)}")
        if tag.name == 'image':
            print(f"IMAGE TEXT: {tag.text}")
