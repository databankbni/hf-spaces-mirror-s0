import requests
from bs4 import BeautifulSoup

url = "https://www.bigpara.com/rss/"
headers = {"User-Agent": "Mozilla/5.0"}
resp = requests.get(url, headers=headers)
soup = BeautifulSoup(resp.content, 'xml')
# Print the first item's content
item = soup.find('item')
if item:
    print(item.prettify())
else:
    print("No items found for Bigpara")
