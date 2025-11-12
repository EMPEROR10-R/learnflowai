# database.py
import sqlite3
import os
import json
import bcrypt
from datetime import datetime, date
import streamlit as st

DB_PATH = "users.db"

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    cursor = conn.cursor()

    # Create tables with ALL columns (including last_active)
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
        user_id TEXT PRIMARY KEY,
        email TEXT UNIQUE,
        password_hash TEXT,
        name TEXT,
        role TEXT DEFAULT 'user',
        streak_days INTEGER DEFAULT 0,
        last_streak_date TEXT,
        total_queries INTEGER DEFAULT 0,
        is_premium INTEGER DEFAULT 0,
        premium_until TEXT,
        parent_id TEXT,
        badges TEXT DEFAULT '[]',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        last_active TEXT DEFAULT CURRENT_TIMESTAMP,
        2fa_secret TEXT
    )
    ''')

    cursor.execute('''
    CREATE TABLE IF NOT EXISTS chat_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT,
        subject TEXT,
        user_query TEXT,
        ai_response TEXT,
        timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users (user_id)
    )
    ''')

    cursor.execute('''
    CREATE TABLE IF NOT EXISTS pdf_uploads (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT,
        filename TEXT,
        upload_date TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users (user_id)
    )
    ''')

    cursor.execute('''
    CREATE TABLE IF NOT EXISTS manual_payments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT,
        phone TEXT,
        mpesa_code TEXT,
        status TEXT DEFAULT 'pending',
        submitted_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users (user_id)
    )
    ''')

    cursor.execute('''
    CREATE TABLE IF NOT EXISTS quiz_results (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT,
        subject TEXT,
        exam_type TEXT,
        score INTEGER,
        total INTEGER,
        timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users (user_id)
    )
    ''')

    # === UPGRADE OLD DATABASES ===
    # Add missing columns if they don't exist
    columns_to_add = [
        ("users", "last_active", "TEXT DEFAULT CURRENT_TIMESTAMP"),
        ("users", "2fa_secret", "TEXT"),
        ("users", "badges", "TEXT DEFAULT '[]'"),
        ("users", "parent_id", "TEXT"),
        ("users", "premium_until", "TEXT"),
        ("users", "is_premium", "INTEGER DEFAULT 0"),
    ]

    for table, col, definition in columns_to_add:
        try:
            cursor.execute(f"ALTER TABLE {table} ADD COLUMN {col} {definition}")
        except sqlite3.OperationalError:
            pass  # Column already exists

    # Create admin if not exists
    cursor.execute("SELECT * FROM users WHERE email = ?", ("kingmumo15@gmail.com",))
    if not cursor.fetchone():
        hashed = bcrypt.hashpw("@Yoounruly10".encode(), bcrypt.gensalt()).decode()
        cursor.execute(
            "INSERT INTO users (user_id, email, password_hash, name, role) VALUES (?, ?, ?, ?, ?)",
            (str(uuid.uuid4()), "kingmumo15@gmail.com", hashed, "Admin King", "admin")
        )

    conn.commit()
    conn.close()

# Initialize on import
init_db()

class Database:
    def __init__(self):
        pass

    # === USER MANAGEMENT ===
    def create_user(self, email: str, password: str):
        user_id = str(uuid.uuid4())
        hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
        try:
            with get_db() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "INSERT INTO users (user_id, email, password_hash, name) VALUES (?, ?, ?, ?)",
                    (user_id, email, hashed, email.split("@")[0])
                )
                conn.commit()
            return user_id
        except:
            return None

    def get_user_by_email(self, email: str):
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM users WHERE email = ?", (email,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def get_user(self, user_id: str):
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def update_user_activity(self, user_id: str):
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE users SET last_active = CURRENT_TIMESTAMP WHERE user_id = ?",
                (user_id,)
            )
            conn.commit()

    # === STREAK ===
    def update_streak(self, user_id: str):
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT last_streak_date, streak_days FROM users WHERE user_id = ?", (user_id,))
            row = cursor.fetchone()
            if not row:
                return 0
            last_date, streak = row["last_streak_date"], row["streak_days"] or 0
            today = date.today().isoformat()
            if last_date == today:
                return streak
            elif last_date == (date.today() - timedelta(days=1)).isoformat():
                streak += 1
            else:
                streak = 1
            cursor.execute(
                "UPDATE users SET streak_days = ?, last_streak_date = ? WHERE user_id = ?",
                (streak, today, user_id)
            )
            conn.commit()
            return streak

    # === PREMIUM ===
    def check_premium(self, user_id: str):
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT is_premium FROM users WHERE user_id = ?", (user_id,))
            row = cursor.fetchone()
            return bool(row and row["is_premium"])

    def add_manual_payment(self, user_id: str, phone: str, mpesa_code: str):
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO manual_payments (user_id, phone, mpesa_code) VALUES (?, ?, ?)",
                (user_id, phone, mpesa_code)
            )
            conn.commit()

    def get_pending_manual_payments(self):
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT mp.id, mp.mpesa_code, mp.phone, u.name, u.email
                FROM manual_payments mp
                JOIN users u ON mp.user_id = u.user_id
                WHERE mp.status = 'pending'
            """)
            return [dict(row) for row in cursor.fetchall()]

    def approve_manual_payment(self, payment_id: int):
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT user_id FROM manual_payments WHERE id = ?", (payment_id,))
            row = cursor.fetchone()
            if row:
                user_id = row["user_id"]
                cursor.execute(
                    "UPDATE users SET is_premium = 1, premium_until = date('now', '+30 days') WHERE user_id = ?",
                    (user_id,)
                )
                cursor.execute("UPDATE manual_payments SET status = 'approved' WHERE id = ?", (payment_id,))
                conn.commit()
                return True
            return False

    def reject_manual_payment(self, payment_id: int):
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE manual_payments SET status = 'rejected' WHERE id = ?", (payment_id,))
            conn.commit()

    # === 2FA ===
    def is_2fa_enabled(self, user_id: str):
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT 2fa_secret FROM users WHERE user_id = ?", (user_id,))
            row = cursor.fetchone()
            return bool(row and row["2fa_secret"])

    def enable_2fa(self, user_id: str, secret: str):
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE users SET 2fa_secret = ? WHERE user_id = ?", (secret, user_id))
            conn.commit()

    def verify_2fa_code(self, user_id: str, code: str):
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT 2fa_secret FROM users WHERE user_id = ?", (user_id,))
            row = cursor.fetchone()
            if not row or not row["2fa_secret"]:
                return False
            return pyotp.TOTP(row["2fa_secret"]).verify(code)

    # === CHAT & LIMITS ===
    def add_chat_history(self, user_id: str, subject: str, query: str, response: str):
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO chat_history (user_id, subject, user_query, ai_response) VALUES (?, ?, ?, ?)",
                (user_id, subject, query, response)
            )
            cursor.execute("UPDATE users SET total_queries = total_queries + 1 WHERE user_id = ?", (user_id,))
            conn.commit()

    def get_daily_query_count(self, user_id: str):
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT COUNT(*) FROM chat_history
                WHERE user_id = ? AND date(timestamp) = date('now')
            """, (user_id,))
            return cursor.fetchone()[0]

    def get_pdf_count_today(self, user_id: str):
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT COUNT(*) FROM pdf_uploads
                WHERE user_id = ? AND date(upload_date) = date('now')
            """, (user_id,))
            return cursor.fetchone()[0]

    def add_pdf_upload(self, user_id: str, filename: str):
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO pdf_uploads (user_id, filename) VALUES (?, ?)",
                (user_id, filename)
            )
            conn.commit()

    # === BADGES ===
    def add_badge(self, user_id: str, badge: str):
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT badges FROM users WHERE user_id = ?", (user_id,))
            row = cursor.fetchone()
            badges = json.loads(row["badges"]) if row and row["badges"] else []
            if badge not in badges:
                badges.append(badge)
                cursor.execute("UPDATE users SET badges = ? WHERE user_id = ?", (json.dumps(badges), user_id))
                conn.commit()

    # === QUIZ ===
    def add_quiz_result(self, user_id: str, subject: str, exam: str, score: int, total: int):
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO quiz_results (user_id, subject, exam_type, score, total) VALUES (?, ?, ?, ?, ?)",
                (user_id, subject, exam, score, total)
            )
            conn.commit()
