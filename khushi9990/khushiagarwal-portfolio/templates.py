# templates.py

import random

from project import PROJECTS
from personal import PERSONAL
from zoyi import ZOYI
from fun import random_response


# -------------------------------
# Helpers
# -------------------------------

def get_project(project_id: str):
    return PROJECTS.get(project_id)


def get_personal(section: str):
    return PERSONAL.get(section)


# -------------------------------
# Project Templates
# -------------------------------

def project_description(project):
    print("PROJECT:", project["id"])
    print("RESPONSES:", project["responses"])
    return random.choice(project["responses"])


def project_purpose(project):
    return project["purpose"]


def project_problem(project):
    return project["problem_statement"]


def project_solution(project):
    return project["solution"]


def project_role(project):
    return project["role"]


def project_status(project):
    return f"Current Status: {project['status']}"


def project_features(project):
    return "Key Features:\n• " + "\n• ".join(project["features"])


def project_workflow(project):
    return "Workflow:\n• " + "\n• ".join(project["workflow"])


def project_architecture(project):
    return "Architecture:\n• " + "\n• ".join(project["architecture"])


def project_challenges(project):
    return "Challenges:\n• " + "\n• ".join(project["challenges"])


def project_future(project):
    return "Future Scope:\n• " + "\n• ".join(project["future_scope"])


def project_frontend(project):
    tech = project["tech_stack"].get("frontend", [])
    return "Frontend:\n• " + "\n• ".join(tech)


def project_backend(project):
    tech = project["tech_stack"].get("backend", [])
    return "Backend:\n• " + "\n• ".join(tech)


def project_database(project):
    tech = project["tech_stack"].get("database", [])
    if not tech:
        return "This project doesn't use a dedicated database."
    return "Database:\n• " + "\n• ".join(tech)


def project_ai(project):
    tech = project["tech_stack"].get("ai", [])
    if not tech:
        return "No dedicated AI technologies are used in this project."
    return "AI Technologies:\n• " + "\n• ".join(tech)


def project_tech(project):
    stack = project["tech_stack"]

    text = ""

    for section, values in stack.items():
        text += f"\n{section.title()}:\n"
        for item in values:
            text += f"• {item}\n"

    return text.strip()


def project_links(project):
    links = project["links"]

    text = ""

    if links.get("github"):
        text += f"GitHub: {links['github']}\n"

    if links.get("live_demo"):
        text += f"Live Demo: {links['live_demo']}\n"

    if links.get("backend"):
        text += f"Backend: {links['backend']}"

    return text.strip()


# -------------------------------
# Personal Templates
# -------------------------------

def personal_response(section):
    info = get_personal(section)

    if not info:
        return None

    return random.choice(info["responses"])


def personal_summary(section):
    info = get_personal(section)

    if not info:
        return None

    return info.get("summary")


def personal_list(section, key):
    info = get_personal(section)

    if not info:
        return None

    values = info.get(key)

    if not values:
        return None

    return "• " + "\n• ".join(values)


# -------------------------------
# Zoyi Templates
# -------------------------------

def zoyi_intro():
    return random.choice(ZOYI["responses"])


def zoyi_built():
    return ZOYI["why_created"]


def zoyi_creator():
    return f"I was created by {ZOYI['creator']}."


def zoyi_purpose():
    return ZOYI["purpose"]


def zoyi_difference():
    return ZOYI["different"]


def zoyi_abilities():
    return "Here's what I can do:\n• " + "\n• ".join(ZOYI["abilities"])


def zoyi_architecture():
    return "Architecture:\n• " + "\n• ".join(ZOYI["architecture"])


def zoyi_workflow():
    return "Workflow:\n• " + "\n• ".join(ZOYI["workflow"])


def zoyi_voice():
    return ZOYI["voice"]["description"]


def zoyi_personality():
    return "Personality:\n• " + "\n• ".join(ZOYI["personality"])


def zoyi_future():
    return "Future Scope:\n• " + "\n• ".join(ZOYI["future_scope"])


def zoyi_fun():
    return "Fun Facts:\n• " + "\n• ".join(ZOYI["fun_facts"])


def zoyi_tech():
    stack = ZOYI["tech_stack"]

    text = ""

    for section, values in stack.items():
        text += f"\n{section.title()}:\n"
        for item in values:
            text += f"• {item}\n"

    return text.strip()


# -------------------------------
# Fun Templates
# -------------------------------

def fun_response(category):
    return random_response(category)