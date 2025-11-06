# database.py
import sqlite3
import json
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Any
import uuid
import bcrypt

class Database:
    def __init__(self, db_path: str = "users.db"):
        self.db_path = db_path
        self.init_database()
        self.migrate_schema()          # <-- NEW: fixes missing columns

    # ------------------------------------------------------------------ #
    # Connection helper
    # ------------------------------------------------------------------ #
    def get_connection(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    # ------------------------------------------------------------------ #
    # Table creation (run once on first start)
    # ------------------------------------------------------------------ #
    def init_database(self):
        conn = self.get_connection()
        cursor = conn.cursor()

        # ---- users ---------------------------------------------------- #
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id TEXT PRIMARY KEY,
                email TEXT UNIQUE,
                password_hash TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_active TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                total_queries INTEGER DEFAULT 0,
                streak_days INTEGER DEFAULT 0,
                last_streak_date DATE,
                badges TEXT DEFAULT '[]',
                is_premium BOOLEAN DEFAULT 0,
                premium_expires_at TIMESTAMP,
                language_preference TEXT DEFAULT 'en',
                learning_goals TEXT DEFAULT '[]'
            )
        """)

        # ---- documents ------------------------------------------------ #
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS documents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT,
                filename TEXT NOT NULL,
                content_text TEXT,
                upload_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
        """)

        # ---- chat_history (ALL columns from the start) -------------- #
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS chat_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                role TEXT,           -- user / assistant
                content TEXT,        -- the actual message
                session_id TEXT,
                subject TEXT,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
        """)

        # ---- essays -------------------------------------------------- #
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS essays (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT,
                submission_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                title TEXT,
                content TEXT,
                grade_json TEXT,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
        """)

        # ---- exam_results -------------------------------------------- #
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS exam_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT,
                exam_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                subject TEXT,
                exam_type TEXT,
                score INTEGER,
                total_questions INTEGER,
                completed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
        """)

        conn.commit()
        conn.close()

    # ------------------------------------------------------------------ #
    # Migration – adds any missing columns to an existing DB
    # ------------------------------------------------------------------ #
    def migrate_schema(self):
        """Add missing columns (content, role, session_id, subject, …) if they are not present."""
        conn = self.get_connection()
        cursor = conn.cursor()

        def add_column(table: str, column: str, definition: str):
            cursor.execute(f"PRAGMA table_info({table})")
            existing = {row[1] for row in cursor.fetchall()}
            if column not in existing:
                cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

        # chat_history – the columns that caused the error
        add_column("chat_history", "role", "TEXT")
        add_column("chat_history", "content", "TEXT")
        add_column("chat_history", "session_id", "TEXT")
        add_column("chat_history", "subject", "TEXT")

        # (optional) any other tables you might add later
        # add_column("documents", "content_text", "TEXT")

        conn.commit()
        conn.close()

    # ------------------------------------------------------------------ #
    # USER AUTH
    # ------------------------------------------------------------------ #
    def get_user_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE email = ?", (email,))
        row = cursor.fetchone()
        conn.close()
        return dict(row) if row else None

    def create_user(self, email: str = None, password: str = None) -> str:
        user_id = str(uuid.uuid4())
        hashed = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8') if password else None

        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO users 
            (user_id, email, password_hash, is_premium, premium_expires_at)
            VALUES (?, ?, ?, 0, NULL)
        """, (user_id, email, hashed))
        conn.commit()
        conn.close()
        return user_id

    def login_user(self, email: str, password: str) -> Optional[str]:
        user = self.get_user_by_email(email)
        if not user or not user.get('password_hash'):
            return None
        if bcrypt.checkpw(password.encode('utf-8'), user['password_hash'].encode('utf-8')):
            return user['user_id']
        return None

    def get_user(self, user_id: str) -> Optional[Dict[str, Any]]:
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        conn.close()
        return dict(row) if row else None

    # ------------------------------------------------------------------ #
    # STREAK & BADGES
    # ------------------------------------------------------------------ #
    def update_streak(self, user_id: str) -> int:
        conn = self.get_connection()
        cursor = conn.cursor()
        today = datetime.now().date()
        yesterday = today - timedelta(days=1)

        cursor.execute("SELECT last_streak_date, streak_days FROM users WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        last_date = row['last_streak_date']
        streak = row['streak_days'] or 0

        if last_date == str(today):
            conn.close()
            return streak
        elif last_date == str(yesterday):
            streak += 1
        else:
            streak = 1

        cursor.execute("""
            UPDATE users SET streak_days = ?, last_streak_date = ?, last_active = CURRENT_TIMESTAMP
            WHERE user_id = ?
        """, (streak, str(today), user_id))
        conn.commit()
        conn.close()
        return streak

    def add_badge(self, user_id: str, badge: str):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT badges FROM users WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        badges = json.loads(row['badges']) if row and row['badges'] else []
        if badge not in badges:
            badges.append(badge)
            cursor.execute("UPDATE users SET badges = ? WHERE user_id = ?", (json.dumps(badges), user_id))
        conn.commit()
        conn.close()

    # ------------------------------------------------------------------ #
    # LIMITS & PREMIUM
    # ------------------------------------------------------------------ #
    def check_premium(self, user_id: str) -> bool:
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT is_premium FROM users WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        conn.close()
        return bool(row['is_premium']) if row else False

    def get_daily_query_count(self, user_id: str) -> int:
        conn = self.get_connection()
        cursor = conn.cursor()
        today = datetime.now().date()
        cursor.execute("""
            SELECT COUNT(*) FROM chat_history 
            WHERE user_id = ? AND role = 'user' AND DATE(timestamp) = ?
        """, (user_id, str(today)))
        count = cursor.fetchone()[0]
        conn.close()
        return count

    def get_pdf_count_today(self, user_id: str) -> int:
        conn = self.get_connection()
        cursor = conn.cursor()
        today = datetime.now().date()
        cursor.execute("""
            SELECT COUNT(*) FROM documents 
            WHERE user_id = ? AND DATE(upload_date) = ?
        """, (user_id, str(today)))
        count = cursor.fetchone()[0]
        conn.close()
        return count

    def add_pdf_upload(self, user_id: str, filename: str):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO documents (user_id, filename) VALUES (?, ?)
        """, (user_id, filename))
        conn.commit()
        conn.close()

    # ------------------------------------------------------------------ #
    # CHAT HISTORY (now safe – columns always exist)
    # ------------------------------------------------------------------ #
    def add_chat_history(self, user_id: str, subject: str, user_msg: str, ai_msg: str):
        conn = self.get_connection()
        cursor = conn.cursor()
        session_id = str(uuid.uuid4())

        cursor.execute("""
            INSERT INTO chat_history (user_id, role, content, session_id, subject)
            VALUES (?, 'user', ?, ?, ?)
        """, (user_id, user_msg, session_id, subject))

        cursor.execute("""
            INSERT INTO chat_history (user_id, role, content, session_id, subject)
            VALUES (?, 'assistant', ?, ?, ?)
        """, (user_id, ai_msg, session_id, subject))

        cursor.execute("UPDATE users SET total_queries = total_queries + 1 WHERE user_id = ?", (user_id,))
        conn.commit()
        conn.close()

    def update_user_activity(self, user_id: str):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET last_active = CURRENT_TIMESTAMP WHERE user_id = ?", (user_id,))
        conn.commit()
        conn.close()

    # ------------------------------------------------------------------ #
    # PLACEHOLDERS (kept for compatibility)
    # ------------------------------------------------------------------ #
    def get_progress_stats(self, user_id: str):
        return []  # placeholder

    def get_quiz_history(self, user_id: str):
        return []  # placeholder

    def add_quiz_result(self, user_id: str, subject: str, exam_type: str, score: int, total: int):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO exam_results (user_id, subject, exam_type, score, total_questions)
            VALUES (?, ?, ?, ?, ?)
        """, (user_id, subject, exam_type, score, total))
        conn.commit()
        conn.close()
