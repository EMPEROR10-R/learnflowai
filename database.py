# database.py
import sqlite3
import bcrypt
import uuid
from datetime import date

DB_PATH = "users.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        user_id TEXT PRIMARY KEY, email TEXT UNIQUE, password_hash TEXT, role TEXT
    )''')
    # FORCE RECREATE ADMIN
    c.execute("DELETE FROM users WHERE email = ?", ("kingmumo15@gmail.com",))
    hashed = bcrypt.hashpw("@Yoounruly10".encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    c.execute("INSERT INTO users VALUES (?, ?, ?, ?)",
              (str(uuid.uuid4()), "kingmumo15@gmail.com", hashed, "admin"))
    conn.commit()
    conn.close()
    print("ADMIN USER RECREATED")

init_db()

class Database:
    def __init__(self): init_db()
    def get_user_by_email(self, email):
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT * FROM users WHERE email = ?", (email,))
        row = c.fetchone()
        conn.close()
        return {"user_id": row[0], "email": row[1], "password_hash": row[2], "role": row[3]} if row else None
