import os
from dotenv import load_dotenv
from groq import Groq

load_dotenv()
client = Groq(api_key=os.environ.get("GROQ_API_KEY"))

problems = [
    "847293 * 58162",
    "(9384.7234 + 18234.991) * 0.3847 / 12.5",
    "2384719 / 7 + 9123 * 4",
]

correct_answers = [49280255466, 850.0243303744002, 377166.14285714284]

for p, correct in zip(problems, correct_answers):
    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": f"What is {p}? Reply with ONLY the final number, no explanation."}]
    )
    answer = response.choices[0].message.content.strip()
    print(f"Question: {p}")
    print(f"  LLM answered:  {answer}")
    print(f"  Actual answer: {correct}")
    print()