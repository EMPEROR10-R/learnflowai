# reset_db.py
import os
if os.path.exists("users.db"):
    os.remove("users.db")
print("Old DB deleted")

from database import Database
db = Database()
print("Fresh database created with ADMIN:")
print("Email: kingmumo15@gmail.com")
print("Password: @Yoounruly10")
