import sqlite3
import typing

def _apply_ops(db_bytes: bytes, op_func: typing.Callable[[sqlite3.Connection], None]) -> bytes:
    """Helper to apply operations on a DB in memory."""
    con = sqlite3.connect(":memory:")
    con.deserialize(db_bytes)
    con.execute("PRAGMA foreign_keys = ON")
    
    op_func(con)
    
    con.commit()
    return con.serialize()

def generate_report(db_bytes: bytes) -> dict:
    """Returns: { categories: [{ id, name, exercises: [{ id, name, log_count }] }] }"""
    con = sqlite3.connect(":memory:")
    con.deserialize(db_bytes)
    
    categories = []
    
    # Get categories
    cat_rows = con.execute("SELECT _id, name FROM Category ORDER BY sort_order, name").fetchall()
    
    for c_id, c_name in cat_rows:
        exercises = []
        # Get exercises and their log counts
        ex_rows = con.execute("""
            SELECT e._id, e.name, COUNT(l._id) 
            FROM exercise e
            LEFT JOIN training_log l ON e._id = l.exercise_id
            WHERE e.category_id = ?
            GROUP BY e._id
            ORDER BY e.name
        """, (c_id,)).fetchall()
        
        for e_id, e_name, l_count in ex_rows:
            exercises.append({
                "id": e_id,
                "name": e_name,
                "log_count": l_count
            })
            
        categories.append({
            "id": c_id,
            "name": c_name,
            "exercises": exercises
        })
        
    return {"categories": categories}

def name_exists(db_bytes: bytes, name: str) -> bool:
    """Checks if a name exists in either Category or exercise tables."""
    con = sqlite3.connect(":memory:")
    con.deserialize(db_bytes)
    
    res = con.execute("SELECT 1 FROM Category WHERE name = ?", (name,)).fetchone()
    if res:
        return True
    
    res = con.execute("SELECT 1 FROM exercise WHERE name = ?", (name,)).fetchone()
    return True if res else False

def create_category(db_bytes: bytes, name: str) -> bytes:
    def op(con):
        if name_exists_internal(con, name):
            raise ValueError(f"Name '{name}' already exists in categories or exercises.")
        con.execute("INSERT INTO Category (name) VALUES (?)", (name,))
    return _apply_ops(db_bytes, op)

def rename_category(db_bytes: bytes, category_id: int, new_name: str) -> bytes:
    def op(con):
        if name_exists_internal(con, new_name):
            raise ValueError(f"Name '{new_name}' already exists in categories or exercises.")
        con.execute("UPDATE Category SET name = ? WHERE _id = ?", (new_name, category_id))
    return _apply_ops(db_bytes, op)

def delete_category(db_bytes: bytes, category_id: int) -> bytes:
    def op(con):
        # Check if any exercise under this category has logs
        res = con.execute("""
            SELECT 1 FROM training_log l
            JOIN exercise e ON l.exercise_id = e._id
            WHERE e.category_id = ?
            LIMIT 1
        """, (category_id,)).fetchone()
        
        if res:
            raise ValueError("Cannot delete category: Contains exercises with logs.")
            
        # Delete exercises first (cascade-like)
        con.execute("DELETE FROM exercise WHERE category_id = ?", (category_id,))
        # Delete category
        con.execute("DELETE FROM Category WHERE _id = ?", (category_id,))
    return _apply_ops(db_bytes, op)

def rename_exercise(db_bytes: bytes, exercise_id: int, new_name: str) -> bytes:
    def op(con):
        if name_exists_internal(con, new_name):
            raise ValueError(f"Name '{new_name}' already exists in categories or exercises.")
        con.execute("UPDATE exercise SET name = ? WHERE _id = ?", (new_name, exercise_id))
    return _apply_ops(db_bytes, op)

def move_exercises(db_bytes: bytes, exercise_ids: list[int], target_category_id: int) -> bytes:
    def op(con):
        placeholders = ",".join("?" * len(exercise_ids))
        con.execute(f"UPDATE exercise SET category_id = ? WHERE _id IN ({placeholders})", 
                    [target_category_id] + exercise_ids)
    return _apply_ops(db_bytes, op)

def delete_exercise(db_bytes: bytes, exercise_id: int) -> bytes:
    def op(con):
        # Block if logs exist
        res = con.execute("SELECT 1 FROM training_log WHERE exercise_id = ? LIMIT 1", (exercise_id,)).fetchone()
        if res:
            raise ValueError("Cannot delete exercise: It has existing logs.")
            
        # Cleanup fluff as requested
        con.execute("DELETE FROM RoutineSectionExercise WHERE exercise_id = ?", (exercise_id,))
        con.execute("DELETE FROM WorkoutGroupExercise WHERE exercise_id = ?", (exercise_id,))
        con.execute("DELETE FROM exercise WHERE _id = ?", (exercise_id,))
    return _apply_ops(db_bytes, op)

def merge_exercises(db_bytes: bytes, source_ids: list[int], target_id: int) -> bytes:
    def op(con):
        if target_id not in source_ids:
            raise ValueError("Target exercise must be part of the source list.")
            
        other_ids = [sid for sid in source_ids if sid != target_id]
        if not other_ids:
            return  # Nothing to merge
            
        placeholders = ",".join("?" * len(other_ids))
        
        # 1. Update identifying tables
        tables = ["training_log", "RoutineSectionExercise", "WorkoutGroupExercise", 
                  "ExerciseGraphFavourite", "Goal", "Barbell"]
        
        for table in tables:
            con.execute(f"UPDATE {table} SET exercise_id = ? WHERE exercise_id IN ({placeholders})",
                        [target_id] + other_ids)
                        
        # 2. Update RepMaxGridFavourite (CSV column)
        rows = con.execute("SELECT _id, exercise_ids FROM RepMaxGridFavourite").fetchall()
        for row_id, ex_csv in rows:
            ids = [id_str.strip() for id_str in ex_csv.split(",") if id_str.strip()]
            new_ids = []
            changed = False
            for tid in ids:
                try:
                    tid_int = int(tid)
                    if tid_int in other_ids:
                        new_ids.append(str(target_id))
                        changed = True
                    else:
                        new_ids.append(tid)
                except ValueError:
                    new_ids.append(tid)
            
            if changed:
                # Dedupe while preserving order
                unique_ids = []
                seen = set()
                for uid in new_ids:
                    if uid not in seen:
                        unique_ids.append(uid)
                        seen.add(uid)
                con.execute("UPDATE RepMaxGridFavourite SET exercise_ids = ? WHERE _id = ?",
                            (",".join(unique_ids), row_id))

        # 3. Delete source exercises
        con.execute(f"DELETE FROM exercise WHERE _id IN ({placeholders})", other_ids)
        
    return _apply_ops(db_bytes, op)

def name_exists_internal(con: sqlite3.Connection, name: str) -> bool:
    """Internal helper to check name existence within an active connection."""
    res = con.execute("SELECT 1 FROM Category WHERE name = ?", (name,)).fetchone()
    if res:
        return True
    res = con.execute("SELECT 1 FROM exercise WHERE name = ?", (name,)).fetchone()
    return True if res else False

def create_exercise(db_bytes: bytes, name: str, category_id: int) -> bytes:
    """Creates a new exercise in the specified category."""
    def op(con):
        if name_exists_internal(con, name):
            raise ValueError(f"Name '{name}' already exists in categories or exercises.")
        con.execute("INSERT INTO exercise (name, category_id) VALUES (?, ?)", (name, category_id))
    return _apply_ops(db_bytes, op)

def get_exercise_id_by_name(db_bytes: bytes, name: str) -> int | None:
    """Returns the exercise ID for a given name, or None if not found."""
    con = sqlite3.connect(":memory:")
    con.deserialize(db_bytes)
    res = con.execute("SELECT _id FROM exercise WHERE name = ?", (name,)).fetchone()
    return res[0] if res else None

def update_category_visuals(db_bytes: bytes, category_id: int, sort_order: int, colour: typing.Optional[int] = None) -> bytes:
    """Updates the sort_order and optionally the colour of a category."""
    def op(con):
        if colour is not None:
            con.execute("UPDATE Category SET sort_order = ?, colour = ? WHERE _id = ?", (sort_order, colour, category_id))
        else:
            con.execute("UPDATE Category SET sort_order = ? WHERE _id = ?", (sort_order, category_id))
    return _apply_ops(db_bytes, op)
