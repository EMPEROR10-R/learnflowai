# database.py
import sqlite3
import bcrypt
import json
import uuid
from datetime import date, timedelta
import pyotp
from typing import Optional, Dict, List

DB_PATH = "users.db"


def get_conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def ensure_schema():
    conn = get_conn()
    c = conn.cursor()

    # Users table
    c.execute('''
    CREATE TABLE IF NOT EXISTS users (
        user_id TEXT PRIMARY KEY,
        email TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        name TEXT,
        role TEXT DEFAULT 'user',
        parent_id TEXT,
        streak_days INTEGER DEFAULT 0,
        last_streak_date TEXT,
        total_queries INTEGER DEFAULT 0,
        is_premium INTEGER DEFAULT 0,
        badges TEXT DEFAULT '[]',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        last_active TEXT DEFAULT CURRENT_TIMESTAMP,
        twofa_secret TEXT,
        profile_pic BLOB,
        theme TEXT DEFAULT 'light',
        brightness INTEGER DEFAULT 100,
        font TEXT DEFAULT 'sans-serif',
        discount REAL DEFAULT 0.0
    )
    ''')

    # Other tables
    for sql in [
        '''CREATE TABLE IF NOT EXISTS chat_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT, subject TEXT, user_query TEXT, ai_response TEXT,
            timestamp TEXT DEFAULT CURRENT_TIMESTAMP
        )''',
        '''CREATE TABLE IF NOT EXISTS pdf_uploads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT, filename TEXT, upload_date TEXT DEFAULT CURRENT_DATE
        )''',
        '''CREATE TABLE IF NOT EXISTS manual_payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT, phone TEXT, mpesa_code TEXT,
            status TEXT DEFAULT 'pending', submitted_at TEXT DEFAULT CURRENT_TIMESTAMP
        )''',
        '''CREATE TABLE IF NOT EXISTS scores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT, category TEXT, score REAL,
            timestamp TEXT DEFAULT CURRENT_TIMESTAMP
        )'''
    ]:
        c.execute(sql)

    # FORCE ONLY ONE ADMIN
    admin_email = "kingmumo15@gmail.com"
    admin_pwd = "@Yoounruly10"
    c.execute("DELETE FROM users WHERE email = ?", (admin_email,))
    hashed = bcrypt.hashpw(admin_pwd.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    admin_id = str(uuid.uuid4())
    today = date.today().isoformat()
    c.execute('''
    INSERT INTO users
    (user_id, email, password_hash, name, role, is_premium,
     streak_days, last_streak_date, last_active, created_at)
    VALUES (?,?,?,?, 'admin',1,1,?,?,?)
    ''', (admin_id, admin_email, hashed, "Admin King", today, today, today))

    conn.commit()
    conn.close()


ensure_schema()  # Run on import


class Database:
    def __init__(self):
        ensure_schema()
        self.conn = get_conn()

    def _c(self):
        return self.conn.cursor()

    def commit(self):
        self.conn.commit()

    # USER MANAGEMENT
    def create_user(self, email: str, password: str) -> Optional[str]:
        if len(password) < 6 or "@" not in email:
            return None
        uid = str(uuid.uuid4())
        hashed = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        today = date.today().isoformat()
        name = email.split("@")[0]
        try:
            c = self._c()
            c.execute('''
            INSERT INTO users
            (user_id, email, password_hash, name, streak_days, last_streak_date, last_active, created_at)
            VALUES (?,?,?, ?,1,?,?,?)
            ''', (uid, email, hashed, name, today, today, today))
            self.commit()
            return uid
        except sqlite3.IntegrityError:
            return None

    def get_user_by_email(self, email: str) -> Optional[Dict]:
        c = self._c()
        c.execute("SELECT * FROM users WHERE email = ?", (email,))
        row = c.fetchone()
        return dict(row) if row else None

    def get_user(self, user_id: str) -> Optional[Dict]:
        c = self._c()
        c.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        row = c.fetchone()
        return dict(row) if row else None

    def update_user_activity(self, user_id: str):
        c = self._c()
        c.execute("UPDATE users SET last_active = CURRENT_TIMESTAMP, total_queries = total_queries + 1 WHERE user_id = ?", (user_id,))
        self.commit()

    def update_streak(self, user_id: str) -> int:
        c = self._c()
        c.execute("SELECT last_streak_date, streak_days FROM users WHERE user_id = ?", (user_id,))
        row = c.fetchone()
        if not row:
            return 0
        last = row["last_streak_date"]
        streak = row["streak_days"]
        today = date.today().isoformat()
        if last == today:
            return streak
        elif last == (date.today() - timedelta(days=1)).isoformat():
            streak += 1
        else:
            streak = 1
        c.execute("UPDATE users SET streak_days = ?, last_streak_date = ? WHERE user_id = ?", (streak, today, user_id))
        self.commit()
        return streak

    def check_premium(self, user_id: str) -> bool:
        c = self._c()
        c.execute("SELECT is_premium FROM users WHERE user_id = ?", (user_id,))
        row = c.fetchone()
        return bool(row and row["is_premium"])

    # PAYMENTS
    def add_manual_payment(self, user_id, phone, code):
        c = self._c()
        c.execute("INSERT INTO manual_payments (user_id, phone, mpesa_code) VALUES (?,?,?)", (user_id, phone, code))
        self.commit()

    def get_pending_payments(self):
        c = self._c()
        c.execute("SELECT * FROM manual_payments WHERE status = 'pending'")
        return [dict(row) for row in c.fetchall()]

    def approve_manual_payment(self, payment_id):
        c = self._c()
        c.execute("SELECT user_id FROM manual_payments WHERE id = ?", (payment_id,))
        row = c.fetchone()
        if row:
            c.execute("UPDATE users SET is_premium = 1 WHERE user_id = ?", (row["user_id"],))
            c.execute("UPDATE manual_payments SET status = 'approved' WHERE id = ?", (payment_id,))
        self.commit()

    def reject_manual_payment(self, payment_id):
        c = self._c()
        c.execute("UPDATE manual_payments SET status = 'rejected' WHERE id = ?", (payment_id,))
        self.commit()

    # 2FA
    def generate_2fa_secret(self, user_id):
        secret = pyotp.random_base32()
        c = self._c()
        c.execute("UPDATE users SET twofa_secret = ? WHERE user_id = ?", (secret, user_id))
        self.commit()
        return secret

    def is_2fa_enabled(self, user_id):
        c = self._c()
        c.execute("SELECT twofa_secret FROM users WHERE user_id = ?", (user_id,))
        row = c.fetchone()
        return bool(row and row["twofa_secret"])

    def verify_2fa_code(self, user_id, code):
        c = self._c()
        c.execute("SELECT twofa_secret FROM users WHERE user_id = ?", (user_id,))
        row = c.fetchone()
        if not row or not row["twofa_secret"]:
            return False
        return pyotp.TOTP(row["twofa_secret"]).verify(code)

    # CHAT & SCORES
    def add_chat_history(self, user_id, subject, query, response):
        c = self._c()
        c.execute("INSERT INTO chat_history (user_id, subject, user_query, ai_response) VALUES (?,?,?,?)",
                  (user_id, subject, query, response))
        self.commit()

    def add_score(self, user_id, category, score):
        c = self._c()
        c.execute("INSERT INTO scores (user_id, category, score) VALUES (?,?,?)", (user_id, category, score))
        self.commit()

    # BADGES
    def add_badge(self, user_id, badge):
        c = self._c()
        c.execute("SELECT badges FROM users WHERE user_id = ?", (user_id,))
        row = c.fetchone()
        badges = json.loads(row["badges"]) if row and row["badges"] else []
        if badge not in badges:
            badges.append(badge)
            c.execute("UPDATE users SET badges = ? WHERE user_id = ?", (json.dumps(badges), user_id))
            self.commit()

    # LEADERBOARD
    def get_leaderboard(self, category):
        c = self._c()
        c.execute("""
        SELECT u.email, SUM(s.score) as total_score
        FROM scores s JOIN users u ON s.user_id = u.user_id
        WHERE s.category = ?
        GROUP BY s.user_id
        ORDER BY total_score DESC
        LIMIT 10
        """, (category,))
        return [{"email": row["email"], "score": row["total_score"]} for row in c.fetchall()]

    # ADMIN
    def get_all_users(self):
        c = self._c()
        c.execute("SELECT user_id, email, name, role, is_premium FROM users")
        return [dict(row) for row in c.fetchall()]
