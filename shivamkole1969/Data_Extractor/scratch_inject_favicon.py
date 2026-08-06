import base64

with open('static/images/favicon.ico', 'rb') as f:
    b64 = base64.b64encode(f.read()).decode('utf-8')

with open('templates/index.html', 'r', encoding='utf-8') as f:
    html = f.read()

html = html.replace('<link rel="icon" type="image/x-icon" href="/static/images/favicon.ico">', f'<link rel="icon" type="image/x-icon" href="data:image/x-icon;base64,{b64}">')
html = html.replace('<link rel="icon" type="image/png" sizes="64x64" href="/static/images/favicon.png">', '')
html = html.replace('<link rel="apple-touch-icon" href="/static/images/favicon.png">', '')

with open('templates/index.html', 'w', encoding='utf-8') as f:
    f.write(html)
