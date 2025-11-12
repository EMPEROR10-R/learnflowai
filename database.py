# database.py
import sqlite3
import os
import json
import bcrypt
from datetime import datetime, date, timedelta
import uuid
import pyotp

DB_PATH = "users.db"

def get_db():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    c = conn.cursor()

    c.execute('''
    CREATE TABLE IF NOT EXISTS users (
        user_id TEXT PRIMARY KEY,
        email TEXT UNIQUE,
        password_hash TEXT,
        name TEXT,
        role TEXT DEFAULT 'user',
        streak_days INTEGER DEFAULT 0,
        last_streak_date TEXT,
        total_queries INTEGER DEFAULT 0,
        is_premium INTEGER DEFAULT 0,
        premium_until TEXT,
        parent_id TEXT,
        badges TEXT DEFAULT '[]',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        last_active TEXT DEFAULT CURRENT_TIMESTAMP,
        twofa_secret TEXT
    )
    ''')

    # Other tables...
    tables = [
        "chat_history", "pdf_uploads", "manual_payments", "quiz_results"
    ]
    for table in tables:
        c.execute(f"CREATE TABLE IF NOT EXISTS {table} (...)")  # Simplified

    # Add missing columns
    columns = [
        ("users", "last_active", "TEXT"),
        ("users", "twofa_secret", "TEXT"),
        ("users", "badges", "TEXT DEFAULT '[]'"),
        ("users", "premium_until", "TEXT"),
        ("users", "is_premium", "INTEGER DEFAULT 0")
    ]
    for table, col, typ in columns:
        try:
            c.execute(f"ALTER TABLE {table} ADD COLUMN {col} {typ}")
        except:
            pass

    # Admin
    c.execute("SELECT 1 FROM users WHERE email = ?", ("kingmumo15@gmail.com",))
    if not c.fetchone():
        hashed = bcrypt.hashpw("@Yoounruly10".encode(), bcrypt.gensalt()).decode()
        c.execute(
            "INSERT INTO users (user_id, email, password_hash, name, role) VALUES (?, ?, ?, ?, ?)",
            (str(uuid.uuid4()), "kingmumo15@gmail.com", hashed, "Admin", "admin")
        )

    conn.commit()
    conn.close()

init_db()

class Database:
    def __init__(self):
        self.conn = get_db()  # Persistent connection

    def _cursor(self):
        return self.conn.cursor()

    def commit(self):
        self.conn.commit()

    # === USER ===
    def create_user(self, email: str, password: str):
        user_id = str(uuid.uuid4())
        hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
        try:
            c = self._cursor()
            c.execute(
                "INSERT INTO users (user_id, email, password_hash, name) VALUES (?, ?, ?, ?)",
                (user_id, email, hashed, email.split("@")[0])
            )
            self.commit()
            return user_id
        except:
            return None

    def get_user_by_email(self, email: str):
        c = self._cursor()
        c.execute("SELECT * FROM users WHERE email = ?", (email,))
        row = c.fetchone()
        return dict(row) if row else None

    def get_user(self, user_id: str):
        c = self._cursor()
        c.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        row = c.fetchone()
        return dict(row) if row else None

    def update_user_activity(self, user_id: str):
        c = self._cursor()
        c.execute("UPDATE users SET last_active = CURRENT_TIMESTAMP WHERE user_id = ?", (user_id,))
        self.commit()

    # === 2FA ===
    def is_2fa_enabled(self, user_id: str):
        c = self._cursor()
        c.execute("SELECT twofa_secret FROM users WHERE user_id = ?", (user_id,))
        row = c.fetchone()
        return bool(row and row["twofa_secret"])

    def enable_2fa(self, user_id: str, secret: str):
        c = self._cursor()
        c.execute("UPDATE users SET twofa_secret = ? WHERE user_id = ?", (secret, user_id))
        self.commit()

    def verify_2fa_code(self, user_id: str, code: str):
        c = self._cursor()
        c.execute("SELECT twofa_secret FROM users WHERE user_id = ?", (user_id,))
        row = c.fetchone()
        if not row or not row["twofa_secret"]:
            return False
        return pyotp.TOTP(row["twofa_secret"]).verify(code)

    # === PREMIUM ===
    def check_premium(self, user_id: str):
        c = self._cursor()
        c.execute("SELECT is_premium FROM users WHERE user_id = ?", (user_id,))
        row = c.fetchone()
        return bool(row and row["is_premium"])

    def add_manual_payment(self, user_id: str, phone: str, mpesa_code: str):
        c = self._cursor()
        c.execute("INSERT INTO manual_payments (user_id, phone, mpesa_code) VALUES (?, ?, ?)", (user_id, phone, mpesa_code))
        self.commit()

    def get_pending_manual_payments(self):
        c = self._cursor()
        c.execute("SELECT mp.id, mp.mpesa_code, u.name FROM manual_payments mp JOIN users u ON mp.user_id = u.user_id WHERE mp.status = 'pending'")
        return [dict(row) for row in c.fetchall()]

    def approve_manual_payment(self, payment_id: int):
        c = self._cursor()
        c.execute("SELECT user_id FROM manual_payments WHERE id = ?", (payment_id,))
        row = c.fetchone()
        if row:
            user_id = row["user_id"]
            c.execute("UPDATE users SET is_premium = 1 WHERE user_id = ?", (user_id,))
            c.execute("UPDATE manual_payments SET status = 'approved' WHERE id = ?", (payment_id,))
            self.commit()
            return True
        return False

    def reject_manual_payment(self, payment_id: int):
        c = self._cursor()
        c.execute("UPDATE manual_payments SET status = 'rejected' WHERE id = ?", (payment_id,))
        self.commit()

    # === CHAT ===
    def add_chat_history(self, user_id: str, subject: str, query: str, response: str):
        c = self._cursor()
        c.execute("INSERT INTO chat_history (user_id, subject, user_query, ai_response) VALUES (?, ?, ?, ?)", (user_id, subject, query, response))
        c.execute("UPDATE users SET total_queries = total_queries + 1 WHERE user_id = ?", (user_id,))
        self.commit()

    def get_daily_query_count(self, user_id: str):
        c = self._cursor()
        c.execute("SELECT COUNT(*) FROM chat_history WHERE user_id = ? AND date(timestamp) = date('now')", (user_id,))
        return c.fetchone()[0]

    def get_pdf_count_today(self, user_id: str):
        c = self._cursor()
        c.execute("SELECT COUNT(*) FROM pdf_uploads WHERE user_id = ? AND date(upload_date) = date('now')", (user_id,))
        return c.fetchone()[0]

    # === STREAK ===
    def update_streak(self, user_id: str):
        c = self._cursor()
        c.execute("SELECT last_streak_date, streak_days FROM users WHERE user_id = ?", (user_id,))
        row = c.fetchone()
        if not row: return 0
        last_date, streak = row["last_streak_date"], row["streak_days"] or 0
        today = date.today().isoformat()
        if last_date == today:
            return streak
        elif last_date == (date.today() - timedelta(days=1)).isoformat():
            streak += 1
        else:
            streak = 1
        c.execute("UPDATE users SET streak_days = ?, last_streak_date = ? WHERE user_id = ?", (streak, today, user_id))
        self.commit()
        return streak

    # === BADGES ===
    def add_badge(self, user_id: str, badge: str):
        c = self._cursor()
        c.execute("SELECT badges FROM users WHERE user_id = ?", (user_id,))
        row = c.fetchone()
        badges = json.loads(row["badges"]) if row and row["badges"] else []
        if badge not in badges:
            badges.append(badge)
            c.execute("UPDATE users SET badges = ? WHERE user_id = ?", (json.dumps(badges), user_id))
            self.commit()
