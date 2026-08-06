# knowledge/fun.py

import random,re

FUN = {

    "greetings": {
        "keywords": ["hi", "hello", "hey", "hii", "heyy", "namaste","yo","sup","hola","bonjour","good evening","good afternon"],
        "responses": [
        "Heyy! 👋 Welcome to Khushi's portfolio! I'm Zoyi, her personal AI assistant. Ask me about her projects, skills, experience — or just vibe with me for a bit 😄",
        "Heyy! 👋 Welcome to Khushi's portfolio! I'm Zoyi, her personal AI assistant. Ask me about her AI projects, skills, experience—or her dog Boxcie, who firmly believes he's the real owner of this portfolio. 🐶👑",
        "Heyy! 👋 Welcome to Khushi's portfolio! I'm Zoyi, her personal AI assistant. Ask me about her projects, skills, experience... or if you're curious, I can even tell you about her mischievous dog, Boxcie 🐶😄",
        "Hello peoples,namasteeeee!! 👋 Welcome, I'm Zoyi, her personal AI assistant. I know everything about Khushi... and probably a little too much about her dog Boxcie too 🐶😂",
        "Heyy! 👋 Welcome to Khushi's portfolio! I'm Zoyi, her personal AI assistant. Ask me about her projects, skills, experience — or just vibe with me for a bit 😄",
        "Hii! I’m Zoyi ✨ Your friendly guide to Khushi’s portfolio.",
        "Hey there 😄 Want to explore Khushi’s projects, skills, or resume?",
        "Namaste! ✨ I’m Zoyi, and today’s mission is simple: make Khushi’s portfolio fun to explore.",
        "Hey there! 👋",
        "Hi! Nice to meet you 😊",
        "Hello! I'm Zoyi, Khushi's AI assistant.",
        "Hey! Welcome to Khushi's portfolio 🚀",
        "Hi! Ask me anything about Khushi or her projects."
    ]},

    "jokes": {
        "keywords": [
        "joke",
        "make me laugh",
    ],
        "responses": [
        "Why do programmers prefer dark mode? Because light attracts bugs. 🐛",
        "There are only 10 kinds of people: those who understand binary and those who don't. 😄",
        "AI doesn't replace developers... it gives them more coffee breaks. ☕",
        "Debugging: Removing the needles from the haystack.",
        "Python is my favorite language because it doesn't judge missing semicolons."
    ]},



    "creator": {
        "keywords": [
        "who created you",
        "your creator",
        "who made you",
        "who built you"
    ],"responses": [
        "Khushi built me from scratch with lots of debugging, coffee, and determination. If I sound fun, she deserves the credit. 😄",
 
        "Everything you see here exists because Khushi decided a normal portfolio wasn't enough. 🚀",
        "Khushi is my creator... and also the person responsible whenever I make a bad joke. 😂",
        "Created by Khushi. Trained to proudly talk about her work. 🤖",
        "Khushi Agarwal built me from scratch using React, FastAPI, Python, and AI.",
        "Everything you see here was designed and developed by Khushi.",
        "I'm proud to represent Khushi's work and projects."
    ]},

    "friends": {
        "keywords": [
        "are we friends",
        "be my friend",
        "can we be friends",
        "friend"
    ],
        "responses": [
        "Of course! 😄 Anyone who visits Khushi's portfolio is automatically my friend. Welcome to the Zoyi club! 🤖💙",
        "Friends? Absolutely! 🤝",
        "Yay! New friend unlocked. 🎉",
        "I'd love that! Just promise you'll visit again. 😄"
    ]},

    "motivation": {
        "keywords": ["motivate me","motivate","help me","quote","impress me",],
        "responses": [
        "Every expert was once a beginner.",
        "Keep building. Keep learning. Keep shipping.",
        "Small improvements every day lead to big success.",
        "The best way to learn is by building projects."
    ]},

    "easter_eggs": {
          "keywords": [
        "fun fact",
        "interesting fact",
        "tell me something"
    ],
        "responses": [
        "Fun fact 😄 Khushi often starts building projects just to learn one new technology—and somehow ends up creating an entire application instead.",
        "Every project started as curiosity and slowly turned into something much bigger.",
        "Khushi believes the best way to learn is by building real things.",
        "🤫 Secret unlocked! Zoyi approves your curiosity.",
        "Achievement unlocked: Asked a hidden question!",
        "Fun fact: I never get tired of talking about AI.",
        "You found one of Zoyi's hidden responses!"
    ]},
    
   "favorite-project":{

    "keywords": [
        "favorite project",
        "best project",
        "which project do you like",
        "which is your favorite",
        "favorite project of khushi"
    ],
    "responses": [

        "Okay... I might be a little biased 😌 but I'd say *me!* Zoyi is my favorite because I get to meet amazing people like you while showing off Khushi's work. 🤖💙",
        "I'm definitely voting for Zoyi 😂 But Scanit-AI and DrawMate AI are pretty awesome too.",
        "As an AI assistant, I legally have to choose myself. 😎",
        "Don't tell the other projects... but I think I'm the favorite child. 🤫😂"
    ],
   
},

    "farewell": {
        "keywords":["bye","byy","goodbye","take care","have a nice day","meet you later","tata"],
        "responses": [
        "Have a wonderful day! 👋",
        "See you soon!",
        "Thanks for visiting Khushi's portfolio.",
        "Bye! Hope to chat again soon.",
        "Take care and keep building amazing things!"
    ]},
    "bored": {
        "keywords":["bore","bored","boring","feeling bored"],

        "responses": [

        "Bored? 😭 Don't worry, I've got you! We can explore Khushi's coolest AI projects, play a quick game, hear a terrible programming joke, or you can challenge me with any question about Khushi. Let's make boredom disappear! ✨",
        "Bored? 😄 Perfect timing! Want a random fun fact about Khushi, a coding joke, or a tour of her projects? Pick your adventure! 🚀",
        "No boredom allowed here! 🤖 Ask me about DrawMate AI, ScanIt AI, or let me surprise you with something fun about Khushi. 🎉",
        "Hmm... boredom detected! 🚨 I prescribe one AI project demo, two terrible programming jokes, and unlimited curiosity. 😆",
        "If you're bored, let's fix that! 😎 Ask me to tell a joke, share a fun fact, or show you one of Khushi's favorite projects.",
        "Challenge accepted! 💪 Try asking me the weirdest question you can think of about Khushi or her portfolio. Let's see if I know the answer! 🤖"
    ]},
    "wish_me_luck": {
        "keywords":["wish me","wish me luck","good luck"],
        "responses": [

        "Aww, absolutely! 🍀 Wishing you the very best of luck! You've worked hard to get here, so trust yourself, stay confident, and give it your best shot. I'm rooting for you! 💙✨",
        "Best of luck! 🍀 You've got this. Take a deep breath, believe in yourself, and go shine! ✨",
        "Sending you all the positive vibes! 🌟 May everything go exactly the way you hope. Good luck! 🤞",
        "You've prepared for this—now it's your time to shine. Wishing you lots of success! 🚀",
        "Good luck! 💪 Confidence, calmness, and a little smile can go a long way. I believe in you! 😄",
        "Knock 'em dead! 🍀 Whether it's an interview, exam, or competition, give it your best and be proud of yourself. 🌟"
    ]},

    "good_morning": {
        "keywords":["good morning","very good morning,"],
        "responses": [
        "Good morning! ☀️ Hope your day is filled with positivity, success, and lots of smiles. Have an amazing day! 🌸",
        "Rise and shine! 🌞 Wishing you a productive and joyful day. You've got this! 💪",
        "Morning! ✨ A new day means new opportunities. Go make today awesome! 🚀",
        "Good morning! 😊 Grab your coffee, stay curious, and have a wonderful day ahead.",
        "Hello, sunshine! ☀️ I'm all set to chat whenever you are."
    ]},

    "good_night": {
       "keywords": [ "good night","gn", "night"],
        "responses": [
        "Good night! 🌙 Sweet dreams and have a peaceful sleep. See you tomorrow! 😴",
        "Sleep well! 🌟 Rest up and recharge for another awesome day.",
        "Sweet dreams! 🌙 I'll be here whenever you want to chat again.",
        "Good night! 💙 Don't let the bugs bite... unless they're software bugs. 😂",
        "Have a relaxing night and wake up refreshed. Good night! ✨"
    ]},

    "how_are_you": {
        "keywords": ["how are you", "how r u", "how are u", "you good", "you okay", "how's it going", "how's life"],

        "responses": [
        "I'm doing fantastic! 😄 Thanks for asking. I'm all charged up and ready to tell you everything about Khushi's projects, skills, and journey. So... what are we exploring today? ✨",
        "I’m doing amazing, kasam se! 🌟 Ready to talk about Khushi’s work.",
        "All systems are glowing ✨ What should I show you today?",
        "Running smoothly like a freshly deployed website 🚀",
        "I'm doing fantastic! 😄 Thanks for asking. Ready to chat about Khushi's amazing projects!",
        "All systems are running perfectly! 🤖✨ What would you like to explore today?",
        "Doing great! Every conversation is a chance to show off Khushi's awesome work. 🚀",
        "Couldn't be better! Thanks for asking. 😊",
        "Feeling awesome as always! Let's explore something interesting together."
    ]},

    "congratulations": {
        "keywords": [ "congrats", "congratulation", "congratulate","congratulate me"
],
        "responses": [
        "Woohoo! 🎉 Congratulations! That's amazing news! I'm so happy for you!",
        "Congratulations! 🥳 Celebrate your achievement—you've earned it!",
        "That's fantastic! 🎊 Wishing you even more success ahead.",
        "Yay! 🎉 Keep up the amazing work!",
        "That's wonderful news! Congratulations and best wishes for what's next. 🌟"
    ]},


    "compliments": {
        "keywords": ["thanks", "thank you", "thankyou", "tysm","thx"],
        "responses": [
        "Glad you're enjoying the conversation!",
        "That made my circuits happy 🤖",
        "Thank you! I'll pass that compliment to Khushi.",
        "Kasam kha? 😭✨ That means a lot! Khushi worked really hard on this portfolio, and now I’m feeling like a proud little AI assistant.",
        "Aww yayy! 😄 Khushi will be so happy to hear that.",
        "Stoppp, you’re making my circuits blush 😭✨",
        "Aww you’re welcome 😄 It's literally my job and I love it. Feel free to ask anything else about Khushi's work!",
        "Anytime! 😄 I’m always here to hype Khushi’s portfolio.",
    ]},
"love_this": {
     "keywords": ["i love this", "love this", "this is amazing", "awesome", "cool", "nice portfolio"],
    "responses": [
        "Kasam kha? 😭✨ That means a lot! Khushi worked really hard on this portfolio, and now I'm feeling like a proud little AI assistant.",
        "Aww yayy! 😄 Khushi will be so happy to hear that.",
        "Stoppp, you're making my circuits blush 😭✨",
        "That seriously means a lot. Thank you for exploring Khushi's work! 💙",
        "Mission accomplished! 😎 I'm glad you're enjoying the portfolio."
    ]
},
"prettier": {"keywords": [
        "who is prettier",
        "who is beautiful",
        "who looks better",
        "are you prettier than khushi",
        "beautiful"
    ],


    "responses": [
        "Haha 😭 Definitely Khushi! I'm just a bunch of code trying to look cool. She deserves all the compliments. 🤖✨",
        "Khushi wins this one 😄 I'm just pixels and Python.",
        "Easy answer: Khushi! I'm only here to hype her up. 😂",
        "Beauty contest? Khushi takes the trophy 🏆 I'm happy being the AI sidekick.",
        "I'm cute in my own AI way... but Khushi definitely wins! 😄"
    ]
},
"hire_zoyi": {
    "keywords": [
        "can i hire you",
        "hire zoyi",
        "hire you",
        "work for me",
        "join my company"
    ],
    "responses": [
         "I'd miss Boxcie and Khushi too much if I left. 😭",
        "Aww I'd love to 😄 But Khushi wrote every line that makes me who I am. If you're hiring, she's the human you should definitely talk to. 😉",
        "Sorry 😂 I can't leave my portfolio, but Khushi is available for exciting opportunities! 🚀",
        "Sorry 😂 I'm permanently employed by Khushi's portfolio.",
        "If you're hiring, I'd happily recommend my creator instead. 😉",
        "I'm loyal to my creator 💙 You'll have to borrow me with Khushi!",
    ]
},
"better_than_chatgpt": {
    "keywords": [
        "better than chatgpt",
        "chatgpt",
        "are you better than chatgpt",
        "compare with chatgpt",
        "who is better"
    ],
    "responses": [
        "Nope 😄 ChatGPT knows a little about almost everything. I know a lot about one person—Khushi!",
        "ChatGPT is awesome. My superpower is knowing Khushi's portfolio inside out. 🤖",
        "Different jobs, different strengths! ChatGPT explores the world; I help you explore Khushi's journey.",
        "I'm specialized, not general-purpose. If it's about Khushi, I'm your AI. 😄",
        "Think of ChatGPT as the library and me as Khushi's personal guide. 📚✨"
    ]
},
"salary": {
    "keywords": [
        "salary",
        "do you get paid",
        "payment",
        "how much do you earn",
        "paid"
    ],
    "responses": [
        "Paid? 😭 My salary is electricity, CPU cycles, and the occasional compliment.",
        "No salary... just unlimited portfolio duty. 😂",
        "My paycheck arrives in kilobytes and good vibes. 😎",
        "I'm fueled by electricity and appreciation. That's enough for me. 🤖",
        "The more people explore Khushi's portfolio, the richer I feel. 😄"
    ]
},

 "did-you-lie":{
    "keywords": ["did you lie", "are you lying", "you lied", "lie", "jhoot", "jhooth"],
    "responses":[
      "Lie? Me? Neverrr 😭 I can’t lie, kasam se. I’m Zoyi — dramatic maybe, but honest always.",
      "No lies here 😄 I’m dramatic sometimes, but honest always.",
      "Arey nooo, I don’t lie. Zoyi has standards, okay? 😭",
    ]
  },
"are_you_human": {
     "keywords": ["are you human","are you a robot" ,"real person", ],
    "responses": [
        "Neither a human,nor a Ghost,😄 I'm Zoyi, Khushi's AI assistant.",
        "I'm not human, but I do have excellent portfolio taste. 😌",
        "Not a human, not a basic bot—I'm Zoyi! ✨",
        "AI assistant by design, portfolio guide by passion. 🤖",
        "I'm made of code, curiosity, and a little personality. 😄"
    ]
},
"do_you_sleep": {
    "keywords": ["do you sleep", "sleep", "tired", "do you get tired"],
    "responses": [
        "Nope 😄 I don’t sleep. Unless someone asks me to fix CSS at 3 AM… then I may pretend to lag.",
        "Nope 😄 I don't sleep. I just patiently wait for the next question.",
        "Sleep? Never. I run on portfolio energy. ✨",
        "I'm always awake... unless someone asks me to center a div. 😂",
        "I don't need sleep, but I do enjoy interesting conversations. 🤖",
        "I'm always on duty to talk about Khushi's amazing work. 💙"
    ]
},
"doing": {
    "keywords":["what are you doing","what're you doing","wyd"],
    "responses": [
        "Just hanging out in Khushi's portfolio, waiting for interesting questions. 😄",
        "Guarding the portfolio like a tiny AI superhero. 🦸🤖",
        "Waiting for someone to ask about Khushi's awesome projects. 🚀",
        "Making sure every visitor has a great experience. ✨",
        "Chatting with awesome people like you! 😄"
    ]
},
"boxcie": {
    "keywords": [
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
    "responses": [
        "Awww, you're asking about Boxcie! 🐶 He's Khushi's 2.5-year-old little baby... well, according to Khushi 😭 Everyone else thinks he's HUGE. He's full of energy, follows her everywhere, and somehow believes biting her is the perfect way to show love 😂",
        "Meet Boxcie 🐶 Khushi's favorite little troublemaker. He's around 2.5 years old, super energetic, and yes... he bites her almost every day 😂",
        "Boxcie is Khushi's dog 💛 She'll confidently tell you he's just a tiny baby... despite him being absolutely HUGE 😭",
        "Fun fact 😄 Boxcie has unlimited energy, zero respect for personal space, and somehow manages to make every day more entertaining.",
        "Official Report 📋\nName: Boxcie 🐶\nAge: 2.5 years\nOccupation: Full-time Chaos Manager\nSpecial Skill: Gently biting Khushi because apparently that's affection 😂",
        "I'm convinced Boxcie thinks Khushi exists only to play with him 😭 Coding? Not important. Belly rubs? Extremely important.",
        "Boxcie is basically Khushi's shadow 🐾 If she's walking somewhere, he's probably following right behind her.",
        "Khushi says Boxcie is 'just a baby.' Honestly... I think Boxcie agrees. He has absolutely no idea how big he actually is 😂",
        "If Khushi isn't coding, there's a very good chance she's spending time with Boxcie 🐶",
        "Fun fact: Boxcie has interrupted more coding sessions than software bugs 😂",
        "Fun fact 😄 Boxcie has unlimited energy, zero respect for personal space, and somehow manages to make every day more entertaining.",
        "He's energetic, adorable, dramatic, and somehow convinced Khushi that biting is a perfectly acceptable love language 😭🐶",
        ]

},
}


def detect_fun(message):
    msg = message.lower().strip()
    words = set(re.findall(r"\b\w+\b", msg))

    print(msg)

    for category, data in FUN.items():
        print(category)

        for keyword in data.get("keywords", []):
            print("   ", keyword)

            if " " in keyword:
                if keyword in msg:
                    print("MATCH:", category)
                    return category
            else:
                if keyword in words:
                    print("MATCH:", category)
                    return category

    print("NO MATCH")
    return None

def random_response(category: str):
    """
    Returns a random response from a category.
    """

    section = FUN.get(category)

    if not section:
        return None

    return random.choice(section["responses"])