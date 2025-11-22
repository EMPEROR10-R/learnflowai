# database.py — UPDATED 2025: Users Start at Level 0 + Added XP Coins, Buy Counts, Inventory Tracking + All Previous Features Intact
import sqlite3
import bcrypt
import json
import pyotp
import qrcode
import io
from datetime import datetime, date, timedelta
from typing import List, Dict, Any, Optional

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
            extra_questions_buy_count INTEGER DEFAULT 0,
            custom_badge_buy_count INTEGER DEFAULT 0,
            total_spent_coins INTEGER DEFAULT 0,
            level INTEGER DEFAULT 0,  # Changed to start at 0 for regular users
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

        CREATE TABLE IF NOT EXISTS leaderboard_resets (
            reset_date TEXT PRIMARY KEY,
            performed_by TEXT
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

        -- NEW: Purchases Table for Inventory Tracking
        CREATE TABLE IF NOT EXISTS purchases (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            item_name TEXT NOT NULL,
            quantity INTEGER DEFAULT 1,
            price_paid INTEGER NOT NULL,
            timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (user_id) ON DELETE CASCADE
        );
        """
        self.conn.executescript(sql)
        self.conn.commit()

    def _create_emperor_admin(self):
        hashed = bcrypt.hashpw("@Unruly10".encode(), bcrypt.gensalt())
        try:
            self.conn.execute("""INSERT INTO users
                (username, email, password_hash, is_premium, level, xp_coins, discount_20, total_xp, spendable_xp)
                VALUES (?, ?, ?, 1, 999, 999999, 1, 999999, 999999)""",
                ("EmperorUnruly", "kingmumo15@gmail.com", hashed))
            self.conn.commit()
        except Exception:
            pass

    def create_user(self, email: str, password: str, username: Optional[str] = None) -> Optional[int]:
        try:
            hash_pwd = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
            cursor = self.conn.execute(
                "INSERT INTO users (email, username, password_hash) VALUES (?, ?, ?)",
                (email.lower(), username, hash_pwd)
            )
            self.conn.commit()
            return cursor.lastrowid
        except sqlite3.IntegrityError:
            return None

    def get_user(self, user_id: int) -> Optional[Dict]:
        row = self.conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()
        return dict(row) if row else None

    def get_user_by_email(self, email: str) -> Optional[Dict]:
        row = self.conn.execute("SELECT * FROM users WHERE email = ?", (email.lower(),)).fetchone()
        return dict(row) if row else None

    def get_user_by_id(self, uid: int) -> Dict:
        row = self.conn.execute("SELECT * FROM users WHERE user_id=?", (uid,)).fetchone()
        return dict(row) if row else {}

    def get_all_users(self) -> List[Dict]:
        rows = self.conn.execute("SELECT * FROM users ORDER BY created_at DESC").fetchall()
        return [dict(row) for row in rows]

    def update_password(self, user_id: int, new_password: str):
        hash_pwd = bcrypt.hashpw(new_password.encode('utf-8'), bcrypt.gensalt())
        self.conn.execute("UPDATE users SET password_hash = ? WHERE user_id = ?", (hash_pwd, user_id))
        self.conn.commit()

    def update_user_activity(self, user_id: int):
        today = date.today().isoformat()
        self.conn.execute(
            "UPDATE users SET last_active = ?, last_daily_reset = COALESCE(last_daily_reset, ?) WHERE user_id = ?",
            (today, today, user_id)
        )
        self.conn.commit()

    def ban_user(self, user_id: int):
        self.conn.execute("UPDATE users SET is_banned = 1 WHERE user_id = ?", (user_id,))
        self.conn.commit()

    def unban_user(self, user_id: int):
        self.conn.execute("UPDATE users SET is_banned = 0 WHERE user_id = ?", (user_id,))
        self.conn.commit()

    def upgrade_to_premium(self, user_id: int):
        expiry = (date.today() + timedelta(days=30)).isoformat()
        self.conn.execute(
            "UPDATE users SET is_premium = 1, premium_expiry = ? WHERE user_id = ?",
            (expiry, user_id)
        )
        self.conn.commit()

    def downgrade_to_basic(self, user_id: int):
        self.conn.execute("UPDATE users SET is_premium = 0, premium_expiry = NULL WHERE user_id = ?", (user_id,))
        self.conn.commit()

    def auto_downgrade(self):
        today = datetime.now().strftime("%Y-%m-%d")
        self.conn.execute("""
            UPDATE users SET is_premium = 0, premium_expiry = NULL
            WHERE premium_expiry < ? AND is_premium = 1
        """, (today,))
        self.conn.commit()

    def add_xp(self, user_id: int, points: int, spendable: bool = True):
        sql = "UPDATE users SET total_xp = total_xp + ?, xp_coins = xp_coins + ?"
        params = [points, points]
        if spendable:
            sql += ", spendable_xp = spendable_xp + ?"
            params.append(points)
        sql += " WHERE user_id = ?"
        params.append(user_id)
        self.conn.execute(sql, params)
        self.conn.commit()

    def deduct_xp_coins(self, user_id: int, amount: int):
        self.conn.execute("""
            UPDATE users SET xp_coins = xp_coins - ?, total_spent_coins = total_spent_coins + ?
            WHERE user_id = ?
        """, (amount, amount, user_id))
        self.conn.commit()

    def increment_buy_count(self, user_id: int, column: str):
        self.conn.execute(f"UPDATE users SET {column} = {column} + 1 WHERE user_id = ?", (user_id,))
        self.conn.commit()

    def buy_discount_cheque(self, user_id: int) -> bool:
        user = self.get_user(user_id)
        buy_count = user["discount_buy_count"]
        price = 5000000 * (2 ** buy_count)
        if user["xp_coins"] >= price:
            self.deduct_xp_coins(user_id, price)
            self.increment_buy_count(user_id, "discount_buy_count")
            self.conn.execute("UPDATE users SET discount_20 = 1 WHERE user_id = ?", (user_id,))
            self.add_purchase(user_id, "Discount Cheque", 1, price)
            self.conn.commit()
            return True
        return False

    def buy_extra_questions(self, user_id: int) -> bool:
        user = self.get_user(user_id)
        buy_count = user["extra_questions_buy_count"]
        price = 100 * (2 ** max(0, buy_count - 1)) if buy_count > 0 else 100
        if user["xp_coins"] >= price:
            self.deduct_xp_coins(user_id, price)
            self.increment_buy_count(user_id, "extra_questions_buy_count")
            self.conn.execute("UPDATE users SET daily_questions = daily_questions + 10 WHERE user_id = ?", (user_id,))
            self.add_purchase(user_id, "Extra Questions", 1, price)
            self.conn.commit()
            return True
        return False

    def buy_custom_badge(self, user_id: int) -> bool:
        user = self.get_user(user_id)
        buy_count = user["custom_badge_buy_count"]
        price = 500000 * (2 ** max(0, buy_count - 1)) if buy_count > 0 else 500000
        if user["xp_coins"] >= price:
            self.deduct_xp_coins(user_id, price)
            self.increment_buy_count(user_id, "custom_badge_buy_count")
            badges = json.loads(user.get("badges", "[]"))
            badges.append(f"Custom Badge #{buy_count + 1}")
            self.conn.execute("UPDATE users SET badges = ? WHERE user_id = ?", (json.dumps(badges), user_id))
            self.add_purchase(user_id, "Custom Badge", 1, price)
            self.conn.commit()
            return True
        return False

    def add_purchase(self, user_id: int, item_name: str, quantity: int, price_paid: int):
        self.conn.execute("""
            INSERT INTO purchases (user_id, item_name, quantity, price_paid)
            VALUES (?, ?, ?, ?)
        """, (user_id, item_name, quantity, price_paid))
        self.conn.commit()

    def get_user_purchases(self, user_id: int) -> List[Dict]:
        rows = self.conn.execute("""
            SELECT item_name, quantity, price_paid, timestamp
            FROM purchases WHERE user_id = ? ORDER BY timestamp DESC
        """, (user_id,)).fetchall()
        return [dict(row) for row in rows]

    def is_2fa_enabled(self, user_id: int) -> bool:
        row = self.conn.execute("SELECT enabled FROM user_2fa WHERE user_id = ?", (user_id,)).fetchone()
        return bool(row and row["enabled"])

    def enable_2fa(self, user_id: int) -> tuple:
        secret = pyotp.random_base32()
        self.conn.execute("INSERT OR REPLACE INTO user_2fa (user_id, secret) VALUES (?, ?)", (user_id, secret))
        self.conn.commit()
        uri = pyotp.totp.TOTP(secret).provisioning_uri(name=self.get_user(user_id)["email"], issuer_name="Kenyan EdTech")
        qr = qrcode.make(uri)
        return secret, qr

    def verify_2fa_code(self, user_id: int, code: str) -> bool:
        row = self.conn.execute("SELECT secret FROM user_2fa WHERE user_id = ?", (user_id,)).fetchone()
        if row:
            totp = pyotp.TOTP(row["secret"])
            return totp.verify(code)
        return False

    def add_score(self, user_id: int, category: str, score: float):
        self.conn.execute(
            "INSERT INTO scores (user_id, category, score) VALUES (?, ?, ?)",
            (user_id, category, score)
        )
        self.conn.commit()

    def get_leaderboard(self, category: str) -> List[Dict]:
        rows = self.conn.execute("""
            SELECT u.email, AVG(s.score) as score
            FROM scores s JOIN users u ON s.user_id = u.user_id
            WHERE s.category = ? AND u.is_banned = 0
            GROUP BY s.user_id ORDER BY score DESC LIMIT 10
        """, (category,)).fetchall()
        return [dict(row) for row in rows]

    def get_xp_leaderboard(self) -> List[Dict]:
        rows = self.conn.execute("""
            SELECT email, total_xp
            FROM users WHERE is_banned = 0 ORDER BY total_xp DESC LIMIT 10
        """).fetchall()
        return [dict(row) for row in rows]

    def add_payment(self, user_id: int, phone: str, mpesa_code: str):
        self.conn.execute("INSERT INTO payments (user_id, phone, mpesa_code) VALUES (?, ?, ?)", (user_id, phone, mpesa_code))
        self.conn.commit()

    def get_pending_payments(self) -> List[Dict]:
        rows = self.conn.execute("SELECT * FROM payments WHERE status = 'pending'").fetchall()
        return [dict(row) for row in rows]

    def approve_payment(self, payment_id: int):
        expiry = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d")
        self.conn.execute("UPDATE payments SET status='approved' WHERE id=?", (payment_id,))
        user_id = self.conn.execute("SELECT user_id FROM payments WHERE id=?", (payment_id,)).fetchone()["user_id"]
        self.conn.execute("UPDATE users SET is_premium=1, premium_expiry=? WHERE user_id=?", (expiry, user_id))
        self.conn.commit()

    def close(self):
        self.conn.close()
