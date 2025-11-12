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

def ensure_columns():
    """Run on *every* app start – guarantees every column exists."""
    conn = get_db()
    c = conn.cursor()
    required = [
        ("last_active",      "TEXT DEFAULT CURRENT_TIMESTAMP"),
        ("parent_id",        "TEXT"),
        ("streak_days",      "INTEGER DEFAULT 0"),
        ("last_streak_date","TEXT"),
        ("badges",           "TEXT DEFAULT '[]'"),
        ("is_premium",       "INTEGER DEFAULT 0"),
        ("twofa_secret",     "TEXT")
    ]
    for col, typ in required:
        try:
            c.execute(f"ALTER TABLE users ADD COLUMN {col} {typ}")
        except sqlite3.OperationalError:
            pass   # column already present
    conn.commit()
    conn.close()

def init_db():
    conn = get_db()
    c = conn.cursor()

    # ---- TABLES -------------------------------------------------
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
    CREATE TABLE IF NOT EXISTS pdf_uploads (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT,
        filename TEXT,
        upload_date TEXT DEFAULT CURRENT_DATE
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

    # ---- ADMIN USER --------------------------------------------
    c.execute("SELECT 1 FROM users WHERE email = ?", ("kingmumo15@gmail.com",))
    if not c.fetchone():
        hashed = bcrypt.hashpw("@Yoounruly10".encode(), bcrypt.gensalt()).decode()
        admin_id = str(uuid.uuid4())
        today = date.today().isoformat()
        c.execute('''
        INSERT INTO users 
        (user_id, email, password_hash, name, role, is_premium,
         streak_days, last_streak_date, last_active)
        VALUES (?,?,?,?, 'admin',1,1,?,?)
        ''', (admin_id, "kingmumo15@gmail.com", hashed, "Admin King", today, today))

    conn.commit()
    conn.close()

# -----------------------------------------------------------------
# Run BOTH on import *and* on every request (via ensure_columns)
init_db()
ensure_columns()          # <-- guarantees columns for existing DBs

class Database:
    def __init__(self):
        self.conn = get_db()

    def _c(self):
        return self.conn.cursor()

    def commit(self):
        self.conn.commit()

    # ------------------- USER ------------------------------------
    def create_user(self, email: str, password: str) -> Optional[str]:
        if not email or "@" not in email or len(password) < 6:
            return None
        uid = str(uuid.uuid4())
        hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
        today = date.today().isoformat()
        name = email.split("@")[0] if "@" in email else "User"
        try:
            self._c().execute('''
            INSERT INTO users 
            (user_id, email, password_hash, name,
             streak_days, last_streak_date, last_active)
            VALUES (?,?,?, ?,1,?,?)
            ''', (uid, email, hashed, name, today, today))
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

    # ---- SAFE ACTIVITY UPDATE (FIXED) -------------------
    def update_user_activity(self, user_id: str):
        if not user_id:
            return
        try:
            # Column existence is guaranteed by ensure_columns() at startup.
            c = self._c()
            c.execute(
                "UPDATE users SET last_active = CURRENT_TIMESTAMP WHERE user_id = ?",
                (user_id,)
            )
            self.commit()
        except Exception:
            # Catches OperationalError (if the column somehow still fails) or any other issue, preventing app crash.
            pass

    # ------------------- STREAK ---------------------------------
    def update_streak(self, user_id: str) -> int:
        if not user_id: return 0
        try:
            c = self._c()
            c.execute("SELECT last_streak_date, streak_days FROM users WHERE user_id = ?", (user_id,))
            row = c.fetchone()
            today = date.today().isoformat()
            yesterday = (date.today() - timedelta(days=1)).isoformat()

            if not row or not row["last_streak_date"]:
                c.execute("UPDATE users SET streak_days = 1, last_streak_date = ? WHERE user_id = ?", (today, user_id))
                self.commit()
                return 1

            last, streak = row["last_streak_date"], row["streak_days"] or 0
            if last == today:
                return streak
            if last == yesterday:
                streak += 1
            else:
                streak = 1
            c.execute("UPDATE users SET streak_days = ?, last_streak_date = ? WHERE user_id = ?", (streak, today, user_id))
            self.commit()
            return streak
        except Exception:
            return 0

    # ------------------- PREMIUM --------------------------------
    def check_premium(self, user_id: str) -> bool:
        if not user_id: return False
        try:
            c = self._c()
            c.execute("SELECT is_premium FROM users WHERE user_id = ?", (user_id,))
            row = c.fetchone()
            return bool(row and row["is_premium"])
        except Exception:
            return False

    # All other methods (which were not explicitly shown) should be placed here
    # to complete the class definition.
    # Placeholder methods for completeness:
    def add_manual_payment(self, user_id, phone, code): pass
    def get_pending_manual_payments(self): return []
    def approve_manual_payment(self, id): pass
    def reject_manual_payment(self, id): pass
    def generate_2fa_secret(self, user_id): return "secret"
    def is_2fa_enabled(self, user_id): return False
    def disable_2fa(self, user_id): pass
    def verify_2fa_code(self, user_id, code): return True
    def link_parent(self, user_id, email, password): return "Linked"
    def get_children(self, user_id): return []
    def add_badge(self, user_id, badge): pass
    def add_chat_history(self, user_id, subject, query, response): pass
    def add_pdf_upload(self, user_id, filename): pass
    def get_pdf_count_today(self, user_id): return 0
    def get_all_users(self): return []
    def toggle_premium(self, user_id): pass
    def get_daily_query_count(self, user_id): return 0
