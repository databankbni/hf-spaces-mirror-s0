import gradio as gr

# 1. Store the reading passage text with <mark> tags for highlighting
reading_text = """
### Bye, bye banknote
**The End of Money by David Wolman, reviewed by Jacob Aron**

**A.** Cash, dough or moolah - whatever you call it, you can't <mark>live without it</mark>. Or can you? Increasingly money is an abstraction residing on a <mark>computer drive</mark>. How long will it be until hard currency disappears altogether? In The End of Money, journalist David Wolman sets out to discover what a cashless world might look like and how we will arrive there. On the way, he gets distracted by those on the fringes of society. The book opens with Glenn Guest, a US pastor who believes credit cards and <mark>online banking</mark> are <mark>tools of Satan</mark>, designed to bring about the end of the world. An entertaining notion, but not relevant to anyone just fed up with carrying a chunk of change.

**B.** Later, Wolman visits Bernard von NotHaus, creator of the Liberty Dollar currency. Until 2009, it was available electronically, in note form and as coins - though von NotHaus denied they were coins, which he says only governments can <mark>mint</mark>. Such semantic wrangling failed to prevent him being found guilty of counterfeiting. It's not surprising, as the Liberty Dollar closely mimics many features of the US dollar, using 'Trust in God' instead of 'In God we Trust' for example. It seems odd to focus on such a strange character when, as Wolman points out, alternative currencies such as the Brixton Pound in London succeed without <mark>falling foul of the law</mark>.

**C.** The book is better when focusing on the real implications of moving away from cash: a particularly good chapter details the mobile-banking revolution in the developing world, which is allowing countries such as Kenya to leapfrog the need for expensive ATM and banking infrastructure. Interesting, too, are the arguments for abolishing cash, such as the fact that making hard currency is a <mark>costly business</mark>, as much as 1 per cent of annual Gross Domestic Product for some countries. Cash is used to <mark>prop up crime</mark>: high-value bills provide an anonymous way to conduct <mark>illicit transactions</mark>. UK exchange offices no longer take €500 notes after an inquiry found that nine in every ten of them were used by criminals.

**D.** So what might replace cash? Wolman touches on energy as a unit of currency, and whizzes through virtual currencies like World of Warcraft gold, Facebook credits and Bitcoin, suggesting conversion software could let people pay using whatever they have to hand. Ultimately, though, one gets the feeling that the cashless society is <mark>already with us</mark>, at least for those that want it. Early in the book, Wolman mentions his attempt to avoid cash for an entire year, but other than a few awkward moments when splitting restaurant bills or passing lemonade stands, he rarely refers to it again perhaps because parting with your cash is easier than you might expect.
"""

# ==========================================
# DATA FOR TAB 1: SYNONYM MATCHER (Ex 4b)
# ==========================================
questions_tab1 = [
    "1. Not having cash could reduce costs of government.",
    "2. No individual has the right to make coins.",
    "3. No society can manage without money.",
    "4. Not all alternatives to official currencies are illegal.",
    "5. Nobody should use credit cards.",
    "6. No computers are designed to manage our money.",
    "7. Nobody actually needs to use cash now.",
    "8. Nothing is more dangerous than carrying cash with you."
]

options_tab1 = [
    "already with us",
    "costly business",
    "falling foul of the law",
    "live without it",
    "mint",
    "online banking / computer drive",
    "prop up crime / illicit transactions",
    "tools of Satan"
]

correct_answers_tab1 = [
    "costly business",                        # Q1 matches "reduce costs"
    "mint",                                   # Q2 matches "make"
    "live without it",                        # Q3 matches "manage without"
    "falling foul of the law",                # Q4 matches "illegal"
    "tools of Satan",                         # Q5 matches "Nobody should use"
    "online banking / computer drive",        # Q6 matches "computers manage"
    "already with us",                        # Q7 matches "needs to use cash now"
    "prop up crime / illicit transactions"    # Q8 matches "dangerous"
]

def grade_tab1(*user_answers):
    score = 0
    feedback = "### 📊 Your Results:\n\n"
    if None in user_answers or "" in user_answers:
        return "⚠️ **Please answer all questions before submitting!**"

    for i, (user_ans, correct_ans) in enumerate(zip(user_answers, correct_answers_tab1)):
        if user_ans == correct_ans:
            score += 1
            feedback += f"✅ **Q{i+1}:** Correct!\n"
        else:
            feedback += f"❌ **Q{i+1}:** Incorrect. (Correct match: *{correct_ans}*)\n"
            
    feedback += f"\n---\n**Total Score: {score} / 8**"
    return feedback


# ==========================================
# DATA FOR TAB 2: WHO SAID IT? (Ex 4c)
# ==========================================
questions_tab2 = questions_tab1 # Uses the same sentences!

options_tab2 = [
    "A. David Wolman",
    "B. Jacob Aron",
    "C. Glenn Guest",
    "D. Bernard von NotHaus",
    "E. Not expressed"
]

correct_answers_tab2 = [
    "A. David Wolman",         # Q1
    "D. Bernard von NotHaus",  # Q2
    "E. Not expressed",        # Q3
    "A. David Wolman",         # Q4
    "C. Glenn Guest",          # Q5
    "E. Not expressed",        # Q6
    "B. Jacob Aron",           # Q7 
    "E. Not expressed"         # Q8
]

def grade_tab2(*user_answers):
    score = 0
    feedback = "### 📊 Your Results:\n\n"
    if None in user_answers or "" in user_answers:
        return "⚠️ **Please answer all questions before submitting!**"

    for i, (user_ans, correct_ans) in enumerate(zip(user_answers, correct_answers_tab2)):
        if user_ans == correct_ans:
            score += 1
            feedback += f"✅ **Q{i+1}:** Correct!\n"
        else:
            feedback += f"❌ **Q{i+1}:** Incorrect. (Correct match: *{correct_ans}*)\n"
            
    feedback += f"\n---\n**Total Score: {score} / 8**"
    return feedback

# ==========================================
# BUILD THE UI WITH TABS
# ==========================================
with gr.Blocks(theme=gr.themes.Soft()) as app:
    gr.Markdown("# 📖 IELTS Reading: Bye, Bye Banknote")
    
    with gr.Row():
        # Left Column: Reading Text remains visible for all tabs
        with gr.Column(scale=5):
            gr.Markdown("### Reading Passage")
            gr.HTML(reading_text) # Switched to HTML to properly render the <mark> tags
            
        # Right Column: The Interactive Tabs
        with gr.Column(scale=4):
            
            # First Tab
            with gr.Tab("Exercise 4b: Synonym Matcher"):
                gr.Markdown("Identify the key idea in the sentence, then select the synonymous phrase found in the highlighted text.")
                dropdowns_t1 = []
                for q in questions_tab1:
                    dropdowns_t1.append(gr.Dropdown(choices=options_tab1, label=q))
                
                submit_btn_t1 = gr.Button("Submit Answers", variant="primary")
                result_display_t1 = gr.Markdown()
                
                submit_btn_t1.click(fn=grade_tab1, inputs=dropdowns_t1, outputs=result_display_t1)
                
            # Second Tab
            with gr.Tab("Exercise 4c: Who Said It?"):
                gr.Markdown("Select the person who expressed the statement, or select 'Not expressed' if it doesn't appear in the text.")
                dropdowns_t2 = []
                for q in questions_tab2:
                    dropdowns_t2.append(gr.Dropdown(choices=options_tab2, label=q))
                
                submit_btn_t2 = gr.Button("Submit Answers", variant="primary")
                result_display_t2 = gr.Markdown()
                
                submit_btn_t2.click(fn=grade_tab2, inputs=dropdowns_t2, outputs=result_display_t2)

# Launch the app
app.launch()