from dotenv import load_dotenv
load_dotenv()

from chatbot.rag import add_wiki_text, get_wiki_context

# Add a sample FAQ/wiki entry
count = add_wiki_text(
    title="Warranty Policy",
    content="""Sala.lk store එකේ electronics products වලට සාමාන්‍යයෙන් මාස 12ක් (1 වසරක්) warranty එකක් තියෙනවා. 
Warranty claim එකක් කරන්න නම්, receipt එක සමග Sala.lk showroom එකට එන්න ඕන, නැත්නම් hotline එකට call කරන්න ඕන.
Defective items refund/replacement සඳහා දින 7ක් ඇතුළත report කරන්න ඕන."""
)

print(f"Wiki entry added. Total chunks in DB: {count}")

# Test retrieval
print("\n--- Testing retrieval ---")
context = get_wiki_context("warranty eka kochchara kaalayak thiyenawada")
print(context)