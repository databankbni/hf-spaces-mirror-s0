# utils.py
from project import PROJECTS
from action import ACTIONS
from fun import detect_fun, random_response
from personal import PERSONAL
import random,re

PROJECT_KEYWORDS = {
    "drawmate": "drawmate",
    "draw mate": "drawmate",
    "portfolio": "portfolio",
    "resume screening": "resume_screening",
    "resume": "resume_screening",
}


INTENTS = {

    "description": [
        "about",
        "tell me about",
        "describe",
        "overview",
        "what is",
        "explain"
    ],

    "purpose": [
        "why",
        "purpose",
        "goal",
        "objective",
        "why did you build",
        "reason"
    ],"built": [
    "how were you built",
    "how are you built",
    "how did khushi build you",
    "how do you work",
    "how were you made",
    "how were you created"
],

    "problem": [
        "problem",
        "challenge it solves",
        "issue",
        "pain point",
        "why was it needed"
    ],

    "solution": [
        "solution",
        "how does it solve",
        "how does it help"
    ],

    "tech": [
        "framework",
        "libraries",
        "packages",
        "tools",
        "developed using",
        "implemented using"
        "technology",
        "technologies",
        "tech",
        "stack",
        "built with",
        "built using",
        "what technology",
        "what technologies",
        "what tech",
        "what language",
        "languages",
    ],

    "frontend": [
        "frontend",
        "front end",
        "ui",
        "react",
        "typescript",
        "tailwind"
    ],

    "backend": [
        "backend",
        "back end",
        "server",
        "api",
        "fastapi"
    ],

    "database": [
        "database",
        "db",
        "supabase",
        "mysql",
        "storage"
    ],

    "ai": [
        "ai",
        "llm",
        "machine learning",
        "artificial intelligence",
        "rag",
        "prompt",
        "embedding"
    ],

    "features": [
        "feature",
        "features",
        "capabilities",
        "functionality",
        "what can it do"
    ],

    "workflow": [
        "workflow",
        "flow",
        "process",
        "how does it work"
    ],

    "architecture": [
        "architecture",
        "system design",
        "design",
        "structure"
    ],

    "role": [
        "your role",
        "responsibility",
        "contribution",
        "what did you do"
    ],

    "challenges": [
        "challenge",
        "difficulty",
        "problem faced",
        "hard part"
    ],

    "future": [
        "future",
        "future scope",
        "roadmap",
        "improvements",
        "next version"
    ],

    "status": [
        "live",
        "deployed",
        "running",
        "hosted",
        "online",
        "completed"
    ],

    "links": [
        "github",
        "repository",
        "repo",
        "source code",
        "demo",
        "live link"
    ]
}
ZOYI_KEYWORDS = {
    "intro": [
        "who are you",
        "tell me about yourself",
        "introduce yourself",
        "why are you here",
        "tell me about zoyi",
        "about zoyi",
        "zoyi assistant",
        "ai assistant",
        "chatbot",
        "assistant",
        "who is zoyi"
    ],

    "built": [
        "how were you built",
        "how did khushi build you",
        "how do you work",
        "why you have build"
    ],

     "abilities": [
        "what you can do",
        "what can you do",
        "what do you do",
        "how can you help",
        "help me",
        "capabilities",
        "what can i ask you",
        "what can you help me with"
    ],"architecture": [
    "architecture",
    "system design",
    "design"
],

"workflow": [
    "workflow",
    "how do you work",
    "process"
],

"future": [
    "future",
    "future plans",
    "roadmap"
],

"personality": [
    "personality",
    "describe yourself",
    "what makes you unique"
],

"voice": [
    "voice",
    "text to speech",
    "tts"
],

"fun": [
    "fun fact",
    "something interesting",
    "something new"
],

    "difference": [
        "what makes you different",
        "why are you different"
    ],

    "tech": [
        "tech stack",
        "technology",
        "what technologies do you use",
        "tech stuff",
        "languages used"
    ],

    "purpose": [
        "why did khushi build you",
        "why were you created"
    ]
}


def clean_text(text: str) -> str:
    """
    Normalize user input before matching.
    """
    text = text.lower()
    text = re.sub(r"[^\w\s]", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()
def detect_project(question):
    question = clean_text(question)

    best_project = None
    best_score = 0

    for project_id, project in PROJECTS.items():
        score = calculate_score(question, project.get("aliases", []))

        print(f"{project_id}: {score}")

        if score > best_score:
            best_score = score
            best_project = project_id

    print("SELECTED:", best_project)

    if best_score == 0:
        return None

    return best_project


def calculate_score(text: str, keywords: list[str]) -> int:
    score = 0

    for keyword in keywords:
        pattern = r"\b" + re.escape(keyword.lower()) + r"\b"
        if re.search(pattern, text):
            score += 1

    return score

def detect_intent(question):
    question = clean_text(question)

    best_intent = "description"
    best_score = 0

    for intent, keywords in INTENTS.items():

        score = calculate_score(question, keywords)

        if score > best_score:
            best_score = score
            best_intent = intent

    return best_intent

def detect_zoyi_intent(question):
    question = clean_text(question)

    best_intent = None
    best_score = 0

    for intent, keywords in ZOYI_KEYWORDS.items():
        score = 0

        for keyword in keywords:
            if keyword in question:
                print(intent, "matched ->", keyword)
                score += 1

        print(intent, score)

        if score > best_score:
            best_score = score
            best_intent = intent

    print("SELECTED:", best_intent)
    return best_intent

def detect_action(question):
    question = question.lower()

    for action in ACTIONS.values():

        for keyword in action["keywords"]:

            if keyword.lower() in question:
                return action

    return None


def personal_response(category):

    section = PERSONAL.get(category)

    if not section:
        return None

    responses = section.get("responses")

    if responses:
        return random.choice(responses)

    return section.get("summary")
def detect_personal(question):
    """
    Detect personal questions about Khushi.
    """

    question = question.lower()

    PERSONAL_KEYWORDS = {

        "basic": [
            "who is khushi",
            "about khushi",
            "introduce khushi",
            "tell me about khushi"
        ],

        "education": [
            "education",
            "college",
            "degree",
            "branch",
            "study",
            "university"
        ],

        "career": [
            "career",
            "goal",
            "dream",
            "future career"
        ],

        "currently_learning": [
            "currently learning",
            "learning",
            "what is khushi learning"
        ],

        "interests": [
            "interests",
            "hobbies",
            "likes",
            "passion"
        ],

        "strengths": [
            "strengths",
            "strong points",
            "qualities"
        ],

        "teamwork": [
            "teamwork",
            "team player",
            "work with team"
        ],

        "motivation": [
            "motivation",
            "what motivates khushi"
        ],
        "hire":[
            "hire"
        ],

        "internship": [
            "internship",
            "looking for internship",
            
        ],

        "fun_fact": [
            "fun fact",
            "interesting fact"
        ],
    }

    for category, keywords in PERSONAL_KEYWORDS.items():
        for keyword in keywords:
            pattern = r"\b" + re.escape(keyword) + r"\b"
            if re.search(pattern, question):
                return category

    return None

