import re
import ssl
from Bio import Entrez
Entrez.email = "azlaanmohammad66@gmail.com"
ssl._create_default_https_context = ssl._create_unverified_context


def parse_abstract_block(pmid, block):
    title = "Title unavailable"
    authors = "Authors unavailable"
    journal = "Journal unavailable"
    year = "n.d."

    lines = block.split("\n")

    # Journal is line 0 (may wrap to line 1 before first blank line)
    # Title is the first non-empty line AFTER the first blank line
    # Authors is the first non-empty line AFTER the second blank line

    # Collect journal lines (everything up to first blank)
    journal_lines = []
    i = 0
    while i < len(lines) and lines[i].strip():
        journal_lines.append(lines[i].strip())
        i += 1

    journal_raw = " ".join(journal_lines)
    journal_raw = re.sub(r"^\d+\.\s*", "", journal_raw)
    year_match = re.search(r"\b(19|20)\d{2}\b", journal_raw)
    if year_match:
        year = year_match.group(0)
    journal = re.split(r"\.\s+\d{4}", journal_raw)[0].strip().rstrip(".")

    # Skip blank lines, collect title (next non-empty block)
    while i < len(lines) and not lines[i].strip():
        i += 1
    title_lines = []
    while i < len(lines) and lines[i].strip():
        title_lines.append(lines[i].strip())
        i += 1
    if title_lines:
        title = " ".join(title_lines).rstrip(".")

    # Skip blank lines, collect authors (next non-empty block)
    while i < len(lines) and not lines[i].strip():
        i += 1
    author_lines = []
    while i < len(lines) and lines[i].strip():
        author_lines.append(lines[i].strip())
        i += 1
    if author_lines:
        raw_authors = re.sub(r"\(\d+\)", "", " ".join(author_lines)).strip().rstrip(".,")
        author_list = [a.strip() for a in raw_authors.split(",") if a.strip()]
        if len(author_list) > 3:
            authors = ", ".join(author_list[:3]) + " et al."
        else:
            authors = ", ".join(author_list)

    return {
        "pmid": pmid,
        "title": title,
        "authors": authors,
        "journal": journal,
        "year": year,
        "abstract": block
    }


def fetch_pubmed(query: str, max_results: int = 5) -> list:
    handle = Entrez.esearch(db="pubmed", term=query, retmax=max_results)
    record = Entrez.read(handle)
    ids = record["IdList"]
    if not ids:
        return []
    handle = Entrez.efetch(db="pubmed", id=ids, rettype="abstract", retmode="text")
    raw = handle.read()
    abstracts = [a.strip() for a in raw.strip().split("\n\n\n") if a.strip()]
    return [parse_abstract_block(pmid, ab) for pmid, ab in zip(ids, abstracts)]


if __name__ == "__main__":
    results = fetch_pubmed("epilepsy seizure detection machine learning", max_results=2)
    for r in results:
        print(f"PMID:    {r['pmid']}")
        print(f"Title:   {r['title']}")
        print(f"Authors: {r['authors']}")
        print(f"Journal: {r['journal']}")
        print(f"Year:    {r['year']}")
        print("-" * 60)

def fetch_europepmc(query: str, max_results: int = 5) -> list:
    import ssl, urllib.request, urllib.parse, json
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    params = urllib.parse.urlencode({
        "query": query,
        "resultType": "core",
        "pageSize": max_results,
        "format": "json",
        "sort": "CITED desc"
    })
    url = "https://www.ebi.ac.uk/europepmc/webservices/rest/search?" + params
    try:
        with urllib.request.urlopen(url, context=ctx, timeout=20) as r:
            data = json.loads(r.read())
        results = []
        for p in data.get("resultList", {}).get("result", []):
            pmid = p.get("pmid", p.get("id", ""))
            if not pmid:
                continue
            authors_list = []
            for a in p.get("authorList", {}).get("author", []):
                name = a.get("fullName", "")
                if name:
                    authors_list.append(name)
            authors = ", ".join(authors_list[:3])
            if len(authors_list) > 3:
                authors += " et al."
            results.append({
                "pmid": str(pmid),
                "title": p.get("title", "Title unavailable").rstrip("."),
                "authors": authors or "Authors unavailable",
                "journal": p.get("journalTitle", "Journal unavailable"),
                "year": str(p.get("pubYear", "n.d.")),
                "abstract": p.get("abstractText", "Abstract not available")
            })
        return results
    except Exception as e:
        print(f"[EuropePMC] fetch failed: {e}")
        return []