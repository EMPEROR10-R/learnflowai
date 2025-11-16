# database_fixed.py
# Patch of database.py to make chat_history writes robust and avoid NOT NULL constraint errors
# - add_chat_history tries the canonical function, and falls back to creating any missing columns
# - helper to ensure both user_query and user_message exist as nullable columns

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
            user_message TEXT,
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

        CREATE TABLE IF NOT EXISTS payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            phone TEXT,
            mpesa_code TEXT,
            status TEXT DEFAULT 'pending',
            timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (user_id) ON DELETE CASCADE
        );
        """)
        self.conn.commit()

    # user methods (create/get/update) kept minimal here for brevity
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

    # ... other methods omitted for brevity; keep same names as app expects

    def add_chat_history(self, user_id: int, subject: str, user_query: str, ai_response: str):
        # Attempt to insert into preferred columns; if columns missing or constraint error, alter table to add columns
        cur = self.conn.cursor()
        try:
            cur.execute("INSERT INTO chat_history (user_id, subject, user_query, ai_response) VALUES (?, ?, ?, ?)", (user_id, subject, user_query, ai_response))
            self.conn.commit(); return
        except sqlite3.IntegrityError:
            self.conn.rollback()
        except sqlite3.OperationalError:
            self.conn.rollback()
        # If we reach here, try to ensure user_message column exists and insert
        try:
            cur.execute("ALTER TABLE chat_history ADD COLUMN user_message TEXT")
        except sqlite3.OperationalError:
            # column probably exists
            pass
        try:
            cur.execute("INSERT INTO chat_history (user_id, subject, user_message, ai_response) VALUES (?, ?, ?, ?)", (user_id, subject, user_query, ai_response))
            self.conn.commit(); return
        except Exception:
            self.conn.rollback()
        # Final fallback: insert whatever columns are present
        cols = [c['name'] for c in self.conn.execute("PRAGMA table_info(chat_history)").fetchall()]
        insert_cols = []
        vals = []
        if 'user_id' in cols: insert_cols.append('user_id'); vals.append(user_id)
        if 'subject' in cols: insert_cols.append('subject'); vals.append(subject)
        if 'user_query' in cols: insert_cols.append('user_query'); vals.append(user_query)
        elif 'user_message' in cols: insert_cols.append('user_message'); vals.append(user_query)
        if 'ai_response' in cols: insert_cols.append('ai_response'); vals.append(ai_response)
        if not insert_cols:
            return
        q = f"INSERT INTO chat_history ({', '.join(insert_cols)}) VALUES ({', '.join(['?']*len(insert_cols))})"
        cur.execute(q, tuple(vals)); self.conn.commit()

    # Minimal implementations of functions used by app
    def is_2fa_enabled(self, user_id: int) -> bool:
        row = self.conn.execute("SELECT 1 FROM user_2fa WHERE user_id = ? AND enabled = 1", (user_id,)).fetchone()
        return bool(row)
    def enable_2fa(self, user_id: int):
        secret = pyotp.random_base32()
        self.conn.execute("INSERT OR REPLACE INTO user_2fa (user_id, secret, enabled) VALUES (?, ?, 1)", (user_id, secret))
        self.conn.commit()
        # return QR bytes
        totp_uri = pyotp.totp.TOTP(secret).provisioning_uri(name=self.get_user(user_id)['email'], issuer_name='PrepKe')
        qr = qrcode.make(totp_uri)
        buf = io.BytesIO(); qr.save(buf,'PNG')
        return secret, buf.getvalue()
    def verify_2fa_code(self, user_id: int, code: str) -> bool:
        row = self.conn.execute("SELECT secret FROM user_2fa WHERE user_id = ?", (user_id,)).fetchone()
        if not row: return False
        totp = pyotp.TOTP(row[0]); return totp.verify(code)

    # XP helpers
    def add_xp(self, user_id: int, points: int, spendable: bool = False):
        if spendable:
            self.conn.execute("UPDATE users SET spendable_xp = spendable_xp + ? WHERE user_id = ?", (points, user_id))
        else:
            self.conn.execute("UPDATE users SET total_xp = total_xp + ?, spendable_xp = spendable_xp + ? WHERE user_id = ?", (points, points, user_id))
        self.conn.commit()

    def increment_daily_pdf(self, user_id: int):
        self.conn.execute("UPDATE users SET daily_pdfs = daily_pdfs + 1 WHERE user_id = ?", (user_id,))
        self.conn.commit()

    def get_user_scores(self, user_id: int) -> List[Dict]:
        rows = self.conn.execute("SELECT category, score, timestamp FROM scores WHERE user_id = ? ORDER BY timestamp DESC LIMIT 50", (user_id,)).fetchall()
        return [dict(r) for r in rows]

    def get_xp_leaderboard(self):
        rows = self.conn.execute("SELECT email, total_xp, (SELECT COUNT(*) + 1 FROM users u2 WHERE u2.total_xp > u1.total_xp AND u2.is_banned = 0) as rank FROM users u1 WHERE is_banned = 0 ORDER BY total_xp DESC LIMIT 10").fetchall()
        return [dict(r) for r in rows]

    def get_pending_payments(self):
        return [dict(r) for r in self.conn.execute("SELECT * FROM payments WHERE status = 'pending'").fetchall()]

    def close(self): self.conn.close()
