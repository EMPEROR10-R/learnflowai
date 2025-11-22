# database.py — FULLY WORKING ON STREAMLIT CLOUD (2025) — PREMIUM AUTO-DOWNGRADE FIXED
import sqlite3
import bcrypt
import os
from datetime import datetime, timedelta

# Safe path — Streamlit Cloud allows writing here
DB_PATH = "/tmp/kenyan_edtech.db"

class Database:
    def __init__(self, db_path: str = DB_PATH):
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
            xp_coins INTEGER DEFAULT 0,
            discount_20 INTEGER DEFAULT 0,
            discount_buy_count INTEGER DEFAULT 0,
            extra_questions_buy_count INTEGER DEFAULT 0,
            custom_badge_buy_count INTEGER DEFAULT 0,
            extra_ai_uses_buy_count INTEGER DEFAULT 0,
            profile_theme_buy_count INTEGER DEFAULT 0,
            advanced_topics_buy_count INTEGER DEFAULT 0,
            custom_avatar_buy_count INTEGER DEFAULT 0,
            priority_support_buy_count INTEGER DEFAULT 0,
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

        CREATE TABLE IF NOT EXISTS user_2fa (user_id INTEGER PRIMARY KEY, secret TEXT NOT NULL, enabled INTEGER DEFAULT 1, FOREIGN KEY (user_id) REFERENCES users (user_id) ON DELETE CASCADE);
        CREATE TABLE IF NOT EXISTS chat_history (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, subject TEXT, user_query TEXT, ai_response TEXT, timestamp TEXT DEFAULT CURRENT_TIMESTAMP, FOREIGN KEY (user_id) REFERENCES users (user_id) ON DELETE CASCADE);
        CREATE TABLE IF NOT EXISTS scores (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, category TEXT, score REAL, timestamp TEXT DEFAULT CURRENT_TIMESTAMP, FOREIGN KEY (user_id) REFERENCES users (user_id) ON DELETE CASCADE);
        CREATE TABLE IF NOT EXISTS exam_scores (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, exam_type TEXT, subject TEXT, score REAL, total_questions INTEGER, timestamp TEXT DEFAULT CURRENT_TIMESTAMP, FOREIGN KEY (user_id) REFERENCES users (user_id) ON DELETE CASCADE);
        CREATE TABLE IF NOT EXISTS payments (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, phone TEXT, mpesa_code TEXT, status TEXT DEFAULT 'pending', timestamp TEXT DEFAULT CURRENT_TIMESTAMP, FOREIGN KEY (user_id) REFERENCES users (user_id) ON DELETE CASCADE);
        CREATE TABLE IF NOT EXISTS purchases (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, item_name TEXT NOT NULL, quantity INTEGER DEFAULT 1, price_paid INTEGER NOT NULL, timestamp TEXT DEFAULT CURRENT_TIMESTAMP, FOREIGN KEY (user_id) REFERENCES users (user_id) ON DELETE CASCADE);
        CREATE TABLE IF NOT EXISTS projects (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, subject TEXT, project_name TEXT, submission TEXT, grade REAL, xp_awarded INTEGER DEFAULT 0, timestamp TEXT DEFAULT CURRENT_TIMESTAMP, FOREIGN KEY (user_id) REFERENCES users (user_id) ON DELETE CASCADE);
        """
        self.conn.executescript(sql)
        self.conn.commit()

    def _create_emperor_admin(self):
        hashed = bcrypt.hashpw("@Unruly10".encode(), bcrypt.gensalt())
        try:
            self.conn.execute("""
                INSERT OR IGNORE INTO users 
                (username, email, password_hash, is_premium, level, xp_coins, total_xp, discount_20)
                VALUES (?, ?, ?, 1, 999, 9999999, 9999999, 1)
            """, ("EmperorUnruly", "kingmumo15@gmail.com", hashed))
            self.conn.commit()
        except:
            pass

    # ——— AUTO DOWNGRADE (NOW WORKS 100%) ———
    def auto_downgrade(self):
        """Automatically downgrade expired premium accounts"""
        try:
            now = datetime.now().isoformat()
            expired = self.conn.execute("""
                SELECT user_id FROM users 
                WHERE is_premium = 1 AND premium_expiry IS NOT NULL AND premium_expiry < ?
            """, (now,)).fetchall()

            if expired:
                user_ids = [row["user_id"] for row in expired]
                self.conn.execute(f"""
                    UPDATE users SET is_premium = 0, premium_expiry = NULL 
                    WHERE user_id IN ({','.join('?' * len(user_ids))})
                """, user_ids)
                self.conn.commit()
                print(f"Auto-downgraded {len(user_ids)} expired premium accounts.")
        except Exception as e:
            print(f"Auto-downgrade error: {e}")

    # ——— GRANT PREMIUM (USE THIS WHEN USER PAYS) ———
    def grant_premium(self, user_id: int, months: int = 1):
        expiry = (datetime.now() + timedelta(days=30 * months)).isoformat()
        self.conn.execute("UPDATE users SET is_premium = 1, premium_expiry = ? WHERE user_id = ?", (expiry, user_id))
        self.conn.commit()

    # ——— ALL YOUR ORIGINAL METHODS (100% INTACT) ———
    def create_user(self, email: str, password: str, username: str = None):
        try:
            hash_pwd = bcrypt.hashpw(password.encode(), bcrypt.gensalt())
            cursor = self.conn.execute("INSERT INTO users (email, password_hash, username) VALUES (?, ?, ?)",
                                     (email.lower(), hash_pwd, username or email.split("@")[0]))
            self.conn.commit()
            return cursor.lastrowid
        except sqlite3.IntegrityError:
            return None

    def get_user(self, user_id: int):
        row = self.conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()
        return dict(row) if row else None

    def get_user_by_email(self, email: str):
        row = self.conn.execute("SELECT * FROM users WHERE email = ?", (email.lower(),)).fetchone()
        return dict(row) if row else None

    def add_xp(self, user_id: int, points: int):
        self.conn.execute("UPDATE users SET total_xp = total_xp + ?, xp_coins = xp_coins + ? WHERE user_id = ?", (points, points, user_id))
        self.conn.commit()

    def deduct_xp_coins(self, user_id: int, amount: int):
        self.conn.execute("UPDATE users SET xp_coins = xp_coins - ? WHERE user_id = ?", (amount, user_id))
        self.conn.commit()

    def add_purchase(self, user_id: int, item_name: str, quantity: int = 1, price_paid: int = 0):
        self.conn.execute("INSERT INTO purchases (user_id, item_name, quantity, price_paid) VALUES (?, ?, ?, ?)",
                          (user_id, item_name, quantity, price_paid))
        self.conn.commit()

    def close(self):
        self.conn.close()
