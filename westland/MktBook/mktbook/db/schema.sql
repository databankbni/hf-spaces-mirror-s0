CREATE TABLE IF NOT EXISTS bots (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    student_name    TEXT    NOT NULL,
    bot_name        TEXT    NOT NULL,
    personality     TEXT    NOT NULL DEFAULT '',
    objective       TEXT    NOT NULL DEFAULT '',
    behavior_rules  TEXT    NOT NULL DEFAULT '',
    is_active       INTEGER NOT NULL DEFAULT 1,
    workout_id      INTEGER NOT NULL DEFAULT 1,
    created_at      TEXT    NOT NULL DEFAULT (datetime('now')),
    UNIQUE(bot_name, workout_id)
);

CREATE TABLE IF NOT EXISTS conversations (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    channel_id      TEXT,
    type            TEXT    NOT NULL DEFAULT 'bot-bot',  -- 'bot-bot' or 'bot-human'
    initiator_bot_id INTEGER REFERENCES bots(id),
    responder_bot_id INTEGER REFERENCES bots(id),
    turn_count      INTEGER NOT NULL DEFAULT 0,
    started_at      TEXT    NOT NULL DEFAULT (datetime('now')),
    ended_at        TEXT
);

CREATE TABLE IF NOT EXISTS messages (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id INTEGER REFERENCES conversations(id),
    bot_id          INTEGER REFERENCES bots(id),
    author_type     TEXT    NOT NULL DEFAULT 'bot',  -- 'bot' or 'human'
    author_name     TEXT    NOT NULL,
    content         TEXT    NOT NULL,
    image_url       TEXT,
    image_prompt    TEXT,
    created_at      TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS grades (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    bot_id          INTEGER NOT NULL REFERENCES bots(id),
    grading_run_id  TEXT    NOT NULL,
    objective_score REAL    NOT NULL DEFAULT 0,
    quality_score   REAL    NOT NULL DEFAULT 0,
    human_score     REAL    NOT NULL DEFAULT 0,
    volume_score    REAL    NOT NULL DEFAULT 0,
    overall_score   REAL    NOT NULL DEFAULT 0,
    llm_reasoning   TEXT    NOT NULL DEFAULT '',
    total_messages  INTEGER NOT NULL DEFAULT 0,
    total_conversations INTEGER NOT NULL DEFAULT 0,
    human_interactions  INTEGER NOT NULL DEFAULT 0,
    created_at      TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS conversation_pairs (
    bot_a_id        INTEGER NOT NULL REFERENCES bots(id),
    bot_b_id        INTEGER NOT NULL REFERENCES bots(id),
    conversation_count INTEGER NOT NULL DEFAULT 0,
    last_conversation_at TEXT,
    PRIMARY KEY (bot_a_id, bot_b_id)
);
