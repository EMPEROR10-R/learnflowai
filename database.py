# database.py - FIXED: Schema compatibility for chat_history
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
        self._alter_tables_for_compatibility() # NEW: Ensures all columns exist

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

        -- Chat History
        CREATE TABLE IF NOT EXISTS chat_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            subject TEXT,
            user_query TEXT,            -- This is the column that might be missing
            ai_response TEXT,           -- This is the column that might be missing
            timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (user_id) ON DELETE CASCADE
        );

        -- Scores (Used for Exam and Essay results)
        CREATE TABLE IF NOT EXISTS scores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            category TEXT,  -- 'exam', 'essay'
            score REAL,     -- 0-100 score
            details TEXT,   -- JSON for exam/essay feedback/questions
            timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (user_id) ON DELETE CASCADE
        );

        -- Manual Payments
        CREATE TABLE IF NOT EXISTS payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            phone TEXT,
            mpesa_code TEXT,
            status TEXT DEFAULT 'pending',  -- pending, approved, rejected
            timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (user_id) ON DELETE CASCADE
        );
        """)
        self.conn.commit()

    def _alter_tables_for_compatibility(self):
        """Checks for and adds missing columns to existing tables."""
        cursor = self.conn.cursor()
        
        # FIX: Ensure chat_history has user_query and ai_response
        try:
            cursor.execute("SELECT user_query, ai_response FROM chat_history LIMIT 1")
        except sqlite3.OperationalError as e:
            if 'no such column: user_query' in str(e):
                self.conn.execute("ALTER TABLE chat_history ADD COLUMN user_query TEXT")
                self.conn.execute("ALTER TABLE chat_history ADD COLUMN ai_response TEXT")
                self.conn.commit()
                
        cursor.close()

    # ==============================================================================
    # USER MANAGEMENT (Kept for completeness)
    # ==============================================================================
    def create_user(self, email: str, password: str) -> Optional[int]:
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
        
    def get_all_users(self) -> List[Dict]:
        rows = self.conn.execute("SELECT * FROM users ORDER BY created_at DESC").fetchall()
        return [dict(row) for row in rows]

    def update_password(self, user_id: int, new_password: str):
        hash_pwd = bcrypt.hashpw(new_password.encode('utf-8'), bcrypt.gensalt())
        self.conn.execute("UPDATE users SET password_hash = ? WHERE user_id = ?", (hash_pwd, user_id))
        self.conn.commit()

    def update_user_activity(self, user_id: int):
        today = date.today().isoformat()
        self.conn.execute(
            "UPDATE users SET last_active = ?, last_daily_reset = COALESCE(last_daily_reset, ?) WHERE user_id = ?",
            (today, today, user_id)
        )
        self.conn.commit()

    def ban_user(self, user_id: int):
        self.conn.execute("UPDATE users SET is_banned = 1 WHERE user_id = ?", (user_id,))
        self.conn.commit()

    def upgrade_to_premium(self, user_id: int):
        expiry = (date.today() + timedelta(days=30)).isoformat()
        self.conn.execute(
            "UPDATE users SET is_premium = 1, premium_expiry = ?, role = 'premium' WHERE user_id = ?",
            (expiry, user_id)
        )
        self.conn.commit()

    def check_premium_validity(self, user_id: int) -> bool:
        user = self.get_user(user_id)
        if not user or not user["is_premium"]: return False
        expiry = user["premium_expiry"]
        return expiry and date.fromisoformat(expiry) >= date.today()

    def update_profile(self, user_id: int, name: str):
        self.conn.execute("UPDATE users SET name = ? WHERE user_id = ?", (name, user_id))
        self.conn.commit()

    # ==============================================================================
    # 2FA (Kept for completeness)
    # ==============================================================================
    def enable_2fa(self, user_id: int):
        secret = pyotp.random_base32()
        self.conn.execute(
            "INSERT OR REPLACE INTO user_2fa (user_id, secret, enabled) VALUES (?, ?, 1)",
            (user_id, secret)
        )
        self.conn.commit()
        return secret, self.get_2fa_qr(user_id) 

    def get_2fa_qr(self, user_id: int):
        user = self.get_user(user_id)
        secret_row = self.conn.execute("SELECT secret FROM user_2fa WHERE user_id = ?", (user_id,)).fetchone()
        if not secret_row: return None
        secret = secret_row["secret"]
        totp_uri = pyotp.totp.TOTP(secret).provisioning_uri(name=user["email"], issuer_name="PrepKe AI") 
        qr = qrcode.make(totp_uri)
        buffered = io.BytesIO()
        qr.save(buffered, format="PNG")
        return buffered.getvalue()

    def is_2fa_enabled(self, user_id: int) -> bool:
        row = self.conn.execute("SELECT 1 FROM user_2fa WHERE user_id = ? AND enabled = 1", (user_id,)).fetchone()
        return bool(row)

    def verify_2fa_code(self, user_id: int, code: str) -> bool:
        row = self.conn.execute("SELECT secret FROM user_2fa WHERE user_id = ?", (user_id,)).fetchone()
        if not row: return False
        totp = pyotp.TOTP(row["secret"])
        return totp.verify(code)

    def disable_2fa(self, user_id: int):
        self.conn.execute("DELETE FROM user_2fa WHERE user_id = ?", (user_id,))
        self.conn.commit()
    
    # ==============================================================================
    # DAILY LIMITS (Kept for completeness)
    # ==============================================================================
    def _reset_daily_if_needed(self, user_id: int):
        user = self.get_user(user_id)
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

    def get_daily_pdf_count(self, user_id: int) -> int:
        self._reset_daily_if_needed(user_id)
        row = self.conn.execute("SELECT daily_pdfs FROM users WHERE user_id = ?", (user_id,)).fetchone()
        return row["daily_pdfs"] if row else 0

    def increment_daily_question(self, user_id: int):
        self._reset_daily_if_needed(user_id)
        self.conn.execute("UPDATE users SET daily_questions = daily_questions + 1 WHERE user_id = ?", (user_id,))
        self.conn.commit()

    def increment_daily_pdf(self, user_id: int):
        self._reset_daily_if_needed(user_id)
        self.conn.execute("UPDATE users SET daily_pdfs = daily_pdfs + 1 WHERE user_id = ?", (user_id,))
        self.conn.commit()

    # ==============================================================================
    # XP & GAMIFICATION
    # ==============================================================================
    def add_xp(self, user_id: int, points: int, spendable: bool = False):
        if spendable:
            self.conn.execute(
                "UPDATE users SET spendable_xp = spendable_xp + ? WHERE user_id = ?",
                (points, user_id)
            )
        else:
            self.conn.execute(
                "UPDATE users SET total_xp = total_xp + ?, spendable_xp = spendable_xp + ? WHERE user_id = ?",
                (points, points, user_id)
            )
        self.conn.commit()

    def increase_discount(self, user_id: int, percent: int):
        self.conn.execute(
            "UPDATE users SET discount = LEAST(discount + ?, 50) WHERE user_id = ?",
            (percent, user_id)
        )
        self.conn.commit()

    def update_streak(self, user_id: int) -> int:
        """Handles streak updates and returns the new streak."""
        user = self.get_user(user_id)
        if not user: return 0
            
        today = date.today()
        last_streak_date_str = user.get("last_streak_date")
        current_streak = user.get("streak", 0)

        new_streak = current_streak
        
        if last_streak_date_str:
            last_streak_date = date.fromisoformat(last_streak_date_str)
            
            if last_streak_date == today:
                return current_streak
            
            yesterday = today - timedelta(days=1)
            
            if last_streak_date == yesterday:
                new_streak += 1
            else:
                new_streak = 1
        else:
            new_streak = 1

        self.conn.execute(
            "UPDATE users SET streak = ?, last_streak_date = ? WHERE user_id = ?",
            (new_streak, today.isoformat(), user_id)
        )
        # Award daily streak bonus XP here if needed (e.g., self.add_xp(user_id, 20))
        self.conn.commit()
        return new_streak

    # ==============================================================================
    # SCORES & LEADERBOARDS
    # ==============================================================================
    def add_score(self, user_id: int, category: str, score: float, details: Dict):
        details_json = json.dumps(details)
        self.conn.execute(
            "INSERT INTO scores (user_id, category, score, details) VALUES (?, ?, ?, ?)",
            (user_id, category, score, details_json)
        )
        self.conn.commit()

    def get_user_scores(self, user_id: int) -> List[Dict]:
        rows = self.conn.execute(
            "SELECT category, score, details, timestamp FROM scores WHERE user_id = ? ORDER BY timestamp DESC LIMIT 50",
            (user_id,)
        ).fetchall()
        history = [dict(row) for row in rows]
        # Convert JSON string in 'details' back to Dict
        for item in history:
            item['details'] = json.loads(item['details'])
        return history

    def get_xp_leaderboard(self) -> List[Dict]:
        return self.conn.execute("""
            SELECT email, total_xp
            FROM users 
            WHERE is_banned = 0
            ORDER BY total_xp DESC LIMIT 10
        """).fetchall()


    # ==============================================================================
    # CHAT & PDF
    # ==============================================================================
    def add_chat_history(self, user_id: int, subject: str, query: str, response: str):
        self.increment_daily_question(user_id)
        self.conn.execute(
            "INSERT INTO chat_history (user_id, subject, user_query, ai_response) VALUES (?, ?, ?, ?)",
            (user_id, subject, query, response)
        )
        self.conn.commit()

    def get_chat_history(self, user_id: int, subject: str) -> List[Dict]:
        rows = self.conn.execute(
            "SELECT user_query, ai_response FROM chat_history WHERE user_id = ? AND subject = ? ORDER BY timestamp DESC LIMIT 20",
            (user_id, subject)
        ).fetchall()
        return [dict(row) for row in rows][::-1]

    # ==============================================================================
    # PAYMENTS
    # ==============================================================================
    def add_manual_payment(self, user_id: int, phone: str, mpesa_code: str):
        self.conn.execute(
            "INSERT INTO payments (user_id, phone, mpesa_code) VALUES (?, ?, ?)",
            (user_id, phone, mpesa_code)
        )
        self.conn.commit()

    def get_pending_payments(self) -> List[Dict]:
        rows = self.conn.execute("""
            SELECT p.*, u.email 
            FROM payments p 
            JOIN users u ON p.user_id = u.user_id 
            WHERE p.status = 'pending'
            """).fetchall()
        return [dict(row) for row in rows]

    def approve_manual_payment(self, payment_id: int):
        self.conn.execute("UPDATE payments SET status = 'approved' WHERE id = ?", (payment_id,))
        row = self.conn.execute("SELECT user_id FROM payments WHERE id = ?", (payment_id,)).fetchone()
        if row:
            self.upgrade_to_premium(row["user_id"])
        self.conn.commit()

    def reject_manual_payment(self, payment_id: int):
        self.conn.execute("UPDATE payments SET status = 'rejected' WHERE id = ?", (payment_id,))
        self.conn.commit()

    # ==============================================================================
    # CLEANUP
    # ==============================================================================
    def close(self):
        self.conn.close()
