# Apply SQLite hot-patch for Hugging Face Spaces compatibility
try:
    __import__('pysqlite3')
    import sys
    sys.modules['sqlite3'] = sys.modules.pop('pysqlite3')
except ImportError:
    pass  # Not installed locally, fallback to standard sqlite3

import html
import pandas as pd  # Data handling
import numpy as np  # Numerical ops
from dotenv import load_dotenv  # Environment variables

from langchain_core.documents import Document  # LangChain document schema
from langchain_huggingface import HuggingFaceEmbeddings  # Embedding model

from langchain_chroma import Chroma  # Vector store

import gradio as gr # UI library

# Load environment variables (API tokens, config)
load_dotenv()

# ---------- Data Preparation ----------
# Read book metadata and prepare thumbnail URLs
books = pd.read_csv("books_with_emotions.csv")
# Fix: check isna() on the RAW thumbnail column BEFORE concatenating
# the URL param — NaN + string becomes "nan&fife=w800" which is not NaN,
# so the fallback was never triggered.
books["large_thumbnail"] = np.where(
    books["thumbnail"].isna() | (books["thumbnail"].astype(str).str.strip() == ""),
    "cover-not-found.jpg",
    books["thumbnail"].astype(str) + "&fife=w800",
)

import os
persist_directory = "chroma_db"
embeddings = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")

# Upgrade 01: Load persistent Chroma DB instead of generating on startup
if os.path.exists(persist_directory):
    db_books = Chroma(
        persist_directory=persist_directory,
        embedding_function=embeddings
    )
else:
    print("Warning: chroma_db not found. Falling back to in-memory generation.")
    with open("tagged_description.txt", "r", encoding="utf-8", errors="ignore") as f:
        content = f.read()
    raw_documents = [
        Document(page_content=line.strip())
        for line in content.split("\n")
        if line.strip()
    ]
    db_books = Chroma.from_documents(
        raw_documents,
        embedding=embeddings
    )

# ---------- Recommendation Logic ----------
def retrieve_semantic_recommendations(
    query: str,
    category: str = None,
    tone: str = None,
    initial_top_k: int = 50,
    final_top_k: int = 16,
) -> pd.DataFrame:
    """
    Running a semantic similarity search, then filter and sort
    by category or emotional tone if specified.
    """
    # Upgrade 02: Pre-retrieval filtering using Chroma metadata filters
    search_kwargs = {"k": initial_top_k}
    if category and category != "All":
        search_kwargs["filter"] = {"category": category}

    recs = db_books.similarity_search_with_score(query, **search_kwargs)
    
    # Extract the ISBN13s robustly to prevent crashes from malformed text
    books_list = []
    for doc, _score in recs:
        try:
            isbn_str = doc.page_content.strip('"').split()[0]
            books_list.append(int(isbn_str))
        except (ValueError, IndexError):
            continue

    # Narrow down to actual book metadata (without slicing yet, to allow proper emotion sorting)
    book_recs = books[books["isbn13"].isin(books_list)]
    
    # Sort by emotional tone if specified
    if tone == "Happy":
        book_recs = book_recs.sort_values("joy", ascending=False)
    elif tone == "Surprising":
        book_recs = book_recs.sort_values("surprise", ascending=False)
    elif tone == "Angry":
        book_recs = book_recs.sort_values("anger", ascending=False)
    elif tone == "Suspenseful":
        book_recs = book_recs.sort_values("fear", ascending=False)
    elif tone == "Sad":
        book_recs = book_recs.sort_values("sadness", ascending=False)
        
    # Return the final top k results after sorting
    return book_recs.head(final_top_k)

# ---------- Gradio UI ----------
def generate_book_card(row):
    description = str(row.get("description", ""))
    
    raw_authors = str(row.get("authors", "Unknown"))
    if raw_authors == "nan" or not raw_authors.strip():
        raw_authors = "Unknown"
    authors_split = raw_authors.split(";")
    if len(authors_split) == 2:
        authors_str = f"{authors_split[0]} and {authors_split[1]}"
    elif len(authors_split) > 2:
        authors_str = f"{', '.join(authors_split[:-1])}, and {authors_split[-1]}"
    else:
        authors_str = raw_authors

    title = str(row.get('title', 'Unknown Title'))
    img_url = str(row.get('large_thumbnail', 'cover-not-found.jpg'))
    
    safe_title = html.escape(title, quote=True)
    safe_author = html.escape(authors_str, quote=True)
    safe_desc = html.escape(description, quote=True)
    safe_img = html.escape(img_url, quote=True)

    # Fallback URL for when cover-not-found.jpg can't be served (e.g. HF Spaces).
    # onerror swaps in a reliable online placeholder so broken covers always render.
    FALLBACK = "https://placehold.co/200x300/1e1f2a/80D0FF?text=No+Cover"

    return f'''
    <div class="custom-book-card" onclick="openBookModal(this)"
         data-title="{safe_title}" 
         data-author="{safe_author}" 
         data-desc="{safe_desc}" 
         data-img="{safe_img}">
        <img src="{img_url}" alt="{safe_title}"
             onerror="this.onerror=null; this.src='{FALLBACK}';">
    </div>
    '''

def recommend_books(query: str, category: str, tone: str):
    """ Gradio UI logic """
    recommendations = retrieve_semantic_recommendations(query, category, tone)
    if recommendations.empty:
        return "<p style='color:white; text-align:center;'>No recommendations found. Please try a different query!</p>"
    
    cards = [generate_book_card(row) for _, row in recommendations.iterrows()]
    return f'<div class="custom-gallery-grid">{"".join(cards)}</div>'

# Dropdown options for category and tone
categories = ["All"] + sorted(books["simple_categories"].unique())
tones = ["All", "Happy", "Surprising", "Angry", "Suspenseful", "Sad"]

# Random featured books
def get_featured_books():
    featured = books.sample(n=12) if len(books) >= 12 else books
    cards = [generate_book_card(row) for _, row in featured.iterrows()]
    return f'<div class="custom-gallery-grid">{"".join(cards)}</div>'

# ---------- UI Definition ----------

# Bug Fix 1: JS must live in gr.Blocks(js=) to bypass Gradio's DOMPurify
# sanitisation of gr.HTML. Using window. makes functions globally accessible
# from any onclick attribute in the HTML components.
MODAL_JS = """
() => {
    window.openBookModal = function(element) {
        document.getElementById('modalTitle').innerText = element.getAttribute('data-title');
        document.getElementById('modalAuthor').innerText = element.getAttribute('data-author');
        document.getElementById('modalDesc').innerText = element.getAttribute('data-desc');
        document.getElementById('modalImg').src = element.getAttribute('data-img');
        document.getElementById('bookModal').classList.add('show');
    };
    window.closeBookModal = function(event) {
        document.getElementById('bookModal').classList.remove('show');
    };
}
"""

with gr.Blocks(
    theme=gr.themes.Glass(),
    js=MODAL_JS,
    css="""
/* --------------------------------------------------
   1. Gallery Item: Hover-Lift Card Effect & Zoom
-------------------------------------------------- */
.gr-gallery-item {
  background: rgba(255,255,255,0.03);
  border-radius: 8px;
  box-shadow: 0 4px 10px rgba(0,0,0,0.3);
  transition: all 0.3s cubic-bezier(0.25, 0.8, 0.25, 1);
  overflow: hidden;
}
.gr-gallery-item:hover {
  transform: translateY(-6px);
  box-shadow: 0 12px 24px rgba(0,200,255,0.25);
  border: 1px solid rgba(128,208,255,0.3);
}
.gr-gallery-item img {
  transition: transform 0.4s ease !important;
}
.gr-gallery-item:hover img {
  transform: scale(1.05) !important;
}

/* --------------------------------------------------
   2. Buttons: Modern Raised Look & Glow
-------------------------------------------------- */
.gradio-button.primary {
  background: linear-gradient(90deg, #00C9FF 0%, #92FE9D 100%) !important;
  border: none !important;
  color: #111 !important;
  padding: 12px 24px !important;
  border-radius: 24px !important;
  font-weight: 700 !important;
  transition: all 0.3s ease !important;
  animation: pulseGlow 2.5s infinite alternate !important;
  text-transform: uppercase;
  letter-spacing: 1px;
}
.gradio-button.primary:hover {
  transform: translateY(-2px) scale(1.02);
  box-shadow: 0 8px 25px rgba(0, 201, 255, 0.6) !important;
}
@keyframes pulseGlow {
  0% { box-shadow: 0 0 5px rgba(0,201,255,0.4); }
  100% { box-shadow: 0 0 20px rgba(0,201,255,0.8); }
}

/* --------------------------------------------------
   2b. Input Hover/Focus States
-------------------------------------------------- */
.gr-box, input, textarea, select {
  transition: all 0.3s ease !important;
}
.gr-box:hover, input:hover, textarea:hover, select:hover {
  border-color: #80D0FF !important;
  box-shadow: 0 0 10px rgba(128,208,255,0.15) !important;
}
.gr-box:focus-within, input:focus, textarea:focus, select:focus {
  transform: translateY(-2px);
  border-color: #80D0FF !important;
  box-shadow: 0 4px 15px rgba(128,208,255,0.3) !important;
}

/* --------------------------------------------------
   3. Gallery Entrance Animation
-------------------------------------------------- */
.gradio-gallery {
  opacity: 0;
  transform: translateY(20px);
  animation: fadeUp 0.5s forwards ease-out;
}
@keyframes fadeUp {
  to { opacity: 1; transform: translateY(0); }
}

/* --------------------------------------------------
   4. Smooth Scroll for Main Gallery
-------------------------------------------------- */
#gallery-box { scroll-behavior: smooth; }

/* --------------------------------------------------
   5. Featured Gallery Layout Tweaks
-------------------------------------------------- */
#featured-gallery {
  overflow-y: visible !important;
  overflow-x: hidden !important;
  padding-bottom: 8px;
  margin-bottom: 24px;
  height: auto !important;
}
#featured-gallery .gradio-gallery {
  min-width: unset !important;
  gap: 16px;
}
#featured-gallery .gradio-gallery img {
  width: 110px !important;
  height: 165px !important;
  object-fit: cover !important;
  border-radius: 6px;
}

@media (max-width: 600px) {
  #featured-gallery .gradio-gallery img {
    width: 80px !important;
    height: 120px !important;
  }
  #featured-gallery .gradio-gallery {
    gap: 8px;
  }
}

/* --------------------------------------------------
   6. Footer ("About") Section
-------------------------------------------------- */
#project-info {
  margin-top: 64px !important;
  padding: 32px 24px !important;
  background: linear-gradient(135deg, #1e1f2a 0%, #2a2c3d 100%) !important;
  border-radius: 12px !important;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.5) !important;
  position: relative !important;
  overflow: hidden !important;
  text-align: center !important;
}

/* a thin accent stripe across the top */
#project-info::before {
  content: "";
  position: absolute;
  top: 0; left: 0;
  width: 100%;
  height: 4px;
  background: #80D0FF;  /* your accent color */
}

/* Footer heading */
#project-info h4 {
  margin: 0 0 12px !important;
  font-size: 1.4rem !important;
  color: #fff !important;
  letter-spacing: 0.5px !important;
}

/* Footer paragraph */
#project-info p {
  margin: 0 auto !important;
  max-width: 700px !important;
  line-height: 1.6 !important;
  color: #ddd !important;
  font-size: 1rem !important;
}

/* optional: style any links you might add later */
#project-info a {
  color: #80D0FF !important;
  text-decoration: none !important;
}
#project-info a:hover {
  text-decoration: underline !important;
}

/* --------------------------------------------------
   7. App Header Styling (Animated)
-------------------------------------------------- */
#app-header {
  display: flex;
  justify-content: center;
  align-items: center;
  background: linear-gradient(135deg, rgba(42,44,61,0.8) 0%, rgba(30,31,42,0.8) 100%);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  border: 1px solid rgba(255,255,255,0.1);
  border-radius: 12px;
  box-shadow: 0 6px 18px rgba(0, 0, 0, 0.5);
  padding: 16px 24px;
  margin-bottom: 32px;
  transition: transform 0.3s ease;
}
#app-header:hover {
  transform: translateY(-2px);
}
#app-header span {
  font-size: 2.8rem;
  font-weight: 800;
  background: linear-gradient(90deg, #80D0FF, #D080FF, #80D0FF);
  background-size: 200% auto;
  color: transparent;
  -webkit-background-clip: text;
  background-clip: text;
  animation: textShine 3s linear infinite;
  letter-spacing: 1px;
}
@keyframes textShine {
  to { background-position: 200% center; }
}

@media (max-width: 600px) {
  #app-header span {
    font-size: 1.8rem;
  }
  #app-header {
    padding: 12px 16px;
    margin-bottom: 20px;
  }
  #project-info h4 {
    font-size: 1.2rem !important;
  }
  #project-info p {
    font-size: 0.9rem !important;
  }
}

/* --------------------------------------------------
   8. Custom Book Grid & Modal
-------------------------------------------------- */
.custom-gallery-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(120px, 1fr));
    gap: 16px;
    justify-content: center;
    padding: 10px;
}
/* Featured section: always 6 columns on desktop → 12 books = exactly 2 rows */
#featured-gallery .custom-gallery-grid {
    grid-template-columns: repeat(6, 1fr);
}
.custom-book-card {
    background: rgba(255,255,255,0.03);
    border-radius: 8px;
    box-shadow: 0 4px 10px rgba(0,0,0,0.3);
    cursor: pointer;
    transition: all 0.3s cubic-bezier(0.25, 0.8, 0.25, 1);
    overflow: hidden;
    position: relative;
}
.custom-book-card:hover {
    transform: translateY(-6px);
    box-shadow: 0 12px 24px rgba(0,200,255,0.25);
    border: 1px solid rgba(128,208,255,0.4);
}
.custom-book-card img {
    width: 100%;
    aspect-ratio: 2/3;
    object-fit: cover;
    transition: transform 0.4s ease;
    display: block;
}
.custom-book-card:hover img {
    transform: scale(1.05);
}
@media (max-width: 600px) {
    .custom-gallery-grid {
        grid-template-columns: repeat(auto-fill, minmax(90px, 1fr));
        gap: 10px;
    }
    /* Reset featured to responsive columns on mobile */
    #featured-gallery .custom-gallery-grid {
        grid-template-columns: repeat(auto-fill, minmax(90px, 1fr));
    }
}

/* Modal CSS */
/* Bug Fix 2: Use visibility+pointer-events instead of display:none so the
   browser can animate the opacity fade-out before the element is hidden.
   display:none is instant and kills the animation before it can run. */
.book-modal-overlay {
    visibility: hidden;
    pointer-events: none;
    display: flex;
    position: fixed;
    z-index: 9999;
    left: 0; top: 0;
    width: 100%; height: 100%;
    background-color: rgba(0,0,0,0.8);
    backdrop-filter: blur(5px);
    align-items: center;
    justify-content: center;
    opacity: 0;
    transition: opacity 0.3s ease, visibility 0.3s ease;
}
.book-modal-overlay.show {
    visibility: visible;
    pointer-events: auto;
    opacity: 1;
}
.book-modal-content {
    background: linear-gradient(135deg, #1e1f2a 0%, #2a2c3d 100%);
    border: 1px solid rgba(128,208,255,0.3);
    border-radius: 12px;
    box-shadow: 0 15px 35px rgba(0,0,0,0.6);
    width: 90%;
    max-width: 800px;
    max-height: 85vh;
    overflow-y: auto;
    position: relative;
    transform: translateY(20px);
    transition: transform 0.3s ease;
    display: flex;
    flex-direction: row;
    padding: 32px;
    gap: 32px;
}
.book-modal-overlay.show .book-modal-content {
    transform: translateY(0);
}
.close-modal {
    position: absolute;
    top: 16px;
    right: 24px;
    color: #aaa;
    font-size: 32px;
    font-weight: bold;
    cursor: pointer;
    transition: color 0.2s;
    line-height: 1;
}
.close-modal:hover {
    color: #fff;
}
.book-modal-img {
    flex-shrink: 0;
    width: 250px;
    height: 375px;
    object-fit: cover;
    border-radius: 8px;
    box-shadow: 0 4px 15px rgba(0,0,0,0.4);
}
.book-modal-info {
    flex-grow: 1;
    display: flex;
    flex-direction: column;
}
.book-modal-title {
    font-size: 2rem !important;
    color: #FFD700 !important;
    margin-top: 0 !important;
    margin-bottom: 8px !important;
    line-height: 1.2 !important;
}
.book-modal-author {
    font-size: 1.2rem !important;
    color: #80D0FF !important;
    font-style: italic !important;
    margin-bottom: 24px !important;
    margin-top: 0 !important;
}
.book-modal-desc {
    color: #ddd !important;
    line-height: 1.6 !important;
    font-size: 1.05rem !important;
    white-space: pre-wrap !important;
    margin: 0 !important;
}

@media (max-width: 768px) {
    .book-modal-content {
        flex-direction: column;
        padding: 24px;
        gap: 20px;
    }
    .book-modal-img {
        width: 180px;
        height: 270px;
        align-self: center;
    }
    .book-modal-title { font-size: 1.6rem !important; }
}

"""
) as dashboard:
#    gr.Markdown(
#        """<span style="color:#80D0FF; font-size:36px; font-weight:600;">📖 NextRead</span>"""
#    )
    # wrap the header in its own div so we can style it
    gr.Markdown(
       """
       <div id="app-header">
         <span>📖 NextRead</span>
       </div>
       """,
       elem_id="app-header"
       )
    # Subheading 
    gr.Markdown(
        """<span style="font-size:18px; font-style:italic; color:#CCCCCC;">
        Welcome to smart book recommendations, powered by <b>semantic discovery</b>.
        </span>"""
    )
    # Featured Books
    gr.Markdown("<h3 style='color:#FFD700;'>🌟 Featured Books 🌟</h3>")
    featured_gallery = gr.HTML(
        value=get_featured_books,
        elem_id="featured-gallery"
    )
    # User Input Block
    with gr.Row():
        user_query = gr.Textbox(
            label="✍️ Please enter a description of a book",
            placeholder="e.g., A Story about forgiveness...",
            lines=2
        )
        category_dropdown = gr.Dropdown(
            choices=categories, label="🔖 Select a category:", value="All"
        )
        tone_dropdown = gr.Dropdown(
            choices=tones, label="🎭 Select an emotional tone:", value="All"
        )
    # Submit Button
    with gr.Row():
        submit_button = gr.Button("🔍 Find recommendations", variant="primary", elem_id="submit-btn")

    # Output Block
    gr.Markdown(
        """<h2 id='recommendations-header' style='text-align:center; color:#80D0FF;'>✨ Recommendations ✨</h2>"""
    )
    output = gr.HTML(
        elem_id="gallery-box"
    )

    # Footer
    gr.Markdown(
        """
        ---  
        <div id="project-info">
          <h4>ℹ️ About NextRead</h4>
          <p>
            NextRead is a hands-on demo of a semantic book recommender built with 
            <b>LangChain</b>, <b>HuggingFace embeddings</b>, and <b>Gradio</b>.  
            Enter what you feel like reading, pick an emotion or category,  
            and voilà! your next great read is just a click away!
          </p>
        </div>
        """,
        elem_id="project-info"
    )
    # Modal HTML only — JS lives in gr.Blocks(js=MODAL_JS) above,
    # which injects at page level and bypasses DOMPurify.
    gr.HTML('''
    <div id="bookModal" class="book-modal-overlay" onclick="closeBookModal(event)">
      <div class="book-modal-content" onclick="event.stopPropagation()">
        <span class="close-modal" onclick="closeBookModal(event)">&times;</span>
        <img id="modalImg" class="book-modal-img" src="" alt="Book Cover">
        <div class="book-modal-info">
          <h2 id="modalTitle" class="book-modal-title"></h2>
          <h4 id="modalAuthor" class="book-modal-author"></h4>
          <p id="modalDesc" class="book-modal-desc"></p>
        </div>
      </div>
    </div>
    ''')

    # wire up the submit button
    submit_button.click(
        fn=recommend_books,
        inputs=[user_query, category_dropdown, tone_dropdown],
        outputs=output,
    )

if __name__ == "__main__":
    dashboard.launch()
