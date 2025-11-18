# database.py
import sqlite3
import bcrypt
import json
import pyotp
import qrcode
import io
from datetime import datetime, date, timedelta
from typing import List, Dict, Any, Optional

class Database:
    def __init__(self, db_path: str = "prepke.db"): # Changed DB file name
        self.db_path = db_path
        # Ensures cross-platform compatibility for Streamlit concurrency
        self.conn = sqlite3.connect(db_path, check_same_thread=False) 
        self.conn.row_factory = sqlite3.Row
        self._create_tables()

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
            is_enabled INTEGER DEFAULT 0,
            FOREIGN KEY (user_id) REFERENCES users (user_id)
        );

        -- Chat History Table (Includes robust columns for different models)
        CREATE TABLE IF NOT EXISTS chat_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            subject TEXT NOT NULL,
            user_query TEXT,
            ai_response TEXT,
            user_message TEXT, -- alternate column name
            timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (user_id)
        );

        -- Payments Table for Manual Review
        CREATE TABLE IF NOT EXISTS payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            phone TEXT NOT NULL,
            mpesa_code TEXT NOT NULL,
            status TEXT DEFAULT 'pending', -- 'pending', 'approved', 'rejected'
            timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (user_id)
        );
        
        -- Scores Table for Quizzes and Essays (NEW)
        CREATE TABLE IF NOT EXISTS scores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            category TEXT NOT NULL, -- e.g., 'Math Quiz: Algebra', 'Essay: The Water Cycle'
            score INTEGER NOT NULL,
            timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (user_id)
        );
        """).executescript("""
        -- Ensure all necessary columns exist and are nullable for robust writes
        ALTER TABLE chat_history ADD COLUMN IF NOT EXISTS user_message TEXT;
        ALTER TABLE chat_history ADD COLUMN IF NOT EXISTS user_query TEXT;
        """)
        self.conn.commit()

    # ==============================================================================
    # USER AUTHENTICATION & MANAGEMENT
    # ==============================================================================

    def register_user(self, email: str, password: str, name: str, role: str = 'user'):
        hashed = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
        self.conn.execute(
            "INSERT INTO users (email, password_hash, name, role) VALUES (?, ?, ?, ?)", 
            (email, hashed, name, role)
        )
        self.conn.commit()

    def authenticate_user(self, email: str, password: str) -> Optional[Dict]:
        row = self.conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        if row and bcrypt.checkpw(password.encode('utf-8'), row['password_hash']):
            return dict(row)
        return None

    def get_user(self, user_id: int) -> Optional[Dict]:
        row = self.conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()
        return dict(row) if row else None

    def upgrade_to_premium(self, user_id: int):
        expiry = (datetime.now() + timedelta(days=30)).isoformat()
        self.conn.execute(
            "UPDATE users SET is_premium = 1, premium_expiry = ? WHERE user_id = ?",
            (expiry, user_id)
        )
        self.conn.commit()

    # ==============================================================================
    # CHAT & DAILY LIMITS
    # ==============================================================================

    def add_chat_history(self, user_id: int, subject: str, user_msg: str, ai_msg: str):
        # Tries to insert into the canonical columns (user_query, ai_response)
        # If the columns don't exist, the `app.py` fallback will handle it.
        self.conn.execute(
            "INSERT INTO chat_history (user_id, subject, user_query, ai_response) VALUES (?, ?, ?, ?)",
            (user_id, subject, user_msg, ai_msg)
        )
        self.conn.commit()

    def increment_daily_pdf(self, user_id: int):
        self.conn.execute("UPDATE users SET daily_pdfs = daily_pdfs + 1 WHERE user_id = ?", (user_id,))
        self.conn.commit()

    # ==============================================================================
    # 2FA
    # ==============================================================================

    def enable_2fa(self, user_id: int) -> tuple[str, str]:
        # Generate new secret
        secret = pyotp.random_base32()
        
        # Check if user_2fa entry exists
        row = self.conn.execute("SELECT * FROM user_2fa WHERE user_id = ?", (user_id,)).fetchone()
        
        if row:
            # Update existing entry
            self.conn.execute(
                "UPDATE user_2fa SET secret = ?, is_enabled = 0 WHERE user_id = ?",
                (secret, user_id)
            )
        else:
            # Insert new entry
            self.conn.execute(
                "INSERT INTO user_2fa (user_id, secret, is_enabled) VALUES (?, ?, 0)",
                (user_id, secret)
            )
            
        # Also update user table
        self.conn.execute("UPDATE users SET has_2fa = 1 WHERE user_id = ?", (user_id,))

        self.conn.commit()
        return secret, f"otpauth://totp/PrepKe:{user_id}?secret={secret}&issuer=PrepKe"
        
    def disable_2fa(self, user_id: int):
        self.conn.execute("UPDATE user_2fa SET is_enabled = 0 WHERE user_id = ?", (user_id,))
        self.conn.execute("UPDATE users SET has_2fa = 0 WHERE user_id = ?", (user_id,))
        self.conn.commit()

    def is_2fa_enabled(self, user_id: int) -> bool:
        row = self.conn.execute("SELECT is_enabled FROM user_2fa WHERE user_id = ?", (user_id,)).fetchone()
        return row and row['is_enabled'] == 1

    def verify_2fa_code(self, user_id: int, code: str) -> bool:
        row = self.conn.execute("SELECT secret FROM user_2fa WHERE user_id = ?", (user_id,)).fetchone()
        if not row: return False
        
        secret = row[0]
        totp = pyotp.TOTP(secret)
        
        if totp.verify(code):
            # If successfully verified, enable 2FA officially
            self.conn.execute("UPDATE user_2fa SET is_enabled = 1 WHERE user_id = ?", (user_id,))
            self.conn.commit()
            return True
        return False

    # ==============================================================================
    # XP & SCORE TRACKING
    # ==============================================================================

    def add_xp(self, user_id: int, points: int):
        # Update both total and spendable XP
        self.conn.execute(
            "UPDATE users SET total_xp = total_xp + ?, spendable_xp = spendable_xp + ? WHERE user_id = ?", 
            (points, points, user_id)
        )
        self.conn.commit()

    def get_xp_leaderboard(self):
        rows = self.conn.execute(
            "SELECT email, total_xp, (SELECT COUNT(*) + 1 FROM users u2 WHERE u2.total_xp > u1.total_xp AND u2.is_banned = 0) as rank FROM users u1 WHERE u1.is_banned = 0 ORDER BY total_xp DESC LIMIT 10"
        ).fetchall()
        return [dict(row) for row in rows]
    
    def add_score(self, user_id: int, category: str, score: int):
        """Adds a quiz or essay score to the scores table."""
        self.conn.execute(
            "INSERT INTO scores (user_id, category, score) VALUES (?, ?, ?)",
            (user_id, category, score)
        )
        self.conn.commit()
        
    def get_user_scores(self, user_id: int) -> List[Dict]:
        """Fetches the 10 most recent scores for the user."""
        rows = self.conn.execute(
            "SELECT category, score, timestamp FROM scores WHERE user_id = ? ORDER BY timestamp DESC LIMIT 10",
            (user_id,)
        ).fetchall()
        return [dict(row) for row in rows]

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
        rows = self.conn.execute("SELECT * FROM payments WHERE status = 'pending'").fetchall()
        return [dict(row) for row in rows]

    def approve_manual_payment(self, payment_id: int):
        self.conn.execute("UPDATE payments SET status = 'approved' WHERE id = ? AND status = 'pending'", (payment_id,))
        row = self.conn.execute("SELECT user_id FROM payments WHERE id = ? AND status = 'approved'", (payment_id,)).fetchone()
        if row:
            self.upgrade_to_premium(row["user_id"])
        self.conn.commit()

    def reject_manual_payment(self, payment_id: int):
        self.conn.execute("UPDATE payments SET status = 'rejected' WHERE id = ? AND status = 'pending'", (payment_id,))
        self.conn.commit()

    # ==============================================================================
    # CLEANUP
    # ==============================================================================
    def close(self):
        self.conn.close()
