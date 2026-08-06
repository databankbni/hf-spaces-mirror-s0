from dash import Dash, html, dcc, Input, Output, State, callback
from tools.model import body
from tools import dash_utils


def _to_metric_len(val, unit):
    return val if unit == 'metric' else val * 2.54


def _to_metric_mass(val, unit):
    return val if unit == 'metric' else val * 0.453592


def _result_row(label, val, unit='', is_hero=False):
    style = {'fontSize': '1.5rem', 'fontWeight': '700', 'color': 'var(--primary)'} if is_hero else {'fontWeight': '600'}
    return html.Div([html.Span(f'{label}: ', style={'fontWeight': '500'}), html.Span(f'{val}{unit}', style=style)])


def _input_row(label_text, input_id, label_id, container_id=None):
    style = {'marginBottom': '1.5rem'}
    if container_id == 'hip-container':
        style['display'] = 'none'
    
    div_kwargs = {
        'children': [
            html.Label(label_text, id=label_id, style={'fontWeight': '600', 'marginBottom': '0.5rem', 'display': 'block', 'color': 'var(--text)'}),
            dcc.Input(
                id=input_id,
                type='number',
                placeholder='0.0',
                className='form-control'
            ),
        ],
        'style': style
    }
    
    if container_id:
        div_kwargs['id'] = container_id
    
    return html.Div(**div_kwargs)


def _create_options(values):
    return [{'label': v, 'value': v} for v in values]


def _create_output_card(children, extra_style=None):
    base_style = {
        'background': 'var(--surface)',
        'padding': '1.5rem',
        'borderRadius': 'var(--radius)',
        'borderLeft': '4px solid var(--primary)',
        'boxShadow': '0 4px 12px rgba(0,0,0,0.1)',
        'maxWidth': '400px'
    }
    if extra_style:
        base_style.update(extra_style)
    return html.Div(children, style=base_style)


def create_body_calculator(server):
    app = Dash(
        __name__,
        server=server,
        url_base_pathname='/tools/body-calculator/',
        external_stylesheets=[
            'https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap',
            '/static/css/style.css'
        ]
    )
    
    # Inject client-side theme switching and smart 'Back' button script
    
    # Inject client-side theme switching and smart 'Back' button script
    app.index_string = dash_utils.get_dash_index_string('Body Calculator', extra_css='''
            <style>
                /* Radio button accent color */
                input[type="radio"]:checked {
                    accent-color: var(--primary);
                }
            </style>
    ''')

    app.layout = html.Div([
        html.Div(id='theme-sync-dummy', style={'display': 'none'}),
        html.Div([
            dash_utils.create_back_button(id='back-btn-bc'),
            html.H1('Body Calculator', style={
                'marginTop': '1.5rem',
                'marginBottom': '0.5rem',
                'fontSize': '2rem',
                'fontWeight': '700',
                'color': 'var(--text)'
            }),
            html.P(
                'Estimate Body Fat %, FFMI and Nutritional Requirements',
                style={'color': 'var(--text-muted)', 'marginBottom': '2rem'}
            ),
        ]),
        
        html.Div([
            html.Div([
                html.Label('Unit System', style={'fontWeight': '600', 'marginBottom': '0.5rem', 'display': 'block', 'color': 'var(--text)'}),
                dcc.RadioItems(
                    id='unit-input',
                    options=[
                        {'label': ' Metric (kg, cm)', 'value': 'metric'},
                        {'label': ' Imperial (lbs, in)', 'value': 'imperial'}
                    ],
                    value='metric',
                    inline=True,
                    labelStyle={'marginRight': '2rem', 'cursor': 'pointer', 'color': 'var(--text)'}
                ),
            ], style={'marginBottom': '1.5rem'}),

            html.Div([
                html.Label('Body Type', style={'fontWeight': '600', 'marginBottom': '0.5rem', 'display': 'block', 'color': 'var(--text)'}),
                dcc.RadioItems(
                    id='sex-input',
                    options=[
                        {'label': ' Male', 'value': 'male'},
                        {'label': ' Female', 'value': 'female'}
                    ],
                    value='male',
                    inline=True,
                    labelStyle={'marginRight': '2rem', 'cursor': 'pointer', 'color': 'var(--text)'}
                ),
            ], style={'marginBottom': '1.5rem'}),

            _input_row('Weight', 'weight-input', 'weight-label'),
            _input_row('Height', 'height-input', 'height-label'),
            _input_row('Abdomen at navel', 'waist-input', 'waist-label'),
            _input_row('Neck at narrowest', 'neck-input', 'neck-label'),
            _input_row('Hips at widest', 'hip-input', 'hip-label', container_id='hip-container'),
            
            html.Button(
                'Calculate Body Composition',
                id='calculate-btn',
                n_clicks=0,
                className='btn btn-primary',
                style={'width': '100%', 'padding': '1rem'}
            ),
        ], style={
            'background': 'var(--surface)',
            'padding': '2rem',
            'borderRadius': 'var(--radius)',
            'maxWidth': '400px'
        }),
        
        html.Div(id='result-output', style={'marginTop': '2rem'}),

        html.Div(
            id='macro-inputs-container',
            children=[
                _input_row('Age (years)', 'age-input', 'age-label'),
                html.Div([
                    html.Label('Activity Level', style={'fontWeight': '600', 'marginBottom': '0.5rem', 'display': 'block', 'color': 'var(--text)'}),
                    dash_utils.create_dropdown(
                        id='activity-input',
                        options=_create_options([
                            body.LETHARGIC,
                            body.SEDENTARY,
                            body.LIGHTLY_ACTIVE,
                            body.MODERATELY_ACTIVE,
                            body.VERY_ACTIVE,
                            body.EXTREMELY_ACTIVE
                        ]),
                        value=body.SEDENTARY,
                    ),
                ], style={'marginBottom': '1.5rem'}),
                html.Button(
                    'Calculate Nutrition Requirements',
                    id='calculate-macros-btn',
                    n_clicks=0,
                    className='btn btn-primary',
                    style={'width': '100%', 'padding': '1rem'}
                ),
            ],
            style={'background': 'var(--surface)', 'padding': '2rem', 'borderRadius': 'var(--radius)', 'maxWidth': '400px', 'marginTop': '1.5rem'}
        ),
        
        html.Div(id='macro-result-output', style={'marginTop': '2rem'}),
    ], style={
        'fontFamily': "'Inter', sans-serif",
        'maxWidth': '800px',
        'margin': '0 auto',
        'padding': '2rem 1.5rem',
        'background': 'var(--canvas)',
        'minHeight': '100vh',
        'color': 'var(--text)'
    })

    # Client-side callback for the smart 'Back' button

    # Register common callbacks
    dash_utils.register_back_button_callback(app, btn_id='back-btn-bc')
    dash_utils.register_theme_sync(app)

    
    @app.callback(
        [
            Output('hip-container', 'style'),
            Output('weight-label', 'children'),
            Output('height-label', 'children'),
            Output('waist-label', 'children'),
            Output('neck-label', 'children'),
            Output('hip-label', 'children')
        ],
        [Input('sex-input', 'value'), Input('unit-input', 'value')]
    )
    def update_form(sex, unit):
        is_metric = unit == 'metric'
        w_unit = ' (kg)' if is_metric else ' (lbs)'
        h_unit = ' (cm)' if is_metric else ' (in)'
        
        display_hip = {'marginBottom': '1.5rem', 'display': 'block'} if sex == 'female' else {'marginBottom': '1.5rem', 'display': 'none'}
        waist_text = 'Waist at narrowest' if sex == 'female' else 'Abdomen at navel'
        
        return (
            display_hip,
            f'Weight{w_unit}',
            f'Height{h_unit}',
            f'{waist_text}{h_unit}',
            f'Neck at narrowest{h_unit}',
            f'Hips at widest{h_unit}'
        )
    
    @app.callback(
        Output('result-output', 'children'),
        Input('calculate-btn', 'n_clicks'),
        [
            State('unit-input', 'value'),
            State('sex-input', 'value'),
            State('weight-input', 'value'),
            State('height-input', 'value'),
            State('waist-input', 'value'),
            State('neck-input', 'value'),
            State('hip-input', 'value')
        ]
    )
    def calculate_body_composition(n_clicks, unit, sex, weight, height, waist, neck, hip):
        if n_clicks == 0:
            return ''
        
        if not all([weight, height, waist, neck]) or (sex == 'female' and not hip):
            return html.Div('Please fill in all required fields.', style={'color': 'var(--error)', 'fontWeight': '500'})
        
        is_male = (sex == 'male')
        metric_h = _to_metric_len(height, unit)
        metric_w = _to_metric_len(waist, unit)
        metric_n = _to_metric_len(neck, unit)
        metric_hip = _to_metric_len(hip or 0, unit)
        metric_mass = _to_metric_mass(weight, unit)

        bf = body.calculate_bf_percent(is_male, metric_h, metric_w, metric_n, metric_hip)
        if bf is None:
            return html.Div('Invalid measurements.', style={'color': 'var(--error)'})

        bmi = body.calc_bmi(metric_mass, metric_h)
        ffm = body.calc_ffm(metric_mass, bf)
        ffmi = body.calc_ffmi(ffm, metric_h)
        adj_ffmi = body.calc_adj_ffmi(ffmi, metric_h)

        # Store cache in a hidden Div or dcc.Store is cleaner, but to avoid huge refactor, we rely on user not changing inputs between steps
        # Actually ideally we use dcc.Store. For now, we will recalculate BF in Step 2 to keep it stateless and simple.
        
        return _create_output_card([
            html.Div([
                _result_row('Body Fat', f'{bf:.1f}', '%', True),
                _result_row('Adj. FFMI', f'{adj_ffmi:.1f}', '', True),
                _result_row('BMI', f'{bmi:.1f}'),
                _result_row('FFMI', f'{ffmi:.1f}'),
            ], style={'display': 'flex', 'flexDirection': 'column', 'gap': '0.5rem'}),
        ])


    @app.callback(
        Output('macro-result-output', 'children'),
        Input('calculate-macros-btn', 'n_clicks'),
        [
            State('unit-input', 'value'),
            State('sex-input', 'value'),
            State('weight-input', 'value'),
            State('height-input', 'value'),
            State('waist-input', 'value'),
            State('neck-input', 'value'),
            State('hip-input', 'value'),
            State('age-input', 'value'),
            State('activity-input', 'value')
        ]
    )
    def calculate_macros(n_clicks, unit, sex, weight, height, waist, neck, hip, age, activity_level):
        if n_clicks == 0:
            return ''
        
        # Validate ALL inputs
        if not all([weight, height, waist, neck]) or (sex == 'female' and not hip):
             return html.Div('Please fill in all body measurements above.', style={'color': 'var(--error)', 'fontWeight': '500'})

        if not age:
             return html.Div('Please enter your age.', style={'color': 'var(--error)', 'fontWeight': '500'})

        is_male = (sex == 'male')
        metric_h = _to_metric_len(height, unit)
        metric_w = _to_metric_len(waist, unit)
        metric_n = _to_metric_len(neck, unit)
        metric_hip = _to_metric_len(hip or 0, unit)
        metric_mass = _to_metric_mass(weight, unit)

        bf = body.calculate_bf_percent(is_male, metric_h, metric_w, metric_n, metric_hip)
        if bf is None:
             return html.Div('Invalid measurements.', style={'color': 'var(--error)'})
        
        macros = body.compute_macros(is_male, age, metric_h, metric_mass, bf, activity_level)

        return _create_output_card([
             html.Div([
                 _result_row('Maintenance Calories', f'{int(macros[body.MAINTENANCE])}', ' kcal', True),
                 _result_row('Basal Metabolic Rate', f'{int(macros[body.BMR])}', ' kcal'),
                 html.Hr(style={'borderColor': 'var(--surface)', 'margin': '0.5rem 0'}),
                 _result_row('Recommended Protein', f'{int(macros[body.RECOMMENDED_PROTEIN])}', 'g', True),
                 _result_row('Minimum Fats', f'{int(macros[body.MIN_FAT])}', 'g'),
                 _result_row('Maximum Carbs', f'{int(macros[body.MAX_CARBS])}', 'g'),
            ], style={'display': 'flex', 'flexDirection': 'column', 'gap': '0.5rem'}),
        ], extra_style={'marginTop': '2rem'})
    
    return app
