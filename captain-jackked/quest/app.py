"""
Run: .venv\Scripts\python.exe app.py
"""
import socket
import os
from pathlib import Path
from flask import Flask, render_template, abort, request
import markdown2


from tools.body_calculator import create_body_calculator
from tools.fitnotes_cleaner import create_fitnotes_cleaner

BASE_DIR = Path(__file__).parent
CONTENT_DIR = BASE_DIR / 'content'

from utils.content_loader import load_content, get_content, get_grouped_content

app = Flask(__name__)



SECTIONS = {
    'archive': 'Deep-dives for your Quest',
    'scrolls': 'Bite-sized answers to burning questions',
    'tools': 'Gauge progress, set realistic goals and more'
}

body_calculator = create_body_calculator(app)
fitnotes_cleaner = create_fitnotes_cleaner(app)

@app.route('/')
def index():
    return render_template('index.html', sections=SECTIONS, page_theme='generic')





@app.route('/archive')
@app.route('/archive/')
def archive_list():
    return render_listing('archive', 'Archive', SECTIONS['archive'], default_theme='generic')

@app.route('/scrolls')
@app.route('/scrolls/')
def scrolls_list():
    return render_listing('scrolls', 'Scrolls', SECTIONS['scrolls'], default_theme='generic')


@app.route('/tools')
@app.route('/tools/')
def tools_list():
    tools = [
        {'title': 'Body Calculator', 'url': '/tools/body-calculator/', 'desc': 'Estimate fat/lean mass and nutrition requirements'},
        {'title': 'FitNotes Cleaner', 'url': '/tools/fitnotes-cleaner/', 'desc': 'Clean up and restructure your FitNotes data'},
        {'title': "The Lifter's Path", 'url': '/the-lifters-path', 'desc': 'Focus areas for each lifter type'}
    ]
    return render_template(
        'tools.html',
        title='Tools',
        tools=tools,
        description=SECTIONS['tools'],
        page_theme='generic'
    )

def render_listing(section, title, description, default_theme='generic'):
    view_mode = request.args.get('view', 'series')
    groups = get_grouped_content(section, view_mode=view_mode)
    
    return render_template(
        'listing.html',
        title=title,
        groups=groups,
        description=description,
        page_theme=default_theme
    )

@app.route('/<section>/<slug>')
def content_view(section, slug):
    if section not in ['archive', 'scrolls']:
        abort(404)
        
    data = get_content(section, slug)
    if not data:
        abort(404)
        
    return render_template(
        'content.html',
        title=data['title'],
        subtitle=data.get('subtitle', ''),
        content=data['content'],
        page_theme=data.get('theme', 'generic'),
        section=section,
        prev=data.get('prev'),
        next=data.get('next')
    )

@app.route('/the-lifters-path')
@app.route('/the-lifters-path/')
def lifters_path_view():
    return render_template('jackked.html', page_theme='jackked')

@app.route('/about')
def about():
    return render_template('about.html', page_theme='generic')

@app.route('/portfolio')
def portfolio():
    return render_template('portfolio.html', page_theme='generic')

@app.route('/privacy')
def privacy():
    return render_template('privacy.html', page_theme='generic')

@app.route('/disclaimer')
def disclaimer():
    return render_template('disclaimer.html', page_theme='generic')


@app.errorhandler(404)
def not_found(e):
    return render_template('404.html', page_theme='generic'), 404


if __name__ == '__main__':
    import os
    import socket
    
    # Try to get local IP for a more helpful dev experience locally
    try:
        host = socket.gethostbyname(socket.gethostname())
    except:
        host = '0.0.0.0'
        
    port = int(os.environ.get('PORT', 9000))
    
    # If running in Docker/Hugging Face, we usually want 0.0.0.0
    if os.environ.get('K_SERVICE') or os.environ.get('SPACE_ID'):
        host = '0.0.0.0'

    print(f'\nQuest Site running at http://{host}:{port}')
    app.run(host=host, port=port, debug=True)
