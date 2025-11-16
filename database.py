# database.py - FIXED
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

    def _create_tables(self):
        self.conn.executescript("""
        -- Users Table (Updated: total_xp, spendable_xp, discount, leaderboard_win_streak)
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            password_hash BLOB NOT NULL,
            role TEXT DEFAULT 'user', -- admin > premium > user (basic)
            is_banned INTEGER DEFAULT 0,
            is_premium INTEGER DEFAULT 0,
            premium_expiry TEXT,
            total_xp INTEGER DEFAULT 0, -- XP for leveling (DOES NOT deplete when spending)
            spendable_xp INTEGER DEFAULT 0, -- XP Coins (DEPLETES when spending)
            discount INTEGER DEFAULT 0, -- Max cumulative discount (e.g., 20)
            name TEXT,
            badges TEXT DEFAULT '[]',
            streak INTEGER DEFAULT 0,
            leaderboard_win_streak INTEGER DEFAULT 0, -- New for 2-week top check
            last_active TEXT,
            last_streak_date TEXT,
            daily_questions INTEGER DEFAULT 0, -- Basic limit counter
            daily_pdfs INTEGER DEFAULT 0, -- Basic limit counter
            last_daily_reset TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        -- Exam Results Table
        CREATE TABLE IF NOT EXISTS exam_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
            subject TEXT NOT NULL,
            score INTEGER NOT NULL, -- Percentage 0-100
            details TEXT, -- JSON structure for questions/answers
            FOREIGN KEY(user_id) REFERENCES users(user_id)
        );

        -- Essay Results Table
        CREATE TABLE IF NOT EXISTS essay_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
            topic TEXT,
            score INTEGER NOT NULL, -- Percentage 0-100
            feedback TEXT NOT NULL,
            essay_text TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(user_id)
        );
        
        -- Other tables (user_2fa, chat_history, payments)
        CREATE TABLE IF NOT EXISTS user_2fa (user_id INTEGER PRIMARY KEY, secret TEXT NOT NULL, is_enabled INTEGER DEFAULT 1, FOREIGN KEY (user_id) REFERENCES users (user_id) ON DELETE CASCADE);
        CREATE TABLE IF NOT EXISTS chat_history (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, subject TEXT, user_query TEXT, ai_response TEXT, timestamp TEXT DEFAULT CURRENT_TIMESTAMP, FOREIGN KEY (user_id) REFERENCES users (user_id) ON DELETE CASCADE);
        CREATE TABLE IF NOT EXISTS payments (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, phone TEXT, mpesa_code TEXT, status TEXT DEFAULT 'pending', timestamp TEXT DEFAULT CURRENT_TIMESTAMP, FOREIGN KEY (user_id) REFERENCES users (user_id) ON DELETE CASCADE);

        """)
        self.conn.commit()

    # ==============================================================================
    # USER AUTHENTICATION & RETRIEVAL
    # ==============================================================================
    
    def get_user_by_email(self, email: str) -> Optional[Dict]:
        """Retrieves a user by email, returns dict or None."""
        row = self.conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        return dict(row) if row else None 

    def get_user(self, user_id: int) -> Optional[Dict]:
        """Retrieves a user by ID, returns dict or None (FIXED name consistency)."""
        row = self.conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()
        return dict(row) if row else None

    def add_user(self, email: str, password: str, name: str = None) -> int:
        hashed = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
        self.conn.execute(
            "INSERT INTO users (email, password_hash, name) VALUES (?, ?, ?)",
            (email, hashed, name)
        )
        self.conn.commit()
        return self.conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    # ==============================================================================
    # GAMIFICATION & XP COINS
    # ==============================================================================
    
    def add_xp(self, user_id: int, total_xp_gain: int, spendable_xp_gain: int = 0):
        """Adds XP to both total_xp (for level) and spendable_xp (XP coins)."""
        if spendable_xp_gain == 0: 
            spendable_xp_gain = total_xp_gain
            
        self.conn.execute(
            "UPDATE users SET total_xp = total_xp + ?, spendable_xp = spendable_xp + ? WHERE user_id = ?",
            (total_xp_gain, spendable_xp_gain, user_id)
        )
        self.conn.commit()

    def deduct_spendable_xp(self, user_id: int, cost: int) -> bool:
        """Deducts XP Coins (spendable_xp) for purchases."""
        user = self.get_user(user_id)
        if user and user.get('spendable_xp', 0) >= cost:
            self.conn.execute(
                "UPDATE users SET spendable_xp = spendable_xp - ? WHERE user_id = ?",
                (cost, user_id)
            )
            self.conn.commit()
            return True
        return False
        
    def add_discount(self, user_id: int, percentage: int):
        """Increments the user's discount percentage."""
        self.conn.execute(
            "UPDATE users SET discount = discount + ? WHERE user_id = ?",
            (percentage, user_id)
        )
        self.conn.commit()
    
    # ==============================================================================
    # DAILY LIMITS (CRITICAL FIX)
    # ==============================================================================
    
    def _reset_daily_if_needed(self, user_id: int):
        """Resets daily usage counters if the last reset was not today."""
        user = self.get_user(user_id)
        if not user or user.get("role") == "admin": return

        last_reset_str = user.get("last_daily_reset")
        today = date.today().isoformat()
        
        # Reset if the date is different or if it's the first time
        if last_reset_str != today:
            self.conn.execute(
                "UPDATE users SET daily_questions = 0, daily_pdfs = 0, last_daily_reset = ? WHERE user_id = ?",
                (today, user_id)
            )
            self.conn.commit()
            
    def increment_daily_question(self, user_id: int):
        """Increments the chat question counter (FIXED)."""
        self._reset_daily_if_needed(user_id)
        self.conn.execute(
            "UPDATE users SET daily_questions = daily_questions + 1 WHERE user_id = ?",
            (user_id,)
        )
        self.conn.commit()

    def increment_daily_pdf(self, user_id: int):
        """Increments the PDF upload counter (FIXED)."""
        self._reset_daily_if_needed(user_id)
        self.conn.execute(
            "UPDATE users SET daily_pdfs = daily_pdfs + 1 WHERE user_id = ?",
            (user_id,)
        )
        self.conn.commit()

    def get_daily_question_count(self, user_id: int) -> int:
        """Retrieves current daily question count (FIXED)."""
        self._reset_daily_if_needed(user_id)
        row = self.conn.execute("SELECT daily_questions FROM users WHERE user_id = ?", (user_id,)).fetchone()
        return row["daily_questions"] if row else 0

    def get_daily_pdf_count(self, user_id: int) -> int:
        """Retrieves current daily PDF count (FIXED)."""
        self._reset_daily_if_needed(user_id)
        row = self.conn.execute("SELECT daily_pdfs FROM users WHERE user_id = ?", (user_id,)).fetchone()
        return row["daily_pdfs"] if row else 0
        
    # ==============================================================================
    # SCORE LOGGING (Remains same, crucial for XP/Leaderboard)
    # ==============================================================================
    def log_exam_score(self, user_id: int, subject: str, score: int, details: str):
        self.conn.execute(
            "INSERT INTO exam_results (user_id, subject, score, details) VALUES (?, ?, ?, ?)",
            (user_id, subject, score, details)
        )
        self.conn.commit()
        xp_gain = score // 10 
        self.add_xp(user_id, xp_gain, xp_gain)

    def log_essay_score(self, user_id: int, topic: str, score: int, feedback: str, essay_text: str):
        self.conn.execute(
            "INSERT INTO essay_results (user_id, topic, score, feedback, essay_text) VALUES (?, ?, ?, ?, ?)",
            (user_id, topic, score, feedback, essay_text)
        )
        self.conn.commit()
        xp_gain = score // 5 
        self.add_xp(user_id, xp_gain, xp_gain)
        
    # ==============================================================================
    # LEADERBOARD LOGIC (Remains same, crucial for ranking)
    # ==============================================================================
    def get_xp_leaderboard(self, limit: int = 10) -> List[Dict]:
        rows = self.conn.execute(
            """
            SELECT user_id, email, name, total_xp, leaderboard_win_streak 
            FROM users 
            WHERE role != 'admin' 
            ORDER BY total_xp DESC 
            LIMIT ?
            """,
            (limit,)
        ).fetchall()
        # FIX: Ensure all user_id data is included for streak tracking in app.py
        return [dict(row) for row in rows] 

    def get_exam_leaderboard(self, limit: int = 10) -> List[Dict]:
        rows = self.conn.execute(
            """
            SELECT 
                u.name, 
                MAX(e.score) AS max_score, 
                e.subject,
                u.user_id, -- Include user_id for streak tracking
                u.email
            FROM exam_results e
            JOIN users u ON e.user_id = u.user_id
            WHERE u.role != 'admin'
            GROUP BY u.user_id
            ORDER BY max_score DESC
            LIMIT ?
            """,
            (limit,)
        ).fetchall()
        return [dict(row) for row in rows]

    def get_essay_leaderboard(self, limit: int = 10) -> List[Dict]:
        rows = self.conn.execute(
            """
            SELECT 
                u.name, 
                MAX(e.score) AS max_score, 
                e.topic,
                u.user_id, -- Include user_id for streak tracking
                u.email
            FROM essay_results e
            JOIN users u ON e.user_id = u.user_id
            WHERE u.role != 'admin'
            GROUP BY u.user_id
            ORDER BY max_score DESC
            LIMIT ?
            """,
            (limit,)
        ).fetchall()
        return [dict(row) for row in rows]
        
    def get_flagged_for_discount(self) -> List[Dict]:
        rows = self.conn.execute(
            """
            SELECT user_id, email, name, leaderboard_win_streak, total_xp, discount 
            FROM users 
            WHERE leaderboard_win_streak >= 14 AND role != 'admin'
            ORDER BY leaderboard_win_streak DESC
            """
        ).fetchall()
        return [dict(row) for row in rows]
        
    # ... (Other essential functions like check_premium_validity, upgrade_to_premium, payments etc. remain) ...
    def check_premium_validity(self, user_id: int) -> bool:
        user = self.get_user(user_id)
        if not user or not user["is_premium"]: return False
        expiry = user["premium_expiry"]
        return expiry and date.fromisoformat(expiry) >= date.today()

    def close(self):
        self.conn.close()
