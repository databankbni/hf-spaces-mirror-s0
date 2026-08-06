"""
FitNotes Cleaner - Dash Application
Rewritten with stable architecture:
- Selection state managed via dcc.Store
- List re-renders ONLY on db-store changes (not selection changes)
- Clientside callback toggles CSS classes for visual feedback
- All action buttons exist in layout (hidden) to avoid missing input errors
"""
from dash import Dash, html, dcc, Input, Output, State, ALL, callback_context, no_update
import base64
import json
from .db import operations
from .db import jackked_mods
from tools import dash_utils


def _get_db_bytes(contents):
    """Extract bytes from base64 upload content."""
    if contents is None:
        return None
    content_type, content_string = contents.split(',')
    return base64.b64decode(content_string)


def _render_report(db_bytes):
    """Render the category/exercise list. Selection is handled via CSS classes."""
    report = operations.generate_report(db_bytes)
    
    children = []
    for cat in report['categories']:
        # Exercise items
        ex_items = []
        for ex in cat['exercises']:
            ex_items.append(html.Div([
                html.Span(ex['name']),
                html.Span(f"{ex['log_count']} logs", className='text-muted text-sm')
            ], className='exercise-item', id={'type': 'ex', 'id': ex['id']}, **{'data-id': ex['id']}))

        # Category header with checkbox on left
        cat_header = html.Div([
            html.Div(className='category-checkbox', id={'type': 'cat', 'id': cat['id']}, **{'data-id': cat['id']}),
            html.Div([
                html.Span(cat['name'], className='font-bold'),
                html.Span(f" ({len(cat['exercises'])} exercises)", className='text-sm text-muted')
            ], style={'flex': '1'})
        ], className='category-header', id={'type': 'cat-header', 'id': cat['id']}, **{'data-id': cat['id']})

        children.append(html.Details([
            html.Summary(cat_header),
            html.Div(ex_items, className='exercise-list')
        ], className='category-block', open=False))
        
    return children


def create_fitnotes_cleaner(server):
    app = Dash(
        __name__,
        server=server,
        url_base_pathname='/tools/fitnotes-cleaner/',
        suppress_callback_exceptions=True,  # Critical for dynamic components
        external_stylesheets=[
            'https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap',
            '/static/css/style.css'
        ]
    )

    # Custom CSS for this tool
    tool_css = """
    <style>
        .category-header {
            padding: 0.75rem 1rem;
            border-radius: var(--radius);
            background: var(--surface);
            display: flex;
            justify-content: space-between;
            align-items: center;
            cursor: pointer;
            margin-bottom: 0.5rem;
            transition: all 0.15s ease;
        }
        .category-header.selected {
            background: var(--primary);
            color: white;
        }
        .category-header.selected .text-muted {
            color: rgba(255,255,255,0.8);
        }
        .dark .category-header.selected {
            color: black;
        }
        .dark .category-header.selected .text-muted {
            color: rgba(0,0,0,0.7);
        }
        .category-checkbox {
            width: 16px;
            height: 16px;
            border: 1px solid var(--primary);
            border-radius: 50%;
            margin-right: 0.75rem;
            flex-shrink: 0;
            transition: all 0.15s ease;
        }
        .category-header.selected .category-checkbox {
            background: transparent;
            border-color: currentColor;
            position: relative;
        }
        .category-header.selected .category-checkbox::after {
            content: '';
            position: absolute;
            top: 50%;
            left: 50%;
            transform: translate(-50%, -50%);
            width: 8px;
            height: 8px;
            border-radius: 50%;
            background: currentColor;
        }
        .btn-delete {
            background: var(--error) !important;
            color: white !important;
            border-color: var(--error) !important;
        }

        .exercise-item {
            padding: 0.75rem 1rem;
            margin-left: 1rem;
            margin-bottom: 0.25rem;
            background: var(--surface);
            border-left: 4px solid transparent;
            display: flex;
            justify-content: space-between;
            cursor: pointer;
            transition: all 0.15s ease;
        }
        .exercise-item.selected {
            border-left-color: var(--primary);
            background: var(--canvas);
            font-weight: 600;
        }
        .exercise-list { padding: 0.5rem 0; }
        .category-block { margin-bottom: 1rem; }
        .category-block summary { list-style: none; }
        .category-block summary::-webkit-details-marker { display: none; }
        .text-muted { color: var(--text-muted); }
        .text-sm { font-size: 0.8rem; }
        .font-bold { font-weight: 700; }
        .btn-sm { padding: 0.25rem 0.5rem; font-size: 0.75rem; }
        .action-bar {
            position: fixed;
            bottom: 0;
            left: 0;
            right: 0;
            background: var(--surface);
            padding: 1rem;
            padding-top: 1.25rem;
            display: none;
            z-index: 1000;
            flex-direction: column;
            align-items: center;
            gap: 0.75rem;
        }
        .action-bar::before {
            content: '';
            position: absolute;
            top: 0;
            left: 0;
            right: 0;
            height: 1px;
            background: var(--primary);
            opacity: 0.3;
        }
        .action-bar.visible { display: flex; }
        .action-bar-summary {
            text-align: center;
            font-weight: 600;
            color: var(--primary);
            font-size: 0.9rem;
        }
        .action-bar-buttons {
            display: flex;
            justify-content: center;
            gap: 0.5rem;
            flex-wrap: wrap;
        }
        .modal-overlay {
            position: fixed;
            inset: 0;
            background: rgba(0,0,0,0.7);
            display: none;
            z-index: 2000;
            align-items: center;
            justify-content: center;
            padding: 1.5rem;
        }
        .modal-overlay.visible { display: flex; }
        .modal-box {
            background: var(--surface);
            padding: 2rem;
            border-radius: var(--radius);
            width: 100%;
            max-width: 400px;
        }
        .btn-icon {
            color: var(--primary);
            font-size: 1.15em;
        }
        .hidden { display: none !important; }
    </style>
    """

    app.index_string = dash_utils.get_dash_index_string('FitNotes Cleaner', extra_css=tool_css + '''
            <script>
                // Prevent checkbox clicks from toggling details, but let event bubble to Dash
                document.addEventListener('click', function(e) {{
                    if (e.target.classList.contains('category-checkbox')) {{
                        e.preventDefault();
                    }}
                }});
                // Close modal on overlay click (outside modal box)
                document.addEventListener('click', function(e) {{
                    if (e.target.id === 'modal-overlay') {{
                        var cancelBtn = document.getElementById('btn-modal-cancel');
                        if (cancelBtn) cancelBtn.click();
                    }}
                }});
            </script>
    ''')

    app.layout = html.Div([
        # Data storage
        dcc.Store(id='db-store'),
        dcc.Store(id='selection-store', data={'categories': [], 'exercises': []}),
        dcc.Download(id='download-db'),
        
        # Theme sync dummy
        html.Div(id='theme-sync-dummy', style={'display': 'none'}),
        
        # Header
        html.Div([
            dash_utils.create_back_button(id='back-btn-fc'),
            html.H1('FitNotes Cleaner', style={'marginTop': '1.5rem', 'marginBottom': '0.5rem'}),
            html.P('Clean, merge and reorganize your FitNotes exports', className='text-muted'),
        ], style={'marginBottom': '2rem'}),

        # Upload area wrapped in Loading
        dcc.Loading(
            id='loading-upload',
            type='dot',
            fullscreen=True,
            color='var(--primary)',
            children=[
                html.Div(id='upload-container', children=[
                    dcc.Upload(
                        id='upload-data',
                        children=html.Div(['Drag and Drop or ', html.A('Select .fitnotes File')]),
                        style={
                            'width': '100%', 'height': '120px', 'lineHeight': '120px',
                            'borderWidth': '2px', 'borderStyle': 'dashed', 'borderRadius': 'var(--radius)',
                            'textAlign': 'center', 'borderColor': 'var(--surface)', 'color': 'var(--text-muted)',
                            'cursor': 'pointer'
                        },
                        multiple=False
                    ),
                    html.Div(id='upload-status')
                ]),
            ]
        ),

        # Tools (hidden until file loaded)
        html.Div(id='tools-container', className='hidden', style={
            'display': 'flex', 'flexDirection': 'column', 'gap': '0.5rem', 'marginBottom': '2rem'
        }, children=[
            html.Button([html.Span('✓', className='btn-icon'), '  Apply Jackked Mods'], id='btn-jackked-mods', className='btn btn-secondary'),
            html.Button([html.Span('⬇', className='btn-icon'), '  Download Modified'], id='btn-download', className='btn btn-secondary'),
        ]),

        # Report container wrapped in Loading
        dcc.Loading(
            id='loading-report',
            type='dot',
            fullscreen=True,
            color='var(--primary)',
            children=[html.Div(id='report-container')]
        ),

        # New Category button (below the list)
        html.Div(id='new-cat-container', className='hidden', style={'marginBottom': '2rem'}, children=[
            html.Button([html.Span('＋', className='btn-icon'), '  New Category'], id='btn-create-cat', className='btn btn-secondary', style={'width': '100%'}),
        ]),
        
        # Action bar (selection-dependent buttons)
        html.Div(id='action-bar', className='action-bar', children=[
            html.Div(id='selection-summary', className='action-bar-summary'),
            html.Div(className='action-bar-buttons', children=[
                html.Button('Rename', id='btn-rename', className='btn btn-secondary hidden'),
                html.Button('Move', id='btn-move', className='btn btn-secondary hidden'),
                html.Button('Delete', id='btn-delete', className='btn btn-delete hidden'),
                html.Button('Merge', id='btn-merge', className='btn btn-primary hidden'),
                html.Button('Clear', id='btn-clear', className='btn btn-secondary'),
            ])
        ]),

        # Modal
        html.Div(id='modal-overlay', className='modal-overlay', children=[
            html.Div(className='modal-box', children=[
                html.H3(id='modal-title'),
                html.Div(id='modal-body'),
                # Input field (shown/hidden based on operation)
                dcc.Input(id='modal-input', placeholder='', style={'width': '100%', 'marginBottom': '1rem', 'display': 'none'}),
                # Dropdown field (shown/hidden via container)
                html.Div(id='modal-dropdown-container', style={'display': 'none', 'marginBottom': '1rem'}, children=[
                    dash_utils.create_dropdown(id='modal-dropdown'),
                ]),
                html.Div(id='modal-error', style={'color': 'var(--error)', 'marginTop': '0.5rem'}),
                html.Div([
                    html.Button('Cancel', id='btn-modal-cancel', className='btn btn-secondary'),
                    html.Button('Confirm', id='btn-modal-confirm', className='btn btn-primary'),
                ], style={'display': 'flex', 'gap': '1rem', 'justifyContent': 'flex-end', 'marginTop': '1.5rem'})
            ])
        ]),
        
        # Hidden store for current operation
        dcc.Store(id='current-op', data=None),

    ], style={
        'fontFamily': "'Inter', sans-serif",
        'maxWidth': '800px',
        'margin': '0 auto',
        'padding': '2rem 1.5rem',
        'minHeight': '100vh',
        'paddingBottom': '100px'
    })

    # ===== CALLBACKS =====

    # 1. Handle file upload
    @app.callback(
        [
            Output('db-store', 'data'),
            Output('upload-container', 'className'),
            Output('tools-container', 'className'),
            Output('new-cat-container', 'className'),
            Output('report-container', 'children'),
            Output('upload-status', 'children'),
        ],
        Input('upload-data', 'contents'),
        prevent_initial_call=True
    )
    def handle_upload(contents):
        if not contents:
            return no_update, '', 'hidden', 'hidden', [], ''
        
        try:
            db_bytes = _get_db_bytes(contents)
            operations.generate_report(db_bytes)  # Validate
            db_b64 = base64.b64encode(db_bytes).decode('utf-8')
            report_children = _render_report(db_bytes)
            return db_b64, 'hidden', '', '', report_children, ''
        except Exception as e:
            return None, '', 'hidden', 'hidden', [], html.Div(f"Error: {str(e)}", style={'color': 'var(--error)'})

    # 2. Clientside: Toggle item selection and update store
    app.clientside_callback(
        """
        function(n_clicks_ex, n_clicks_cat, clear_clicks, current_selection) {
            const ctx = dash_clientside.callback_context;
            if (!ctx.triggered.length) return window.dash_clientside.no_update;
            
            const trigger = ctx.triggered[0];
            const prop_id = trigger.prop_id;
            const value = trigger.value;
            
            // Ignore initialization (value is null or 0)
            if (!value) return window.dash_clientside.no_update;
            
            // Clear button
            if (prop_id === 'btn-clear.n_clicks') {
                document.querySelectorAll('.selected').forEach(el => el.classList.remove('selected'));
                return {categories: [], exercises: []};
            }
            
            // Parse the component ID
            let id_obj;
            try {
                id_obj = JSON.parse(prop_id.split('.')[0]);
            } catch(e) {
                return window.dash_clientside.no_update;
            }
            
            const item_type = id_obj.type;
            const item_id = id_obj.id;
            
            // Find the clicked element and toggle
            const selector = `[data-id="${item_id}"]`;
            const elements = document.querySelectorAll(selector);
            
            let newSel = {categories: [], exercises: []};
            
            if (item_type === 'ex') {
                // Clear category selections when selecting exercise
                document.querySelectorAll('.category-header.selected').forEach(el => el.classList.remove('selected'));
                
                const idx = current_selection.exercises.indexOf(item_id);
                if (idx > -1) {
                    // Deselecting this exercise
                    newSel.exercises = current_selection.exercises.filter(id => id !== item_id);
                    elements.forEach(el => el.classList.remove('selected'));
                } else {
                    // Selecting this exercise
                    newSel.exercises = [...current_selection.exercises, item_id];
                    elements.forEach(el => el.classList.add('selected'));
                }
            } else if (item_type === 'cat' || item_type === 'cat-header') {
                // Clear exercise selections when selecting category
                document.querySelectorAll('.exercise-item.selected').forEach(el => el.classList.remove('selected'));
                
                // Enforce single select: Clear all other category selections visually
                document.querySelectorAll('.category-header.selected').forEach(el => el.classList.remove('selected'));
                
                const idx = current_selection.categories.indexOf(item_id);
                if (idx > -1) {
                    // Deselecting this category (it was already selected)
                    newSel.categories = [];
                    // Visual removal handled by the global clear above
                } else {
                    // Selecting this category
                    newSel.categories = [item_id];
                    elements.forEach(el => el.classList.add('selected'));
                }
            }
            
            return newSel;
        }
        """,
        Output('selection-store', 'data'),
        [
            Input({'type': 'ex', 'id': ALL}, 'n_clicks'),
            Input({'type': 'cat', 'id': ALL}, 'n_clicks'),
            Input('btn-clear', 'n_clicks'),
        ],
        State('selection-store', 'data'),
        prevent_initial_call=True
    )

    # 3. Update action bar based on selection
    @app.callback(
        [
            Output('action-bar', 'className'),
            Output('selection-summary', 'children'),
            Output('btn-rename', 'className'),
            Output('btn-move', 'className'),
            Output('btn-delete', 'className'),
            Output('btn-merge', 'className'),
        ],
        Input('selection-store', 'data')
    )
    def update_action_bar(selection):
        n_cats = len(selection['categories'])
        n_exs = len(selection['exercises'])
        
        if n_cats == 0 and n_exs == 0:
            return 'action-bar', '', 'btn btn-secondary hidden', 'btn btn-secondary hidden', 'btn btn-secondary hidden', 'btn btn-primary hidden'
        
        # Build readable summary
        summary_parts = []
        if n_cats == 1:
            summary_parts.append("1 Category Selected")
        elif n_cats > 1:
            summary_parts.append(f"{n_cats} Categories Selected")
        if n_exs == 1:
            summary_parts.append("1 Exercise Selected")
        elif n_exs > 1:
            summary_parts.append(f"{n_exs} Exercises Selected")
        summary = ", ".join(summary_parts)
        
        # Determine which buttons to show
        show_rename = (n_cats == 1 and n_exs == 0) or (n_exs == 1 and n_cats == 0)
        show_move = n_exs >= 1 and n_cats == 0
        show_delete = (n_cats == 1 and n_exs == 0) or (n_exs == 1 and n_cats == 0)
        show_merge = n_exs >= 2 and n_cats == 0
        
        rename_cls = 'btn btn-secondary' if show_rename else 'btn btn-secondary hidden'
        move_cls = 'btn btn-secondary' if show_move else 'btn btn-secondary hidden'
        delete_cls = 'btn btn-delete' if show_delete else 'btn btn-delete hidden'
        merge_cls = 'btn btn-primary' if show_merge else 'btn btn-primary hidden'
        
        return 'action-bar visible', summary, rename_cls, move_cls, delete_cls, merge_cls

    # 4. Open modal for operations
    @app.callback(
        [
            Output('modal-overlay', 'className'),
            Output('modal-title', 'children'),
            Output('modal-body', 'children'),
            Output('modal-input', 'style'),
            Output('modal-input', 'placeholder'),
            Output('modal-input', 'value'),
            Output('modal-dropdown-container', 'style'),
            Output('modal-dropdown', 'options'),
            Output('modal-dropdown', 'placeholder'),
            Output('modal-dropdown', 'value'),
            Output('current-op', 'data'),
            Output('modal-error', 'children'),
        ],
        [
            Input('btn-create-cat', 'n_clicks'),
            Input('btn-rename', 'n_clicks'),
            Input('btn-move', 'n_clicks'),
            Input('btn-delete', 'n_clicks'),
            Input('btn-merge', 'n_clicks'),
            Input('btn-modal-cancel', 'n_clicks'),
        ],
        [
            State('selection-store', 'data'),
            State('db-store', 'data'),
        ],
        prevent_initial_call=True
    )
    def handle_modal(create_n, rename_n, move_n, delete_n, merge_n, cancel_n, selection, db_b64):
        ctx = callback_context
        if not ctx.triggered_id:
            return [no_update] * 12
        
        tid = ctx.triggered_id
        
        # Hidden styles
        hidden = {'display': 'none'}
        shown_input = {'width': '100%', 'marginBottom': '1rem', 'display': 'block'}
        shown_dropdown = {'marginBottom': '1rem'}
        
        # Cancel closes modal
        if tid == 'btn-modal-cancel':
            return 'modal-overlay', '', [], hidden, '', '', hidden, [], '', None, None, ''
        
        n_cats = len(selection['categories'])
        n_exs = len(selection['exercises'])
        
        if tid == 'btn-create-cat':
            return (
                'modal-overlay visible', 'Create Category', [],
                shown_input, 'Category Name', '',
                hidden, [], '', None,
                {'op': 'create-cat'}, ''
            )
        
        if tid == 'btn-rename':
            op_type = 'rename-cat' if n_cats == 1 else 'rename-ex'
            # Get current name
            db_bytes = base64.b64decode(db_b64)
            report = operations.generate_report(db_bytes)
            current_name = ''
            if n_cats == 1:
                cat_id = selection['categories'][0]
                for cat in report['categories']:
                    if cat['id'] == cat_id:
                        current_name = cat['name']
                        break
            else:
                ex_id = selection['exercises'][0]
                for cat in report['categories']:
                    for ex in cat['exercises']:
                        if ex['id'] == ex_id:
                            current_name = ex['name']
                            break
            return (
                'modal-overlay visible', 'Rename', [],
                shown_input, 'New Name', current_name,
                hidden, [], '', None,
                {'op': op_type}, ''
            )
        
        if tid == 'btn-move':
            db_bytes = base64.b64decode(db_b64)
            report = operations.generate_report(db_bytes)
            options = [{'label': cat['name'], 'value': cat['id']} for cat in report['categories']]
            first_val = options[0]['value'] if options else None
            return (
                'modal-overlay visible', 'Move to Category', [],
                hidden, '', '',
                shown_dropdown, options, 'Select Category', first_val,
                {'op': 'move-ex'}, ''
            )
        
        if tid == 'btn-delete':
            op_type = 'delete-cat' if n_cats == 1 else 'delete-ex'
            return (
                'modal-overlay visible', 'Confirm Delete', [html.P('This action cannot be undone.')],
                hidden, '', '',
                hidden, [], '', None,
                {'op': op_type}, ''
            )
        
        if tid == 'btn-merge':
            db_bytes = base64.b64decode(db_b64)
            report = operations.generate_report(db_bytes)
            ex_names = {}
            for cat in report['categories']:
                for ex in cat['exercises']:
                    ex_names[ex['id']] = ex['name']
            
            options = [{'label': ex_names.get(eid, f"ID: {eid}"), 'value': eid} for eid in selection['exercises']]
            first_val = options[0]['value'] if options else None
            return (
                'modal-overlay visible', 'Merge Exercises', [html.P('Select the exercise to KEEP:')],
                hidden, '', '',
                shown_dropdown, options, 'Select Target', first_val,
                {'op': 'merge-ex'}, ''
            )
        
        return [no_update] * 12

    # 5. Execute operation
    @app.callback(
        [
            Output('db-store', 'data', allow_duplicate=True),
            Output('selection-store', 'data', allow_duplicate=True),
            Output('modal-overlay', 'className', allow_duplicate=True),
            Output('report-container', 'children', allow_duplicate=True),
            Output('modal-error', 'children', allow_duplicate=True),
        ],
        Input('btn-modal-confirm', 'n_clicks'),
        [
            State('current-op', 'data'),
            State('selection-store', 'data'),
            State('db-store', 'data'),
            State('modal-input', 'value'),
            State('modal-dropdown', 'value'),
        ],
        prevent_initial_call=True
    )
    def execute_operation(n_clicks, current_op, selection, db_b64, input_val, dropdown_val):
        if not n_clicks or not current_op:
            return no_update, no_update, no_update, no_update, no_update
        
        op = current_op['op']
        db_bytes = base64.b64decode(db_b64)
        
        try:
            if op == 'create-cat':
                if not input_val:
                    return no_update, no_update, no_update, no_update, 'Please enter a name'
                db_bytes = operations.create_category(db_bytes, input_val)
            
            elif op == 'rename-cat':
                if not input_val:
                    return no_update, no_update, no_update, no_update, 'Please enter a name'
                db_bytes = operations.rename_category(db_bytes, selection['categories'][0], input_val)
            
            elif op == 'rename-ex':
                if not input_val:
                    return no_update, no_update, no_update, no_update, 'Please enter a name'
                db_bytes = operations.rename_exercise(db_bytes, selection['exercises'][0], input_val)
            
            elif op == 'delete-cat':
                db_bytes = operations.delete_category(db_bytes, selection['categories'][0])
            
            elif op == 'delete-ex':
                db_bytes = operations.delete_exercise(db_bytes, selection['exercises'][0])
            
            elif op == 'move-ex':
                if not dropdown_val:
                    return no_update, no_update, no_update, no_update, 'Please select a category'
                db_bytes = operations.move_exercises(db_bytes, selection['exercises'], dropdown_val)
            
            elif op == 'merge-ex':
                if not dropdown_val:
                    return no_update, no_update, no_update, no_update, 'Please select target exercise'
                db_bytes = operations.merge_exercises(db_bytes, selection['exercises'], dropdown_val)
            
            new_b64 = base64.b64encode(db_bytes).decode('utf-8')
            new_report = _render_report(db_bytes)
            return new_b64, {'categories': [], 'exercises': []}, 'modal-overlay', new_report, ''
            
        except Exception as e:
            return no_update, no_update, no_update, no_update, f'Error: {str(e)}'

    # 6. Jackked Mods - Apply all Jackked-recommended operations
    @app.callback(
        [
            Output('db-store', 'data', allow_duplicate=True),
            Output('selection-store', 'data', allow_duplicate=True),
            Output('report-container', 'children', allow_duplicate=True),
        ],
        Input('btn-jackked-mods', 'n_clicks'),
        State('db-store', 'data'),
        prevent_initial_call=True
    )
    def apply_jackked_modifications(n_clicks, db_b64):
        if not n_clicks or not db_b64:
            return no_update, no_update, no_update
        
        try:
            db_bytes = base64.b64decode(db_b64)
            db_bytes = jackked_mods.apply_jackked_mods(db_bytes)
            new_b64 = base64.b64encode(db_bytes).decode('utf-8')
            new_report = _render_report(db_bytes)
            return new_b64, {'categories': [], 'exercises': []}, new_report
        except Exception as e:
            # On error, keep current state
            return no_update, no_update, no_update

    # 7. Download handler
    @app.callback(
        Output('download-db', 'data'),
        Input('btn-download', 'n_clicks'),
        State('db-store', 'data'),
        prevent_initial_call=True
    )
    def handle_download(n_clicks, db_b64):
        if not n_clicks or not db_b64:
            return no_update
        return dcc.send_bytes(base64.b64decode(db_b64), "FitNotes_Modified.fitnotes")

    # Register common callbacks
    dash_utils.register_back_button_callback(app, btn_id='back-btn-fc')
    dash_utils.register_theme_sync(app)

    return app
