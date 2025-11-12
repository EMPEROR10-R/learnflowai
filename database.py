# database.py
import sqlite3
import bcrypt
import json
import uuid
from datetime import date, timedelta
import pyotp
from typing import Optional, List, Dict

DB_PATH = "users.db"

def get_db():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    c = conn.cursor()

    # === USERS TABLE ===
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
        twofa_secret TEXT
    )
    ''')

    # === CHAT HISTORY (FIXED: ai_response, not ai('_response')) ===
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

    # === PDF UPLOADS ===
    c.execute('''
    CREATE TABLE IF NOT EXISTS pdf_uploads (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT,
        filename TEXT,
        upload_date TEXT DEFAULT CURRENT_DATE
    )
    ''')

    # === MANUAL PAYMENTS ===
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

    # === AUTO-ADD MISSING COLUMNS ===
    columns_to_add = [
        ("last_active", "TEXT DEFAULT CURRENT_TIMESTAMP"),
        ("parent_id", "TEXT"),
        ("streak_days", "INTEGER DEFAULT 0"),
        ("last_streak_date", "TEXT"),
        ("badges", "TEXT DEFAULT '[]'"),
        ("is_premium", "INTEGER DEFAULT 0"),
        ("twofa_secret", "TEXT")
    ]
    for col, typ in columns_to_add:
        try:
            c.execute(f"ALTER TABLE users ADD COLUMN {col} {typ}")
        except sqlite3.OperationalError:
            pass  # already exists

    # === CREATE ADMIN ===
    c.execute("SELECT 1 FROM users WHERE email = ?", ("kingmumo15@gmail.com",))
    if not c.fetchone():
        hashed = bcrypt.hashpw("@Yoounruly10".encode(), bcrypt.gensalt()).decode()
        admin_id = str(uuid.uuid4())
        today = date.today().isoformat()
        c.execute('''
        INSERT INTO users 
        (user_id, email, password_hash, name, role, is_premium, streak_days, last_streak_date)
        VALUES (?, ?, ?, ?, 'admin', 1, 1, ?)
        ''', (admin_id, "kingmumo15@gmail.com", hashed, "Admin King", today))

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

    # === USER ===
    def create_user(self, email: str, password: str) -> Optional[str]:
        uid = str(uuid.uuid4())
        hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
        today = date.today().isoformat()
        try:
            self._c().execute('''
            INSERT INTO users (user_id, email, password_hash, name, streak_days, last_streak_date)
            VALUES (?, ?, ?, ?, 1, ?)
            ''', (uid, email, hashed, email.split("@")[0], today))
            self.commit()
            return uid
        except sqlite3.IntegrityError:
            return None

    def get_user_by_email(self, email: str) -> Optional[Dict]:
        c = self._c()
        c.execute("SELECT * FROM users WHERE email = ?", (email,))
        r = c.fetchone()
        return dict(r) if r else None

    def get_user(self, user_id: str) -> Optional[Dict]:
        c = self._c()
        c.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        r = c.fetchone()
        return dict(r) if r else None

    def update_user_activity(self, user_id: str):
        if not user_id: return
        self._c().execute("UPDATE users SET last_active = CURRENT_TIMESTAMP WHERE user_id = ?", (user_id,))
        self.commit()

    # === STREAK ===
    def update_streak(self, user_id: str) -> int:
        if not user_id: return 0
        c = self._c()
        c.execute("SELECT last_streak_date, streak_days FROM users WHERE user_id = ?", (user_id,))
        r = c.fetchone()
        if not r or r["last_streak_date"] is None:
            today = date.today().isoformat()
            c.execute("UPDATE users SET streak_days = 1, last_streak_date = ? WHERE user_id = ?", (today, user_id))
            self.commit()
            return 1
        last, streak = r["last_streak_date"], r["streak_days"] or 0
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

    # === PREMIUM ===
    def check_premium(self, user_id: str) -> bool:
        if not user_id: return False
        c = self._c()
        c.execute("SELECT is_premium FROM users WHERE user_id = ?", (user_id,))
        r = c.fetchone()
        return bool(r and r["is_premium"])

    def add_manual_payment(self, user_id: str, phone: str, code: str):
        self._c().execute("INSERT INTO manual_payments (user_id, phone, mpesa_code) VALUES (?, ?, ?)", (user_id, phone, code))
        self.commit()

    def get_pending_manual_payments(self) -> List[Dict]:
        c = self._c()
        c.execute('''
        SELECT mp.id, mp.phone, mp.mpesa_code, u.email, u.name 
        FROM manual_payments mp JOIN users u ON mp.user_id = u.user_id 
        WHERE mp.status = 'pending'
        ''')
        return [dict(r) for r in c.fetchall()]

    def approve_manual_payment(self, pid: int) -> bool:
        c = self._c()
        c.execute("SELECT user_id FROM manual_payments WHERE id = ?", (pid,))
        r = c.fetchone()
        if not r: return False
        uid = r["user_id"]
        c.execute("UPDATE users SET is_premium = 1 WHERE user_id = ?", (uid,))
        c.execute("UPDATE manual_payments SET status = 'approved' WHERE id = ?", (pid,))
        self.commit()
        return True

    def reject_manual_payment(self, pid: int):
        self._c().execute("UPDATE manual_payments SET status = 'rejected' WHERE id = ?", (pid,))
        self.commit()

    # === 2FA ===
    def generate_2fa_secret(self, user_id: str) -> str:
        secret = pyotp.random_base32()
        self._c().execute("UPDATE users SET twofa_secret = ? WHERE user_id = ?", (secret, user_id))
        self.commit()
        return secret

    def is_2fa_enabled(self, user_id: str) -> bool:
        c = self._c()
        c.execute("SELECT twofa_secret FROM users WHERE user_id = ?", (user_id,))
        r = c.fetchone()
        return bool(r and r["twofa_secret"])

    def enable_2fa(self, user_id: str, secret: str):
        self._c().execute("UPDATE users SET twofa_secret = ? WHERE user_id = ?", (secret, user_id))
        self.commit()

    def disable_2fa(self, user_id: str):
        self._c().execute("UPDATE users SET twofa_secret = NULL WHERE user_id = ?", (user_id,))
        self.commit()

    def verify_2fa_code(self, user_id: str, code: str) -> bool:
        c = self._c()
        c.execute("SELECT twofa_secret FROM users WHERE user_id = ?", (user_id,))
        r = c.fetchone()
        return pyotp.TOTP(r["twofa_secret"]).verify(code) if r and r["twofa_secret"] else False

    # === PARENT LINK ===
    def link_parent(self, child_id: str, parent_email: str, parent_pass: str) -> str:
        parent = self.get_user_by_email(parent_email)
        if not parent: return "Parent not found."
        if not bcrypt.checkpw(parent_pass.encode(), parent["password_hash"].encode()): return "Wrong password."
        self._c().execute("UPDATE users SET parent_id = ? WHERE user_id = ?", (parent["user_id"], child_id))
        self.commit()
        return f"Linked to {parent['email']}"

    def get_children(self, parent_id: str) -> List[Dict]:
        c = self._c()
        c.execute("SELECT * FROM users WHERE parent_id = ?", (parent_id,))
        return [dict(r) for r in c.fetchall()]

    # === BADGES & CHAT ===
    def add_badge(self, user_id: str, badge: str):
        user = self.get_user(user_id)
        badges = json.loads(user.get("badges", "[]"))
        if badge not in badges:
            badges.append(badge)
            self._c().execute("UPDATE users SET badges = ? WHERE user_id = ?", (json.dumps(badges), user_id))
            self.commit()

    def add_chat_history(self, user_id: str, subject: str, q: str, r: str):
        self._c().execute('''
        INSERT INTO chat_history (user_id, subject, user_query, ai_response) VALUES (?, ?, ?, ?)
        ''', (user_id, subject, q, r))
        self._c().execute("UPDATE users SET total_queries = total_queries + 1 WHERE user_id = ?", (user_id,))
        self.commit()

    def add_pdf_upload(self, user_id: str, filename: str):
        self._c().execute("INSERT INTO pdf_uploads (user_id, filename) VALUES (?, ?)", (user_id, filename))
        self.commit()

    def get_pdf_count_today(self, user_id: str) -> int:
        c = self._c()
        c.execute("SELECT COUNT(*) FROM pdf_uploads WHERE user_id = ? AND upload_date = ?", (user_id, date.today().isoformat()))
        return c.fetchone()[0]

    # === ADMIN ===
    def get_all_users(self) -> List[Dict]:
        c = self._c()
        c.execute("SELECT user_id, email, name, role, is_premium, created_at FROM users")
        return [dict(r) for r in c.fetchall()]

    def delete_user(self, user_id: str) -> bool:
        if user_id == st.session_state.get("user_id"): return False
        self._c().execute("DELETE FROM users WHERE user_id = ?", (user_id,))
        self.commit()
        return True

    def toggle_premium(self, user_id: str):
        self._c().execute("UPDATE users SET is_premium = NOT is_premium WHERE user_id = ?", (user_id,))
        self.commit()

    def get_daily_query_count(self, user_id: str) -> int:
        c = self._c()
        c.execute('''
        SELECT COUNT(*) FROM chat_history WHERE user_id = ? AND date(timestamp) = ?
        ''', (user_id, date.today().isoformat()))
        return c.fetchone()[0]
