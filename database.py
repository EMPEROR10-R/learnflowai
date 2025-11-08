# database.py
import sqlite3
import bcrypt
import uuid
from typing import Optional, Dict, List

class Database:
    ADMIN_EMAIL = "kingmumo15@gmail.com"
    ADMIN_PASSWORD = "@Yoounruly10"

    def __init__(self, db_path: str = "users.db"):
        self.db_path = db_path
        self.init_db()
        self.ensure_admin()

    def get_connection(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def init_db(self):
        conn = self.get_connection()
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS users (
            user_id TEXT PRIMARY KEY,
            name TEXT,
            email TEXT UNIQUE,
            password_hash TEXT,
            role TEXT DEFAULT 'user',
            is_premium INTEGER DEFAULT 0,
            two_fa_secret TEXT,
            parent_id TEXT
        )''')
        c.execute('''CREATE TABLE IF NOT EXISTS activity_log (
            id INTEGER PRIMARY KEY,
            user_id TEXT,
            action TEXT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )''')
        c.execute('''CREATE TABLE IF NOT EXISTS manual_payments (
            id INTEGER PRIMARY KEY,
            user_id TEXT,
            phone TEXT,
            mpesa_code TEXT,
            status TEXT DEFAULT 'pending',
            requested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )''')
        conn.commit()
        conn.close()

    def ensure_admin(self):
        if not self.get_user_by_email(self.ADMIN_EMAIL):
            self.create_user("King Mumo", self.ADMIN_EMAIL, self.ADMIN_PASSWORD, role="admin", premium=1)

    def create_user(self, name: str, email: str, password: str, phone: str = "", role: str = "user", premium: int = 0):
        user_id = str(uuid.uuid4())
        # ALWAYS STORE AS STRING
        hashed = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt(12)).decode('utf-8')
        conn = self.get_connection()
        c = conn.cursor()
        try:
            c.execute("""INSERT INTO users 
                (user_id, name, email, password_hash, role, is_premium) 
                VALUES (?, ?, ?, ?, ?, ?)""",
                (user_id, name, email, hashed, role, premium))
            conn.commit()
        except sqlite3.IntegrityError:
            return False
        finally:
            conn.close()
        return user_id

    def get_user_by_email(self, email: str) -> Optional[Dict]:
        conn = self.get_connection()
        c = conn.cursor()
        c.execute("SELECT * FROM users WHERE email = ?", (email,))
        row = c.fetchone()
        conn.close()
        return dict(row) if row else None

    def get_children(self, parent_id: str) -> List[Dict]:
        conn = self.get_connection()
        c = conn.cursor()
        c.execute("SELECT * FROM users WHERE parent_id = ?", (parent_id,))
        rows = c.fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def log_activity(self, user_id: str, action: str):
        conn = self.get_connection()
        c = conn.cursor()
        c.execute("INSERT INTO activity_log (user_id, action) VALUES (?, ?)", (user_id, action))
        conn.commit()
        conn.close()

    def get_all_users(self) -> List[Dict]:
        conn = self.get_connection()
        c = conn.cursor()
        c.execute("SELECT user_id, name, email, role FROM users")
        rows = c.fetchall()
        conn.close()
        return [dict(r) for r in rows]
