# database.py
import sqlite3
import json
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Any
import uuid
import bcrypt
import os

class Database:
    ADMIN_ROLE = "admin"
    ADMIN_EMAIL = "kingmumo15@gmail.com"
    ADMIN_PASSWORD = "@Yoounruly10"

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
        print("[DB] Creating tables if not exist...")
        conn = self.get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id TEXT PRIMARY KEY,
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
                role TEXT DEFAULT 'user'
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS pending_payments (
                checkout_id TEXT PRIMARY KEY,
                user_id TEXT,
                phone TEXT,
                amount REAL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS documents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT,
                filename TEXT NOT NULL,
                content_text TEXT,
                upload_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS chat_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                role TEXT,
                content TEXT,
                session_id TEXT,
                subject TEXT,
                FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS essays (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT,
                submission_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                title TEXT,
                content TEXT,
                grade_json TEXT,
                FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS exam_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT,
                exam_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                subject TEXT,
                exam_type TEXT,
                score INTEGER,
                total_questions INTEGER,
                completed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
            )
        """)

        conn.commit()
        conn.close()
        print("[DB] Tables ready.")

    def migrate_schema(self):
        print("[DB] Running schema migration...")
        conn = self.get_connection()
        cursor = conn.cursor()

        def add_column(table: str, column: str, definition: str):
            try:
                cursor.execute(f"PRAGMA table_info({table})")
                cols = {row[1] for row in cursor.fetchall()}
                if column not in cols:
                    print(f"[MIGRATE] Adding column {column} to {table}")
                    cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
            except Exception as e:
                print(f"[MIGRATE ERROR] {e}")

        add_column("users", "role", "TEXT DEFAULT 'user'")
        add_column("users", "last_payment_ref", "TEXT")
        add_column("users", "last_payment_amount", "REAL")
        add_column("chat_history", "role", "TEXT")
        add_column("chat_history", "content", "TEXT")
        add_column("chat_history", "session_id", "TEXT")
        add_column("chat_history", "subject", "TEXT")

        conn.commit()
        conn.close()
        print("[DB] Migration complete.")

    def _ensure_admin_user(self):
        print(f"[ADMIN] Ensuring admin user exists: {self.ADMIN_EMAIL}")
        if self.get_user_by_email(self.ADMIN_EMAIL):
            print(f"[ADMIN] Already exists: {self.ADMIN_EMAIL}")
            return

        print(f"[ADMIN] Creating admin: {self.ADMIN_EMAIL}")
        user_id = str(uuid.uuid4())
        try:
            hashed = bcrypt.hashpw(self.ADMIN_PASSWORD.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        except Exception as e:
            print(f"[ADMIN] bcrypt error: {e}")
            return

        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("""
                INSERT INTO users 
                (user_id, email, password_hash, role, is_premium)
                VALUES (?, ?, ?, ?, 1)
            """, (user_id, self.ADMIN_EMAIL.lower(), hashed, self.ADMIN_ROLE))
            conn.commit()
            print(f"[ADMIN] SUCCESS: Admin created → {self.ADMIN_EMAIL} (ID: {user_id})")
        except Exception as e:
            print(f"[ADMIN] FAILED to insert: {e}")
        finally:
            conn.close()

    def get_user_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        if not email: return None
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE email = ?", (email.lower(),))
        row = cursor.fetchone()
        conn.close()
        return dict(row) if row else None

    def create_user(self, email: Optional[str] = None, password: Optional[str] = None) -> str:
        user_id = str(uuid.uuid4())
        hashed = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8') if password else None
        email_value = email.lower() if email else None

        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("""
                INSERT INTO users 
                (user_id, email, password_hash, role, is_premium, premium_expires_at)
                VALUES (?, ?, ?, 'user', 0, NULL)
            """, (user_id, email_value, hashed))
            conn.commit()
            print(f"[USER] Created user ID: {user_id} (Email: {email_value})")
        except Exception as e:
            print(f"[USER] Failed to create user: {e}")
            raise
        finally:
            conn.close()
        return user_id

    def login_user(self, email: str, password: str) -> Optional[str]:
        user = self.get_user_by_email(email)
        if not user or not user.get('password_hash'):
            print(f"[LOGIN] Failed: User not found or no password: {email}")
            return None

        try:
            if bcrypt.checkpw(password.encode('utf-8'), user['password_hash'].encode('utf-8')):
                print(f"[LOGIN] SUCCESS: {email} (Role: {user.get('role')})")
                return user['user_id']
            else:
                print(f"[LOGIN] Failed: Wrong password for {email}")
                return None
        except Exception as e:
            print(f"[LOGIN] bcrypt error: {e}")
            return None

    def get_user(self, user_id: str) -> Optional[Dict[str, Any]]:
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        conn.close()
        return dict(row) if row else None

    def is_admin(self, user_id: str) -> bool:
        user = self.get_user(user_id)
        is_admin = user.get("role") == self.ADMIN_ROLE if user else False
        if is_admin:
            print(f"[PERM] User {user_id} is ADMIN")
        return is_admin

    def update_streak(self, user_id: str) -> int:
        conn = self.get_connection()
        cursor = conn.cursor()
        today = datetime.now().date()
        yesterday = today - timedelta(days=1)

        cursor.execute("SELECT last_streak_date, streak_days FROM users WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        last_date = row['last_streak_date'] if row else None
        streak = row['streak_days'] or 0 if row else 0

        if last_date == str(today):
            conn.close()
            return streak
        elif last_date == str(yesterday):
            streak += 1
        else:
            streak = 1

        cursor.execute("""
            UPDATE users SET streak_days = ?, last_streak_date = ?, last_active = CURRENT_TIMESTAMP
            WHERE user_id = ?
        """, (streak, str(today), user_id))
        conn.commit()
        conn.close()
        return streak

    def add_badge(self, user_id: str, badge: str):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT badges FROM users WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        badges = json.loads(row['badges']) if row and row['badges'] else []
        if badge not in badges:
            badges.append(badge)
            cursor.execute("UPDATE users SET badges = ? WHERE user_id = ?", (json.dumps(badges), user_id))
        conn.commit()
        conn.close()

    def check_premium(self, user_id: str) -> bool:
        if self.is_admin(user_id): return True
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT is_premium FROM users WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        conn.close()
        return bool(row['is_premium']) if row else False

    def get_daily_query_count(self, user_id: str) -> int:
        if self.is_admin(user_id): return 0
        conn = self.get_connection()
        cursor = conn.cursor()
        today = datetime.now().date()
        cursor.execute("""
            SELECT COUNT(*) FROM chat_history 
            WHERE user_id = ? AND role = 'user' AND DATE(timestamp) = ?
        """, (user_id, str(today)))
        count = cursor.fetchone()[0]
        conn.close()
        return count

    def get_pdf_count_today(self, user_id: str) -> int:
        if self.is_admin(user_id): return 0
        conn = self.get_connection()
        cursor = conn.cursor()
        today = datetime.now().date()
        cursor.execute("""
            SELECT COUNT(*) FROM documents 
            WHERE user_id = ? AND DATE(upload_date) = ?
        """, (user_id, str(today)))
        count = cursor.fetchone()[0]
        conn.close()
        return count

    def add_pdf_upload(self, user_id: str, filename: str):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("INSERT INTO documents (user_id, filename) VALUES (?, ?)", (user_id, filename))
        conn.commit()
        conn.close()

    def add_chat_history(self, user_id: str, subject: str, user_msg: str, ai_msg: str):
        conn = self.get_connection()
        cursor = conn.cursor()
        session_id = str(uuid.uuid4())
        cursor.execute("""
            INSERT INTO chat_history (user_id, role, content, session_id, subject)
            VALUES (?, 'user', ?, ?, ?)
        """, (user_id, user_msg, session_id, subject))
        cursor.execute("""
            INSERT INTO chat_history (user_id, role, content, session_id, subject)
            VALUES (?, 'assistant', ?, ?, ?)
        """, (user_id, ai_msg, session_id, subject))
        cursor.execute("UPDATE users SET total_queries = total_queries + 1 WHERE user_id = ?", (user_id,))
        conn.commit()
        conn.close()

    def update_user_activity(self, user_id: str):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET last_active = CURRENT_TIMESTAMP WHERE user_id = ?", (user_id,))
        conn.commit()
        conn.close()

    def add_quiz_result(self, user_id: str, subject: str, exam_type: str, score: int, total: int):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO exam_results (user_id, subject, exam_type, score, total_questions)
            VALUES (?, ?, ?, ?, ?)
        """, (user_id, subject, exam_type, score, total))
        conn.commit()
        conn.close()

    def get_all_users(self) -> List[Dict]:
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT user_id, email, role, is_premium, created_at, total_queries, streak_days 
            FROM users ORDER BY created_at DESC
        """)
        rows = cursor.fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def toggle_premium(self, user_id: str):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET is_premium = NOT is_premium WHERE user_id = ?", (user_id,))
        conn.commit()
        conn.close()

    def delete_user(self, user_id: str):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM users WHERE user_id = ?", (user_id,))
        conn.commit()
        conn.close()

    # M-Pesa Payment Methods (New/Fixed)
    def record_pending_payment(self, user_id: str, phone: str, amount: float, checkout_id: str):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO pending_payments 
            (checkout_id, user_id, phone, amount)
            VALUES (?, ?, ?, ?)
        """, (checkout_id, user_id, phone, amount))
        conn.commit()
        conn.close()

    def get_pending_payment(self, checkout_id: str) -> Optional[Dict]:
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM pending_payments WHERE checkout_id = ?", (checkout_id,))
        row = cursor.fetchone()
        conn.close()
        return dict(row) if row else None

    def clear_pending_payment(self, checkout_id: str):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM pending_payments WHERE checkout_id = ?", (checkout_id,))
        conn.commit()
        conn.close()

    def activate_premium(self, user_id: str, amount: float, mpesa_ref: str):
        conn = self.get_connection()
        cursor = conn.cursor()
        expires_at = (datetime.now() + timedelta(days=30)).strftime('%Y-%m-%d %H:%M:%S')
        cursor.execute("""
            UPDATE users 
            SET is_premium = 1, 
                premium_expires_at = ?, 
                last_payment_ref = ?, 
                last_payment_amount = ?
            WHERE user_id = ?
        """, (expires_at, mpesa_ref, amount, user_id))
        conn.commit()
        conn.close()
