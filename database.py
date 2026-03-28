import sqlite3
from werkzeug.security import generate_password_hash, check_password_hash

DB_NAME = 'users.db'

def get_db_connection():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS supervisors (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            full_name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL,
            status TEXT NOT NULL,
            joined_date TEXT NOT NULL,
            last_active TEXT NOT NULL,
            phone TEXT DEFAULT ''
        )
    ''')
    
    # Create reports table
    c.execute('''
        CREATE TABLE IF NOT EXISTS reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            time TEXT NOT NULL,
            shop_name TEXT NOT NULL,
            exit_name TEXT,
            corridors TEXT
        )
    ''')
    # Migration: ensure columns exist in reports
    try:
        c.execute('SELECT total_people FROM reports LIMIT 1')
    except Exception:
        c.execute('ALTER TABLE reports ADD COLUMN total_people INTEGER DEFAULT 0')
    try:
        c.execute('SELECT shop_people FROM reports LIMIT 1')
    except Exception:
        c.execute('ALTER TABLE reports ADD COLUMN shop_people INTEGER DEFAULT 0')

    # Create daily_sms table (also acts as migration for existing DBs)
    c.execute('''
        CREATE TABLE IF NOT EXISTS daily_sms (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            user_id INTEGER NOT NULL
        )
    ''')
    # Migration: ensure table exists even if DB was created before this feature
    try:
        c.execute('SELECT id FROM daily_sms LIMIT 1')
    except Exception:
        c.execute('''
            CREATE TABLE daily_sms (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                user_id INTEGER NOT NULL
            )
        ''')
    
    # Create default Super Admin if not exists
    c.execute("SELECT * FROM supervisors WHERE role = 'Super Admin' AND email = 'admin'")
    if c.fetchone() is None:
        hashed = generate_password_hash('admin123')
        c.execute('''INSERT INTO supervisors (full_name, email, password_hash, role, status, joined_date, last_active, phone) 
                     VALUES (?, ?, ?, ?, ?, ?, ?, ?)''', 
                  ('Super Admin', 'admin', hashed, 'Super Admin', 'Active', 'Just now', 'Just now', '05XXXXXXXX'))
        print("[OK] Default Super Admin created (admin / admin123)")
        
    conn.commit()
    conn.close()

def authenticate_user(email, password):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('SELECT id, password_hash FROM supervisors WHERE email = ?', (email,))
    user = c.fetchone()
    conn.close()
    if user and check_password_hash(user['password_hash'], password):
        return user['id']
    return None

def get_all_supervisors():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('SELECT * FROM supervisors')
    supervisors = c.fetchall()
    conn.close()
    
    supervisors_data = []
    for s in supervisors:
        supervisors_data.append({
            'id': s['id'],
            'full_name': s['full_name'],
            'email': s['email'],
            'role': s['role'],
            'status': s['status'],
            'joined_date': s['joined_date'],
            'last_active': s['last_active'],
            'phone': s['phone'],
            'corridor': s['corridor'] if 'corridor' in s.keys() else 'None'
        })
    return supervisors_data

def get_supervisor_stats():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('SELECT COUNT(*) FROM supervisors')
    total = c.fetchone()[0]
    
    c.execute("SELECT COUNT(*) FROM supervisors WHERE status = 'Active'")
    active = c.fetchone()[0]
    
    c.execute("SELECT COUNT(*) FROM supervisors WHERE status = 'Pending'")
    pending = c.fetchone()[0]
    
    conn.close()
    return total, active, pending

def add_supervisor(data):
    conn = get_db_connection()
    c = conn.cursor()
    hashed = generate_password_hash(data['password'])
    try:
        c.execute('''
            INSERT INTO supervisors (full_name, email, password_hash, role, status, joined_date, last_active, phone, corridor)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (data['full_name'], data['email'], hashed, data['role'], data['status'], data['joined_date'], data['last_active'], data['phone'], data.get('corridor', 'None')))
        conn.commit()
        return True, "Success"
    except sqlite3.IntegrityError:
        return False, "Email already exists!"
    finally:
        conn.close()

def update_supervisor(sup_id, data):
    conn = get_db_connection()
    c = conn.cursor()
    try:
        c.execute('''
            UPDATE supervisors 
            SET full_name = ?, email = ?, role = ?, status = ?, phone = ?, corridor = ?
            WHERE id = ?
        ''', (data['full_name'], data['email'], data['role'], data['status'], data['phone'], data.get('corridor', 'None'), sup_id))
        conn.commit()
        return True, "Success"
    except sqlite3.IntegrityError:
        return False, "Email already exists!"
    finally:
        conn.close()

def delete_supervisor(sup_id):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT role, email FROM supervisors WHERE id = ?", (sup_id,))
    sup = c.fetchone()
    if sup and sup['role'] == 'Super Admin' and sup['email'] == 'admin':
        conn.close()
        return False, "Cannot delete the default Super Admin!"
        
    c.execute('DELETE FROM supervisors WHERE id = ?', (sup_id,))
    conn.commit()
    conn.close()
    return True, "Success"

def add_report(shop_name, exit_name, corridors, total_people=0, shop_people=0):
    """Insert a new fire report and return its row ID."""
    conn = get_db_connection()
    c = conn.cursor()
    from datetime import datetime
    now = datetime.now()
    date_str = now.strftime("%Y-%m-%d")
    time_str = now.strftime("%H:%M:%S")
    c.execute('''
        INSERT INTO reports (date, time, shop_name, exit_name, corridors, total_people, shop_people)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (date_str, time_str, shop_name, exit_name, corridors, total_people, shop_people))
    report_id = c.lastrowid
    conn.commit()
    conn.close()
    return report_id

def update_report(report_id, exit_name, corridors):
    """Append the exit and corridors of an existing report to store the path change trajectory."""
    conn = get_db_connection()
    c = conn.cursor()
    
    c.execute('SELECT exit_name, corridors FROM reports WHERE id = ?', (report_id,))
    row = c.fetchone()
    if row:
        old_exit = row['exit_name'] or ''
        old_corridors = row['corridors'] or ''
        
        # Prevent duplicate sequential appends caused by brief ML noise
        # Only append if the new state actually differs from the *last* appended state
        last_exit = old_exit.split(' | ')[-1] if ' | ' in old_exit else old_exit
        last_corridors = old_corridors.split(' | ')[-1] if ' | ' in old_corridors else old_corridors
        
        if last_exit != exit_name or last_corridors != corridors:
            new_exit = f"{old_exit} | {exit_name}" if old_exit else exit_name
            new_corridors = f"{old_corridors} | {corridors}" if old_corridors else corridors
            
            c.execute('''
                UPDATE reports SET exit_name = ?, corridors = ?
                WHERE id = ?
            ''', (new_exit, new_corridors, report_id))
            
    conn.commit()
    conn.close()

def get_all_reports():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('SELECT * FROM reports ORDER BY id DESC')
    reports = c.fetchall()
    conn.close()
    
    reports_data = []
    for r in reports:
        reports_data.append({
            'id': r['id'],
            'date': r['date'],
            'time': r['time'],
            'shop_name': r['shop_name'],
            'exit_name': r['exit_name'],
            'corridors': r['corridors'],
            'total_people': r['total_people'],
            'shop_people': r['shop_people'] if 'shop_people' in r.keys() else 0
        })
    return reports_data

def get_reports_by_date(date):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('SELECT * FROM reports WHERE date = ? ORDER BY id DESC', (date,))
    reports = c.fetchall()
    conn.close()
    
    reports_data = []
    for r in reports:
        reports_data.append({
            'id': r['id'],
            'date': r['date'],
            'time': r['time'],
            'shop_name': r['shop_name'],
            'exit_name': r['exit_name'],
            'corridors': r['corridors'],
            'total_people': r['total_people'],
            'shop_people': r['shop_people'] if 'shop_people' in r.keys() else 0
        })
    return reports_data

def get_notified_users_by_date(date):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('SELECT user_id FROM daily_sms WHERE date = ?', (date,))
    rows = c.fetchall()
    conn.close()
    return [r['user_id'] for r in rows]

def log_sms_sent(user_id):
    conn = get_db_connection()
    c = conn.cursor()
    from datetime import datetime
    date_str = datetime.now().strftime("%Y-%m-%d")
    
    # check if already logged today
    c.execute('SELECT 1 FROM daily_sms WHERE date = ? AND user_id = ?', (date_str, user_id))
    if not c.fetchone():
        c.execute('INSERT INTO daily_sms (date, user_id) VALUES (?, ?)', (date_str, user_id))
        conn.commit()
    conn.close()

def clear_reports():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('DELETE FROM reports')
    c.execute('DELETE FROM daily_sms')
    conn.commit()
    conn.close()
