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
    def __init__(self, db_path: str = "prepke.db"):
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
            FOREIGN KEY(user_id) REFERENCES users(user_id)
        );

        -- Chat History Table
        CREATE TABLE IF NOT EXISTS chat_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
            subject TEXT NOT NULL,
            user_message TEXT NOT NULL,
            ai_response TEXT NOT NULL,
            xp_earned INTEGER DEFAULT 0,
            FOREIGN KEY(user_id) REFERENCES users(user_id)
        );

        -- Exam Results Table
        CREATE TABLE IF NOT EXISTS exam_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
            exam_type TEXT NOT NULL,
            subject TEXT NOT NULL,
            score INTEGER NOT NULL,
            details TEXT, -- JSON structure for questions/answers
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
        
        -- User Achievements Table
        CREATE TABLE IF NOT EXISTS user_achievements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            badge_key TEXT NOT NULL,
            timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(user_id) REFERENCES users(user_id)
        );

        -- Payments Table
        CREATE TABLE IF NOT EXISTS payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
            phone TEXT NOT NULL,
            mpesa_code TEXT NOT NULL,
            amount REAL DEFAULT 500.0,
            status TEXT DEFAULT 'pending', -- pending, approved, rejected
            FOREIGN KEY(user_id) REFERENCES users(user_id)
        );
        """)

    # ==============================================================================
    # USER AUTHENTICATION & RETRIEVAL (Includes crash fixes)
    # ==============================================================================
    
    def get_user_by_email(self, email: str) -> Optional[Dict]:
        """Retrieves a user by email, returns dict or None."""
        row = self.conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        return dict(row) if row else None 

    def get_user_data(self, user_id: int) -> Optional[Dict]:
        """Retrieves a user by ID, returns dict or None."""
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
    # 2FA RETRIEVAL (New function for password reset)
    # ==============================================================================

    def get_2fa_secret(self, user_id: int) -> Optional[str]:
        """Retrieves the 2FA secret key for a user if 2FA is enabled."""
        row = self.conn.execute("SELECT secret FROM user_2fa WHERE user_id = ? AND is_enabled = 1", (user_id,)).fetchone()
        # Ensure we return the secret string, or None if no row is found/2FA disabled
        return dict(row)['secret'] if row else None


    # ==============================================================================
    # USER ACCOUNT MANAGEMENT
    # ==============================================================================

    def upgrade_to_premium(self, user_id: int):
        expiry_date = (datetime.now() + timedelta(days=30)).isoformat()
        self.conn.execute(
            "UPDATE users SET is_premium = 1, premium_expiry = ? WHERE user_id = ?",
            (expiry_date, user_id)
        )
        self.conn.commit()

    def update_last_active(self, user_id: int):
        self.conn.execute(
            "UPDATE users SET last_active = ? WHERE user_id = ?",
            (datetime.now().isoformat(), user_id)
        )
        self.conn.commit()
        
    def update_user_xp(self, user_id: int, xp_change: int):
        self.conn.execute(
            "UPDATE users SET total_xp = total_xp + ?, spendable_xp = spendable_xp + ? WHERE user_id = ?",
            (xp_change, xp_change, user_id)
        )
        self.conn.commit()

    def get_user_achievements(self, user_id: int) -> List[Dict]:
        rows = self.conn.execute(
            "SELECT * FROM user_achievements WHERE user_id = ? ORDER BY timestamp DESC LIMIT 20",
            (user_id,)
        ).fetchall()
        return [dict(row) for row in rows]

    # ==============================================================================
    # CHAT HISTORY
    # ==============================================================================
    def add_chat_message(self, user_id: int, subject: str, user_message: str, ai_response: str, xp_earned: int = 0):
        self.conn.execute(
            "INSERT INTO chat_history (user_id, subject, user_message, ai_response, xp_earned) VALUES (?, ?, ?, ?, ?)",
            (user_id, subject, user_message, ai_response, xp_earned)
        )
        self.conn.commit()

    def get_chat_history(self, user_id: int, limit: int = 20) -> List[Dict]:
        rows = self.conn.execute(
            "SELECT * FROM chat_history WHERE user_id = ? ORDER BY timestamp DESC LIMIT ?",
            (user_id, limit)
        ).fetchall()
        # History is retrieved newest first, reverse for chat display
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
        rows = self.conn.execute("SELECT * FROM payments WHERE status = 'pending'").fetchall()
        return [dict(row) for row in rows]

    def approve_manual_payment(self, payment_id: int):
        self.conn.execute("UPDATE payments SET status = 'approved' WHERE id = ?", (payment_id,))
        row = self.conn.execute("SELECT user_id FROM payments WHERE id = ?", (payment_id,)).fetchone()
        if row:
            self.upgrade_to_premium(dict(row)["user_id"])
        self.conn.commit()

    def reject_manual_payment(self, payment_id: int):
        self.conn.execute("UPDATE payments SET status = 'rejected' WHERE id = ?", (payment_id,))
        self.conn.commit()

    # ==============================================================================
    # CLEANUP
    # ==============================================================================
    def close(self):
        self.conn.close()
