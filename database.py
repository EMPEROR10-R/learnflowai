# database.py
import sqlite3
import json
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Any
import uuid
import bcrypt
import os
import pandas as pd
import pyotp  # pip install pyotp

class Database:
    ADMIN_ROLE = "admin"
    ADMIN_EMAIL = "kingmumo15@gmail.com"
    ADMIN_PASSWORD = "@Yoounruly10"
    BCRYPT_ROUNDS = 12

    def __init__(self, db_path: str = "users.db"):
        self.db_path = db_path
        print(f"[DB] Initializing database at: {self.db_path}")
        self.init_database()
        self.migrate_schema()
        self._ensure_admin_user()

    def get_connection(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def init_database(self):
        print("[DB] Creating tables...")
        conn = self.get_connection()
        cursor = conn.cursor()

        # Users table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id TEXT PRIMARY KEY,
                name TEXT,
                email TEXT UNIQUE,
                password_hash TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_active TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                total_queries INTEGER DEFAULT 0,
                streak_days INTEGER DEFAULT 0,
                last_streak_date DATE,
                badges TEXT DEFAULT '[]',
                is_premium BOOLEAN DEFAULT 0,
                premium_expires_at TIMESTAMP,
                last_payment_ref TEXT,
                last_payment_amount REAL,
                language_preference TEXT DEFAULT 'en',
                learning_goals TEXT DEFAULT '[]',
                role TEXT DEFAULT 'user',
                failed_logins INTEGER DEFAULT 0,
                lockout_until TIMESTAMP,
                two_fa_secret TEXT,
                parent_id TEXT,
                FOREIGN KEY (parent_id) REFERENCES users(user_id) ON DELETE SET NULL
            )
        """)

        # Manual payments
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS manual_payments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                phone TEXT NOT NULL,
                mpesa_code TEXT NOT NULL,
                amount REAL DEFAULT 500,
                status TEXT DEFAULT 'pending',
                requested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                processed_at TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
            )
        """)

        # Activity log
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS activity_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT,
                action TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                duration_minutes INTEGER DEFAULT 0,
                FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
            )
        """)

        # Quiz results
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS quiz_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT,
                subject TEXT,
                exam TEXT,
                score INTEGER,
                total INTEGER,
                date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
            )
        """)

        # Chat history
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS chat_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT,
                subject TEXT,
                user_query TEXT,
                ai_response TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
            )
        """)

        # PDF uploads
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS pdf_uploads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT,
                filename TEXT,
                upload_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
            )
        """)

        # Daily query count (for limits)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS daily_queries (
                user_id TEXT,
                query_date DATE,
                count INTEGER DEFAULT 1,
                PRIMARY KEY (user_id, query_date),
                FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
            )
        """)

        conn.commit()
        conn.close()

    def migrate_schema(self):
        conn = self.get_connection()
        cursor = conn.cursor()
        for col in ["name", "failed_logins", "lockout_until", "two_fa_secret", "parent_id"]:
            try:
                cursor.execute(f"ALTER TABLE users ADD COLUMN {col} TEXT")
            except sqlite3.OperationalError:
                pass
        conn.commit()
        conn.close()

    def _ensure_admin_user(self):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT user_id FROM users WHERE email = ?", (self.ADMIN_EMAIL,))
        if not cursor.fetchone():
            admin_id = str(uuid.uuid4())
            hashed = bcrypt.hashpw(self.ADMIN_PASSWORD.encode(), bcrypt.gensalt(self.BCRYPT_ROUNDS)).decode()
            cursor.execute("""
                INSERT INTO users (user_id, name, email, password_hash, role)
                VALUES (?, ?, ?, ?, ?)
            """, (admin_id, "Admin", self.ADMIN_EMAIL, hashed, self.ADMIN_ROLE))
            print(f"[DB] Admin created: {self.ADMIN_EMAIL}")
        conn.commit()
        conn.close()

    # ==================== USER AUTH ====================
    def create_user(self, email: str, password: str) -> str:
        user_id = str(uuid.uuid4())
        hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt(self.BCRYPT_ROUNDS)).decode()
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("""
                INSERT INTO users (user_id, email, password_hash)
                VALUES (?, ?, ?)
            """, (user_id, email, hashed))
            conn.commit()
        except sqlite3.IntegrityError:
            conn.close()
            return None
        conn.close()
        return user_id

    def get_user_by_email(self, email: str) -> Optional[Dict]:
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE email = ?", (email,))
        row = cursor.fetchone()
        conn.close()
        return dict(row) if row else None

    def get_user(self, user_id: str) -> Optional[Dict]:
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        conn.close()
        return dict(row) if row else None

    def update_user_activity(self, user_id: str):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET last_active = CURRENT_TIMESTAMP WHERE user_id = ?", (user_id,))
        conn.commit()
        conn.close()

    # ==================== 2FA ====================
    def generate_2fa_secret(self, user_id: str):
        secret = pyotp.random_base32()
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET two_fa_secret = ? WHERE user_id = ?", (secret, user_id))
        conn.commit()
        conn.close()
        return secret

    def verify_2fa_code(self, user_id: str, code: str) -> bool:
        user = self.get_user(user_id)
        if not user or not user.get("two_fa_secret"):
            return False
        totp = pyotp.TOTP(user["two_fa_secret"])
        return totp.verify(code)

    def is_2fa_enabled(self, user_id: str) -> bool:
        user = self.get_user(user_id)
        return bool(user and user.get("two_fa_secret"))

    # ==================== PARENT LINKING ====================
    def link_parent(self, child_id: str, parent_email: str, parent_password: str) -> str:
        parent = self.get_user_by_email(parent_email)
        if not parent or not bcrypt.checkpw(parent_password.encode(), parent["password_hash"].encode()):
            return "Invalid parent credentials."
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET parent_id = ? WHERE user_id = ?", (parent["user_id"], child_id))
        conn.commit()
        conn.close()
        return "Parent linked successfully!"

    def get_children(self, parent_id: str) -> List[Dict]:
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE parent_id = ?", (parent_id,))
        rows = cursor.fetchall()
        conn.close()
        return [dict(r) for r in rows]

    # ==================== ACTIVITY LOG ====================
    def log_activity(self, user_id: str, action: str, duration: int = 0):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO activity_log (user_id, action, duration_minutes)
            VALUES (?, ?, ?)
        """, (user_id, action, duration))
        conn.commit()
        conn.close()

    def get_user_activity(self, user_id: str, days: int = 7) -> List[Dict]:
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT action, timestamp, duration_minutes
            FROM activity_log
            WHERE user_id = ? AND timestamp > datetime('now', ?)
            ORDER BY timestamp DESC
        """, (user_id, f"-{days} days"))
        rows = cursor.fetchall()
        conn.close()
        return [dict(r) for r in rows]

    # ==================== STREAK & BADGES ====================
    def update_streak(self, user_id: str) -> int:
        user = self.get_user(user_id)
        if not user:
            return 0
        today = datetime.now().date()
        last_date = user["last_streak_date"]
        if last_date:
            last_date = datetime.strptime(last_date, "%Y-%m-%d").date()
            if today == last_date:
                return user["streak_days"]
            elif today == last_date + timedelta(days=1):
                new_streak = user["streak_days"] + 1
            else:
                new_streak = 1
        else:
            new_streak = 1
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE users SET streak_days = ?, last_streak_date = ?
            WHERE user_id = ?
        """, (new_streak, today.strftime("%Y-%m-%d"), user_id))
        conn.commit()
        conn.close()
        return new_streak

    def add_badge(self, user_id: str, badge: str):
        user = self.get_user(user_id)
        badges = json.loads(user.get("badges", "[]"))
        if badge not in badges:
            badges.append(badge)
            conn = self.get_connection()
            cursor = conn.cursor()
            cursor.execute("UPDATE users SET badges = ? WHERE user_id = ?", (json.dumps(badges), user_id))
            conn.commit()
            conn.close()

    # ==================== PREMIUM & LIMITS ====================
    def check_premium(self, user_id: str) -> bool:
        user = self.get_user(user_id)
        if not user or not user["is_premium"]:
            return False
        expires = datetime.fromisoformat(user["premium_expires_at"]) if user["premium_expires_at"] else datetime.min
        return datetime.now() < expires

    def get_daily_query_count(self, user_id: str) -> int:
        today = datetime.now().date().isoformat()
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT count FROM daily_queries WHERE user_id = ? AND query_date = ?
        """, (user_id, today))
        row = cursor.fetchone()
        count = row["count"] if row else 0
        conn.close()
        return count

    def increment_query_count(self, user_id: str):
        today = datetime.now().date().isoformat()
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO daily_queries (user_id, query_date, count)
            VALUES (?, ?, 1)
            ON CONFLICT(user_id, query_date) DO UPDATE SET count = count + 1
        """, (user_id, today))
        conn.commit()
        conn.close()

    def get_pdf_count_today(self, user_id: str) -> int:
        today = datetime.now().date().isoformat()
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT COUNT(*) as count FROM pdf_uploads
            WHERE user_id = ? AND date(upload_date) = ?
        """, (user_id, today))
        row = cursor.fetchone()
        conn.close()
        return row["count"] if row else 0

    def add_pdf_upload(self, user_id: str, filename: str):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO pdf_uploads (user_id, filename)
            VALUES (?, ?)
        """, (user_id, filename))
        conn.commit()
        conn.close()

    # ==================== CHAT & QUIZ ====================
    def add_chat_history(self, user_id: str, subject: str, user_query: str, ai_response: str):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO chat_history (user_id, subject, user_query, ai_response)
            VALUES (?, ?, ?, ?)
        """, (user_id, subject, user_query, ai_response))
        cursor.execute("UPDATE users SET total_queries = total_queries + 1 WHERE user_id = ?", (user_id,))
        conn.commit()
        conn.close()
        self.increment_query_count(user_id)

    def add_quiz_result(self, user_id: str, subject: str, exam: str, score: int, total: int):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO quiz_results (user_id, subject, exam, score, total)
            VALUES (?, ?, ?, ?, ?)
        """, (user_id, subject, exam, score, total))
        conn.commit()
        conn.close()

    # ==================== MANUAL PAYMENTS ====================
    def add_manual_payment(self, user_id: str, phone: str, mpesa_code: str):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO manual_payments (user_id, phone, mpesa_code)
            VALUES (?, ?, ?)
        """, (user_id, phone, mpesa_code.upper()))
        conn.commit()
        conn.close()

    def get_pending_manual_payments(self) -> List[Dict]:
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT mp.id, mp.phone, mp.mpesa_code, u.email, u.name, u.user_id
            FROM manual_payments mp
            JOIN users u ON mp.user_id = u.user_id
            WHERE mp.status = 'pending'
            ORDER BY mp.requested_at DESC
        """)
        rows = cursor.fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def approve_manual_payment(self, payment_id: int) -> bool:
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT user_id FROM manual_payments WHERE id = ?", (payment_id,))
        row = cursor.fetchone()
        if not row:
            conn.close()
            return False
        user_id = row["user_id"]
        expires_at = (datetime.now() + timedelta(days=30)).strftime('%Y-%m-%d %H:%M:%S')
        cursor.execute("""
            UPDATE users SET is_premium = 1, premium_expires_at = ?
            WHERE user_id = ?
        """, (expires_at, user_id))
        cursor.execute("""
            UPDATE manual_payments SET status = 'approved', processed_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (payment_id,))
        conn.commit()
        conn.close()
        return True

    def reject_manual_payment(self, payment_id: int):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE manual_payments SET status = 'rejected', processed_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (payment_id,))
        conn.commit()
        conn.close()

    def toggle_premium(self, user_id: str):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET is_premium = NOT is_premium WHERE user_id = ?", (user_id,))
        conn.commit()
        conn.close()

    # ==================== RANKINGS ====================
    def get_subject_rankings(self, subject: str) -> pd.DataFrame:
        conn = self.get_connection()
        df = pd.read_sql_query("""
            SELECT u.name AS user, AVG(qr.score * 100.0 / qr.total) as avg_score
            FROM quiz_results qr
            JOIN users u ON qr.user_id = u.user_id
            WHERE qr.subject = ?
            GROUP BY qr.user_id
            ORDER BY avg_score DESC
            LIMIT 10
        """, conn, params=(subject,))
        conn.close()
        df["avg_score"] = df["avg_score"].round(1)
        return df

    def get_all_users(self) -> List[Dict]:
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT user_id, name, email, role, is_premium, created_at FROM users ORDER BY created_at DESC")
        rows = cursor.fetchall()
        conn.close()
        return [dict(r) for r in rows]
