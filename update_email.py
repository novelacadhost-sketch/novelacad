import sqlite3
import getpass

DATABASE = 'database.db'

def update_admin_email(username, email):
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    c.execute("UPDATE admins SET email = ? WHERE username = ?", (email, username))
    if c.rowcount > 0:
        print(f"Updated email for user '{username}' to '{email}'.")
    else:
        print(f"User '{username}' not found.")
    conn.commit()
    conn.close()

if __name__ == "__main__":
    update_admin_email('admin', 'admin@novelacad.com')
