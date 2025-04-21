import sqlite3

def check_db():
    conn = sqlite3.connect('Ozon1688.db')
    cursor = conn.cursor()
    
    print("\n=== Users Table ===")
    cursor.execute("SELECT id, telegram_id, username, is_admin, subscription_type, requests_limit, requests_used FROM users")
    users = cursor.fetchall()
    for user in users:
        print(f"ID: {user[0]}, Telegram ID: {user[1]}, Username: {user[2]}, Is Admin: {user[3]}, Sub Type: {user[4]}, Limit: {user[5]}, Used: {user[6]}")
    
    print("\n=== Tasks Table ===")
    cursor.execute("SELECT id, user_id, status, created_at FROM tasks ORDER BY created_at DESC LIMIT 5")
    tasks = cursor.fetchall()
    for task in tasks:
        print(f"ID: {task[0]}, User ID: {task[1]}, Status: {task[2]}, Created: {task[3]}")
    
    conn.close()

if __name__ == "__main__":
    check_db() 