# database.py — FINAL 2025 | Leaderboards + Projects + Shop + All Features
import sqlite3
import bcrypt
from datetime import datetime, timedelta

DB_PATH = "kenyan_edtech.db"

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
            xp_coins INTEGER DEFAULT 100,
            total_xp INTEGER DEFAULT 100,
            streak INTEGER DEFAULT 0,
            is_premium INTEGER DEFAULT 0,
            premium_expiry TEXT,
            is_banned INTEGER DEFAULT 0,
            daily_questions_used INTEGER DEFAULT 0,
            last_question_date TEXT,
            shop_discount INTEGER DEFAULT 0,
            extra_questions INTEGER DEFAULT 0,
            custom_badge TEXT,
            extra_ai_uses INTEGER DEFAULT 0,
            profile_theme TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS exam_scores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            exam_type TEXT,
            subject TEXT,
            score REAL,
            timestamp TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            subject TEXT,
            title TEXT,
            description TEXT,
            grade REAL,
            feedback TEXT,
            timestamp TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS purchases (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            item_name TEXT,
            price_paid INTEGER,
            timestamp TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            phone TEXT,
            mpesa_code TEXT,
            timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
            approved INTEGER DEFAULT 0
        );
        """)
        self.conn.commit()

    def _create_emperor_admin(self):
        hashed = bcrypt.hashpw(b"@Unruly10", bcrypt.gensalt())
        self.conn.execute("""
            INSERT OR IGNORE INTO users 
            (email, password_hash, username, level, xp_coins, total_xp, is_premium)
            VALUES ('kingmumo15@gmail.com', ?, 'EmperorUnruly', 999, 9999999, 9999999, 1)
        """, (hashed,))
        self.conn.commit()

    def auto_downgrade(self):
        now = datetime.now().isoformat()
        self.conn.execute("UPDATE users SET is_premium=0, premium_expiry=NULL WHERE premium_expiry < ? AND is_premium=1", (now,))
        self.conn.commit()

    def create_user(self, email, password):
        try:
            hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt())
            cur = self.conn.execute("INSERT INTO users (email, password_hash) VALUES (?, ?)", (email.lower(), hashed))
            self.conn.commit()
            return cur.lastrowid
        except sqlite3.IntegrityError:
            return None

    def get_user_by_email(self, email):
        row = self.conn.execute("SELECT * FROM users WHERE email=?", (email.lower(),)).fetchone()
        return dict(row) if row else None

    def get_user(self, user_id):
        row = self.conn.execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone()
        return dict(row) if row else None

    def add_xp(self, user_id, points):
        self.conn.execute("UPDATE users SET total_xp = total_xp + ?, xp_coins = xp_coins + ? WHERE user_id=?", (points, points, user_id))
        self.conn.commit()

    def spend_xp_coins(self, user_id, amount):
        self.conn.execute("UPDATE users SET xp_coins = xp_coins - ? WHERE user_id=?", (amount, user_id))
        self.conn.commit()

    def log_purchase(self, user_id, item_name, price):
        self.conn.execute("INSERT INTO purchases (user_id, item_name, price_paid) VALUES (?, ?, ?)", (user_id, item_name, price))
        self.conn.commit()

    def submit_project(self, user_id, subject, title, description):
        self.conn.execute("INSERT INTO projects (user_id, subject, title, description) VALUES (?, ?, ?, ?)",
                          (user_id, subject, title, description))
        self.conn.commit()

    def get_pending_projects(self):
        rows = self.conn.execute("SELECT p.*, u.email, u.username FROM projects p JOIN users u ON p.user_id = u.user_id WHERE p.grade IS NULL").fetchall()
        return [dict(row) for row in rows]

    def grade_project(self, project_id, grade, feedback):
        self.conn.execute("UPDATE projects SET grade=?, feedback=? WHERE id=?", (grade, feedback, project_id))
        self.conn.commit()

    def get_user_projects(self, user_id):
        rows = self.conn.execute("SELECT * FROM projects WHERE user_id=? ORDER BY timestamp DESC", (user_id,)).fetchall()
        return [dict(row) for row in rows]

    # Leaderboards
    def get_leaderboard(self, metric="total_xp", limit=20):
        valid_metrics = ["total_xp", "xp_coins", "level"]
        if metric not in valid_metrics:
            metric = "total_xp"
        rows = self.conn.execute(f"""
            SELECT username, email, {metric}, custom_badge 
            FROM users 
            WHERE is_banned=0 
            ORDER BY {metric} DESC 
            LIMIT ?
        """, (limit,))
        return [dict(row) for row in rows]

    def get_subject_leaderboard(self, subject, limit=20):
        rows = self.conn.execute("""
            SELECT u.username, u.email, AVG(e.score) as avg_score, u.custom_badge
            FROM exam_scores e
            JOIN users u ON e.user_id = u.user_id
            WHERE e.subject = ? AND u.is_banned=0
            GROUP BY u.user_id
            ORDER BY avg_score DESC
            LIMIT ?
        """, (subject, limit))
        return [dict(row) for row in rows]

    def add_payment(self, user_id, phone, code):
        self.conn.execute("INSERT INTO payments (user_id, phone, mpesa_code) VALUES (?, ?, ?)", (user_id, phone, code))
        self.conn.commit()

    def get_pending_payments(self):
        rows = self.conn.execute("SELECT * FROM payments WHERE approved=0").fetchall()
        return [dict(row) for row in rows]

    def approve_payment(self, payment_id):
        expiry = (datetime.now() + timedelta(days=30)).isoformat()
        row = self.conn.execute("SELECT user_id FROM payments WHERE id=?", (payment_id,)).fetchone()
        if row:
            self.conn.execute("UPDATE users SET is_premium=1, premium_expiry=? WHERE user_id=?", (expiry, row['user_id']))
            self.conn.execute("UPDATE payments SET approved=1 WHERE id=?", (payment_id,))
            self.conn.commit()

    def ban_user(self, user_id): self.conn.execute("UPDATE users SET is_banned=1 WHERE user_id=?", (user_id,)); self.conn.commit()
    def unban_user(self, user_id): self.conn.execute("UPDATE users SET is_banned=0 WHERE user_id=?", (user_id,)); self.conn.commit()
    def upgrade_to_premium(self, user_id):
        expiry = (datetime.now() + timedelta(days=30)).isoformat()
        self.conn.execute("UPDATE users SET is_premium=1, premium_expiry=? WHERE user_id=?", (expiry, user_id))
        self.conn.commit()
    def downgrade_to_basic(self, user_id):
        self.conn.execute("UPDATE users SET is_premium=0, premium_expiry=NULL WHERE user_id=?", (user_id,))
        self.conn.commit()

    def close(self):
        self.conn.close()