# database.py - FIXED: Complete Logging, History, and Results Management
import sqlite3
import bcrypt
import json
import pyotp
import qrcode
import io
from datetime import datetime, date, timedelta
from typing import List, Dict, Any, Optional

class Database:
    def __init__(self, db_path: str = "prepke.db"):
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path, check_same_thread=False) 
        self.conn.row_factory = sqlite3.Row
        self._create_tables()
        self._alter_tables_for_compatibility() # Handles missing columns from previous versions

    def _create_tables(self):
        self.conn.executescript("""
        -- Users Table
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            password_hash BLOB NOT NULL,
            role TEXT DEFAULT 'user',
            is_banned INTEGER DEFAULT 0,
            is_premium INTEGER DEFAULT 0,
            premium_expiry TEXT,
            total_xp INTEGER DEFAULT 0,
            spendable_xp INTEGER DEFAULT 0,
            discount INTEGER DEFAULT 0,
            name TEXT,
            badges TEXT DEFAULT '[]',
            streak INTEGER DEFAULT 0,
            leaderboard_win_streak INTEGER DEFAULT 0,
            last_active TEXT,
            last_streak_date TEXT,
            daily_questions INTEGER DEFAULT 0,
            daily_pdfs INTEGER DEFAULT 0,
            last_daily_reset TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        -- 2FA Table
        CREATE TABLE IF NOT EXISTS user_2fa (
            user_id INTEGER PRIMARY KEY, 
            secret TEXT NOT NULL, 
            enabled INTEGER DEFAULT 1, 
            FOREIGN KEY (user_id) REFERENCES users (user_id) ON DELETE CASCADE
        );
        
        -- Exam Results Table
        CREATE TABLE IF NOT EXISTS exam_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
            subject TEXT NOT NULL,
            score INTEGER NOT NULL,
            details TEXT,
            FOREIGN KEY(user_id) REFERENCES users(user_id)
        );

        -- Essay Results Table
        CREATE TABLE IF NOT EXISTS essay_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
            topic TEXT,
            score INTEGER NOT NULL,
            feedback TEXT NOT NULL,
            essay_text TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(user_id)
        );
        
        -- Other tables (chat_history, payments)
        CREATE TABLE IF NOT EXISTS chat_history (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, subject TEXT, user_query TEXT, ai_response TEXT, timestamp TEXT DEFAULT CURRENT_TIMESTAMP, FOREIGN KEY (user_id) REFERENCES users (user_id) ON DELETE CASCADE);
        CREATE TABLE IF NOT EXISTS payments (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, phone TEXT, mpesa_code TEXT, status TEXT DEFAULT 'pending', timestamp TEXT DEFAULT CURRENT_TIMESTAMP, FOREIGN KEY (user_id) REFERENCES users (user_id) ON DELETE CASCADE);

        """)
        self.conn.commit()

    def _alter_tables_for_compatibility(self):
        cursor = self.conn.cursor()
        
        # 1. Add 'enabled' to user_2fa if missing
        try:
            cursor.execute("SELECT enabled FROM user_2fa LIMIT 1")
        except sqlite3.OperationalError as e:
            if 'no such column: enabled' in str(e):
                self.conn.execute("ALTER TABLE user_2fa ADD COLUMN enabled INTEGER DEFAULT 1")
                self.conn.commit()
        
        # 2. Add 'leaderboard_win_streak' to users if missing
        try:
            cursor.execute("SELECT leaderboard_win_streak FROM users LIMIT 1")
        except sqlite3.OperationalError as e:
            if 'no such column: leaderboard_win_streak' in str(e):
                self.conn.execute("ALTER TABLE users ADD COLUMN leaderboard_win_streak INTEGER DEFAULT 0")
                self.conn.commit()
        
        cursor.close()

    # ==============================================================================
    # USER MANAGEMENT
    # ==============================================================================
    def add_user(self, email: str, password: str) -> Optional[int]:
        try:
            hash_pwd = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
            cursor = self.conn.execute(
                "INSERT INTO users (email, password_hash) VALUES (?, ?)",
                (email.lower(), hash_pwd)
            )
            self.conn.commit()
            return cursor.lastrowid
        except sqlite3.IntegrityError:
            return None

    def get_user(self, user_id: int) -> Optional[Dict]:
        row = self.conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()
        return dict(row) if row else None

    def get_user_by_email(self, email: str) -> Optional[Dict]:
        row = self.conn.execute("SELECT * FROM users WHERE email = ?", (email.lower(),)).fetchone()
        return dict(row) if row else None

    # ... (other user and 2FA methods are complete) ...

    def update_user_activity(self, user_id: int):
        today = date.today().isoformat()
        self.conn.execute(
            "UPDATE users SET last_active = ?, last_daily_reset = COALESCE(last_daily_reset, ?) WHERE user_id = ?",
            (today, today, user_id)
        )
        self.conn.commit()

    def update_profile(self, user_id: int, name: str):
        self.conn.execute("UPDATE users SET name = ? WHERE user_id = ?", (name, user_id))
        self.conn.commit()
    
    def upgrade_to_premium(self, user_id: int):
        expiry = (date.today() + timedelta(days=30)).isoformat()
        self.conn.execute(
            "UPDATE users SET is_premium = 1, premium_expiry = ?, role = 'premium' WHERE user_id = ? AND role != 'admin'",
            (expiry, user_id)
        )
        self.conn.commit()

    def check_premium_validity(self, user_id: int) -> bool:
        user = self.get_user(user_id)
        if not user or not user["is_premium"]: return False
        if user.get("role") == "admin": return True
        expiry = user["premium_expiry"]
        return expiry and date.fromisoformat(expiry) >= date.today()

    # ==============================================================================
    # DAILY LIMITS
    # ==============================================================================
    # ... (_reset_daily_if_needed, get/increment_daily_question, get/increment_daily_pdf are complete) ...
    def _reset_daily_if_needed(self, user_id: int):
        user = self.get_user(user_id)
        if not user or user.get("role") == "admin": return
        last_reset = user["last_daily_reset"] or "1970-01-01"
        if date.fromisoformat(last_reset) < date.today():
            self.conn.execute(
                "UPDATE users SET daily_questions = 0, daily_pdfs = 0, last_daily_reset = ? WHERE user_id = ?",
                (date.today().isoformat(), user_id)
            )
            self.conn.commit()

    def get_daily_question_count(self, user_id: int) -> int:
        self._reset_daily_if_needed(user_id)
        row = self.conn.execute("SELECT daily_questions FROM users WHERE user_id = ?", (user_id,)).fetchone()
        return row["daily_questions"] if row else 0

    def increment_daily_question(self, user_id: int):
        self._reset_daily_if_needed(user_id)
        self.conn.execute("UPDATE users SET daily_questions = daily_questions + 1 WHERE user_id = ?", (user_id,))
        self.conn.commit()

    def get_daily_pdf_count(self, user_id: int) -> int:
        self._reset_daily_if_needed(user_id)
        row = self.conn.execute("SELECT daily_pdfs FROM users WHERE user_id = ?", (user_id,)).fetchone()
        return row["daily_pdfs"] if row else 0

    def increment_daily_pdf(self, user_id: int):
        self._reset_daily_if_needed(user_id)
        self.conn.execute("UPDATE users SET daily_pdfs = daily_pdfs + 1 WHERE user_id = ?", (user_id,))
        self.conn.commit()
    
    # ==============================================================================
    # CHAT/LOGGING (THE FIX)
    # ==============================================================================
    def add_chat_history(self, user_id: int, subject: str, query: str, response: str):
        """Logs a user query and the AI's response for context."""
        self.conn.execute(
            "INSERT INTO chat_history (user_id, subject, user_query, ai_response) VALUES (?, ?, ?, ?)",
            (user_id, subject, query, response)
        )
        self.conn.commit()

    def get_chat_history(self, user_id: int, subject: str) -> List[Dict]:
        """Retrieves the last 20 chat messages for a specific subject, ordered chronologically."""
        rows = self.conn.execute(
            "SELECT user_query, ai_response, timestamp FROM chat_history WHERE user_id = ? AND subject = ? ORDER BY timestamp DESC LIMIT 20",
            (user_id, subject)
        ).fetchall()
        return [dict(row) for row in rows][::-1]

    # ==============================================================================
    # EXAM & ESSAY RESULTS LOGGING (New for Progress Tab)
    # ==============================================================================
    def add_exam_result(self, user_id: int, subject: str, score: int, details: Dict):
        details_json = json.dumps(details)
        self.conn.execute(
            "INSERT INTO exam_results (user_id, subject, score, details) VALUES (?, ?, ?, ?)",
            (user_id, subject, score, details_json)
        )
        self.conn.commit()

    def get_exam_history(self, user_id: int) -> List[Dict]:
        rows = self.conn.execute(
            "SELECT timestamp, subject, score, details FROM exam_results WHERE user_id = ? ORDER BY timestamp DESC",
            (user_id,)
        ).fetchall()
        history = [dict(row) for row in rows]
        # Convert JSON string in 'details' back to Dict
        for item in history:
            item['details'] = json.loads(item['details'])
        return history

    def add_essay_result(self, user_id: int, topic: str, score: int, feedback: str, essay_text: str):
        self.conn.execute(
            "INSERT INTO essay_results (user_id, topic, score, feedback, essay_text) VALUES (?, ?, ?, ?, ?)",
            (user_id, topic, score, feedback, essay_text)
        )
        self.conn.commit()
    
    def get_essay_history(self, user_id: int) -> List[Dict]:
        rows = self.conn.execute(
            "SELECT timestamp, topic, score, feedback, essay_text FROM essay_results WHERE user_id = ? ORDER BY timestamp DESC",
            (user_id,)
        ).fetchall()
        return [dict(row) for row in rows]
        
    # ... (XP, Payments, Admin methods are complete) ...

    def close(self):
        self.conn.close()
