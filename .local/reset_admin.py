# reset_admin.py  ← create this file
import bcrypt
import sqlite3
import uuid

email = "kingmumo15@gmail.com"
new_password = "@Yoounruly10"   # change this if you want a new one

hashed = bcrypt.hashpw(new_password.encode(), bcrypt.gensalt(12)).decode()

conn = sqlite3.connect("users.db")
c = conn.cursor()

# Delete old admin (if exists)
c.execute("DELETE FROM users WHERE email = ?", (email,))

# Create fresh admin
admin_id = str(uuid.uuid4())
c.execute("""INSERT INTO users 
             (user_id, name, email, password_hash, role, is_premium) 
             VALUES (?, ?, ?, ?, ?, ?)""", 
          (admin_id, "KingMumo", email, hashed, "admin", 1))

conn.commit()
conn.close()
print("ADMIN RESET SUCCESSFUL!")
print("Email:", email)
print("Password:", new_password)
