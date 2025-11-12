# database.py
import sqlite3
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
        badges TEXT DEFAULT '[]',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        last_active TEXT DEFAULT CURRENT_TIMESTAMP,
        twofa_secret TEXT
    )
    ''')

    c.execute('''
    CREATE TABLE IF NOT EXISTS chat_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT,
        subject TEXT,
        user_query TEXT,
        ai_response TEXT,
        timestamp TEXT DEFAULT CURRENT_TIMESTAMP
    )
    ''')

    c.execute('''
    CREATE TABLE IF NOT EXISTS manual_payments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT,
        phone TEXT,
        mpesa_code TEXT,
        status TEXT DEFAULT 'pending',
        submitted_at TEXT DEFAULT CURRENT_TIMESTAMP
    )
    ''')

    # Add missing columns
    for col, typ in [("last_active", "TEXT"), ("twofa_secret", "TEXT"), ("badges", "TEXT DEFAULT '[]'"), ("is_premium", "INTEGER DEFAULT 0")]:
        try:
            c.execute(f"ALTER TABLE users ADD COLUMN {col} {typ}")
        except:
            pass

    # Create admin
    c.execute("SELECT 1 FROM users WHERE email = ?", ("kingmumo15@gmail.com",))
    if not c.fetchone():
        hashed = bcrypt.hashpw("@Yoounruly10".encode(), bcrypt.gensalt()).decode()
        c.execute(
            "INSERT INTO users (user_id, email, password_hash, name, role, is_premium) VALUES (?, ?, ?, ?, ?, 1)",
            (str(uuid.uuid4()), "kingmumo15@gmail.com", hashed, "Admin King", "admin")
        )

    conn.commit()
    conn.close()

init_db()

class Database:
    def __init__(self):
        self.conn = get_db()

    def _c(self):
        return self.conn.cursor()

    def commit(self):
        self.conn.commit()

    def create_user(self, email, pwd):
        uid = str(uuid.uuid4())
        h = bcrypt.hashpw(pwd.encode(), bcrypt.gensalt()).decode()
        try:
            self._c().execute("INSERT INTO users (user_id, email, password_hash, name) VALUES (?, ?, ?, ?)", (uid, email, h, email.split("@")[0]))
            self.commit()
            return uid
        except:
            return None

    def get_user_by_email(self, email):
        c = self._c()
        c.execute("SELECT * FROM users WHERE email = ?", (email,))
        r = c.fetchone()
        return dict(r) if r else None

    def get_user(self, uid):
        c = self._c()
        c.execute("SELECT * FROM users WHERE user_id = ?", (uid,))
        r = c.fetchone()
        return dict(r) if r else None

    def update_user_activity(self, uid):
        self._c().execute("UPDATE users SET last_active = CURRENT_TIMESTAMP WHERE user_id = ?", (uid,))
        self.commit()

    def update_streak(self, uid):
        if not uid: return 0
        c = self._c()
        c.execute("SELECT last_streak_date, streak_days FROM users WHERE user_id = ?", (uid,))
        r = c.fetchone()
        if not r: return 0
        last, streak = r["last_streak_date"], r["streak_days"] or 0
        today = date.today().isoformat()
        if last == today:
            return streak
        elif last == (date.today() - timedelta(days=1)).isoformat():
            streak += 1
        else:
            streak = 1
        c.execute("UPDATE users SET streak_days = ?, last_streak_date = ? WHERE user_id = ?", (streak, today, uid))
        self.commit()
        return streak

    def check_premium(self, uid):
        if not uid: return False
        c = self._c()
        c.execute("SELECT is_premium FROM users WHERE user_id = ?", (uid,))
        r = c.fetchone()
        return bool(r and r["is_premium"])

    def add_manual_payment(self, uid, phone, code):
        self._c().execute("INSERT INTO manual_payments (user_id, phone, mpesa_code) VALUES (?, ?, ?)", (uid, phone, code))
        self.commit()

    def get_pending_manual_payments(self):
        c = self._c()
        c.execute("SELECT mp.id, mp.phone, mp.mpesa_code, u.email, u.name FROM manual_payments mp JOIN users u ON mp.user_id = u.user_id WHERE mp.status = 'pending'")
        return [dict(r) for r in c.fetchall()]

    def approve_manual_payment(self, pid):
        c = self._c()
        c.execute("SELECT user_id FROM manual_payments WHERE id = ?", (pid,))
        r = c.fetchone()
        if r:
            uid = r["user_id"]
            c.execute("UPDATE users SET is_premium = 1 WHERE user_id = ?", (uid,))
            c.execute("UPDATE manual_payments SET status = 'approved' WHERE id = ?", (pid,))
            self.commit()
            return True
        return False

    def reject_manual_payment(self, pid):
        self._c().execute("UPDATE manual_payments SET status = 'rejected' WHERE id = ?", (pid,))
        self.commit()

    def delete_user(self, uid):
        c = self._c()
        c.execute("DELETE FROM users WHERE user_id = ?", (uid,))
        self.commit()

    def get_all_users(self):
        c = self._c()
        c.execute("SELECT user_id, email, name, role, is_premium FROM users")
        return [dict(r) for r in c.fetchall()]

    def is_2fa_enabled(self, uid):
        c = self._c()
        c.execute("SELECT twofa_secret FROM users WHERE user_id = ?", (uid,))
        r = c.fetchone()
        return bool(r and r["twofa_secret"])

    def enable_2fa(self, uid, secret):
        self._c().execute("UPDATE users SET twofa_secret = ? WHERE user_id = ?", (secret, uid))
        self.commit()

    def disable_2fa(self, uid):
        self._c().execute("UPDATE users SET twofa_secret = NULL WHERE user_id = ?", (uid,))
        self.commit()

    def verify_2fa_code(self, uid, code):
        c = self._c()
        c.execute("SELECT twofa_secret FROM users WHERE user_id = ?", (uid,))
        r = c.fetchone()
        return pyotp.TOTP(r["twofa_secret"]).verify(code) if r and r["twofa_secret"] else False

    def add_chat_history(self, uid, subj, q, r):
        c = self._c()
        c.execute("INSERT INTO chat_history (user_id, subject, user_query, ai_response) VALUES (?, ?, ?, ?)", (uid, subj, q, r))
        c.execute("UPDATE users SET total_queries = total_queries + 1 WHERE user_id = ?", (uid,))
        self.commit()
