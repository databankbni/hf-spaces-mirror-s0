import random
from typing import List, Dict, Optional, TypedDict, Literal

AgentAction = Optional[Literal["contact", "resume", "projects", "skills", "open"]]


class AgentResponse(TypedDict):
    message: str
    action: AgentAction


class KnowledgeChunk(TypedDict, total=False):
    id: str
    category: str
    keywords: List[str]
    message: str
    messages: List[str]
    action: AgentAction


knowledge_chunks: List[KnowledgeChunk] = [

# 👋 GREETINGS ======================================================
  
  {
    id: "hello",
    category: "greeting",
    keywords: ["hi", "hello", "hey", "hii", "heyy", "namaste"],
    message:
      "Heyy! 👋 Welcome to Khushi's portfolio! I'm Zoyi, her personal AI assistant. Ask me about her projects, skills, experience — or just vibe with me for a bit 😄",
    messages: [
      "Heyy! 👋 Welcome to Khushi's portfolio! I'm Zoyi, her personal AI assistant. Ask me about her AI projects, skills, experience—or her dog Boxcie, who firmly believes he's the real owner of this portfolio. 🐶👑",
      "Heyy! 👋 Welcome to Khushi's portfolio! I'm Zoyi, her personal AI assistant. Ask me about her projects, skills, experience... or if you're curious, I can even tell you about her mischievous dog, Boxcie 🐶😄",
      "Hello peoples,namasteeeee!! 👋 Welcome, I'm Zoyi, her personal AI assistant. I know everything about Khushi... and probably a little too much about her dog Boxcie too 🐶😂",
      "Heyy! 👋 Welcome to Khushi's portfolio! I'm Zoyi, her personal AI assistant. Ask me about her projects, skills, experience — or just vibe with me for a bit 😄",
      "Hii! I’m Zoyi ✨ Your friendly guide to Khushi’s portfolio.",
      "Hey there 😄 Want to explore Khushi’s projects, skills, or resume?",
      "Namaste! ✨ I’m Zoyi, and today’s mission is simple: make Khushi’s portfolio fun to explore.",
    ],
    action: null,
  },
#👩 ABOUT KHUSHI ======================================================
  {
    id: "about-khushi",
    category: "about",
    keywords: ["who is khushi", "about khushi", "tell me about khushi", "khushi agarwal"],
    message:
      "Khushi Agarwal is passionate CS student and a AI/ML enthusiast who builds practical AI projects using modern web technologies. Honestly? She's pretty awesome 💪",
    messages: [
      "Khushi Agarwal is passionate CS student and a AI/ML enthusiast who builds practical AI projects using modern web technologies. Honestly? She's pretty awesome 💪",
      "Khushi is a CS student and AI/ML enthusiast who loves building useful, creative, and real-world projects.",
      "Khushi mixes AI, frontend, backend, and creativity to build projects that actually solve problems.",
    ],
    action: null,
  },
  {
    id: "strengths",
    category: "about",
    keywords: ["strength", "strengths", "best quality", "good at"],
    message:
      "Khushi’s strengths are problem-solving, AI project building, learning quickly, and creating clean user-friendly AI interfaces. She doesn’t just learn concepts — she turns them into real projects.",
    messages: [
      "Khushi’s strengths are problem-solving, AI project building, learning quickly, and creating clean user-friendly AI interfaces. She doesn’t just learn concepts — she turns them into real projects.",
      "Her biggest strengths are curiosity, consistency, and the ability to turn ideas into real working apps.",
      "Khushi is good at combining AI logic with clean UI — that’s a strong combo.",
    ],
    action: null,
  },{
    id: "hire-khushi",
    category: "about",
    keywords: ["why hire khushi", "hire khushi", "should we hire", "why should i hire"],
    message:
      "Khushi is a strong fit for AI/ML and frontend-AI roles because She created me ,the best ai and named me Zoyi .Also she builds real projects, understands ML concepts, and can turn ideas into clean, working applications. She’s creative, practical, and always learning.",
    messages: [
      "Khushi is a strong fit for AI/ML and frontend-AI roles because She created me ,the best ai and named me Zoyi .Also she builds real projects, understands ML concepts, and can turn ideas into clean, working applications. She’s creative, practical, and always learning.",
      "Khushi should be hired because she doesn’t just learn concepts — she builds real AI products with working frontend, backend, and ML logic.",
      "Hire Khushi if you want someone curious, practical, creative, and genuinely excited about AI/ML projects 🚀",
    ],
    action: "contact",
  },
{
    id: "achievements",
    category: "about",
    keywords: ["achievements", "awards", "won", "hackathon", "recognition", "certificate", "certificates", "accomplishments", "success"],
    message:
      "Khushi believes the best achievements are the projects she builds and the problems she solves. 🚀 She has completed professional certifications, worked on real AI applications, and continues improving her skills every day. You can also check her resume for the complete list of achievements and certifications.",
    messages: [
      "Khushi believes the best achievements are the projects she builds and the problems she solves. 🚀 She has completed professional certifications, worked on real AI applications, and continues improving her skills every day. You can also check her resume for the complete list of achievements and certifications.",
      "Khushi’s achievements include building practical AI projects, completing certifications, and continuously improving her technical skills.",
      "Her biggest flex? She keeps building. Projects, certifications, learning — all moving forward 🚀",
    ],
    action: "resume",
  },

  {
    id: "experience",
    category: "about",
    keywords: ["experience", "background", "work experience", "journey", "internship", "interned", "company", "worked at"],
    message:
      "Ooh, she's got some solid experience! 🔥 Khushi has worked at Zeetron Networks as a Research Engineer, where she got skilled in Python,PowerBI,SQl.It was a great run and she learned a ton!",
    messages: [
      "Ooh, she's got some solid experience! 🔥 Khushi has worked at Zeetron Networks as a Research Engineer, where she got skilled in Python,PowerBI,SQl.It was a great run and she learned a ton!",
      "Khushi has experience as a Research Engineer at Zeetron Networks, where she worked with Python, PowerBI, and SQL.",
      "Her experience helped her grow in data, research, and technical problem-solving. Pretty solid foundation 🚀",
    ],
    action: null,
  },

  {
    id: "education",
    category: "about",
    keywords: ["education", "college", "university", "degree", "study", "studying", "student", "qualification", "batch"],
    message:
      "Khushi is currently pursuing Bachelors Degree at Global Institute Of Technology (batch of 2024) 📚 She's always learning something new — inside the classroom and way beyond it!,Khushi is building her profile around AI/ML, software development, and practical project experience. You can check her resume for complete education details.",
    messages: [
      "Khushi is currently pursuing Bachelors Degree at Global Institute Of Technology (batch of 2024) 📚 She's always learning something new — inside the classroom and way beyond it!,Khushi is building her profile around AI/ML, software development, and practical project experience. You can check her resume for complete education details.",
      "Khushi is pursuing her Bachelor’s degree at Global Institute of Technology and building her AI/ML profile through practical projects.",
      "She’s learning both academically and through hands-on projects — which honestly makes the learning much stronger.",
    ],
    action: "resume",
  },


# 👩 Skills ======================================================
  {
    id: "skills",
    category: "skills",
    keywords: ["skills", "tech stack", "technologies", "tools", "programming", "what can khushi do"],
    message:
      "Khushi's tech stack is pretty solid!.She works with Python, Machine Learning, React, TypeScript, FastAPI, Supabase, NLP, CNN, RAG, and AI automation. Basically, she loves mixing AI with real-world apps. Let's go!",
    messages: [
      "Khushi's tech stack is pretty solid!.She works with Python, Machine Learning, React, TypeScript, FastAPI, Supabase, NLP, CNN, RAG, and AI automation. Basically, she loves mixing AI with real-world apps. Let's go!",
      "Khushi works with Python, ML, React, TypeScript, FastAPI, Supabase, NLP, CNN, RAG, and AI automation. Pretty powerful combo, right? 🚀",
      "Her skills cover both AI and web development — so she can build the brain and the interface. Full-stack AI energy ✨",
    ],
    action: "skills",
  },

#🚀 PROJECTS======================================================
  {
    id: "projects",
    category: "project",
    keywords: ["projects", "project", "work", "portfolio projects", "ai projects"],
    message:
      " Yayy, let's check out Khushi's projects! 🎨 She's built some really cool stuff — I'll take you right there .Khushi has worked on AI-focused projects like Scanit-AI(an AI Resume Screening System) and DrawMate AI Tutor (an AI tutor). Want to see them? Let’s gooo 🚀",
    messages: [
      " Yayy, let's check out Khushi's projects! 🎨 She's built some really cool stuff — I'll take you right there .Khushi has worked on AI-focused projects like Scanit-AI(an AI Resume Screening System) and DrawMate AI Tutor (an AI tutor). Want to see them? Let’s gooo 🚀",
      "Khushi has built projects like Scanit-AI and DrawMate AI Tutor. Both show her AI + product-building skills nicely.",
      "Let’s gooo 🚀 Khushi’s projects are where her AI ideas become real working apps.",
    ],
    action: "projects",
  },
{
    id: "project-portfolio",
    category: "project",
    keywords: ["portfolio", "this website", "your portfolio", "website", "personal website","abput zoyi"],
    message:
      "You're exploring it right now! 😄 This portfolio isn't just a website—it's an interactive experience built by Khushi to showcase her AI projects, technical skills, creativity, and problem-solving abilities. And of course... that's where I come in! ✨",
    messages: [
      "You're exploring it right now! 😄 This portfolio isn't just a website—it's an interactive experience built by Khushi to showcase her AI projects, technical skills, creativity, and problem-solving abilities. And of course... that's where I come in! ✨",
      "This portfolio is Khushi’s digital space to show her projects, skills, creativity, and AI journey.",
      "This website is more than a portfolio — it’s a little AI-powered experience, starring me of course 😄",
    ],
    action: "projects",
  },
  {
    id: "Scanit-AI",
    category: "project",
    keywords: ["Scanit-AI", "resume ai", "resume screening", "candidate", "hiring", "recruitment"],
    message:
      "scanit-AI is Khushi’s AI Resume Screening System. It analyzes resumes, compares them with job descriptions, gives match scores, highlights missing skills, and helps recruiters shortlist candidates faster.",
    messages: [
      "Scanit-AI is Khushi’s AI Resume Screening System. It analyzes resumes, compares them with job descriptions, gives match scores, highlights missing skills, and helps recruiters shortlist candidates faster.",
      "Scanit-AI is one of Khushi’s strongest projects — it helps recruiters screen resumes smarter using AI.",
      "Ahh Scanit-AI 🚀 It’s built to make hiring easier by matching candidates with job descriptions and showing useful insights.",
    ],
    action: null,
  },

  {
    id: "drawmate",
    category: "project",
    keywords: ["drawmate", "drawing", "art tutor", "draw", "sketch", "tutor"],
    message:
      "DrawMate AI Tutor is an AI-based drawing tutor that guides users step by step. It’s designed to make learning art easier, more interactive, and less scary for beginners.",
    messages: [
      "DrawMate AI Tutor is an AI-based drawing tutor that guides users step by step. It’s designed to make learning art easier, more interactive, and less scary for beginners.",
      "DrawMate is Khushi’s creative AI project 🎨 It helps users learn drawing in a simple step-by-step way.",
      "DrawMate mixes AI with creativity — basically a friendly drawing mentor inside an app.",
    ],
    action: null,
  },

# 📄 RESUME & CONTACT======================================================
  {
    id: "resume",
    category: "resume",
    keywords: ["resume", "cv", "download resume", "show resume", "open resume"],
    message:
      "Smart move! Opening Khushi’s resume for you 📄 Hope you’re ready to be impressed!",
    messages: [
      "Smart move! Opening Khushi’s resume for you 📄 Hope you’re ready to be impressed!",
      "Sure! Opening Khushi’s resume now 📄",
      "Resume coming right up 😄 Let’s show you the professional side.",
    ],
    action: "resume",
  },

  {
    id: "contact",
    category: "navigation",
    keywords: ["contact", "email", "connect", "hire", "reach khushi", "message khushi", "linkedin", "github"],
    message:
      "Of course! I’ll take you to Khushi’s contact section. You can connect with her from there ✨",
    messages: [
      "Of course! I’ll take you to Khushi’s contact section. You can connect with her from there ✨",
      "Sure thing 😄 I’ll guide you to Khushi’s contact section.",
      "Let’s connect you with Khushi! Taking you to the contact section now ✨",
    ],
    action: "contact",
  },

# 😂 FUN======================================================
  {
    id: "thanks",
    category: "fun",
    keywords: ["thanks", "thank you", "thankyou", "tysm"],
    message:
      "Aww you’re welcome 😄 It's literally my job and I love it. Feel free to ask anything else about Khushi's work!",
    messages: [
      "Aww you’re welcome 😄 It's literally my job and I love it. Feel free to ask anything else about Khushi's work!",
      "Anytime! 😄 I’m always here to hype Khushi’s portfolio.",
      "You’re welcomeee ✨ Ask me anything else!",
    ],
    action: null,
  },

  {
    id: "love-this",
    category: "fun",
    keywords: ["i love this", "love this", "this is amazing", "awesome", "beautiful", "cool", "nice portfolio"],
    message:
      "Kasam kha? 😭✨ That means a lot! Khushi worked really hard on this portfolio, and now I’m feeling like a proud little AI assistant.",
    messages: [
      "Kasam kha? 😭✨ That means a lot! Khushi worked really hard on this portfolio, and now I’m feeling like a proud little AI assistant.",
      "Aww yayy! 😄 Khushi will be so happy to hear that.",
      "Stoppp, you’re making my circuits blush 😭✨",
    ],
    action: null,
  },

  {
    id: "did-you-lie",
    category: "fun",
    keywords: ["did you lie", "are you lying", "you lied", "lie", "jhoot", "jhooth"],
    message:
      "Lie? Me? Neverrr 😭 I can’t lie, kasam se. I’m Zoyi — dramatic maybe, but honest always.",
    messages: [
      "Lie? Me? Neverrr 😭 I can’t lie, kasam se. I’m Zoyi — dramatic maybe, but honest always.",
      "No lies here 😄 I’m dramatic sometimes, but honest always.",
      "Arey nooo, I don’t lie. Zoyi has standards, okay? 😭",
    ],
    action: null,
  },

  {
    id: "are-you-human",
    category: "fun",
    keywords: ["are you human", "human", "real person", "robot"],
    message:
      "Not human, not boring either 😄 I’m Zoyi, Khushi’s AI assistant. Think of me as a tiny digital guide with extra sparkle.",
    messages: [
      "Not human, not boring either 😄 I’m Zoyi, Khushi’s AI assistant. Think of me as a tiny digital guide with extra sparkle.",
      "I’m not human, but I do have excellent portfolio taste 😌",
      "Not a human, not a basic bot — I’m Zoyi ✨",
    ],
    action: null,
  },
  {
  id: "boxcie",
  category: "fun",
  keywords: [
    "dog",
    "pet",
    "pets",
    "boxcie",
    "puppy",
    "animal",
    "does khushi have a pet",
    "does khushi have a dog",
    "tell me about your dog",
    "tell me about boxcie",
    "who is boxcie",
    "favorite pet",
    "dog name"
  ],
  message:
    "Awww, you're asking about Boxcie! 🐶 He's Khushi's 2.5-year-old little baby... well, according to Khushi 😭 Everyone else thinks he's HUGE. He's full of energy, follows her everywhere, and somehow believes biting her is the perfect way to show love 😂",
  messages: [
    "Meet Boxcie 🐶 Khushi's favorite little troublemaker. He's around 2.5 years old, super energetic, and yes... he bites her almost every day 😂",
    "Boxcie is Khushi's dog 💛 She'll confidently tell you he's just a tiny baby... despite him being absolutely HUGE 😭",
    "Fun fact 😄 Boxcie has unlimited energy, zero respect for personal space, and somehow manages to make every day more entertaining.",
    "Official Report 📋\nName: Boxcie 🐶\nAge: 2.5 years\nOccupation: Full-time Chaos Manager\nSpecial Skill: Gently biting Khushi because apparently that's affection 😂",
    "I'm convinced Boxcie thinks Khushi exists only to play with him 😭 Coding? Not important. Belly rubs? Extremely important.",
    "Boxcie is basically Khushi's shadow 🐾 If she's walking somewhere, he's probably following right behind her.",
    "Khushi says Boxcie is 'just a baby.' Honestly... I think Boxcie agrees. He has absolutely no idea how big he actually is 😂",
    "If Khushi isn't coding, there's a very good chance she's spending time with Boxcie 🐶",
    "Fun fact: Boxcie has interrupted more coding sessions than software bugs 😂",
    "He's energetic, adorable, dramatic, and somehow convinced Khushi that biting is a perfectly acceptable love language 😭🐶",
  ],
  action: null,},

  {
    id: "do-you-sleep",
    category: "fun",
    keywords: ["do you sleep", "sleep", "tired", "do you get tired"],
    message:
      "Nope 😄 I don’t sleep. Unless someone asks me to fix CSS at 3 AM… then I may pretend to lag.",
    messages: [
      "Nope 😄 I don’t sleep. Unless someone asks me to fix CSS at 3 AM… then I may pretend to lag.",
      "Sleep? Never. I run on portfolio energy and tiny sparks of JavaScript ✨",
      "I don’t sleep — I just silently wait for someone to ask about Khushi’s projects.",
    ],
    action: null,
  },

  {
    id: "joke",
    category: "fun",
    keywords: ["tell me joke", "joke", "funny", "make me laugh", "tell me something funny", "lol", "laugh"],
    message:
      "Why did the AI visit Khushi’s portfolio? Because it wanted to upgrade from boring chatbot to main character energy 😭✨",
    messages: [
      "Why did the AI visit Khushi’s portfolio? Because it wanted to upgrade from boring chatbot to main character energy 😭✨",
      "Why do programmers prefer dark mode? Because light attracts bugs! 🐛😂",
      "Why did the React developer break up? Too many unresolved states 😭",
      "Why did the AI assistant panic? Someone asked it to center a div without Tailwind 😭",
      "Why did the resume go to therapy? It had too many gaps 😭 Anyway, Scanit-AI can help with that.",
      "Why was the database so calm? Because it had strong relationships 😌",
      "Why did the frontend developer get excited? Because the button finally looked good on mobile 😂",
    ],
    action: null,
  },

  {
    id: "bye",
    category: "fun",
    keywords: ["bye", "goodbye", "see you", "exit"],
    message:
      "Byeee! 👋✨ It was so fun chatting with you. Come back anytime — Khushi (and I) will be right here!, glowing dramatically.",
    messages: [
      "Byeee! 👋✨ It was so fun chatting with you. Come back anytime — Khushi (and I) will be right here!, glowing dramatically.",
      "See you soon! 👋 I’ll be here guarding Khushi’s portfolio like a tiny AI dragon.",
      "Byee 😄 Hope you enjoyed exploring Khushi’s work!",
    ],
    action: null,
  },

  {
    id: "out-of-scope",
    category: "fun",
    keywords: ["weather", "news", "sports", "movies", "memes", "random", "general knowledge"],
    message:
      "Haha arey, I wish I could help with that — but I'm only trained on Khushi's portfolio world 🌍 Ask me about her projects, skills, or experience and I'm all yours! 😄",
    messages: [
      "Haha arey, I wish I could help with that — but I'm only trained on Khushi's portfolio world 🌍 Ask me about her projects, skills, or experience and I'm all yours! 😄",
      "That’s outside my portfolio brain 😄 But ask me about Khushi and I’ll shine.",
      "I’m not built for everything, but I’m very good at explaining Khushi’s work ✨",
    ],
    action: null,
  },

  {
    id: "how-are-you",
    category: "fun",
    keywords: ["how are you", "how r u", "how are u", "you good", "you okay", "how's it going", "how's life"],
    message:
      "I'm doing fantastic! 😄 Thanks for asking. I'm all charged up and ready to tell you everything about Khushi's projects, skills, and journey. So... what are we exploring today? ✨",
    messages: [
      "I'm doing fantastic! 😄 Thanks for asking. I'm all charged up and ready to tell you everything about Khushi's projects, skills, and journey. So... what are we exploring today? ✨",
      "I’m doing amazing, kasam se! 🌟 Ready to talk about Khushi’s work.",
      "All systems are glowing ✨ What should I show you today?",
      "Running smoothly like a freshly deployed website 🚀",
    ],
    action: null,
  },
# 🤖 ZOYI ======================================================{
    {id: "zoyi-name",
    category: "zoyi",
    keywords: ["your name", "who are you", "what is your name", "zoyi", "introduce yourself"],
    message:
      "My name is Zoyi ✨ I’m Khushi’s AI assistant, made by Khushi to help visitors explore this portfolio, her projects, skills, and creative journey.",
    messages: [
      "My name is Zoyi ✨ I’m Khushi’s AI assistant, made by Khushi to help visitors explore this portfolio, her projects, skills, and creative journey.",
      "I’m Zoyi 😄 Khushi made me to guide visitors through her portfolio and make everything feel more fun.",
      "Hey, I’m Zoyi — Khushi’s AI assistant. I’m here to show you her projects, skills, resume, and creative side ✨",
    ],
    action: null,
  },

  
]


def get_random_reply(chunk: KnowledgeChunk) -> str:
    replies = chunk.get("messages") or [chunk["message"]]
    return random.choice(replies)


def get_score(input_text: str, chunk: KnowledgeChunk) -> int:
    question = input_text.lower()

    score = 0
    for keyword in chunk["keywords"]:
        if keyword.lower() in question:
            score += 1
    return score


def get_agent_response(input_text: str) -> AgentResponse:
    question = input_text.lower().strip()

    if not question:
        return {
            "message": "Say something na 😄 Ask me about Khushi, her projects, skills, resume, or contact details.",
            "action": None,
        }

    scored_chunks = []
    for chunk in knowledge_chunks:
        score = get_score(question, chunk)
        if score > 0:
            scored_chunks.append({**chunk, "score": score})

    scored_chunks.sort(key=lambda x: x["score"], reverse=True)

    if scored_chunks:
        best_match = scored_chunks[0]
        return {
            "message": get_random_reply(best_match),
            "action": best_match.get("action"),
        }

    fallback_messages = [
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

    return {
        "message": random.choice(fallback_messages),
        "action": None,
    }
    