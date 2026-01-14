import sqlite3

def init_db():
    conn = sqlite3.connect('sleep_tracker.db')
    cur = conn.cursor()
    # ユーザーテーブル (UNIQUE制約で名前の重複を防止)
    cur.execute('''CREATE TABLE IF NOT EXISTS users 
                   (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                    username TEXT UNIQUE NOT NULL, 
                    password TEXT NOT NULL)''')
    # 睡眠記録テーブル (durationはREAL型で秒数を精密保存)
    cur.execute('''CREATE TABLE IF NOT EXISTS sleep_records 
                   (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, 
                    start_time TEXT NOT NULL, end_time TEXT NOT NULL, 
                    duration REAL NOT NULL, satisfaction INTEGER NOT NULL,
                    FOREIGN KEY (user_id) REFERENCES users(id))''')
    conn.commit()
    conn.close()
    print("✅ データベース(秒単位対応)が正常に作成されました。")

if __name__ == "__main__":
    init_db()