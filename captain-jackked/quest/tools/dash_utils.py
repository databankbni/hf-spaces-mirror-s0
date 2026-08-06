from dash import html, dcc, Input, Output


def create_dropdown(id, options=None, value=None, placeholder='', clearable=False, searchable=False, style=None):
    """
    Standardized dropdown builder. Mirrors the Body Calculator's working config.
    Never sets display mode — visibility must be controlled via className or container.
    """
    return dcc.Dropdown(
        id=id,
        options=options or [],
        value=value,
        placeholder=placeholder,
        clearable=clearable,
        searchable=searchable,
        style=style or {},
    )

def create_back_button(id='back-btn'):
    """
    Creates a standardized Back button (FitNotes style).
    """
    return html.Button('← Back', id=id, className='btn btn-secondary')

def get_dash_index_string(title, extra_css=''):
    """
    Returns the standard HTML template for Dash tools, including:
    - Fonts (Inter)
    - Favicon
    - Theme Sync Script
    - Global CSS injection
    """
    return f'''
    <!DOCTYPE html>
    <html>
        <head>
            {{%metas%}}
            <title>{title}</title>
            <link rel='icon' type='image/svg+xml' href='/static/images/Jackked/jackked_logo.svg'>
            <link rel='preconnect' href='https://fonts.googleapis.com'>
            <link rel='preconnect' href='https://fonts.gstatic.com' crossorigin>
            <link href='https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=Sora:wght@600;700;800&display=swap' rel='stylesheet'>
            {{%css%}}
            {extra_css}
            <script>
                if (localStorage.getItem('theme') === 'dark' || !localStorage.getItem('theme')) {{
                    document.documentElement.className = 'dark';
                }}
                
                let hue = localStorage.getItem('brand-hue');
                
                if (!hue) {{
                     const isDark = document.documentElement.classList.contains('dark');
                     hue = isDark ? '31' : '165';
                }}
                
                if (hue) {{
                    document.documentElement.style.setProperty('--brand-hue', hue);
                }}
            </script>
        </head>
        <body>
            {{%app_entry%}}
            <footer>
                {{%config%}}
                {{%scripts%}}
                {{%renderer%}}
            </footer>
        </body>
    </html>
    '''

def register_theme_sync(app):
    """
    Registers the clientside callback to sync theme from localStorage.
    Requires a hidden Div with id='theme-sync-dummy' in the layout.
    """
    app.clientside_callback(
        '''
        function(dummy) {
            const theme = localStorage.getItem('theme');
            if (theme === 'dark' || !theme) {
                document.body.classList.add('dark');
                document.documentElement.classList.add('dark');
            } else {
                document.body.classList.remove('dark');
                document.documentElement.classList.remove('dark');
            }
            
            // 1. Read from localStorage
            let hue = localStorage.getItem('brand-hue');
             
            // 2. Fallback to Defaults
            if (!hue) {
                 const isDark = document.documentElement.classList.contains('dark');
                 hue = isDark ? '31' : '165';
            }
            
            // 3. Apply
            if (hue) {
                document.documentElement.style.setProperty('--brand-hue', hue);
            }
            
            return '';
        }
        ''',
        Output('theme-sync-dummy', 'children'),
        Input('theme-sync-dummy', 'id')
    )

def register_back_button_callback(app, btn_id='back-btn'):
    """
    Registers the clientside callback for the Back button.
    Handles 'smart back' logic (history.back() if referrer matches).
    """
    app.clientside_callback(
        '''
        function(n_clicks) {
            if (n_clicks > 0) {
                // If referrer is internal, navigate to it explicitly (avoiding history stack traps)
                if (document.referrer && document.referrer.includes(window.location.host)) {
                    window.location.href = document.referrer;
                } else {
                    window.location.href = '/';
                }
            }
            return window.dash_clientside.no_update;
        }
        ''',
        Output(btn_id, 'n_clicks'),
        Input(btn_id, 'n_clicks')
    )
