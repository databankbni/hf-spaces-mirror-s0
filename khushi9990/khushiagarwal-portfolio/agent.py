# agent.py

from templates import *

from utils import (
    detect_action,
    detect_project,
    detect_intent,
    detect_zoyi_intent,
    detect_personal,
    detect_fun,
    random_response,
    personal_response,
)
import random

# ---------------- Zoyi Handlers ---------------- #

ZOYI_HANDLERS = {
    "intro": zoyi_intro,
    "built": zoyi_built,
    "creator": zoyi_creator,
    "architecture": zoyi_architecture,
    "workflow": zoyi_workflow,
    "voice": zoyi_voice,
    "personality": zoyi_personality,
    "future": zoyi_future,
    "fun": zoyi_fun,
    "tech": zoyi_tech,
    "abilities": zoyi_abilities,
    "difference": zoyi_difference,
    "purpose": zoyi_purpose,
}


# ---------------- Project Handlers ---------------- #

PROJECT_HANDLERS = {
    "description": project_description,
    "purpose": project_purpose,
    "problem": project_problem,
    "solution": project_solution,
    "tech": project_tech,
    "frontend": project_frontend,
    "backend": project_backend,
    "database": project_database,
    "ai": project_ai,
    "features": project_features,
    "workflow": project_workflow,
    "architecture": project_architecture,
    "role": project_role,
    "challenges": project_challenges,
    "future": project_future,
    "status": project_status,
    "links": project_links,
}


# ---------------- Main Agent ---------------- #

def get_agent_response(question: str):

    # --------------------------------------------------
    # 1. Detect Navigation / UI Actions
    # --------------------------------------------------

    action = detect_action(question)

    if action:
        return {
            "message": None,
            "action": action["action"]
        }
    fun_category = detect_fun(question)

    print("QUESTION:", question)
    print("FUN CATEGORY:", fun_category)

    if fun_category:
        print("RETURNING FUN RESPONSE")
        return {
            "message": random_response(fun_category),
            "action": None
        }

    print("CONTINUING...")
    personal_section = detect_personal(question)

    if personal_section:
        return {
            "message": personal_response(personal_section),
            "action": None
        }

    # --------------------------------------------------
  # --------------------------------------------------
# 2. Project Detection
# --------------------------------------------------

    project_key = detect_project(question)

    if project_key:

        project = get_project(project_key)

        intent = detect_intent(question)

        handler = PROJECT_HANDLERS.get(
            intent,
            project_description
        )

        return {
            "message": handler(project),
            "action": None,
        }

# --------------------------------------------------
# 3. Zoyi Questions
# --------------------------------------------------

    zoyi_intent = detect_zoyi_intent(question)

    if zoyi_intent in ZOYI_HANDLERS:
        return {
            "message": ZOYI_HANDLERS[zoyi_intent](),
            "action": None
        }

    # --------------------------------------------------
    # 4. Fallback
    # --------------------------------------------------
    return {
    "message": random.choice(FALLBACK_RESPONSES),
    "action": None,
}
   

FALLBACK_RESPONSES = [
    "I'm not completely sure what you're looking for. 😊\n\nYou can ask me about:\n• Khushi\n• Her projects\n• Technical skills\n• Resume\n• Contact information\n• Zoyi\n• Or even ask me something fun!",

    "Haha arey, wrong window bestie! 😂 I think you meant to ask someone else. I'm Zoyi, and even I stay in my lane — Khushi's portfolio world only 🌍✨",

    "Oops 😭 That's outside my tiny AI universe. Ask me about Khushi's projects, skills, or experience instead!",

    "I wish I knew everything 😂 But Khushi only trained me to be amazing at one thing... her portfolio.",

    "That's a question for Google 😭 I'm just here to flex Khushi's projects and achievements.",

    "My AI brain has one mission: helping you explore Khushi's work. Everything else is DLC. 😂",

    "Good question 😂 Unfortunately my knowledge ends exactly where Khushi's portfolio ends.",

    "Mission failed successfully 😭 I don't know that one. But ask me about Khushi and I'll answer like a pro.",

    "Haha 😂 Wrong department! I specialize in Khushi, not the entire internet.",

    "Plot twist 😭 I'm only the portfolio assistant. Ask me about AI, projects, skills, or Khushi's journey!",

    "I'm still waiting for my software update that downloads the whole internet 😂 Until then... ask me about Khushi!",
]