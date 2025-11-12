# database.py
import sqlite3
import bcrypt
import json
import uuid
from datetime import date, timedelta, datetime
import pyotp
from typing import Optional, List, Dict

DB_PATH = "users.db"

def get_db():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def ensure_columns():
    """Run on *every* app start – guarantees every column exists."""
    conn = get_db()
    c = conn.cursor()
    required = [
        ("last_active",      "TEXT DEFAULT CURRENT_TIMESTAMP"),
        ("parent_id",        "TEXT"),
        ("streak_days",      "INTEGER DEFAULT 0"),
        ("last_streak_date","TEXT"),
        ("badges",           "TEXT DEFAULT '[]'"),
        ("is_premium",       "INTEGER DEFAULT 0"),
        ("twofa_secret",     "TEXT"),
        ("total_queries",    "INTEGER DEFAULT 0"),
        ("created_at",       "TEXT DEFAULT CURRENT_TIMESTAMP"),
        ("profile_pic",      "BLOB"),
        ("theme",            "TEXT DEFAULT 'light'"),
        ("brightness",       "INTEGER DEFAULT 100"),
        ("font",             "TEXT DEFAULT 'sans-serif'"),
        ("discount",         "REAL DEFAULT 0.0")
    ]
    for col, typ in required:
        try:
            c.execute(f"ALTER TABLE users ADD COLUMN {col} {typ}")
        except sqlite3.OperationalError:
            pass   # column already present
    conn.commit()
    conn.close()

def init_db():
    conn = get_db()
    c = conn.cursor()

    # ---- TABLES -------------------------------------------------
    c.execute('''
    CREATE TABLE IF NOT EXISTS users (
        user_id TEXT PRIMARY KEY,
        email TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        name TEXT,
        role TEXT DEFAULT 'user',
        parent_id TEXT,
        streak_days INTEGER DEFAULT 0,
        last_streak_date TEXT,
        total_queries INTEGER DEFAULT 0,
        is_premium INTEGER DEFAULT 0,
        badges TEXT DEFAULT '[]',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        last_active TEXT DEFAULT CURRENT_TIMESTAMP,
        twofa_secret TEXT,
        profile_pic BLOB,
        theme TEXT DEFAULT 'light',
        brightness INTEGER DEFAULT 100,
        font TEXT DEFAULT 'sans-serif',
        discount REAL DEFAULT 0.0
    )
    ''')

    c.execute('''
    CREATE TABLE IF NOT EXISTS chat_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT,
        subject TEXT,
        user_query TEXT,
        ai_response TEXT,
        timestamp TEXT DEFAULT CURRENT_TIMESTAMP
    )
    ''')

    c.execute('''
    CREATE TABLE IF NOT EXISTS pdf_uploads (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT,
        filename TEXT,
        upload_date TEXT DEFAULT CURRENT_DATE
    )
    ''')

    c.execute('''
    CREATE TABLE IF NOT EXISTS manual_payments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT,
        phone TEXT,
        mpesa_code TEXT,
        status TEXT DEFAULT 'pending',
        submitted_at TEXT DEFAULT CURRENT_TIMESTAMP
    )
    ''')

    c.execute('''
    CREATE TABLE IF NOT EXISTS scores (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT,
        category TEXT,  -- 'exam' or 'essay'
        score REAL,
        timestamp TEXT DEFAULT CURRENT_TIMESTAMP
    )
    ''')

    # ---- ADMIN USER --------------------------------------------
    c.execute("SELECT 1 FROM users WHERE email = ?", ("kingmumo15@gmail.com",))
    if not c.fetchone():
        hashed = bcrypt.hashpw("@Yoounruly10".encode(), bcrypt.gensalt()).decode()
        admin_id = str(uuid.uuid4())
        today = date.today().isoformat()
        c.execute('''
        INSERT INTO users 
        (user_id, email, password_hash, name, role, is_premium,
         streak_days, last_streak_date, last_active, created_at)
        VALUES (?,?,?,?, 'admin',1,1,?, ?, ?)
        ''', (admin_id, "kingmumo15@gmail.com", hashed, "Admin King", today, today, today))

    conn.commit()
    conn.close()
    ensure_columns()  # <-- Critical: Run after init

# -----------------------------------------------------------------
# Run on import
init_db()

class Database:
    def __init__(self):
        init_db()  # Ensure tables always
        self.conn = get_db()
        ensure_columns()  # Ensure columns exist on every instance

    def _c(self):
        return self.conn.cursor()

    def commit(self):
        self.conn.commit()

    # ------------------- USER ------------------------------------
    def create_user(self, email: str, password: str) -> Optional[str]:
        if not email or "@" not in email or len(password) < 6:
            return None
        uid = str(uuid.uuid4())
        hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
        today = date.today().isoformat()
        name = email.split("@")[0] if "@" in email else "User"
        try:
            c = self._c()
            c.execute('''
            INSERT INTO users 
            (user_id, email, password_hash, name,
             streak_days, last_streak_date, last_active, created_at, total_queries)
            VALUES (?,?,?, ?,1,?,?,?,0)
            ''', (uid, email, hashed, name, today, today, today))
            self.commit()
            return uid
        except sqlite3.IntegrityError:
            return None
        except Exception as e:
            print(f"Create user error: {e}")
            return None

    def get_user_by_email(self, email: str) -> Optional[Dict]:
        try:
            c = self._c()
            c.execute("SELECT * FROM users WHERE email = ?", (email,))
            row = c.fetchone()
            return dict(row) if row else None
        except Exception as e:
            print(f"Get user by email error: {e}")
            return None

    def get_user(self, user_id: str) -> Optional[Dict]:
        try:
            c = self._c()
            c.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
            row = c.fetchone()
            return dict(row) if row else None
        except Exception as e:
            print(f"Get user error: {e}")
            return None

    def update_user_activity(self, user_id: str):
        if not user_id:
            return
        try:
            c = self._c()
            c.execute(
                "UPDATE users SET last_active = CURRENT_TIMESTAMP, total_queries = total_queries + 1 WHERE user_id = ?",
                (user_id,)
            )
            self.commit()
        except sqlite3.OperationalError as e:
            if "no such column" in str(e):
                ensure_columns()
                try:
                    c = self._c()
                    c.execute(
                        "UPDATE users SET last_active = CURRENT_TIMESTAMP WHERE user_id = ?",
                        (user_id,)
                    )
                    self.commit()
                except:
                    pass
            else:
                print(f"Activity update error: {e}")
        except Exception as e:
            print(f"Activity update error: {e}")

    def update_streak(self, user_id: str) -> int:
        if not user_id:
            return 0
        try:
            c = self._c()
            c.execute("SELECT last_streak_date, streak_days FROM users WHERE user_id = ?", (user_id,))
            row = c.fetchone()
            today = date.today().isoformat()
            yesterday = (date.today() - timedelta(days=1)).isoformat()

            if not row:
                c.execute("UPDATE users SET streak_days = 1, last_streak_date = ? WHERE user_id = ?", (today, user_id))
                self.commit()
                return 1

            last, streak = (row["last_streak_date"] or today), (row["streak_days"] or 0)

            if last == today:
                return streak
            elif last == yesterday:
                streak += 1
                if streak == 3: self.add_badge(user_id, "streak_3")
                if streak == 7: self.add_badge(user_id, "streak_7")
                if streak == 30: self.add_badge(user_id, "streak_30")
            else:
                streak = 1
            c.execute("UPDATE users SET streak_days = ?, last_streak_date = ? WHERE user_id = ?", (streak, today, user_id))
            self.commit()
            return streak
        except Exception as e:
            print(f"Streak update error: {e}")
            return 0

    def check_premium(self, user_id: str) -> bool:
        if not user_id:
            return False
        try:
            c = self._c()
            c.execute("SELECT is_premium FROM users WHERE user_id = ?", (user_id,))
            row = c.fetchone()
            return bool(row and row["is_premium"])
        except Exception:
            return False

    def add_manual_payment(self, user_id, phone, code):
        try:
            c = self._c()
            c.execute("INSERT INTO manual_payments (user_id, phone, mpesa_code) VALUES (?, ?, ?)", (user_id, phone, code))
            self.commit()
        except Exception as e:
            print(f"Payment add error: {e}")

    def get_pending_manual_payments(self):
        try:
            c = self._c()
            c.execute("SELECT * FROM manual_payments WHERE status = 'pending'")
            return [dict(row) for row in c.fetchall()]
        except Exception:
            return []

    def approve_manual_payment(self, id):
        try:
            c = self._c()
            c.execute("UPDATE manual_payments SET status = 'approved' WHERE id = ?", (id,))
            c.execute("SELECT user_id FROM manual_payments WHERE id = ?", (id,))
            row = c.fetchone()
            if row:
                self.toggle_premium(row["user_id"], True)
            self.commit()
        except Exception as e:
            print(f"Approve error: {e}")

    def reject_manual_payment(self, id):
        try:
            c = self._c()
            c.execute("UPDATE manual_payments SET status = 'rejected' WHERE id = ?", (id,))
            self.commit()
        except Exception as e:
            print(f"Reject error: {e}")

    def generate_2fa_secret(self, user_id):
        secret = pyotp.random_base32()
        try:
            c = self._c()
            c.execute("UPDATE users SET twofa_secret = ? WHERE user_id = ?", (secret, user_id))
            self.commit()
        except Exception as e:
            print(f"2FA secret error: {e}")
        return secret

    def is_2fa_enabled(self, user_id):
        try:
            c = self._c()
            c.execute("SELECT twofa_secret FROM users WHERE user_id = ?", (user_id,))
            row = c.fetchone()
            return bool(row and row["twofa_secret"])
        except Exception:
            return False

    def verify_2fa_code(self, user_id, code):
        try:
            c = self._c()
            c.execute("SELECT twofa_secret FROM users WHERE user_id = ?", (user_id,))
            row = c.fetchone()
            if not row or not row["twofa_secret"]:
                return False
            totp = pyotp.TOTP(row["twofa_secret"])
            return totp.verify(code)
        except Exception:
            return False

    def disable_2fa(self, user_id):
        try:
            c = self._c()
            c.execute("UPDATE users SET twofa_secret = NULL WHERE user_id = ?", (user_id,))
            self.commit()
        except Exception as e:
            print(f"Disable 2FA error: {e}")

    def link_parent(self, user_id, email, password):
        parent = self.get_user_by_email(email)
        if parent and bcrypt.checkpw(password.encode(), parent["password_hash"].encode()):
            try:
                c = self._c()
                c.execute("UPDATE users SET parent_id = ? WHERE user_id = ?", (parent["user_id"], user_id))
                self.commit()
                return "Linked successfully!"
            except Exception as e:
                return f"Error: {e}"
        return "Invalid parent credentials."

    def get_children(self, user_id):
        try:
            c = self._c()
            c.execute("SELECT * FROM users WHERE parent_id = ?", (user_id,))
            return [dict(row) for row in c.fetchall()]
        except Exception:
            return []

    def add_chat_history(self, user_id, subject, query, response):
        try:
            c = self._c()
            c.execute("INSERT INTO chat_history (user_id, subject, user_query, ai_response) VALUES (?, ?, ?, ?)",
                      (user_id, subject, query, response))
            self.commit()
        except Exception as e:
            print(f"Chat history error: {e}")

    def get_all_users(self):
        try:
            c = self._c()
            c.execute("SELECT user_id, email, name, role, created_at, is_premium FROM users")
            return [dict(row) for row in c.fetchall()]
        except Exception:
            return []

    def toggle_premium(self, user_id, enable: bool):
        try:
            c = self._c()
            c.execute("UPDATE users SET is_premium = ? WHERE user_id = ?", (1 if enable else 0, user_id))
            self.commit()
        except Exception as e:
            print(f"Toggle premium error: {e}")

    def revoke_user(self, user_id):
        try:
            c = self._c()
            c.execute("UPDATE users SET badges = '[]', streak_days = 0 WHERE user_id = ?", (user_id,))
            c.execute("DELETE FROM scores WHERE user_id = ?", (user_id,))
            self.commit()
        except Exception as e:
            print(f"Revoke user error: {e}")

    def add_score(self, user_id, category, score):
        try:
            c = self._c()
            c.execute("INSERT INTO scores (user_id, category, score) VALUES (?, ?, ?)", (user_id, category, score))
            self.commit()
        except Exception as e:
            print(f"Add score error: {e}")

    def get_leaderboard(self, category):
        try:
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
        except Exception as e:
            print(f"Get leaderboard error: {e}")
            return []

    def get_monthly_leaders(self):
        # Simulate getting top leaders for last month
        last_month = (datetime.now() - timedelta(days=30)).isoformat()
        try:
            c = self._c()
            c.execute("""
            SELECT user_id, category, SUM(score) as total
            FROM scores
            WHERE timestamp > ?
            GROUP BY user_id, category
            ORDER BY category, total DESC
            """, (last_month,))
            # Get top per category
            leaders = {}
            for row in c.fetchall():
                cat = row["category"]
                if cat not in leaders:
                    leaders[cat] = row["user_id"]
            return [(uid, cat) for cat, uid in leaders.items()]
        except Exception as e:
            print(f"Get monthly leaders error: {e}")
            return []

    def apply_discount(self, user_id, discount):
        try:
            c = self._c()
            c.execute("UPDATE users SET discount = ? WHERE user_id = ?", (discount, user_id))
            self.commit()
        except Exception as e:
            print(f"Apply discount error: {e}")

    def add_badge(self, user_id, badge):
        try:
            c = self._c()
            c.execute("SELECT badges FROM users WHERE user_id = ?", (user_id,))
            row = c.fetchone()
            badges = json.loads(row["badges"]) if row else []
            if badge not in badges:
                badges.append(badge)
                c.execute("UPDATE users SET badges = ? WHERE user_id = ?", (json.dumps(badges), user_id))
                self.commit()
        except Exception as e:
            print(f"Add badge error: {e}")

    def update_settings(self, user_id, settings: Dict):
        try:
            c = self._c()
            query = "UPDATE users SET "
            params = []
            for k, v in settings.items():
                query += f"{k} = ?, "
                params.append(v)
            query = query.rstrip(", ") + " WHERE user_id = ?"
            params.append(user_id)
            c.execute(query, params)
            self.commit()
        except Exception as e:
            print(f"Update settings error: {e}")
