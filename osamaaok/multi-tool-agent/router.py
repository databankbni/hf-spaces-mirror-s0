import os
import json
from dotenv import load_dotenv
from groq import Groq

from tools.calculator import calculator
from tools.web_search import web_search
from tools.rag_retrieval import rag_retrieval

load_dotenv()
client = Groq(api_key=os.environ.get("GROQ_API_KEY"))

TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "calculator",
            "description": "Performs precise arithmetic calculations. Use this for any math problem involving numbers, even simple ones, since it guarantees a correct result.",
            "parameters": {
                "type": "object",
                "properties": {
                    "expression": {
                        "type": "string",
                        "description": "A mathematical expression using only numbers and + - * / ( ), e.g. '15 * 4.5 + 2'"
                    }
                },
                "required": ["expression"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "Searches the live internet for current, real-world information such as recent events, current prices, weather, or anything that may have changed recently or is not general knowledge.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The search query"
                    }
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "rag_retrieval",
            "description": "Searches a private knowledge base containing notes on AI agents, the Model Context Protocol (MCP), and generative AI/RAG fundamentals. Use this ONLY for questions specifically about these topics' definitions, concepts, or explanations as covered in the notes.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The question to search the knowledge base for"
                    }
                },
                "required": ["query"]
            }
        }
    }
]

AVAILABLE_FUNCTIONS = {
    "calculator": calculator,
    "web_search": web_search,
    "rag_retrieval": rag_retrieval
}

def ask_with_routing(question):
    """
    Fallback router: asks the LLM in plain text which tool to use,
    used when structured function-calling fails.
    """
    tool_list_text = "\n".join(
        f"- {t['function']['name']}: {t['function']['description']}"
        for t in TOOL_DEFINITIONS
    )

    system_message = f"""You must choose exactly one tool to answer the user's question, or answer directly if no tool is needed.

    Available tools:
    {tool_list_text}

    Respond in EXACTLY this format:
    TOOL: <tool_name or NONE>
    QUERY: <the search query or expression to pass to the tool, or your direct answer if TOOL is NONE>
    """

    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {"role": "system", "content": system_message},
            {"role": "user", "content": question}
        ],
        temperature=0
    )

    text = response.choices[0].message.content
    tool_line = next((l for l in text.split("\n") if l.startswith("TOOL:")), "TOOL: NONE")
    query_line = next((l for l in text.split("\n") if l.startswith("QUERY:")), "QUERY: ")

    tool_name = tool_line.replace("TOOL:", "").strip()
    query = query_line.replace("QUERY:", "").strip()

    if tool_name == "NONE" or tool_name not in AVAILABLE_FUNCTIONS:
        return query, None, None

    print(f"[Fallback router] chose tool: {tool_name}")
    tool_function = AVAILABLE_FUNCTIONS[tool_name]

    if tool_name == "calculator":
        tool_result = tool_function(expression=query)
    else:
        tool_result = tool_function(query=query)

    final_response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {"role": "user", "content": question},
            {"role": "assistant", "content": f"I'll use {tool_name} to find this."},
            {"role": "user", "content": f"Tool result: {tool_result}\n\nNow answer the original question using this result."}
        ]
    )

    return final_response.choices[0].message.content, tool_name, tool_result
    print("Structured function-calling failed — falling back to text-based routing.")
    return ask_with_routing_fallback(question)

if __name__ == "__main__":
    test_questions = [
        "What is 847293 * 58162?",
        "What is the current weather in Lahore?",
        "What is the N times M integration problem that MCP solves?",
    ]

    for q in test_questions:
        print(f"\n{'='*60}\nQuestion: {q}")
        try:
            answer, tool_used, raw_result = ask_with_routing(q)
            print(f"Tool used: {tool_used}")
            print(f"Final answer: {answer}")
        except RuntimeError as e:
            print(f"FAILED: {e}")