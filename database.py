# database.py
import sqlite3
import bcrypt
import uuid
from datetime import datetime
from typing import List, Dict, Optional

class Database:
    ADMIN_EMAIL = "kingmumo15@gmail.com"
    ADMIN_PASSWORD = "@Yoounruly10"

    def __init__(self, db_path: str = "users.db"):
        self.db_path = db_path
        self.init_db()
        self.ensure_admin()

    def get_conn(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def init_db(self):
        conn = self.get_conn()
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS users (
            user_id TEXT PRIMARY KEY, name TEXT, email TEXT UNIQUE,
            password_hash TEXT, role TEXT DEFAULT 'user', is_premium INTEGER DEFAULT 0,
            two_fa_secret TEXT, parent_id TEXT
        )''')
        c.execute('''CREATE TABLE IF NOT EXISTS activity_log (
            id INTEGER PRIMARY KEY, user_id TEXT, action TEXT, timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )''')
        c.execute('''CREATE TABLE IF NOT EXISTS manual_payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT, phone TEXT,
            mpesa_code TEXT, status TEXT DEFAULT 'pending', requested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            processed_at TIMESTAMP
        )''')
        c.execute('''CREATE TABLE IF NOT EXISTS quiz_scores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT, subject TEXT, score INTEGER, total INTEGER, timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )''')
        c.execute('''CREATE TABLE IF NOT EXISTS user_badges (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT, badge_key TEXT, unlocked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, badge_key)
        )''')
        conn.commit()
        conn.close()

    def ensure_admin(self):
        if not self.get_user_by_email(self.ADMIN_EMAIL):
            self.create_user("King Mumo", self.ADMIN_EMAIL, self.ADMIN_PASSWORD, role="admin", premium=1)

    def create_user(self, name: str, email: str, password: str, phone: str = "", role: str = "user", premium: int = 0):
        user_id = str(uuid.uuid4())
        hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt(12)).decode('utf-8')
        conn = self.get_conn()
        c = conn.cursor()
        try:
            c.execute("INSERT INTO users VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                      (user_id, name, email, hashed, role, premium, None, None))
            conn.commit()
        except: pass
        conn.close()
        return user_id

    def get_user_by_email(self, email: str) -> Optional[Dict]:
        conn = self.get_conn()
        c = conn.cursor()
        c.execute("SELECT * FROM users WHERE email = ?", (email,))
        row = c.fetchone()
        conn.close()
        return dict(row) if row else None

    def log_activity(self, user_id: str, action: str):
        try:
            conn = self.get_conn()
            c = conn.cursor()
            c.execute("INSERT INTO activity_log (user_id, action) VALUES (?, ?)", (user_id, action))
            conn.commit()
            conn.close()
        except: pass

    def get_pending_payments(self) -> List[Dict]:
        conn = self.get_conn()
        c = conn.cursor()
        c.execute("""SELECT mp.*, u.name, u.email FROM manual_payments mp
                     JOIN users u ON mp.user_id = u.user_id
                     WHERE mp.status = 'pending' ORDER BY requested_at DESC""")
        rows = c.fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def approve_payment(self, payment_id: int):
        conn = self.get_conn()
        c = conn.cursor()
        c.execute("UPDATE manual_payments SET status='approved', processed_at=CURRENT_TIMESTAMP WHERE id=?", (payment_id,))
        c.execute("SELECT user_id FROM manual_payments WHERE id=?", (payment_id,))
        user_id = c.fetchone()["user_id"]
        c.execute("UPDATE users SET is_premium=1 WHERE user_id=?", (user_id,))
        conn.commit()
        conn.close()

    def reject_payment(self, payment_id: int):
        conn = self.get_conn()
        c = conn.cursor()
        c.execute("UPDATE manual_payments SET status='rejected' WHERE id=?", (payment_id,))
        conn.commit()
        conn.close()

    def get_all_users(self): 
        conn = self.get_conn()
        c = conn.cursor()
        c.execute("SELECT * FROM users")
        rows = c.fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def get_revenue(self):
        conn = self.get_conn()
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM manual_payments WHERE status='approved'")
        count = c.fetchone()[0]
        conn.close()
        return count * 500

    # QUIZ & BADGES
    def record_quiz_score(self, user_id: str, subject: str, score: int, total: int):
        conn = self.get_conn()
        c = conn.cursor()
        c.execute("INSERT INTO quiz_scores (user_id, subject, score, total) VALUES (?, ?, ?, ?)",
                  (user_id, subject, score, total))
        conn.commit()
        conn.close()

    def get_leaderboard(self, limit: int = 10) -> List[Dict]:
        conn = self.get_conn()
        c = conn.cursor()
        c.execute("""SELECT u.name, SUM(q.score) as total_score, COUNT(q.id) as quizzes
                     FROM quiz_scores q JOIN users u ON q.user_id = u.user_id
                     GROUP BY q.user_id ORDER BY total_score DESC LIMIT ?""", (limit,))
        rows = c.fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def unlock_badge(self, user_id: str, badge_key: str):
        conn = self.get_conn()
        c = conn.cursor()
        try:
            c.execute("INSERT INTO user_badges (user_id, badge_key) VALUES (?, ?)", (user_id, badge_key))
            conn.commit()
        except sqlite3.IntegrityError:
            pass  # Already unlocked
        conn.close()

    def get_user_badges(self, user_id: str) -> List[str]:
        conn = self.get_conn()
        c = conn.cursor()
        c.execute("SELECT badge_key FROM user_badges WHERE user_id = ?", (user_id,))
        rows = c.fetchall()
        conn.close()
        return [r["badge_key"] for r in rows]
