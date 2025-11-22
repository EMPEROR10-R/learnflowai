# database.py — FULLY FIXED FOR PYTHON 3.13 & STREAMLIT CLOUD
import sqlite3
import bcrypt
import json
import pyotp
import qrcode
import io
from datetime import datetime, date, timedelta
from typing import Optional, Dict, List

class Database:
    def __init__(self, db_path: str = "kenyan_edtech.db"):
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._create_tables()
        self._create_emperor_admin()

    def _create_tables(self):
        sql = """
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE,
            email TEXT UNIQUE NOT NULL,
            password_hash BLOB NOT NULL,
            role TEXT DEFAULT 'user',
            is_banned INTEGER DEFAULT 0,
            is_premium INTEGER DEFAULT 0,
            premium_expiry TEXT,
            total_xp INTEGER DEFAULT 0,
            spendable_xp INTEGER DEFAULT 0,
            xp INTEGER DEFAULT 0,
            xp_coins INTEGER DEFAULT 0,
            discount INTEGER DEFAULT 0,
            discount_20 INTEGER DEFAULT 0,
            discount_buy_count INTEGER DEFAULT 0,
            level INTEGER DEFAULT 1,
            name TEXT,
            badges TEXT DEFAULT '[]',
            streak INTEGER DEFAULT 0,
            last_active TEXT,
            last_streak_date TEXT,
            daily_questions INTEGER DEFAULT 0,
            daily_pdfs INTEGER DEFAULT 0,
            daily_exams INTEGER DEFAULT 0,
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

        CREATE TABLE IF NOT EXISTS exam_scores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            exam_type TEXT,
            subject TEXT,
            score REAL,
            total_questions INTEGER,
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

        CREATE TABLE IF NOT EXISTS projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            subject TEXT,
            project_name TEXT,
            submission TEXT,
            grade REAL,
            xp_awarded INTEGER DEFAULT 0,
            timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (user_id) ON DELETE CASCADE
        );
        """
        self.conn.executescript(sql)
        self.conn.commit()

    def _create_emperor_admin(self):
        hashed = bcrypt.hashpw("@Unruly10".encode(), bcrypt.gensalt())
        try:
            self.conn.execute(
                "INSERT OR IGNORE INTO users (username, email, password_hash, is_premium, level, xp_coins, discount_20, total_xp, spendable_xp) VALUES (?, ?, ?, 1, 999, 999999, 1, 999999, 999999)",
                ("EmperorUnruly", "kingmumo15@gmail.com", hashed)
            )
            self.conn.commit()
        except:
            pass

    # === USER METHODS (ALL PRESERVED) ===
    def create_user(self, email: str, password: str, username: Optional[str] = None) -> Optional[int]:
        try:
            hash_pwd = bcrypt.hashpw(password.encode(), bcrypt.gensalt())
            cur = self.conn.execute(
                "INSERT INTO users (email, username, password_hash) VALUES (?, ?, ?)",
                (email.lower(), username or email.split("@")[0], hash_pwd)
            )
            self.conn.commit()
            return cur.lastrowid
        except sqlite3.IntegrityError:
            return None

    def get_user(self, user_id: int) -> Optional[Dict]:
        row = self.conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()
        return dict(row) if row else None

    def get_user_by_email(self, email: str) -> Optional[Dict]:
        row = self.conn.execute("SELECT * FROM users WHERE email = ?", (email.lower(),)).fetchone()
        return dict(row) if row else None

    def verify_login(self, identifier: str, password: str) -> Optional[Dict]:
        row = self.conn.execute(
            "SELECT * FROM users WHERE email = ? OR username = ?", (identifier.lower(), identifier)
        ).fetchone()
        if row and bcrypt.checkpw(password.encode(), row["password_hash"]):
            return dict(row)
        return None

    # === XP & GAMIFICATION (ALL PRESERVED + ENHANCED) ===
    def add_xp(self, user_id: int, points: int, spendable: bool = False, coins: int = 0):
        user = self.get_user(user_id)
        multiplier = 3 if user["is_premium"] or user.get("username") == "EmperorUnruly" else 1
        points *= multiplier
        coins *= multiplier

        self.conn.execute(
            """UPDATE users SET 
               total_xp = total_xp + ?, 
               spendable_xp = spendable_xp + ?,
               xp = xp + ?,
               xp_coins = xp_coins + ?,
               level = 1 + (xp + ?) // 100
               WHERE user_id = ?""",
            (points, points if spendable else 0, points, coins, points, user_id)
        )
        self.conn.commit()

    def buy_discount_cheque(self, user_id: int) -> bool:
        user = self.get_user(user_id)
        count = user["discount_buy_count"]
        cost = int(1_000_000 * (2.5 ** count))
        if user["is_premium"] or user.get("username") == "EmperorUnruly":
            cost //= 4
        if user["xp_coins"] >= cost:
            self.conn.execute(
                "UPDATE users SET xp_coins = xp_coins - ?, discount_20 = 1, discount_buy_count = discount_buy_count + 1 WHERE user_id = ?",
                (cost, user_id)
            )
            self.conn.commit()
            return True
        return False

    # === PROJECTS (NEW & FULLY WORKING) ===
    def submit_project(self, user_id: int, subject: str, project_name: str, submission: str, grade: float, xp: int):
        self.conn.execute(
            "INSERT INTO projects (user_id, subject, project_name, submission, grade, xp_awarded) VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, subject, project_name, submission, grade, xp)
        )
        self.add_xp(user_id, xp, coins=xp//2)
        self.conn.commit()

    def get_user_projects(self, user_id: int) -> List[Dict]:
        rows = self.conn.execute("SELECT * FROM projects WHERE user_id = ? ORDER BY timestamp DESC", (user_id,)).fetchall()
        return [dict(r) for r in rows]

    # === PAYMENTS & PREMIUM ===
    def upgrade_to_premium(self, user_id: int):
        expiry = (date.today() + timedelta(days=30)).isoformat()
        self.conn.execute("UPDATE users SET is_premium = 1, premium_expiry = ? WHERE user_id = ?", (expiry, user_id))
        self.conn.commit()

    def auto_downgrade(self):
        today = date.today().isoformat()
        self.conn.execute("UPDATE users SET is_premium = 0, premium_expiry = NULL WHERE premium_expiry < ? AND username != 'EmperorUnruly'", (today,))
        self.conn.commit()

    # === DAILY LIMITS ===
    def increment_daily_question(self, user_id: int):
        self.conn.execute("UPDATE users SET daily_questions = daily_questions + 1 WHERE user_id = ?", (user_id,))
        self.conn.commit()

    def close(self):
        self.conn.close()
