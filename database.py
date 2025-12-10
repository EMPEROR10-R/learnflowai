# database.py — FIXED 2025: Admin Excluded Everywhere + Added get_user_scores + Purchases Tracking + Auto-Downgrade
import sqlite3
import bcrypt
from datetime import datetime, timedelta

DB_PATH = "/tmp/kenyan_edtech.db"  # Or use ':memory:' for testing

class Database:
    def __init__(self, db_path=DB_PATH):
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._create_tables()
        self._create_emperor_admin()

    def _create_tables(self):
        self.conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            password_hash BLOB NOT NULL,
            username TEXT,
            level INTEGER DEFAULT 1,
            xp_coins INTEGER DEFAULT 0,
            total_xp INTEGER DEFAULT 0,
            streak INTEGER DEFAULT 0,
            is_premium INTEGER DEFAULT 0,
            premium_expiry TEXT,
            is_banned INTEGER DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS exam_scores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            exam_type TEXT,
            subject TEXT,
            score REAL,
            timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (user_id)
        );
        CREATE TABLE IF NOT EXISTS purchases (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            item_name TEXT,
            price_paid INTEGER,
            timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (user_id)
        );
        """)
        self.conn.commit()

    def _create_emperor_admin(self):
        hashed = bcrypt.hashpw(b"@Unruly10", bcrypt.gensalt())
        self.conn.execute("""
            INSERT OR IGNORE INTO users (email, password_hash, username, level, xp_coins, total_xp, is_premium)
            VALUES ('kingmumo15@gmail.com', ?, 'EmperorUnruly', 999, 9999999, 9999999, 1)
        """, (hashed,))
        self.conn.commit()

    def auto_downgrade(self):
        now = datetime.now().isoformat()
        self.conn.execute("UPDATE users SET is_premium=0 WHERE premium_expiry < ? AND is_premium=1", (now,))
        self.conn.commit()

    def create_user(self, email, password):
        try:
            hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt())
            cur = self.conn.execute("INSERT INTO users (email, password_hash) VALUES (?, ?)", (email, hashed))
            self.conn.commit()
            return cur.lastrowid
        except sqlite3.IntegrityError:
            return None

    def get_user_by_email(self, email):
        row = self.conn.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
        return dict(row) if row else None

    def get_user(self, user_id):
        row = self.conn.execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone()
        return dict(row) if row else None

    def add_xp(self, user_id, points):
        self.conn.execute("UPDATE users SET total_xp = total_xp + ?, xp_coins = xp_coins + ? WHERE user_id=?", (points, points, user_id))
        self.conn.commit()

    def deduct_xp_coins(self, user_id, amount):
        self.conn.execute("UPDATE users SET xp_coins = xp_coins - ? WHERE user_id=?", (amount, user_id))
        self.conn.commit()

    def get_xp_leaderboard(self):
        rows = self.conn.execute("""
            SELECT email, total_xp, level FROM users 
            WHERE is_banned=0 AND email != 'kingmumo15@gmail.com'
            ORDER BY total_xp DESC LIMIT 20
        """).fetchall()
        return [dict(row) for row in rows]

    def get_user_scores(self, user_id):
        rows = self.conn.execute("SELECT * FROM exam_scores WHERE user_id=?", (user_id,)).fetchall()
        return [dict(row) for row in rows]

    def close(self):
        self.conn.close()