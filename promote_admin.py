#!/usr/bin/env python
import sqlite3

DATABASE = 'database.db'

conn = sqlite3.connect(DATABASE, timeout=20)
c = conn.cursor()

# Promote first admin to master
c.execute("UPDATE admins SET role = 'master' WHERE username = 'admin'")
conn.commit()

# Show all admins
c.execute('SELECT id, username, email, role FROM admins')
print("Current admins:")
for row in c.fetchall():
    print(f"ID: {row[0]}, Username: {row[1]}, Email: {row[2]}, Role: {row[3]}")

conn.close()
print("\nAdmin 'admin' has been promoted to master role!")
