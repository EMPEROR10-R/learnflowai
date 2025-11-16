# database.py
import sqlite3
import bcrypt
import json
import uuid
from datetime import date, timedelta, datetime
import pyotp
import qrcode
from io import BytesIO

DB_PATH = "users.db"

def get_conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def ensure_schema():
    conn = get_conn()
    c = conn.cursor()

    c.execute('''
    CREATE TABLE IF NOT EXISTS users (
        user_id TEXT PRIMARY KEY,
        email TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        name TEXT,
        role TEXT DEFAULT 'user',
        streak_days INTEGER DEFAULT 0,
        last_streak_date TEXT,
        total_xp INTEGER DEFAULT 0,
        is_premium INTEGER DEFAULT 0,
        badges TEXT DEFAULT '[]',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        last_active TEXT DEFAULT CURRENT_TIMESTAMP,
        twofa_secret TEXT,
        daily_questions INTEGER DEFAULT 0,
        last_question_date TEXT,
        daily_pdf_uploads INTEGER DEFAULT 0,
        last_pdf_date TEXT
    )
    ''')

    for sql in [
        '''CREATE TABLE IF NOT EXISTS chat_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT, subject TEXT, user_query TEXT, ai_response TEXT,
            timestamp TEXT DEFAULT CURRENT_TIMESTAMP
        )''',
        '''CREATE TABLE IF NOT EXISTS scores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT, category TEXT, score REAL,
            timestamp TEXT DEFAULT CURRENT_TIMESTAMP
        )''',
        '''CREATE TABLE IF NOT EXISTS manual_payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT, phone TEXT, mpesa_code TEXT,
            status TEXT DEFAULT 'pending', submitted_at TEXT DEFAULT CURRENT_TIMESTAMP
        )'''
    ]:
        c.execute(sql)

    for col, col_type in [
        ("total_xp", "INTEGER DEFAULT 0"),
        ("daily_questions", "INTEGER DEFAULT 0"),
        ("last_question_date", "TEXT"),
        ("daily_pdf_uploads", "INTEGER DEFAULT 0"),
        ("last_pdf_date", "TEXT")
    ]:
        try:
            c.execute(f"ALTER TABLE users ADD COLUMN {col} {col_type}")
        except: pass

    # FORCE ADMIN
    admin_email = "kingmumo15@gmail.com"
    admin_pwd = "@Yoounruly10"
    c.execute("DELETE FROM users WHERE email = ?", (admin_email,))
    hashed = bcrypt.hashpw(admin_pwd.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    admin_id = str(uuid.uuid4())
    today = date.today().isoformat()
    c.execute('''
    INSERT INTO users
    (user_id, email, password_hash, name, role, is_premium, streak_days, last_streak_date, last_active, created_at, total_xp)
    VALUES (?,?,?, 'Admin King', 'admin', 1, 1, ?, ?, ?, 1000)
    ''', (admin_id, admin_email, hashed, today, today, today))

    conn.commit()
    conn.close()

ensure_schema()

class Database:
    def __init__(self):
        ensure_schema()
        self.conn = get_conn()

    def _c(self):
        return self.conn.cursor()

    def commit(self):
        self.conn.commit()

    def create_user(self, email, password):
        if len(password) < 6: return None
        uid = str(uuid.uuid4())
        hashed = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        today = date.today().isoformat()
        try:
            c = self._c()
            c.execute('''
            INSERT INTO users
            (user_id, email, password_hash, name, streak_days, last_streak_date, last_active, created_at, total_xp)
            VALUES (?,?,?, ?,1,?,?,?,50)
            ''', (uid, email, hashed, email.split("@")[0], today, today, today))
            self.commit()
            return uid
        except: return None

    def get_user(self, user_id):
        c = self._c()
        c.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        row = c.fetchone()
        return dict(row) if row else None

    def get_user_by_email(self, email):
        c = self._c()
        c.execute("SELECT * FROM users WHERE email = ?", (email,))
        row = c.fetchone()
        return dict(row) if row else None

    def update_user_activity(self, user_id):
        c = self._c()
        c.execute("UPDATE users SET last_active = CURRENT_TIMESTAMP WHERE user_id = ?", (user_id,))
        self.commit()

    def update_streak(self, user_id):
        c = self._c()
        c.execute("SELECT last_streak_date, streak_days FROM users WHERE user_id = ?", (user_id,))
        row = c.fetchone()
        if not row: return 0
        last, streak = row["last_streak_date"], row["streak_days"]
        today = date.today().isoformat()
        if last == today: return streak
        elif last == (date.today() - timedelta(days=1)).isoformat():
            streak += 1
        else:
            streak = 1
        c.execute("UPDATE users SET streak_days = ?, last_streak_date = ? WHERE user_id = ?", (streak, today, user_id))
        self.commit()
        return streak

    def add_xp(self, user_id, points):
        c = self._c()
        c.execute("UPDATE users SET total_xp = total_xp + ? WHERE user_id = ?", (points, user_id))
        self.commit()

    def add_score(self, user_id, category, score):
        c = self._c()
        c.execute("INSERT INTO scores (user_id, category, score) VALUES (?,?,?)", (user_id, category, score))
        self.commit()

    def get_user_scores(self, user_id):
        c = self._c()
        c.execute("SELECT category, score, timestamp FROM scores WHERE user_id = ? ORDER BY timestamp", (user_id,))
        return [dict(row) for row in c.fetchall()]

    def get_subject_performance(self, user_id):
        c = self._c()
        c.execute("""
        SELECT ch.subject, AVG(s.score) as avg_score
        FROM chat_history ch JOIN scores s ON ch.user_id = s.user_id AND ch.subject = s.category
        WHERE ch.user_id = ?
        GROUP BY ch.subject
        """, (user_id,))
        return [dict(row) for row in c.fetchall()]

    def get_daily_question_count(self, user_id):
        today = date.today().isoformat()
        c = self._c()
        c.execute("SELECT daily_questions, last_question_date FROM users WHERE user_id = ?", (user_id,))
        row = c.fetchone()
        if not row or row["last_question_date"] != today:
            return 0
        return row["daily_questions"]

    def can_ask_question(self, user_id):
        if self.get_user(user_id).get("role") == "admin": return True
        today = date.today().isoformat()
        count = self.get_daily_question_count(user_id)
        if count >= 10: return False
        c = self._c()
        c.execute("UPDATE users SET daily_questions = daily_questions + 1, last_question_date = ? WHERE user_id = ?", (today, user_id))
        self.commit()
        return True

    def get_daily_pdf_count(self, user_id):
        today = date.today().isoformat()
        c = self._c()
        c.execute("SELECT daily_pdf_uploads, last_pdf_date FROM users WHERE user_id = ?", (user_id,))
        row = c.fetchone()
        if not row or row["last_pdf_date"] != today:
            return 0
        return row["daily_pdf_uploads"]

    def can_upload_pdf(self, user_id):
        if self.get_user(user_id).get("role") == "admin": return True
        today = date.today().isoformat()
        count = self.get_daily_pdf_count(user_id)
        if count >= 3: return False
        c = self._c()
        c.execute("UPDATE users SET daily_pdf_uploads = daily_pdf_uploads + 1, last_pdf_date = ? WHERE user_id = ?", (today, user_id))
        self.commit()
        return True

    def add_chat_history(self, user_id, subject, query, response):
        c = self._c()
        c.execute("INSERT INTO chat_history (user_id, subject, user_query, ai_response) VALUES (?,?,?,?)",
                  (user_id, subject, query, response))
        self.commit()

    def get_chat_history(self, user_id):
        c = self._c()
        c.execute("SELECT * FROM chat_history WHERE user_id = ? ORDER BY timestamp DESC", (user_id,))
        return [dict(row) for row in c.fetchall()]

    def add_badge(self, user_id, badge):
        c = self._c()
        c.execute("SELECT badges FROM users WHERE user_id = ?", (user_id,))
        row = c.fetchone()
        badges = json.loads(row["badges"]) if row and row["badges"] else []
        if badge not in badges:
            badges.append(badge)
            c.execute("UPDATE users SET badges = ? WHERE user_id = ?", (json.dumps(badges), user_id))
            self.commit()

    def get_leaderboard(self, category):
        c = self._c()
        c.execute("""
        SELECT u.email, SUM(s.score) as total_score
        FROM scores s JOIN users u ON s.user_id = u.user_id
        WHERE s.category = ?
        GROUP BY s.user_id
        ORDER BY total_score DESC
        LIMIT 10
        """, (category,))
        return [{"email": row["email"], "score": row["total_score"]} for row in c.fetchall()]

    def check_premium_validity(self, user_id):
        c = self._c()
        c.execute("SELECT submitted_at FROM manual_payments WHERE user_id = ? AND status = 'approved' ORDER BY submitted_at DESC LIMIT 1", (user_id,))
        row = c.fetchone()
        if not row: return False
        approval = datetime.fromisoformat(row["submitted_at"].split()[0])
        return datetime.now() < approval + timedelta(days=30)

    def add_manual_payment(self, user_id, phone, code):
        c = self._c()
        c.execute("INSERT INTO manual_payments (user_id, phone, mpesa_code) VALUES (?,?,?)", (user_id, phone, code))
        self.commit()

    def get_pending_payments(self):
        c = self._c()
        c.execute("SELECT * FROM manual_payments WHERE status = 'pending'")
        return [dict(row) for row in c.fetchall()]

    def approve_manual_payment(self, payment_id):
        c = self._c()
        c.execute("SELECT user_id FROM manual_payments WHERE id = ?", (payment_id,))
        row = c.fetchone()
        if row:
            c.execute("UPDATE users SET is_premium = 1 WHERE user_id = ?", (row["user_id"],))
            c.execute("UPDATE manual_payments SET status = 'approved' WHERE id = ?", (payment_id,))
        self.commit()

    def reject_manual_payment(self, payment_id):
        c = self._c()
        c.execute("UPDATE manual_payments SET status = 'rejected' WHERE id = ?", (payment_id,))
        self.commit()

    def get_all_users(self):
        c = self._c()
        c.execute("SELECT user_id, email, name, role, is_premium, total_xp FROM users")
        return [dict(row) for row in c.fetchall()]

    def ban_user(self, user_id):
        c = self._c()
        c.execute("UPDATE users SET role = 'banned' WHERE user_id = ?", (user_id,))
        self.commit()

    def upgrade_to_premium(self, user_id):
        c = self._c()
        c.execute("UPDATE users SET is_premium = 1 WHERE user_id = ?", (user_id,))
        self.commit()

    def downgrade_to_basic(self, user_id):
        c = self._c()
        c.execute("UPDATE users SET is_premium = 0 WHERE user_id = ?", (user_id,))
        self.commit()

    def is_2fa_enabled(self, user_id):
        c = self._c()
        c.execute("SELECT twofa_secret FROM users WHERE user_id = ?", (user_id,))
        row = c.fetchone()
        return bool(row and row["twofa_secret"])

    def verify_2fa_code(self, user_id, code):
        c = self._c()
        c.execute("SELECT twofa_secret FROM users WHERE user_id = ?", (user_id,))
        row = c.fetchone()
        if not row or not row["twofa_secret"]: return False
        totp = pyotp.TOTP(row["twofa_secret"])
        return totp.verify(code)

    def enable_2fa(self, user_id):
        secret = pyotp.random_base32()
        c = self._c()
        c.execute("UPDATE users SET twofa_secret = ? WHERE user_id = ?", (secret, user_id))
        self.commit()
        return secret

    def disable_2fa(self, user_id):
        c = self._c()
        c.execute("UPDATE users SET twofa_secret = NULL WHERE user_id = ?", (user_id,))
        self.commit()

    def get_2fa_qr(self, user_id):
        user = self.get_user(user_id)
        if not user or not user.get("twofa_secret"): return None
        totp = pyotp.TOTP(user["twofa_secret"])
        uri = totp.provisioning_uri(name=user["email"], issuer_name="LearnFlow AI")
        qr = qrcode.make(uri)
        buffered = BytesIO()
        qr.save(buffered, format="PNG")
        return buffered.getvalue()

    def generate_otp(self, user_id):
        import random
        otp = random.randint(100000, 999999)
        c = self._c()
        c.execute("UPDATE users SET temp_otp = ? WHERE user_id = ?", (otp, user_id))
        self.commit()
        return otp

    def update_password(self, user_id, new_pwd):
        hashed = bcrypt.hashpw(new_pwd.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        c = self._c()
        c.execute("UPDATE users SET password_hash = ?, temp_otp = NULL WHERE user_id = ?", (hashed, user_id))
        self.commit()
