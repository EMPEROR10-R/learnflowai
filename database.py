# database.py — FINAL SAFE VERSION (NO # COMMENTS IN SQL)
def _create_tables(self):
    self.conn.executescript("""
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE,
        email TEXT UNIQUE NOT NULL,
        password_hash BLOB NOT NULL,
        role TEXT DEFAULT 'user',
        is_banned INTEGER DEFAULT 0,
        is_premium INTEGER DEFAULT 0,
        premium_expiry TEXT,
        total_xp INTEGER DEFAULT 0,
        spendable_xp INTEGER DEFAULT 0,
        xp INTEGER DEFAULT 0,
        xp_coins INTEGER DEFAULT 0,
        discount INTEGER DEFAULT 0,
        discount_20 INTEGER DEFAULT 0,
        discount_buy_count INTEGER DEFAULT 0,
        level INTEGER DEFAULT 1,
        name TEXT,
        badges TEXT DEFAULT '[]',
        streak INTEGER DEFAULT 0,
        last_active TEXT,
        last_streak_date TEXT,
        daily_questions INTEGER DEFAULT 0,
        daily_pdfs INTEGER DEFAULT 0,
        daily_exams INTEGER DEFAULT 0,
        last_daily_reset TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS user_2fa (
        user_id INTEGER PRIMARY KEY,
        secret TEXT NOT NULL,
        enabled INTEGER DEFAULT 1,
        FOREIGN KEY (user_id) REFERENCES users (user_id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS chat_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        subject TEXT,
        user_query TEXT,
        ai_response TEXT,
        timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users (user_id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS scores (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        category TEXT,
        score REAL,
        timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users (user_id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS exam_scores (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        exam_type TEXT,
        subject TEXT,
        score REAL,
        total_questions INTEGER,
        timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users (user_id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS payments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        phone TEXT,
        mpesa_code TEXT,
        status TEXT DEFAULT 'pending',
        timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users (user_id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS projects (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        subject TEXT,
        project_name TEXT,
        submission TEXT,
        grade REAL,
        xp_awarded INTEGER DEFAULT 0,
        timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users (user_id) ON DELETE CASCADE
    );
    """)
    self.conn.commit()
