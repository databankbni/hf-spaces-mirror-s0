import sqlite3
from pathlib import Path
from datetime import datetime
import json

DB_PATH = Path("data/jovan_os.db")


def configure_database_path(path):
    global DB_PATH
    DB_PATH = Path(path)


def get_connection():
    DB_PATH.parent.mkdir(exist_ok=True)
    return sqlite3.connect(DB_PATH)

def add_column_if_not_exists(cursor, table_name, column_name, column_definition):
    cursor.execute(f"PRAGMA table_info({table_name})")
    columns = [row[1] for row in cursor.fetchall()]

    if column_name not in columns:
        cursor.execute(
            f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_definition}"
        )

def create_tables():
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS goals (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        domain TEXT NOT NULL,
        title TEXT NOT NULL,
        description TEXT,
        status TEXT DEFAULT 'active',
        priority TEXT DEFAULT 'medium',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS plans (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,
    summary TEXT,
    markdown TEXT,
    created_at TEXT NOT NULL
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS domain_weights (
        domain TEXT PRIMARY KEY,
        weight INTEGER NOT NULL,
        updated_at TEXT NOT NULL
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS weight_updates (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        domain TEXT NOT NULL,
        old_weight INTEGER,
        new_weight INTEGER NOT NULL,
        reason TEXT,
        created_at TEXT NOT NULL
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS daily_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT NOT NULL,
        formal TEXT,
        informal TEXT,
        sport TEXT,
        career TEXT,
        sleep_hours REAL,
        energy INTEGER,
        notes TEXT,
        created_at TEXT NOT NULL
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS evaluations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        period_type TEXT NOT NULL,
        period_label TEXT NOT NULL,
        score REAL,
        feedback TEXT,
        next_actions TEXT,
        created_at TEXT NOT NULL
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS optimizations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        summary TEXT,
        markdown TEXT NOT NULL,
        weight_recommendations_json TEXT,
        goal_recommendations_json TEXT,
        created_at TEXT NOT NULL
    )
    """)

    add_column_if_not_exists(
        cur,
        "optimizations",
        "weight_recommendations_json",
        "TEXT"
    )

    add_column_if_not_exists(
        cur,
        "optimizations",
        "goal_recommendations_json",
        "TEXT"
    )

    conn.commit()
    conn.close()


def add_goal(domain, title, description="", priority="medium"):
    now = datetime.now().isoformat(timespec="seconds")
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
    INSERT INTO goals (domain, title, description, priority, created_at, updated_at)
    VALUES (?, ?, ?, ?, ?, ?)
    """, (domain, title, description, priority, now, now))
    conn.commit()
    conn.close()


def get_goals():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
    SELECT id, domain, title, description, status, priority
    FROM goals
    ORDER BY domain, id
    """)
    rows = cur.fetchall()
    conn.close()
    return rows


def set_domain_weight(domain, weight, reason=""):
    now = datetime.now().isoformat(timespec="seconds")
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("SELECT weight FROM domain_weights WHERE domain = ?", (domain,))
    row = cur.fetchone()
    old_weight = row[0] if row else None

    cur.execute("""
    INSERT INTO domain_weights (domain, weight, updated_at)
    VALUES (?, ?, ?)
    ON CONFLICT(domain) DO UPDATE SET
        weight = excluded.weight,
        updated_at = excluded.updated_at
    """, (domain, weight, now))

    cur.execute("""
    INSERT INTO weight_updates (domain, old_weight, new_weight, reason, created_at)
    VALUES (?, ?, ?, ?, ?)
    """, (domain, old_weight, weight, reason, now))

    conn.commit()
    conn.close()


def get_domain_weights():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
    SELECT domain, weight
    FROM domain_weights
    ORDER BY domain
    """)
    rows = cur.fetchall()
    conn.close()
    return rows


def add_daily_log(date, formal="", informal="", sport="", career="", sleep_hours=None, energy=None, notes=""):
    now = datetime.now().isoformat(timespec="seconds")
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
    INSERT INTO daily_logs (date, formal, informal, sport, career, sleep_hours, energy, notes, created_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (date, formal, informal, sport, career, sleep_hours, energy, notes, now))
    conn.commit()
    conn.close()


def get_recent_logs(limit=7):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
    SELECT date, formal, informal, sport, career, sleep_hours, energy, notes
    FROM daily_logs
    ORDER BY date DESC, id DESC
    LIMIT ?
    """, (limit,))
    rows = cur.fetchall()
    conn.close()
    return rows

def update_goal(goal_id, title=None, description=None, status=None, priority=None, reason=""):
    now = datetime.now().isoformat(timespec="seconds")
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
    SELECT title, description, status, priority
    FROM goals
    WHERE id = ?
    """, (goal_id,))
    old = cur.fetchone()

    if not old:
        conn.close()
        raise ValueError(f"Goal with id {goal_id} not found")

    old_title, old_description, old_status, old_priority = old

    new_title = title if title is not None else old_title
    new_description = description if description is not None else old_description
    new_status = status if status is not None else old_status
    new_priority = priority if priority is not None else old_priority

    cur.execute("""
    UPDATE goals
    SET title = ?, description = ?, status = ?, priority = ?, updated_at = ?
    WHERE id = ?
    """, (new_title, new_description, new_status, new_priority, now, goal_id))

    cur.execute("""
    CREATE TABLE IF NOT EXISTS goal_updates (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        goal_id INTEGER NOT NULL,
        old_title TEXT,
        new_title TEXT,
        old_description TEXT,
        new_description TEXT,
        old_status TEXT,
        new_status TEXT,
        old_priority TEXT,
        new_priority TEXT,
        reason TEXT,
        created_at TEXT NOT NULL
    )
    """)

    cur.execute("""
    INSERT INTO goal_updates (
        goal_id,
        old_title, new_title,
        old_description, new_description,
        old_status, new_status,
        old_priority, new_priority,
        reason,
        created_at
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        goal_id,
        old_title, new_title,
        old_description, new_description,
        old_status, new_status,
        old_priority, new_priority,
        reason,
        now
    ))

    conn.commit()
    conn.close()


def get_goal_history(goal_id):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
    SELECT created_at, old_title, new_title, old_description, new_description,
           old_status, new_status, old_priority, new_priority, reason
    FROM goal_updates
    WHERE goal_id = ?
    ORDER BY created_at DESC
    """, (goal_id,))
    rows = cur.fetchall()
    conn.close()
    return rows

def change_domain_weights(new_weights: dict, reason=""):
    total = sum(new_weights.values())
    if total != 100:
        raise ValueError(f"Domain weights must sum to 100. Current sum: {total}")

    now = datetime.now().isoformat(timespec="seconds")
    conn = get_connection()
    cur = conn.cursor()

    for domain, new_weight in new_weights.items():
        cur.execute("SELECT weight FROM domain_weights WHERE domain = ?", (domain,))
        row = cur.fetchone()
        old_weight = row[0] if row else None

        cur.execute("""
        INSERT INTO domain_weights (domain, weight, updated_at)
        VALUES (?, ?, ?)
        ON CONFLICT(domain) DO UPDATE SET
            weight = excluded.weight,
            updated_at = excluded.updated_at
        """, (domain, new_weight, now))

        cur.execute("""
        INSERT INTO weight_updates (domain, old_weight, new_weight, reason, created_at)
        VALUES (?, ?, ?, ?, ?)
        """, (domain, old_weight, new_weight, reason, now))

    conn.commit()
    conn.close()


def get_weight_history(limit=20):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
    SELECT created_at, domain, old_weight, new_weight, reason
    FROM weight_updates
    ORDER BY created_at DESC
    LIMIT ?
    """, (limit,))
    rows = cur.fetchall()
    conn.close()
    return rows

def save_evaluation(period_type, period_label, score, feedback, next_actions=""):
    now = datetime.now().isoformat(timespec="seconds")
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
    INSERT INTO evaluations (period_type, period_label, score, feedback, next_actions, created_at)
    VALUES (?, ?, ?, ?, ?, ?)
    """, (period_type, period_label, score, feedback, next_actions, now))

    conn.commit()
    conn.close()


def get_recent_evaluations(limit=10):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
    SELECT period_type, period_label, score, feedback, next_actions, created_at
    FROM evaluations
    ORDER BY created_at DESC
    LIMIT ?
    """, (limit,))

    rows = cur.fetchall()
    conn.close()
    return rows


def export_latest_evaluation_to_md(path="reports/latest_evaluation.md"):
    rows = get_recent_evaluations(limit=1)
    if not rows:
        return None

    period_type, period_label, score, feedback, next_actions, created_at = rows[0]

    output = f"""# Jovan OS Evaluation

**Period:** {period_type}  
**Label:** {period_label}  
**Score:** {score}/10  
**Created:** {created_at}

---

{feedback}

---

## Saved Next Actions

{next_actions}
"""

    path = Path(path)
    path.parent.mkdir(exist_ok=True)
    path.write_text(output, encoding="utf-8")
    return str(path)

def save_plan(date, summary, markdown):
    now = datetime.now().isoformat(timespec="seconds")
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
    INSERT INTO plans (date, summary, markdown, created_at)
    VALUES (?, ?, ?, ?)
    """, (date, summary, markdown, now))

    conn.commit()
    conn.close()


def get_recent_plans(limit=10):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
    SELECT date, summary, markdown, created_at
    FROM plans
    ORDER BY created_at DESC
    LIMIT ?
    """, (limit,))

    rows = cur.fetchall()
    conn.close()
    return rows


def export_latest_plan_to_md(path="reports/latest_plan.md"):
    from pathlib import Path

    rows = get_recent_plans(limit=1)
    if not rows:
        return None

    date, summary, markdown, created_at = rows[0]

    output = f"""# Jovan OS Plan

**Date:** {date}  
**Created:** {created_at}

---

{markdown}
"""

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(output, encoding="utf-8")
    return str(path)

def get_goal_summary(log_limit=14, evaluation_limit=10):
    return {
        "active_goals": get_goals(),
        "domain_weights": get_domain_weights(),
        "recent_logs": get_recent_logs(limit=log_limit),
        "recent_evaluations": get_recent_evaluations(limit=evaluation_limit),
    }

def apply_weight_recommendations(weight_recommendations, reason="Approved optimizer recommendation"):
    new_weights = {}

    current = dict(get_domain_weights())

    for domain, current_weight in current.items():
        new_weights[domain] = current_weight

    for rec in weight_recommendations:
        new_weights[rec.domain] = rec.proposed_weight

    change_domain_weights(new_weights, reason=reason)
    return new_weights

def apply_latest_optimization_weights(reason="Approved latest optimizer weight recommendations"):
    import json

    latest = get_latest_optimization()

    if not latest:
        return None, "No optimization report found."

    weight_json = latest[3]

    if not weight_json:
        return None, "Latest optimization has no weight recommendations."

    weight_recommendations = json.loads(weight_json)

    if not weight_recommendations:
        return None, "Latest optimization weight recommendations are empty."

    current_weights = dict(get_domain_weights())

    new_weights = dict(current_weights)

    for rec in weight_recommendations:
        domain = rec["domain"]
        proposed_weight = rec["proposed_weight"]
        new_weights[domain] = proposed_weight

    total = sum(new_weights.values())

    if total != 100:
        return None, f"Cannot apply weights. Proposed total is {total}, not 100."

    change_domain_weights(
        new_weights,
        reason=reason,
    )

    return new_weights, "Latest optimizer weight recommendations applied successfully."

def get_latest_evaluation():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT period_type, period_label, score, feedback, next_actions, created_at
        FROM evaluations
        ORDER BY created_at DESC
        LIMIT 1
    """)

    row = cursor.fetchone()
    conn.close()
    return row

def save_optimization(
    summary,
    markdown,
    weight_recommendations=None,
    goal_recommendations=None,
):
    now = datetime.now().isoformat(timespec="seconds")
    conn = get_connection()
    cursor = conn.cursor()

    weight_json = json.dumps(weight_recommendations or [], ensure_ascii=False)
    goal_json = json.dumps(goal_recommendations or [], ensure_ascii=False)

    cursor.execute("""
        INSERT INTO optimizations (
            summary,
            markdown,
            weight_recommendations_json,
            goal_recommendations_json,
            created_at
        )
        VALUES (?, ?, ?, ?, ?)
    """, (summary, markdown, weight_json, goal_json, now))

    conn.commit()
    conn.close()


def get_recent_optimizations(limit=10):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id, summary, markdown, created_at
        FROM optimizations
        ORDER BY created_at DESC
        LIMIT ?
    """, (limit,))

    rows = cursor.fetchall()
    conn.close()
    return rows


def get_latest_optimization():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            id,
            summary,
            markdown,
            weight_recommendations_json,
            goal_recommendations_json,
            created_at
        FROM optimizations
        ORDER BY created_at DESC
        LIMIT 1
    """)

    row = cursor.fetchone()
    conn.close()
    return row


def export_latest_optimization_to_md(path="reports/latest_optimization.md"):
    latest = get_latest_optimization()

    if not latest:
        return None

    _, summary, markdown, weight_json, goal_json, created_at = latest

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(markdown, encoding="utf-8")

    return str(path)





