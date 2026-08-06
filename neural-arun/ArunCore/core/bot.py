import asyncio
import json
import os
import re
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# Import the core ArunCore engine
from core.agent import init_agent, RollingMemory, queue_debug_event, queue_maybe_notify_arun, run_pre_escalation

load_dotenv()

# === In-Memory Session Store (telegram chat_id -> RollingMemory) ===
sessions: dict[int, RollingMemory] = {}

# Initialize the engine once at startup
print("Initializing ArunCore Telegram Bot...")
main_llm, prompt, _, tools = init_agent()
tool_map = {t.name: t for t in tools}
print("Bot engine ready.")


def get_or_create_memory(chat_id: int) -> RollingMemory:
    """Returns existing memory for this user, or creates a new one."""
    if chat_id not in sessions:
        summary_llm = ChatOpenAI(
            temperature=0.0,
            model="gpt-4o-mini",
            api_key=os.getenv("OPENAI_API_KEY")
        )
        sessions[chat_id] = RollingMemory(summary_llm=summary_llm)
    return sessions[chat_id]


def run_agent(chat_id: int, user_message: str) -> str:
    """Runs the full stateful agent loop for a given user message."""
    memory = get_or_create_memory(chat_id)
    scratchpad = []

    try:
        queue_debug_event(
            "user_message",
            user_message,
            {"channel": "telegram", "chat_id": chat_id},
        )

        pre_escalation = run_pre_escalation(
            user_message,
            tool_map,
            {"channel": "telegram", "chat_id": chat_id},
            False,
        )
        if pre_escalation:
            queue_debug_event(
                "pre_escalation",
                pre_escalation.get("result", ""),
                {
                    "channel": "telegram",
                    "chat_id": chat_id,
                    "category": pre_escalation.get("category"),
                    "reason": pre_escalation.get("reason"),
                },
            )

        final_response = None
        max_iterations = 3

        for _ in range(max_iterations):
            messages = prompt.format_messages(
                running_summary=memory.running_summary,
                chat_history=memory.get_messages(),
                input=user_message,
                agent_scratchpad=scratchpad,
            )
            ai_msg = main_llm.invoke(messages)

            if ai_msg.tool_calls:
                scratchpad.append(ai_msg)
                for tc in ai_msg.tool_calls:
                    tool_name = tc["name"]
                    tool_args = tc.get("args", {})
                    queue_debug_event(
                        "tool_call",
                        json.dumps(tool_args, ensure_ascii=False, indent=2, default=str),
                        {
                            "channel": "telegram",
                            "chat_id": chat_id,
                            "tool_name": tool_name,
                        },
                    )

                    tool_func = tool_map.get(tool_name)
                    try:
                        result = tool_func.invoke(tool_args)
                    except Exception as e:
                        result = f"Tool error: {e}"

                    scratchpad.append({
                        "role": "tool",
                        "name": tool_name,
                        "tool_call_id": tc["id"],
                        "content": str(result)[:2000],
                    })
                    queue_debug_event(
                        "tool_result",
                        str(result),
                        {
                            "channel": "telegram",
                            "chat_id": chat_id,
                            "tool_name": tool_name,
                        },
                    )
            else:
                final_response = ai_msg.content
                break

        if not final_response:
            final_response = "I ran into an issue internally. Please try again."

        queue_debug_event(
            "assistant_reply",
            final_response,
            {"channel": "telegram", "chat_id": chat_id},
        )

        queue_maybe_notify_arun(
            user_input=user_message,
            final_response=final_response,
            scratchpad=scratchpad,
            tool_map=tool_map,
            user_metadata={"channel": "telegram", "chat_id": chat_id},
            pre_notified=bool(pre_escalation and pre_escalation.get("handled")),
        )

        memory.add_interaction(user_message, final_response)
        return final_response
    except Exception as e:
        queue_debug_event(
            "error",
            str(e),
            {"channel": "telegram", "chat_id": chat_id},
        )
        raise


# === Telegram Handlers ===

async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    welcome = (
        "Hi! I'm *ArunCore*, the AI digital twin of *Arun Yadav*.\n\n"
        "Ask me anything about his projects, skills, or background in AI engineering. "
        "I'm here to give you the real picture."
    )
    await update.message.reply_text(welcome, parse_mode="Markdown")


def format_for_telegram(text: str) -> str:
    """Converts LLM Markdown into Telegram-safe HTML."""
    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    text = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', text)
    text = re.sub(r'^###?\s+(.+)$', r'\n<b>\1</b>', text, flags=re.MULTILINE)
    text = re.sub(r'```(?:[a-zA-Z]+)?\n?(.*?)\n?```', r'<pre>\1</pre>', text, flags=re.DOTALL)
    text = re.sub(r'`([^`]+)`', r'<code>\1</code>', text)
    text = re.sub(r'^[*-]\s+', '• ', text, flags=re.MULTILINE)

    def link_repl(match):
        label, url = match.groups()
        return f'<a href="{url}">{label}</a>'

    text = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', link_repl, text)
    return text.strip()


from core.agent import save_unknown_question_answer

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text
    chat_id = update.effective_chat.id

    # Check if this is a Telegram reply to an Alert message
    if update.message.reply_to_message:
        reply_to_text = update.message.reply_to_message.text or update.message.reply_to_message.caption or ""
        
        extracted_question = ""
        if "User Query / Details:" in reply_to_text:
            parts = reply_to_text.split("User Query / Details:")
            if len(parts) > 1:
                extracted_question = parts[1].split("Category:")[0].split("Contact:")[0].split("Chat ID:")[0].strip()
        elif "User Message:" in reply_to_text:
            parts = reply_to_text.split("User Message:")
            if len(parts) > 1:
                extracted_question = parts[1].split("Category:")[0].split("Contact:")[0].split("Chat ID:")[0].strip()
        
        if not extracted_question and len(reply_to_text) > 5:
            extracted_question = reply_to_text.split("\n\n")[0].strip()

        if extracted_question:
            res = save_unknown_question_answer(extracted_question, user_text)
            confirmation = (
                f"<b>✅ Answer Saved & Ingested into AI Memory!</b>\n\n"
                f"<b>Question:</b> <code>{extracted_question}</code>\n"
                f"<b>Your Verified Answer:</b>\n{user_text}\n\n"
                f"<i>Result: {res}</i>"
            )
            await update.message.reply_text(confirmation, parse_mode="HTML")
            return

    await update.message.chat.send_action("typing")
    reply = await asyncio.to_thread(run_agent, chat_id, user_text)

    html_reply = format_for_telegram(reply)
    try:
        await update.message.reply_text(html_reply, parse_mode="HTML")
    except Exception:
        await update.message.reply_text(reply)


if __name__ == "__main__":
    token = os.getenv("TELEGRAM_PUBLIC_BOT_TOKEN")
    if not token:
        raise ValueError("TELEGRAM_PUBLIC_BOT_TOKEN not set in .env")

    application = Application.builder().token(token).build()
    application.add_handler(CommandHandler("start", start_handler))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))

    print("ArunCore Telegram Bot is running...")
    application.run_polling()
