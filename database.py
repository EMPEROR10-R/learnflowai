# database.py — Updated with project gamification (new table for projects, XP awards)
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
        self.conn.executescript("""
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
            discount_buy_count INTEGER DEFAULT 0,  # New: Track buys for exponential pricing
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
        );  # New table for project gamification
        """)
        self.conn.commit()

    def _create_emperor_admin(self):
        hashed = bcrypt.hashpw("@Unruly10".encode(), bcrypt.gensalt())
        try:
            self.conn.execute("""INSERT INTO users
                (username, email, password_hash, is_premium, level, xp_coins, discount_20, total_xp, spendable_xp)
                VALUES (?, ?, ?, 1, 999, 999999, 1, 999999, 999999)""",
                ("EmperorUnruly", "kingmumo15@gmail.com", hashed))
            self.conn.commit()
        except: pass

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
        self.conn.execute("UPDATE users SET is_premium=0, premium_expiry=NULL WHERE premium_expiry < ? AND username != 'EmperorUnruly'", (today,))
        self.conn.commit()

    def check_premium_validity(self, user_id: int) -> bool:
        user = self.get_user(user_id)
        if not user or not user["is_premium"]: return False
        expiry = user["premium_expiry"]
        return expiry and date.fromisoformat(expiry) >= date.today()

    def update_profile(self, user_id: int, name: str):
        self.conn.execute("UPDATE users SET name = ? WHERE user_id = ?", (name, user_id))
        self.conn.commit()

    def enable_2fa(self, user_id: int):
        secret = pyotp.random_base32()
        self.conn.execute(
            "INSERT OR REPLACE INTO user_2fa (user_id, secret, enabled) VALUES (?, ?, 1)",
            (user_id, secret)
        )
        self.conn.commit()
        return secret, self.get_2fa_qr_bytes(user_id, secret)

    def get_2fa_qr_bytes(self, user_id: int, secret: str):
        user = self.get_user(user_id)
        totp_uri = pyotp.totp.TOTP(secret).provisioning_uri(name=user["email"], issuer_name="Kenyan EdTech")
        qr = qrcode.make(totp_uri)
        buffered = io.BytesIO()
        qr.save(buffered, format="PNG")
        return buffered.getvalue()

    def is_2fa_enabled(self, user_id: int) -> bool:
        row = self.conn.execute("SELECT 1 FROM user_2fa WHERE user_id = ? AND enabled = 1", (user_id,)).fetchone()
        return bool(row)

    def verify_2fa_code(self, user_id: int, code: str) -> bool:
        row = self.conn.execute("SELECT secret FROM user_2fa WHERE user_id = ?", (user_id,)).fetchone()
        if not row: return False
        totp = pyotp.TOTP(row["secret"])
        return totp.verify(code)

    def disable_2fa(self, user_id: int):
        self.conn.execute("DELETE FROM user_2fa WHERE user_id = ?", (user_id,))
        self.conn.commit()

    def generate_otp(self, user_id: int) -> str:
        row = self.conn.execute("SELECT secret FROM user_2fa WHERE user_id = ?", (user_id,)).fetchone()
        if not row: return ""
        return pyotp.TOTP(row["secret"]).now()

    def _reset_daily_if_needed(self, user_id: int):
        user = self.get_user(user_id)
        last_reset = user.get("last_daily_reset")
        if not last_reset or date.fromisoformat(last_reset) < date.today():
            self.conn.execute(
                "UPDATE users SET daily_questions = 0, daily_pdfs = 0, daily_exams = 0, last_daily_reset = ? WHERE user_id = ?",
                (date.today().isoformat(), user_id)
            )
            self.conn.commit()

    def get_daily_question_count(self, user_id: int) -> int:
        self._reset_daily_if_needed(user_id)
        row = self.conn.execute("SELECT daily_questions FROM users WHERE user_id = ?", (user_id,)).fetchone()
        return row["daily_questions"] if row else 0

    def get_daily_pdf_count(self, user_id: int) -> int:
        self._reset_daily_if_needed(user_id)
        row = self.conn.execute("SELECT daily_pdfs FROM users WHERE user_id = ?", (user_id,)).fetchone()
        return row["daily_pdfs"] if row else 0

    def increment_daily_question(self, user_id: int):
        self._reset_daily_if_needed(user_id)
        self.conn.execute("UPDATE users SET daily_questions = daily_questions + 1 WHERE user_id = ?", (user_id,))
        self.conn.commit()

    def increment_daily_pdf(self, user_id: int):
        self._reset_daily_if_needed(user_id)
        self.conn.execute("UPDATE users SET daily_pdfs = daily_pdfs + 1 WHERE user_id = ?", (user_id,))
        self.conn.commit()

    def add_xp(self, user_id: int, points: int, spendable: bool = False, coins: int = 0, multiplier: int = 1):
        user = self.get_user(user_id)
        if user['is_premium'] or user.get('username') == 'EmperorUnruly':
            points *= 3
            coins *= 3
        points *= multiplier
        coins *= multiplier
        new_total_xp = user['total_xp'] + points
        new_spendable_xp = user['spendable_xp'] + (points if spendable else 0)
        new_xp = user['xp'] + points
        new_coins = user['xp_coins'] + coins
        new_level = 1 + (new_xp // 100)
        self.conn.execute(
            "UPDATE users SET total_xp = ?, spendable_xp = ?, xp = ?, xp_coins = ?, level = ? WHERE user_id = ?",
            (new_total_xp, new_spendable_xp, new_xp, new_coins, new_level, user_id)
        )
        self.conn.commit()
        return new_level

    def spend_coins(self, user_id: int, amount: int) -> bool:
        user = self.get_user(user_id)
        if user['xp_coins'] >= amount:
            self.conn.execute("UPDATE users SET xp_coins = xp_coins - ? WHERE user_id=?", (amount, user_id))
            self.conn.commit()
            return True
        return False

    def buy_discount_cheque(self, user_id: int) -> bool:
        user = self.get_user(user_id)
        buy_count = user['discount_buy_count']
        cost = int(1000000 * (2.5 ** buy_count))  # Exponential: 1M, 2.5M, 6.25M...
        if user['is_premium'] or user.get('username') == 'EmperorUnruly':
            cost = int(cost * 0.25)  # 25% of normal for premium/admin
        if self.spend_coins(user_id, cost):
            self.conn.execute("UPDATE users SET discount_20=1, discount_buy_count = discount_buy_count + 1 WHERE user_id=?", (user_id,))
            self.conn.commit()
            return True
        return False

    def award_top3_bonus(self):
        for exam_type in [None, "KCPE", "KPSEA", "KJSEA", "KCSE", "Python Programming"]:
            top3 = self.conn.execute(f"""
                SELECT user_id FROM users u
                LEFT JOIN exam_scores e ON u.user_id=e.user_id
                {'WHERE e.exam_type=? ' if exam_type else ''}
                GROUP BY u.user_id ORDER BY AVG(e.score) DESC LIMIT 3
            """, (exam_type,) if exam_type else ()).fetchall()
            for row in top3:
                self.conn.execute("UPDATE users SET discount_20=1 WHERE user_id=?", (row['user_id'],))
        self.conn.commit()

    def increase_discount(self, user_id: int, percent: int):
        self.conn.execute(
            "UPDATE users SET discount = LEAST(discount + ?, 50) WHERE user_id = ?",
            (percent, user_id)
        )
        self.conn.commit()

    def reset_spendable_progress(self, user_id: int):
        self.conn.execute("UPDATE users SET spendable_xp = 0 WHERE user_id = ?", (user_id,))
        self.conn.commit()

    def add_badge(self, user_id: int, badge_key: str):
        user = self.get_user(user_id)
        badges = json.loads(user["badges"])
        if badge_key not in badges:
            badges.append(badge_key)
            self.conn.execute("UPDATE users SET badges = ? WHERE user_id = ?", (json.dumps(badges), user_id))
            self.conn.commit()

    def update_streak(self, user_id: int) -> int:
        user = self.get_user(user_id)
        today = date.today()
        last_date = date.fromisoformat(user["last_streak_date"]) if user["last_streak_date"] else None
        streak = user["streak"]

        if last_date == today - timedelta(days=1):
            streak += 1
        elif last_date != today:
            streak = 1

        self.conn.execute(
            "UPDATE users SET streak = ?, last_streak_date = ? WHERE user_id = ?",
            (streak, today.isoformat(), user_id)
        )
        if last_date != today:
            self.add_xp(user_id, 20, spendable=False)
        self.conn.commit()
        return streak

    def add_score(self, user_id: int, category: str, score: float):
        self.conn.execute(
            "INSERT INTO scores (user_id, category, score) VALUES (?, ?, ?)",
            (user_id, category, score)
        )
        self.conn.commit()

    def get_user_scores(self, user_id: int) -> List[Dict]:
        rows = self.conn.execute(
            "SELECT category, score, timestamp FROM scores WHERE user_id = ? ORDER BY timestamp DESC LIMIT 50",
            (user_id,)
        ).fetchall()
        return [dict(row) for row in rows]

    def get_subject_performance(self, user_id: int) -> List[Dict]:
        rows = self.conn.execute("""
            SELECT subject, AVG(score) as avg_score
            FROM chat_history ch
            JOIN scores s ON ch.user_id = s.user_id AND DATE(ch.timestamp) = DATE(s.timestamp)
            WHERE ch.user_id = ? AND s.category = 'exam'
            GROUP BY subject
        """, (user_id,)).fetchall()
        return [dict(row) for row in rows]

    def get_leaderboard(self, category: str) -> List[Dict]:
        return self.conn.execute(f"""
            SELECT u.email, s.score
            FROM scores s
            JOIN users u ON s.user_id = u.user_id
            WHERE s.category = ? AND u.is_banned = 0
            ORDER BY s.score DESC LIMIT 10
        """, (category,)).fetchall()

    def get_xp_leaderboard(self) -> List[Dict]:
        return self.conn.execute("""
            SELECT email, total_xp,
                   (SELECT COUNT(*) + 1 FROM users u2 
                    WHERE u2.total_xp > u1.total_xp AND u2.is_banned = 0) as rank
            FROM users u1
            WHERE is_banned = 0
            ORDER BY total_xp DESC LIMIT 10
        """).fetchall()

    def get_rankings(self, exam_type=None, limit=50) -> List[Dict]:
        query = """
            SELECT u.username, u.level, u.xp, u.xp_coins,
                   AVG(e.score) as avg_score, COUNT(e.id) as exams
            FROM users u LEFT JOIN exam_scores e ON u.user_id = e.user_id
        """
        params = []
        if exam_type:
            query += " AND e.exam_type = ?"
            params.append(exam_type)
        query += " GROUP BY u.user_id ORDER BY avg_score DESC, u.xp DESC LIMIT ?"
        params.append(limit)
        return self.conn.execute(query, params).fetchall()

    def add_chat_history(self, user_id: int, subject: str, query: str, response: str):
        self.increment_daily_question(user_id)
        self.conn.execute(
            "INSERT INTO chat_history (user_id, subject, user_query, ai_response) VALUES (?, ?, ?, ?)",
            (user_id, subject, query, response)
        )
        self.conn.commit()

    def get_chat_history(self, user_id: int) -> List[Dict]:
        rows = self.conn.execute(
            "SELECT * FROM chat_history WHERE user_id = ? ORDER BY timestamp DESC LIMIT 20",
            (user_id,)
        ).fetchall()
        return [dict(row) for row in rows]

    def add_payment(self, uid: int, phone: str, code: str):
        self.conn.execute("INSERT INTO payments (user_id, phone, mpesa_code) VALUES (?, ?, ?)", (uid, phone, code))
        self.conn.commit()

    def add_manual_payment(self, user_id: int, phone: str, mpesa_code: str):
        self.conn.execute(
            "INSERT INTO payments (user_id, phone, mpesa_code) VALUES (?, ?, ?)",
            (user_id, phone, mpesa_code)
        )
        self.conn.commit()

    def get_pending_payments(self) -> List[Dict]:
        rows = self.conn.execute("SELECT * FROM payments WHERE status = 'pending'").fetchall()
        return [dict(row) for row in rows]

    def approve_manual_payment(self, payment_id: int):
        self.conn.execute("UPDATE payments SET status = 'approved' WHERE id = ?", (payment_id,))
        row = self.conn.execute("SELECT user_id FROM payments WHERE id = ?", (payment_id,)).fetchone()
        if row:
            self.upgrade_to_premium(row["user_id"])
        self.conn.commit()

    def approve_payment(self, pid: int):
        expiry = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d")
        self.conn.execute("UPDATE payments SET status='approved' WHERE id=?", (pid,))
        self.conn.execute("UPDATE users SET is_premium=1, premium_expiry=? WHERE user_id=(SELECT user_id FROM payments WHERE id=?)", (expiry, pid))
        self.conn.commit()

    def reject_manual_payment(self, payment_id: int):
        self.conn.execute("UPDATE payments SET status = 'rejected' WHERE id = ?", (payment_id,))
        self.conn.commit()

    # New: Project Gamification Methods
    def submit_project(self, user_id: int, subject: str, project_name: str, submission: str, grade: float, xp: int):
        self.conn.execute(
            "INSERT INTO projects (user_id, subject, project_name, submission, grade, xp_awarded) VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, subject, project_name, submission, grade, xp)
        )
        self.conn.commit()
        self.add_xp(user_id, xp, coins=xp // 2)  # Award XP + half as coins
        project_count = self.conn.execute("SELECT COUNT(*) FROM projects WHERE user_id = ?", (user_id,)).fetchone()[0]
        if project_count == 1:
            self.add_badge(user_id, "project_rookie")
        if project_count >= 5:
            self.add_badge(user_id, "project_master")

    def get_user_projects(self, user_id: int) -> List[Dict]:
        rows = self.conn.execute("SELECT * FROM projects WHERE user_id = ? ORDER BY timestamp DESC", (user_id,)).fetchall()
        return [dict(row) for row in rows]

    def close(self):
        self.conn.close()
