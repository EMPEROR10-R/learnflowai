import sqlite3
import json
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Any
import uuid

class Database:
    def __init__(self, db_path: str = "users.db"):
        self.db_path = db_path
        self.init_database()
    
    def get_connection(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn
    
    def init_database(self):
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id TEXT PRIMARY KEY,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_active TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                total_queries INTEGER DEFAULT 0,
                streak_days INTEGER DEFAULT 0,
                last_streak_date DATE,
                badges TEXT DEFAULT '[]',
                is_premium BOOLEAN DEFAULT 0,
                premium_expires_at TIMESTAMP,
                language_preference TEXT DEFAULT 'en',
                learning_goals TEXT DEFAULT '[]'
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS chat_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT,
                subject TEXT,
                question TEXT,
                answer TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS progress_tracking (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT,
                subject TEXT,
                topic TEXT,
                confidence_level INTEGER DEFAULT 1,
                times_reviewed INTEGER DEFAULT 0,
                last_reviewed TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS pdf_uploads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT,
                filename TEXT,
                upload_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS quiz_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT,
                subject TEXT,
                exam_type TEXT,
                score INTEGER,
                total_questions INTEGER,
                completed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS subscriptions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT,
                stripe_customer_id TEXT,
                stripe_subscription_id TEXT,
                status TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
        """)
        
        conn.commit()
        conn.close()
    
    def create_user(self, user_id: Optional[str] = None) -> str:
        if not user_id:
            user_id = str(uuid.uuid4())
        
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute("""
                INSERT INTO users (user_id) VALUES (?)
            """, (user_id,))
            conn.commit()
        except sqlite3.IntegrityError:
            pass
        finally:
            conn.close()
        
        return user_id
    
    def get_user(self, user_id: str) -> Optional[Dict[str, Any]]:
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        conn.close()
        
        if row:
            return dict(row)
        return None
    
    def update_user_activity(self, user_id: str):
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            UPDATE users 
            SET last_active = CURRENT_TIMESTAMP,
                total_queries = total_queries + 1
            WHERE user_id = ?
        """, (user_id,))
        
        conn.commit()
        conn.close()
    
    def update_streak(self, user_id: str):
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT last_streak_date, streak_days FROM users WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        
        today = datetime.now().date()
        
        if row:
            last_date = row['last_streak_date']
            current_streak = row['streak_days']
            
            if last_date:
                last_date = datetime.strptime(last_date, '%Y-%m-%d').date()
                
                if last_date == today:
                    return current_streak
                elif last_date == today - timedelta(days=1):
                    new_streak = current_streak + 1
                else:
                    new_streak = 1
            else:
                new_streak = 1
            
            cursor.execute("""
                UPDATE users 
                SET streak_days = ?,
                    last_streak_date = ?
                WHERE user_id = ?
            """, (new_streak, today.strftime('%Y-%m-%d'), user_id))
            
            conn.commit()
            conn.close()
            
            return new_streak
        
        conn.close()
        return 0
    
    def add_badge(self, user_id: str, badge: str):
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT badges FROM users WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        
        if row:
            badges = json.loads(row['badges'])
            if badge not in badges:
                badges.append(badge)
                cursor.execute("""
                    UPDATE users SET badges = ? WHERE user_id = ?
                """, (json.dumps(badges), user_id))
                conn.commit()
        
        conn.close()
    
    def add_chat_history(self, user_id: str, subject: str, question: str, answer: str):
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO chat_history (user_id, subject, question, answer)
            VALUES (?, ?, ?, ?)
        """, (user_id, subject, question, answer))
        
        conn.commit()
        conn.close()
    
    def get_chat_history(self, user_id: str, limit: int = 10) -> List[Dict[str, Any]]:
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT * FROM chat_history 
            WHERE user_id = ? 
            ORDER BY timestamp DESC 
            LIMIT ?
        """, (user_id, limit))
        
        rows = cursor.fetchall()
        conn.close()
        
        return [dict(row) for row in rows]
    
    def track_progress(self, user_id: str, subject: str, topic: str, confidence: int):
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT id, times_reviewed FROM progress_tracking 
            WHERE user_id = ? AND subject = ? AND topic = ?
        """, (user_id, subject, topic))
        
        row = cursor.fetchone()
        
        if row:
            cursor.execute("""
                UPDATE progress_tracking 
                SET confidence_level = ?,
                    times_reviewed = ?,
                    last_reviewed = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (confidence, row['times_reviewed'] + 1, row['id']))
        else:
            cursor.execute("""
                INSERT INTO progress_tracking (user_id, subject, topic, confidence_level, times_reviewed)
                VALUES (?, ?, ?, ?, 1)
            """, (user_id, subject, topic, confidence))
        
        conn.commit()
        conn.close()
    
    def get_progress_stats(self, user_id: str) -> Dict[str, Any]:
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT subject, AVG(confidence_level) as avg_confidence, COUNT(*) as topics_covered
            FROM progress_tracking
            WHERE user_id = ?
            GROUP BY subject
        """, (user_id,))
        
        rows = cursor.fetchall()
        conn.close()
        
        return [dict(row) for row in rows]
    
    def add_pdf_upload(self, user_id: str, filename: str):
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO pdf_uploads (user_id, filename)
            VALUES (?, ?)
        """, (user_id, filename))
        
        conn.commit()
        conn.close()
    
    def get_pdf_count_today(self, user_id: str) -> int:
        conn = self.get_connection()
        cursor = conn.cursor()
        
        today = datetime.now().date()
        cursor.execute("""
            SELECT COUNT(*) as count FROM pdf_uploads
            WHERE user_id = ? AND DATE(upload_date) = ?
        """, (user_id, today.strftime('%Y-%m-%d')))
        
        row = cursor.fetchone()
        conn.close()
        
        return row['count'] if row else 0
    
    def add_quiz_result(self, user_id: str, subject: str, exam_type: str, score: int, total: int):
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO quiz_results (user_id, subject, exam_type, score, total_questions)
            VALUES (?, ?, ?, ?, ?)
        """, (user_id, subject, exam_type, score, total))
        
        conn.commit()
        conn.close()
    
    def get_quiz_history(self, user_id: str) -> List[Dict[str, Any]]:
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT * FROM quiz_results
            WHERE user_id = ?
            ORDER BY completed_at DESC
            LIMIT 20
        """, (user_id,))
        
        rows = cursor.fetchall()
        conn.close()
        
        return [dict(row) for row in rows]
    
    def check_premium(self, user_id: str) -> bool:
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT is_premium, premium_expires_at FROM users WHERE user_id = ?
        """, (user_id,))
        
        row = cursor.fetchone()
        conn.close()
        
        if row and row['is_premium']:
            if row['premium_expires_at']:
                expires = datetime.strptime(row['premium_expires_at'], '%Y-%m-%d %H:%M:%S')
                return expires > datetime.now()
            return True
        
        return False
    
    def get_daily_query_count(self, user_id: str) -> int:
        conn = self.get_connection()
        cursor = conn.cursor()
        
        today = datetime.now().date()
        cursor.execute("""
            SELECT COUNT(*) as count FROM chat_history
            WHERE user_id = ? AND DATE(timestamp) = ?
        """, (user_id, today.strftime('%Y-%m-%d')))
        
        row = cursor.fetchone()
        conn.close()
        
        return row['count'] if row else 0
