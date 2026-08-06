from groq import Groq
import os
from file_reader import read_uploaded_file
from scraper import scrape_url
# from dotenv import load_dotenv
# load_dotenv()
api_key = os.getenv("GROQ_API")
if not api_key:
    raise ValueError("GROQ_API environment variable is not set.")

client = Groq(
    api_key=os.getenv("GROQ_API")
)
def generate_summary(
    
    input_type,
    text,
    file,
    url,
    length,
    style
):

    if input_type == "Text":

        article = text

    elif input_type == "Upload File":

        article = read_uploaded_file(file)

    else:

        article = scrape_url(url)

    prompt = f"""
You are a professional AI assistant.

Summarize this article.

Length:
{length}

Style:
{style}

Article:
{article}
"""

    response = client.chat.completions.create(

        model="llama-3.3-70b-versatile",

        messages=[
            {
                "role":"user",
                "content":prompt
            }
        ],

        temperature=0.3

    )

    return response.choices[0].message.content