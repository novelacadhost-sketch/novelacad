#!/usr/bin/env python
import sqlite3
from datetime import datetime

DATABASE = 'database.db'

conn = sqlite3.connect(DATABASE, timeout=20)
c = conn.cursor()

try:
    # Add created_at column without default
    c.execute("ALTER TABLE admins ADD COLUMN created_at TIMESTAMP")
    conn.commit()
    print("Column 'created_at' added successfully!")
    
    # Update existing rows with current timestamp
    now = datetime.now().isoformat()
    c.execute("UPDATE admins SET created_at = ? WHERE created_at IS NULL", (now,))
    conn.commit()
    print(f"Updated existing admins with timestamp: {now}")
    
except sqlite3.OperationalError as e:
    print(f"Error: {e}")
    conn.close()
    exit(1)

# Verify columns
c.execute('PRAGMA table_info(admins)')
cols = [(col[1], col[2]) for col in c.fetchall()]
print(f'\nAdmin table columns ({len(cols)} total):')
for i, (name, dtype) in enumerate(cols):
    print(f'  {i}: {name} ({dtype})')

# Show sample data
c.execute('SELECT id, username, email, role, created_at FROM admins')
print('\nAdmin data:')
for row in c.fetchall():
    print(f'  ID: {row[0]}, User: {row[1]}, Email: {row[2]}, Role: {row[3]}, Created: {row[4]}')

conn.close()
