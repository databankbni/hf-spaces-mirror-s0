from langchain_google_genai import ChatGoogleGenerativeAI

class LLM_Agent:
    def __init__(self, model_name="gemini-3.5-flash-lite", temperature=1):
        self.llm = ChatGoogleGenerativeAI(model=model_name, temperature=temperature)
        self.memory = {}  # dictionary to store memory per user_id

    def ask(self, user_id: str, question: str, documents: list) -> str:
        if user_id not in self.memory:
            self.memory[user_id] = []

        conversation_history = self.memory[user_id]

        docs_string = "".join([doc.page_content for doc in documents])
        previous_messages = "\n".join([f"{role}: {msg}" for role, msg in conversation_history])

        instructions = f"""You are a helpful assistant.
Use the following documents to answer the user's questions.
If you don't know the answer, just say so.
Use three sentences maximum.
Include context from previous conversation.

Previous conversation:
{previous_messages}

Documents:
{docs_string}"""

        ai_msg = self.llm.invoke([
            {"role": "system", "content": instructions},
            {"role": "user", "content": question},
        ])

        # Save to memory
        conversation_history.append(("user", question))
        conversation_history.append(("assistant", ai_msg.content))
        self.memory[user_id] = conversation_history

        return ai_msg.content
