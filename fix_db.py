# fix_db.py
import os
if os.path.exists("users.db"): os.remove("users.db")
from database import Database
db = Database()
print("DATABASE FIXED + ADMIN READY")
print("Login: kingmumo15@gmail.com")
print("Pass: @Yoounruly10")
