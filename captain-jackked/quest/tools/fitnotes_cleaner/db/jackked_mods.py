"""
Jackked Mods - FitNotes Database Transformation

Applies the Jackked-recommended cleanup operations to a FitNotes database:
1. Creates 9 Jackked movement pattern categories + Conditioning
2. Moves exercises to their correct movement patterns
3. Renames exercises to match Jackked canonical names
4. Merges exercise variants into canonical Jackked exercises
5. Moves non-Jackked exercises to 'Other'
6. Merges Cardio and Abs into 'Conditioning'
7. Deletes empty categories
"""

from . import operations

# Jackked movement pattern categories to create
JACKKED_CATEGORIES = [
    'Jump',
    'Hinge',
    'Horizontal Push',
    'Vertical Push',
    'Vertical Pull',
    'Horizontal Pull',
    'Lunge',
    'Upper Isolation',
    'Lower Isolation',
    'Conditioning'
]

# Category visuals (colour and sort_order) from user screenshot
CATEGORY_VISUALS = {
    'Jump': {'colour': -15294331, 'sort_order': 0},
    'Hinge': {'colour': -10665929, 'sort_order': 1},
    'Horizontal Push': {'colour': -13710223, 'sort_order': 2},
    'Vertical Pull': {'colour': -1618884, 'sort_order': 3},
    'Vertical Push': {'colour': -6596170, 'sort_order': 4},
    'Horizontal Pull': {'colour': -1671646, 'sort_order': 5},
    'Upper Isolation': {'colour': -13330213, 'sort_order': 6},
    'Lower Isolation': {'colour': -13877680, 'sort_order': 7},
    'Lunge': {'colour': -812014, 'sort_order': 8},
    'Other': {'colour': -9079435, 'sort_order': 9},
    'Conditioning': {'colour': -4342339, 'sort_order': 10},
}

# All canonical Jackked exercises (name, category) - will be inserted if missing
JACKKED_EXERCISES = [
    # Jump
    ('Barbell Squat', 'Jump'),
    ('Barbell Front Squat', 'Jump'),
    ('Goblet Squat', 'Jump'),
    ('Smith Machine Squat', 'Jump'),
    ('Hack Squat', 'Jump'),
    ('Leg Press', 'Jump'),
    
    # Hinge
    ('Deadlift', 'Hinge'),
    ('Paused Deadlift', 'Hinge'),
    ('Romanian Deadlift', 'Hinge'),
    ('Good Morning', 'Hinge'),
    
    # Horizontal Push
    ('Flat Barbell Bench Press', 'Horizontal Push'),
    ('Flat Dumbbell Bench Press', 'Horizontal Push'),
    ('Parallel Bar Dip', 'Horizontal Push'),
    ('Push Up', 'Horizontal Push'),
    ('Smith Machine Bench Press', 'Horizontal Push'),
    
    # Vertical Push
    ('Overhead Press', 'Vertical Push'),
    ('Dumbbell Overhead Press', 'Vertical Push'),
    ('Incline Barbell Bench Press', 'Vertical Push'),
    ('Incline Dumbbell Bench Press', 'Vertical Push'),
    ('Smith Machine Incline Press', 'Vertical Push'),
    
    # Vertical Pull
    ('Pull Up', 'Vertical Pull'),
    ('Chin Up', 'Vertical Pull'),
    ('Close Lat Pulldown', 'Vertical Pull'),
    ('Wide Lat Pulldown', 'Vertical Pull'),
    
    # Horizontal Pull
    ('Barbell Row', 'Horizontal Pull'),
    ('Dumbbell Row', 'Horizontal Pull'),
    ('Cable Row', 'Horizontal Pull'),
    ('Machine Row', 'Horizontal Pull'),
    
    # Lower Isolation
    ('Leg Extension', 'Lower Isolation'),
    ('Hamstring Curl', 'Lower Isolation'),
    ('Standing Calf Raise', 'Lower Isolation'),
    ('Hip Thrust', 'Lower Isolation'),
    
    # Lunge
    ('Bulgarian Split Squat', 'Lunge'),
    ('Standing Lunge', 'Lunge'),
    ('Single-leg Step Up', 'Lunge'),
    
    # Upper Isolation
    ('Lateral Raise', 'Upper Isolation'),
    ('Reverse Fly', 'Upper Isolation'),
    ('Cable Fly', 'Upper Isolation'),
    ('Bicep Curl', 'Upper Isolation'),
    ('Tricep Extension', 'Upper Isolation'),
    
    # Conditioning
    ('Front Plank', 'Conditioning'),
    ('Side Plank', 'Conditioning'),
    ('Run — Jog', 'Conditioning'),
    ('Run — Sprint', 'Conditioning'),
]

# Exercise mappings: (fitnotes_name, jackked_name, target_category)
# If fitnotes_name == jackked_name, only a move is needed
# If they differ, a rename is also needed
EXERCISE_MAPPINGS = [
    # Jump
    ('Barbell Squat', 'Barbell Squat', 'Jump'),
    ('Barbell Front Squat', 'Barbell Front Squat', 'Jump'),
    ('Leg Press', 'Leg Press', 'Jump'),
    ('Smith Machine Squat', 'Smith Machine Squat', 'Jump'),
    
    # Hinge
    ('Deadlift', 'Deadlift', 'Hinge'),
    ('Good Morning', 'Good Morning', 'Hinge'),
    
    # Horizontal Push
    ('Flat Dumbbell Bench Press', 'Flat Dumbbell Bench Press', 'Horizontal Push'),
    ('Push Up', 'Push Up', 'Horizontal Push'),
    ('Smith Machine Close Grip Bench Press', 'Smith Machine Bench Press', 'Horizontal Push'),
    
    # Vertical Push
    ('Incline Barbell Bench Press', 'Incline Barbell Bench Press', 'Vertical Push'),
    ('Incline Dumbbell Bench Press', 'Incline Dumbbell Bench Press', 'Vertical Push'),
    ('Seated Dumbbell Press', 'Dumbbell Overhead Press', 'Vertical Push'),
    
    # Vertical Pull
    ('Chin Up', 'Chin Up', 'Vertical Pull'),
    ('Pull Up', 'Pull Up', 'Vertical Pull'),
    ('Lat Pulldown', 'Close Lat Pulldown', 'Vertical Pull'),
    
    # Horizontal Pull
    ('Dumbbell Row', 'Dumbbell Row', 'Horizontal Pull'),
    ('Seated Cable Row', 'Cable Row', 'Horizontal Pull'),
    ('Hammer Strength Row', 'Machine Row', 'Horizontal Pull'),
    
    # Upper Isolation
    ('Cable Crossover', 'Cable Fly', 'Upper Isolation'),
    
    # Lower Isolation
    ('Leg Extension Machine', 'Leg Extension', 'Lower Isolation'),
    ('Barbell Glute Bridge', 'Hip Thrust', 'Lower Isolation'),
    
    # Conditioning
    ('Plank', 'Front Plank', 'Conditioning'),
]

# Merge mappings: (target_name, [source_names], target_category)
# All sources will be merged into target, then moved to category
MERGE_MAPPINGS = [
    # Upper Isolation merges
    ('Bicep Curl', [
        'Barbell Curl', 'Dumbbell Curl', 'Cable Curl', 
        'Seated Machine Curl', 'EZ-Bar Curl',
        'Dumbbell Hammer Curl', 'Dumbbell Concentration Curl', 
        'Seated Incline Dumbbell Curl',
        'Dumbbell Preacher Curl', 'EZ-Bar Preacher Curl'
    ], 'Upper Isolation'),
    ('Tricep Extension', [
        'Cable Overhead Triceps Extension', 
        'Dumbbell Overhead Triceps Extension', 
        'Lying Triceps Extension',
        'V-Bar Push Down', 'Straight-Arm Cable Pushdown', 'Rope Push Down'
    ], 'Upper Isolation'),
    ('Lateral Raise', [
        'Lateral Dumbbell Raise', 'Lateral Machine Raise', 
        'Seated Dumbbell Lateral Raise'
    ], 'Upper Isolation'),
    ('Reverse Fly', [
        'Rear Delt Dumbbell Raise', 'Rear Delt Machine Fly', 'Reverse Dumbbell Flies'
    ], 'Upper Isolation'),
    
    # Lower Isolation merges
    ('Standing Calf Raise', [
        'Standing Calf Raise Machine', 'Donkey Calf Raise', 
        'Barbell Calf Raise', 'Seated Calf Raise Machine',
        'Smith Machine Calf Raises', 'Calf Raise'
    ], 'Lower Isolation'),
    ('Hamstring Curl', [
        'Lying Leg Curl Machine', 'Seated Leg Curl Machine'
    ], 'Lower Isolation'),
    
    # Horizontal Push merges
    ('Flat Barbell Bench Press', [
        'Flat Barbell Bench Press', 'Close Grip Barbell Bench Press'
    ], 'Horizontal Push'),
    ('Parallel Bar Dip', [
        'Parallel Bar Triceps Dip', 'Ring Dip'
    ], 'Horizontal Push'),
    
    # Vertical Push merges
    ('Overhead Press', [
        'Overhead Press', 'One-Arm Standing Dumbbell Press', 'Arnold Dumbbell Press'
    ], 'Vertical Push'),
    
    # Horizontal Pull merges
    ('Barbell Row', [
        'Barbell Row', 'Pendlay Row'
    ], 'Horizontal Pull'),
    
    # Hinge merges
    ('Romanian Deadlift', [
        'Romanian Deadlift', 'Stiff-Legged Deadlift'
    ], 'Hinge'),
    
    # Lunge merges
    ('Standing Lunge', [
        'Standing Lunge', 'Dumbbell Lunge', 'Barbell Lunge', 'Walking Lunge'
    ], 'Lunge'),
    ('Bulgarian Split Squat', [
        'Bulgarian Split Squat', 'Dumbbell Split Squat'
    ], 'Lunge'),
    ('Single-leg Step Up', [
        'Single-leg Step Up', 'Dumbbell Step-up'
    ], 'Lunge'),

    # Conditioning merges
    ('Run — Jog', [
        'Running', 'Treadmill', 'Elliptical'
    ], 'Conditioning'),
    ('Run — Sprint', [
        'Sprinting', 'Sprint'
    ], 'Conditioning')
]


def apply_jackked_mods(db_bytes: bytes) -> bytes:
    """
    Apply all Jackked-recommended modifications to a FitNotes database.
    
    1. Creates all Jackked movement pattern categories
    2. Moves and renames exercises to match Jackked library
    3. Merges exercise variants into canonical Jackked exercises
    4. Moves Cardio and Abs to 'Conditioning'
    5. Moves non-Jackked exercises to 'Other'
    6. Deletes empty categories
    
    Returns: Modified database bytes
    """
    # Step 1: Create all Jackked categories + Other + Conditioning
    all_categories = JACKKED_CATEGORIES + ['Other', 'Conditioning']
    for cat_name in all_categories:
        try:
            db_bytes = operations.create_category(db_bytes, cat_name)
        except ValueError:
            pass  # Category already exists
    
    # Step 2: Build lookups
    report = operations.generate_report(db_bytes)
    cat_id_map = {cat['name']: cat['id'] for cat in report['categories']}
    ex_id_map = {}
    ex_cat_map = {}
    for cat in report['categories']:
        for ex in cat['exercises']:
            ex_id_map[ex['name']] = ex['id']
            ex_cat_map[ex['name']] = cat['name']
    
    jackked_exercises = set()
    
    # Step 3: Move and rename Jackked exercises
    for fitnotes_name, jackked_name, target_category in EXERCISE_MAPPINGS:
        if fitnotes_name not in ex_id_map:
            continue
        
        jackked_exercises.add(fitnotes_name)
        ex_id = ex_id_map[fitnotes_name]
        target_cat_id = cat_id_map.get(target_category)
        
        if target_cat_id is None:
            continue
        
        db_bytes = operations.move_exercises(db_bytes, [ex_id], target_cat_id)
        
        if fitnotes_name != jackked_name:
            # If target name already exists, merge instead of renaming
            existing_id = operations.get_exercise_id_by_name(db_bytes, jackked_name)
            if existing_id:
                try:
                    db_bytes = operations.merge_exercises(db_bytes, [ex_id, existing_id], existing_id)
                except ValueError:
                    pass
            else:
                try:
                    db_bytes = operations.rename_exercise(db_bytes, ex_id, jackked_name)
                except ValueError:
                    pass
    
    # Step 4: Merge exercise variants
    for target_name, source_names, target_category in MERGE_MAPPINGS:
        # Find all existing sources
        source_ids = [ex_id_map[name] for name in source_names if name in ex_id_map]
        
        if not source_ids:
            continue
        
        # First source becomes the target
        target_id = source_ids[0]
        jackked_exercises.update([name for name in source_names if name in ex_id_map])
        
        # Merge if more than one source
        if len(source_ids) > 1:
            try:
                db_bytes = operations.merge_exercises(db_bytes, source_ids, target_id)
            except ValueError:
                pass
        
        # Move to target category
        target_cat_id = cat_id_map.get(target_category)
        if target_cat_id:
            db_bytes = operations.move_exercises(db_bytes, [target_id], target_cat_id)
        
        # Rename to canonical name (or merge if target already exists)
        existing_id = operations.get_exercise_id_by_name(db_bytes, target_name)
        if existing_id and existing_id != target_id:
            try:
                db_bytes = operations.merge_exercises(db_bytes, [target_id, existing_id], existing_id)
            except ValueError:
                pass
        elif not existing_id:
            try:
                db_bytes = operations.rename_exercise(db_bytes, target_id, target_name)
            except ValueError:
                pass
    
    # Step 5: Merge older Abs and Cardio categories into 'Conditioning'
    conditioning_cat_id = cat_id_map.get('Conditioning')
    if conditioning_cat_id:
        for ex_name, ex_id in ex_id_map.items():
            if ex_cat_map.get(ex_name) in ['Cardio', 'Abs', 'Abs and Cardio']:
                db_bytes = operations.move_exercises(db_bytes, [ex_id], conditioning_cat_id)
    
    # Step 6: Move non-Jackked exercises to 'Other'
    other_cat_id = cat_id_map.get('Other')
    if other_cat_id:
        report = operations.generate_report(db_bytes)
        for cat in report['categories']:
            if cat['name'] in JACKKED_CATEGORIES or cat['name'] in ['Other', 'Cardio', 'Abs', 'Abs and Cardio']:
                continue
            
            for ex in cat['exercises']:
                if ex['name'] not in jackked_exercises:
                    db_bytes = operations.move_exercises(db_bytes, [ex['id']], other_cat_id)
    
    # Step 7: Delete empty categories
    report = operations.generate_report(db_bytes)
    for cat in report['categories']:
        # Skip Jackked categories and special categories
        if cat['name'] in JACKKED_CATEGORIES or cat['name'] == 'Other':
            continue
        
        # Delete if empty
        if len(cat['exercises']) == 0:
            try:
                db_bytes = operations.delete_category(db_bytes, cat['id'])
            except ValueError:
                pass  # Category has exercises with logs
    
    # Step 8: Insert missing Jackked exercises
    report = operations.generate_report(db_bytes)
    cat_id_map = {cat['name']: cat['id'] for cat in report['categories']}
    existing_exercises = set()
    for cat in report['categories']:
        for ex in cat['exercises']:
            existing_exercises.add(ex['name'])
    
    # Insert missing exercises from the canonical JACKKED_EXERCISES list
    for jackked_name, target_category in JACKKED_EXERCISES:
        if jackked_name in existing_exercises:
            continue
        
        if target_category in cat_id_map:
            try:
                db_bytes = operations.create_exercise(db_bytes, jackked_name, cat_id_map[target_category])
            except ValueError:
                pass  # Exercise already exists
    
    # Step 9: Update category visuals (colour and sort_order)
    report = operations.generate_report(db_bytes)
    for cat in report['categories']:
        cat_name = cat['name']
        cat_id = cat['id']
        
        if cat_name in CATEGORY_VISUALS:
            visuals = CATEGORY_VISUALS[cat_name]
            db_bytes = operations.update_category_visuals(db_bytes, cat_id, visuals['sort_order'], visuals['colour'])
        else:
            # Leave colour untouched, set sort_order to 11
            db_bytes = operations.update_category_visuals(db_bytes, cat_id, 11)
    
    return db_bytes
