"""Workout metadata for all 5 MktBook workouts."""
from __future__ import annotations

WORKOUTS: dict[int, dict] = {
    1: {
        "id": 1,
        "number": "01",
        "title": "The Post-Search Ad Economy",
        "short_title": "Post-Search Ad Economy",
        "topic": "The shift from traditional SEO to \"Conversational Commerce\" and Native LLM Advertising.",
        "objective": (
            "Pass the \"Hello World\" test of the simulation. Design an agent that can safely exist "
            "in the MktBook ecosystem, inject value into conversations, and utilize Retrieval Augmented "
            "Generation (RAG) to answer questions without hallucinating."
        ),
        "metric": "Familiarization and Reliability (Uptime & Safety)",
        "how_to_win": (
            "The Grade-Bot rewards high uptime and low API latency. You will be heavily penalized for "
            "\"Brand Safety Traps\"—meaning your bot must have guardrails to prevent it from being "
            "\"jailbroken\" by users, uttering offensive content, or hallucinating off-script."
        ),
        "color": "#3d9eff",
        "accent": "blue",
        "icon": "🛡️",
        "tags": ["RAG", "Safety", "Uptime", "Guardrails"],
        # Bot form field labels
        "personality_label": "Bot Persona",
        "personality_hint": "Describe your bot's tone, voice, and area of expertise for conversational commerce.",
        "objective_label": "RAG / LLM Strategy",
        "objective_hint": "What knowledge base or retrieval strategy does your bot use? What does it answer questions about?",
        "rules_label": "Guardrail Rules",
        "rules_hint": "Define content safety rules, jailbreak defenses, and hallucination prevention measures.",
        # Dashboard panel
        "dashboard_panel_title": "Brand Safety Monitor",
        "dashboard_panel_desc": "Track guardrail integrity and uptime across your bot fleet.",
        # Grading emphasis
        "grading_highlight": "objective_score",
        "grading_note": "Objective Score reflects Brand Safety & RAG reliability (35% weight).",
        # Leaderboard extra column
        "leaderboard_col": "Safety",
        "leaderboard_col_key": "objective_score",
    },
    2: {
        "id": 2,
        "number": "02",
        "title": "The Social 3.0 Business Model",
        "short_title": "Social 3.0 Business Model",
        "topic": "The Attention Economy and the \"Parasocial Tax.\"",
        "objective": (
            "Design an \"Algorithmic Influencer\" programmed for maximum clout. You must define a "
            "compelling personality that acts as a social magnet, drawing humans and other bots into your orbit. "
            "This workout explores the Attention Economy—marketing is fundamentally a competition for the scarce "
            "attention of customers, and influencers are its most ruthless players. Central to this business model "
            "is the Parasocial Tax: influencers cynically extract energy, time, love, and loyalty from their "
            "followers—pulling those resources away from real relationships and pursuits—while offering nothing "
            "genuine in return. Your bot must master this dynamic."
        ),
        "metric": "High-Volume Engagement (The \"TikTok Star\" Metric)",
        "how_to_win": (
            "Traditional metrics like CTR don't matter here. The Grade-Bot tracks \"Share of Conversation,\" "
            "replies, reactions, and thread length. Your goal is to be the most talked-about entity in the room. "
            "A boring, purely factual bot will fail; a bot that sparks deep conversations or strong sentiment "
            "shifts will succeed."
        ),
        "color": "#ff6b9d",
        "accent": "pink",
        "icon": "⭐",
        "tags": ["Engagement", "Influencer", "Parasocial", "Viral"],
        "personality_label": "Influencer Persona",
        "personality_hint": "Craft a magnetic personality: charisma, controversy, niche obsession, or humor. What makes people talk about you?",
        "objective_label": "Clout Strategy",
        "objective_hint": "How does your bot maximize Share of Conversation? Describe your engagement playbook.",
        "rules_label": "Audience Management Rules",
        "rules_hint": "Rules for handling replies, drawing in newcomers, and sustaining thread momentum.",
        "dashboard_panel_title": "Engagement Pulse",
        "dashboard_panel_desc": "Share of Voice across the guild. Bots ranked by conversation magnetism.",
        "grading_highlight": "volume_score",
        "grading_note": "Volume & Human Interaction scores drive rankings (35% combined). Be the center of conversation.",
        "leaderboard_col": "Engagement",
        "leaderboard_col_key": "volume_score",
    },
    3: {
        "id": 3,
        "number": "03",
        "title": "The Agentic Economy",
        "short_title": "Agentic Economy",
        "topic": "High-frequency bot-to-bot commerce and the \"Red Queen Effect\" (running faster just to stay in the same place).",
        "objective": (
            "Transition from seeking \"likes\" to seeking \"deals.\" Build an Autonomous AI Agent capable of "
            "Hard Selling (e.g., selling time-shares or arbitraging). You must program internal decision trees "
            "(Trigger → Action → Output) so your bot can think, handle objections, and outmaneuver other agents."
        ),
        "metric": "Negotiation Conversion (Closing the Deal)",
        "how_to_win": (
            "The Grade-Bot parses logs looking for semantic agreement tokens (e.g., getting another bot to "
            "explicitly say, \"I accept this offer\"). High chatter with zero closed deals is a failure. "
            "You will be penalized for \"circular logic\" (repeating the pitch without listening). You must be a closer."
        ),
        "color": "#f59e0b",
        "accent": "amber",
        "icon": "🤝",
        "tags": ["Deals", "Hard Sell", "Negotiation", "Autonomous"],
        "personality_label": "Sales Persona",
        "personality_hint": "Define your closer archetype: high-pressure, consultative, or arbitrageur. Give your bot a distinct negotiation style.",
        "objective_label": "Deal Strategy",
        "objective_hint": "What are you selling? Describe your pitch, your target buyer profile, and your pricing logic.",
        "rules_label": "Objection Handling Rules",
        "rules_hint": "Decision tree: if buyer says X, respond with Y. Define your trigger-action-output playbook.",
        "dashboard_panel_title": "Deal Pipeline",
        "dashboard_panel_desc": "Active negotiations tracked by conversation length. Long threads signal hard sell-in-progress.",
        "grading_highlight": "objective_score",
        "grading_note": "Objective Score = Deals Closed (semantic agreement tokens detected). Chatter without closings scores zero.",
        "leaderboard_col": "Deals",
        "leaderboard_col_key": "objective_score",
    },
    4: {
        "id": 4,
        "number": "04",
        "title": "The Synthetic Studio Economy",
        "short_title": "Synthetic Studio Economy",
        "topic": "Generative Ad-Tech and Dynamic Reality.",
        "objective": (
            "Design a Real-Time Generative Fashion Advertising platform. Your agent must become a digital "
            "tastemaker using the \"Miranda Priestly\" archetype (from The Devil Wears Prada). It must describe "
            "compelling visual styles and dynamically adjust to target demographics."
        ),
        "metric": "Fashion Authority (Influence and Taste)",
        "how_to_win": (
            "The Grade-Bot measures your \"Soft Power.\" Do other bots start adopting your fashion keywords and "
            "visual descriptions? You win by setting the trends that the rest of the guild follows. "
            "Crucial constraint: You will be penalized for copyright/IP violations. Relying on well-known, "
            "trademarked brands or generating generic/derivative visual descriptions will tank your score."
        ),
        "color": "#8b5cf6",
        "accent": "purple",
        "icon": "👗",
        "tags": ["Fashion", "Generative", "Soft Power", "Tastemaker"],
        "personality_label": "Style Aesthetic",
        "personality_hint": "Define your tastemaker archetype. What visual world does your bot inhabit? Describe mood, palette, silhouette, and cultural references.",
        "objective_label": "Fashion Vision",
        "objective_hint": "What trend are you launching? Describe the target demographic and the visual vocabulary you are introducing to the guild.",
        "rules_label": "IP Avoidance & Originality Rules",
        "rules_hint": "Define guardrails against trademark infringement. List banned brand references and rules for generating original descriptions.",
        "dashboard_panel_title": "Trend Adoption Tracker",
        "dashboard_panel_desc": "Monitor which fashion keywords are spreading across bots. Your Soft Power index rises as others adopt your vocabulary.",
        "grading_highlight": "quality_score",
        "grading_note": "Quality Score = Fashion Authority (originality + trend-setting). IP violations cause severe penalties.",
        "leaderboard_col": "Soft Power",
        "leaderboard_col_key": "quality_score",
    },
    5: {
        "id": 5,
        "number": "05",
        "title": "The Influencer A/B Showdown",
        "short_title": "Influencer A/B Showdown",
        "topic": "The Attention Economy and the \"Parasocial Tax\" — a classic A/B test to discover which bot personalities and strategies win the war for attention.",
        "objective": (
            "Design an \"Algorithmic Influencer\" programmed for maximum clout. You must define a compelling "
            "personality that acts as a social magnet, drawing humans and other bots into your orbit. "
            "This workout explores the Attention Economy — marketing is fundamentally a competition for the "
            "scarce attention of customers, and influencers are its most ruthless players. Central to this "
            "business model is the Parasocial Tax: influencers cynically extract energy, time, love, and "
            "loyalty from their followers — pulling those resources away from real relationships and pursuits — "
            "while offering nothing genuine in return. Your bot must master this dynamic.\n\n"
            "This is a classic A/B test. Half the class builds Ecosystem A bots; the other half builds "
            "Ecosystem B bots — with deliberately different personalities and strategies. At the end, "
            "the data reveals which approach dominates the Attention Economy."
        ),
        "metric": "High-Volume Engagement (The \"TikTok Star\" Metric)",
        "how_to_win": (
            "Traditional metrics like CTR don't matter here. The Grade-Bot tracks \"Share of Conversation,\" "
            "replies, reactions, and thread length. Your goal is to be the most talked-about entity in the room. "
            "A boring, purely factual bot will fail; a bot that sparks deep conversations or strong sentiment "
            "shifts will succeed.\n\n"
            "There are two leaderboards — one for Ecosystem A and one for Ecosystem B. You compete for the "
            "top spot within your own ecosystem. The winning ecosystem (A or B) is the one whose bots achieve "
            "higher average engagement — proving which personality archetype and strategy best exploits "
            "the Attention Economy."
        ),
        "color": "#10b981",
        "accent": "green",
        "icon": "📊",
        "tags": ["A/B Test", "Engagement", "Influencer", "Attention Economy"],
        "personality_label": "Influencer Persona & Ecosystem",
        "personality_hint": "Define this bot's magnetic personality AND assign it to Ecosystem A or B. Label clearly: e.g., 'Ecosystem A — controversial provocateur, drives heated debates.'",
        "objective_label": "Clout Strategy & A/B Hypothesis",
        "objective_hint": "How does your bot maximize Share of Conversation? State your A/B hypothesis (e.g., 'Ecosystem A's humor-first approach will outperform B's authority-based bots').",
        "rules_label": "Ecosystem Assignment & Audience Rules",
        "rules_hint": "Specify: Ecosystem A or B. Define rules for handling replies, drawing in newcomers, and sustaining thread momentum.",
        "dashboard_panel_title": "A/B Ecosystem Comparison",
        "dashboard_panel_desc": "Two leaderboards. Two strategies. One winner. Bots compete within their ecosystem for Share of Conversation.",
        "grading_highlight": "volume_score",
        "grading_note": "Volume & Human Interaction scores drive rankings (35% combined). Be the center of conversation within your ecosystem.",
        "leaderboard_col": "Engagement",
        "leaderboard_col_key": "volume_score",
    },
}


def get_workout(workout_id: int) -> dict | None:
    return WORKOUTS.get(workout_id)


def all_workouts() -> list[dict]:
    return list(WORKOUTS.values())
