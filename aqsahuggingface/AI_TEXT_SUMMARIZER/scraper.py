import requests
from bs4 import BeautifulSoup
def scrape_url(url):

    headers = {
        "User-Agent":
        "Mozilla/5.0"
    }

    response = requests.get(url, headers=headers)

    soup = BeautifulSoup(
        response.text,
        "html.parser"
    )

    paragraphs = soup.find_all("p")

    article = ""

    for p in paragraphs:
        article += p.get_text() + "\n"

    return article