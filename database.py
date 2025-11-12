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
    """Run on every app start – guarantees every column exists."""
    conn = get_db()
    c = conn.cursor()
    required = [
        ("last_active",      "TEXT DEFAULT CURRENT_TIMESTAMP"),
        ("parent_id",        "TEXT"),
        ("streak_days",      "INTEGER DEFAULT 0"),
        ("last_streak_date", "TEXT"),
        ("badges",           "TEXT DEFAULT '[]'"),
        ("is_premium",       "INTEGER DEFAULT 0"),
        ("twofa_secret",     "TEXT")
    ]
    for col, typ in required:
        try:
            c.execute(f"ALTER TABLE users ADD COLUMN {col} {typ}")
        except sqlite3.OperationalError:
            pass
    conn.commit()
    conn.close()

def init_db():
    conn = get_db()
    c = conn.cursor()

    # --- USERS TABLE ---
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

    # --- OTHER TABLES ---
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

    # --- ADMIN USER ---
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

# Run on import AND ensure columns
init_db()
ensure_columns()

class Database:
    def __init__(self):
        self.conn = get_db()

    def _c(self):
        return self.conn.cursor()

    def commit(self):
        self.conn.commit()

    # === USER ===
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

    def update_user_activity(self, user_id: str):
        if not user_id: return
        try:
            c = self._c()
            c.execute("UPDATE users SET last_active = CURRENT_TIMESTAMP WHERE user_id = ?", (user_id,))
            self.commit()
        except Exception:
            pass  # Never crash

    # === STREAK ===
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
            if last == today: return streak
            if last == yesterday: streak += 1
            else: streak = 1
            c.execute("UPDATE users SET streak_days = ?, last_streak_date = ? WHERE user_id = ?", (streak, today, user_id))
            self.commit()
            return streak
        except Exception:
            return 0

    # === PREMIUM ===
    def check_premium(self, user_id: str) -> bool:
        if not user_id: return False
        try:
            c = self._c()
            c.execute("SELECT is_premium FROM users WHERE user_id = ?", (user_id,))
            row = c.fetchone()
            return bool(row and row["is_premium"])
        except Exception:
            return False

    def add_manual_payment(self, user_id: str, phone: str, code: str):
        try:
            self._c().execute("INSERT INTO manual_payments (user_id, phone, mpesa_code) VALUES (?, ?, ?)", (user_id, phone, code))
            self.commit()
        except Exception:
            pass

    def get_pending_manual_payments(self) -> List[Dict]:
        try:
            c = self._c()
            c.execute('''
            SELECT mp.id, mp.phone, mp.mpesa_code, u.email, u.name 
            FROM manual_payments mp 
            JOIN users u ON mp.user_id = u.user_id 
            WHERE mp.status = 'pending'
            ''')
            return [dict(r) for r in c.fetchall()]
        except Exception:
            return []

    def approve_manual_payment(self, pid: int) -> bool:
        try:
            c = self._c()
            c.execute("SELECT user_id FROM manual_payments WHERE id = ?", (pid,))
            row = c.fetchone()
            if not row: return False
            uid = row["user_id"]
            c.execute("UPDATE users SET is_premium = 1 WHERE user_id = ?", (uid,))
            c.execute("UPDATE manual_payments SET status = 'approved' WHERE id = ?", (pid,))
            self.commit()
            return True
        except Exception:
            return False

    def reject_manual_payment(self, pid: int):
        try:
            self._c().execute("UPDATE manual_payments SET status = 'rejected' WHERE id = ?", (pid,))
            self.commit()
        except Exception:
            pass

    # === 2FA ===
    def generate_2fa_secret(self, user_id: str) -> str:
        secret = pyotp.random_base32()
        try:
            self._c().execute("UPDATE users SET twofa_secret = ? WHERE user_id = ?", (secret, user_id))
            self.commit()
        except Exception:
            pass
        return secret

    def is_2fa_enabled(self, user_id: str) -> bool:
        try:
            c = self._c()
            c.execute("SELECT twofa_secret FROM users WHERE user_id = ?", (user_id,))
            row = c.fetchone()
            return bool(row and row["twofa_secret"])
        except Exception:
            return False

    def disable_2fa(self, user_id: str):
        try:
            self._c().execute("UPDATE users SET twofa_secret = NULL WHERE user_id = ?", (user_id,))
            self.commit()
        except Exception:
            pass

    def verify_2fa_code(self, user_id: str, code: str) -> bool:
        try:
            c = self._c()
            c.execute("SELECT twofa_secret FROM users WHERE user_id = ?", (user_id,))
            row = c.fetchone()
            if not row or not row["twofa_secret"]: return False
            return pyotp.TOTP(row["twofa_secret"]).verify(code)
        except Exception:
            return False

    # === PARENT LINK ===
    def link_parent(self, child_id: str, parent_email: str, parent_pass: str) -> str:
        try:
            parent = self.get_user_by_email(parent_email)
            if not parent: return "Parent email not found."
            if not bcrypt.checkpw(parent_pass.encode(), parent["password_hash"].encode()):
                return "Incorrect password."
            self._c().execute("UPDATE users SET parent_id = ? WHERE user_id = ?", (parent["user_id"], child_id))
            self.commit()
            return f"Linked to {parent['email']}"
        except Exception:
            return "Failed to link parent."

    def get_children(self, parent_id: str) -> List[Dict]:
        try:
            c = self._c()
            c.execute("SELECT * FROM users WHERE parent_id = ?", (parent_id,))
            return [dict(r) for r in c.fetchall()]
        except Exception:
            return []

    # === BADGES & CHAT ===
    def add_badge(self, user_id: str, badge: str):
        try:
            user = self.get_user(user_id)
            if not user: return
            badges = json.loads(user.get("badges", "[]"))
            if badge not in badges:
                badges.append(badge)
                self._c().execute("UPDATE users SET badges = ? WHERE user_id = ?", (json.dumps(badges), user_id))
                self.commit()
        except Exception:
            pass

    def add_chat_history(self, user_id: str, subject: str, q: str, r: str):
        try:
            self._c().execute('''
            INSERT INTO chat_history (user_id, subject, user_query, ai_response) 
            VALUES (?, ?, ?, ?)
            ''', (user_id, subject, q, r))
            self._c().execute("UPDATE users SET total_queries = total_queries + 1 WHERE user_id = ?", (user_id,))
            self.commit()
        except Exception:
            pass

    def add_pdf_upload(self, user_id: str, filename: str):
        try:
            self._c().execute("INSERT INTO pdf_uploads (user_id, filename) VALUES (?, ?)", (user_id, filename))
            self.commit()
        except Exception:
            pass

    def get_pdf_count_today(self, user_id: str) -> int:
        try:
            c = self._c()
            c.execute("SELECT COUNT(*) FROM pdf_uploads WHERE user_id = ? AND upload_date = ?", (user_id, date.today().isoformat()))
            return c.fetchone()[0]
        except Exception:
            return 0

    # === ADMIN ===
    def get_all_users(self) -> List[Dict]:
        try:
            c = self._c()
            c.execute("SELECT user_id, email, name, role, is_premium, created_at FROM users")
            return [dict(r) for r in c.fetchall()]
        except Exception:
            return []

    def toggle_premium(self, user_id: str):
        try:
            self._c().execute("UPDATE users SET is_premium = NOT is_premium WHERE user_id = ?", (user_id,))
            self.commit()
        except Exception:
            pass

    def get_daily_query_count(self, user_id: str) -> int:
        try:
            c = self._c()
            c.execute('''
            SELECT COUNT(*) FROM chat_history 
            WHERE user_id = ? AND date(timestamp) = ?
            ''', (user_id, date.today().isoformat()))
            return c.fetchone()[0]
        except Exception:
            return 0
