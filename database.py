import sqlite3
import os
from flask import g
from werkzeug.security import generate_password_hash
from config import Config

def get_db():
    """
    Opens a unique database connection per request, storing it in Flask's application context 'g'.
    Configures row_factory to sqlite3.Row for dictionary-like column access.
    """
    if 'db' not in g:
        g.db = sqlite3.connect(Config.DATABASE_PATH)
        g.db.row_factory = sqlite3.Row
        # Enable foreign key enforcement
        g.db.execute("PRAGMA foreign_keys = ON;")
    return g.db

def close_db(e=None):
    """
    Closes the database connection at the end of the request context.
    """
    db = g.pop('db', None)
    if db is not None:
        db.close()

def query_db(query, args=(), one=False):
    """
    Convenience helper to query the database.
    Returns a list of sqlite3.Row or a single sqlite3.Row if one=True.
    """
    cur = get_db().execute(query, args)
    rv = cur.fetchall()
    cur.close()
    return (rv[0] if rv else None) if one else rv

def execute_db(query, args=(), commit=True):
    """
    Convenience helper to execute an INSERT/UPDATE/DELETE query.
    Returns the lastrowid or rowcount.
    """
    db = get_db()
    cur = db.execute(query, args)
    if commit:
        db.commit()
    last_id = cur.lastrowid
    cur.close()
    return last_id

def init_db(app=None):
    """
    Initializes the database using schema.sql and seeds initial data if empty.
    """
    os.makedirs(os.path.dirname(Config.DATABASE_PATH), exist_ok=True)
    os.makedirs(Config.UPLOAD_FOLDER, exist_ok=True)
    
    conn = sqlite3.connect(Config.DATABASE_PATH)
    conn.execute("PRAGMA foreign_keys = ON;")
    
    # Read and execute schema
    schema_path = os.path.join(Config.BASE_DIR, 'schema.sql')
    with open(schema_path, 'r', encoding='utf-8') as f:
        conn.executescript(f.read())
    conn.commit()
    conn.close()

def generate_complaint_code():
    """
    Generates a unique complaint code like CMP-2026-0001 based on current year and sequence.
    """
    import datetime
    current_year = datetime.datetime.now().year
    prefix = f"CMP-{current_year}-"
    
    db = get_db()
    cursor = db.execute(
        "SELECT complaint_code FROM complaints WHERE complaint_code LIKE ? ORDER BY id DESC LIMIT 1",
        (f"{prefix}%",)
    )
    last_row = cursor.fetchone()
    
    if last_row:
        last_code = last_row['complaint_code']
        try:
            last_seq = int(last_code.split('-')[-1])
            new_seq = last_seq + 1
        except ValueError:
            new_seq = 1
    else:
        new_seq = 1
        
    return f"{prefix}{new_seq:04d}"

def seed_db():
    """
    Seeds initial default admin, students, departments, complaints, timeline updates, and feedback.
    """
    conn = sqlite3.connect(Config.DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    cur = conn.cursor()
    
    # Check if admin already exists
    cur.execute("SELECT id FROM users WHERE email = ?", ('admin@college.com',))
    if cur.fetchone() is not None:
        conn.close()
        return

    # 1. Seed Departments
    departments = [
        "Hostel & Housing",
        "Mess & Cafeteria",
        "Classroom & Labs",
        "Faculty & Academics",
        "Library & Study Halls",
        "Transport & Bus Service",
        "IT & Campus Wi-Fi",
        "Accounts & Scholarships"
    ]
    for dept in departments:
        cur.execute("INSERT OR IGNORE INTO departments (name) VALUES (?)", (dept,))

    # 2. Seed Users
    # Default Admin
    admin_pw = generate_password_hash("Admin@123")
    cur.execute("""
        INSERT INTO users (name, email, password_hash, role, roll_no, department, is_active)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, ("Dr. Rajesh Sharma (Dean)", "admin@college.com", admin_pw, "admin", "ADM-001", "Grievance Redressal Cell", 1))
    
    # Sample Student 1
    student1_pw = generate_password_hash("Student@123")
    cur.execute("""
        INSERT INTO users (name, email, password_hash, role, roll_no, department, is_active)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, ("Rahul Verma", "rahul.sharma@college.com", student1_pw, "student", "2024CS101", "Computer Science & Engg", 1))
    student1_id = cur.lastrowid
    
    # Sample Student 2
    student2_pw = generate_password_hash("Student@123")
    cur.execute("""
        INSERT INTO users (name, email, password_hash, role, roll_no, department, is_active)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, ("Priya Patel", "priya.patel@college.com", student2_pw, "student", "2024EC205", "Electronics & Comm. Engg", 1))
    student2_id = cur.lastrowid

    import datetime
    now = datetime.datetime.now()
    year = now.year

    def d_str(days_ago, hour, minute):
        dt = (now - datetime.timedelta(days=days_ago)).replace(hour=hour, minute=minute, second=0, microsecond=0)
        return dt.strftime('%Y-%m-%d %H:%M:%S')

    # Sample Complaints Data across various statuses
    sample_complaints = [
        {
            "code": f"CMP-{year}-0001",
            "user_id": student1_id,
            "title": "Wi-Fi connectivity issue in Block B Hostel 3rd Floor",
            "category": "IT & Campus Wi-Fi",
            "description": "The campus Wi-Fi access point on Block B, 3rd floor drops connection every 10 minutes. Students are unable to attend online certification tests.",
            "priority": "High",
            "status": "In Progress",
            "is_anonymous": 0,
            "assigned_to": "Mr. Anil Kumar (IT Cell)",
            "created_at": d_str(6, 10, 15),
            "updates": [
                ("Pending", "Complaint submitted successfully by student.", "System", d_str(6, 10, 15)),
                ("Under Review", "Grievance cell reviewed the report and forwarded to Network team.", "Dr. Rajesh Sharma (Dean)", d_str(6, 14, 30)),
                ("In Progress", "IT technician assigned to replace the faulty router switch. Hardware replacement in progress.", "Mr. Anil Kumar (IT Cell)", d_str(5, 9, 0))
            ],
            "feedback": None
        },
        {
            "code": f"CMP-{year}-0002",
            "user_id": student2_id,
            "title": "Unhygienic drinking water cooler in Mess Block A",
            "category": "Mess & Cafeteria",
            "description": "Water cooler in Mess Block A has rust and sediment deposits. Needs immediate water filter replacement and tank cleaning.",
            "priority": "Urgent",
            "status": "Resolved",
            "is_anonymous": 0,
            "assigned_to": "Mess Committee In-Charge",
            "created_at": d_str(10, 8, 30),
            "updates": [
                ("Pending", "Complaint registered.", "System", d_str(10, 8, 30)),
                ("Under Review", "Mess supervisor inspected the water purification unit.", "Dr. Rajesh Sharma (Dean)", d_str(10, 11, 0)),
                ("In Progress", "RO filter replaced and water tank completely sanitized.", "Mess Committee In-Charge", d_str(9, 16, 0)),
                ("Resolved", "Water quality tested and certified clean. Cooler restored to full service.", "Mess Committee In-Charge", d_str(8, 10, 0))
            ],
            "feedback": (5, "Issue resolved very quickly and the water cooler is sparkling clean now. Thank you!")
        },
        {
            "code": f"CMP-{year}-0003",
            "user_id": student1_id,
            "title": "Air Conditioner malfunctioning in Seminar Hall 2",
            "category": "Classroom & Labs",
            "description": "The central AC unit in Seminar Hall 2 makes a loud grinding noise and does not cool during afternoon lectures.",
            "priority": "Medium",
            "status": "Pending",
            "is_anonymous": 1,
            "assigned_to": "Estate & Maintenance Office",
            "created_at": d_str(2, 11, 45),
            "updates": [
                ("Pending", "Complaint submitted anonymously. Awaiting admin review.", "System", d_str(2, 11, 45))
            ],
            "feedback": None
        },
        {
            "code": f"CMP-{year}-0004",
            "user_id": student2_id,
            "title": "Delay in publishing Semester 4 Re-evaluation Results",
            "category": "Faculty & Academics",
            "description": "Applied for re-evaluation over 45 days ago for Digital Signal Processing. The portal still shows pending status.",
            "priority": "High",
            "status": "Under Review",
            "is_anonymous": 0,
            "assigned_to": "Controller of Examinations",
            "created_at": d_str(4, 15, 20),
            "updates": [
                ("Pending", "Complaint submitted.", "System", d_str(4, 15, 20)),
                ("Under Review", "Forwarded to Controller of Examinations for verification.", "Dr. Rajesh Sharma (Dean)", d_str(3, 10, 10))
            ],
            "feedback": None
        },
        {
            "code": f"CMP-{year}-0005",
            "user_id": student1_id,
            "title": "Overcrowding in Route 4 College Bus during peak morning hours",
            "category": "Transport & Bus Service",
            "description": "Route 4 bus from North Campus is overloaded with standing passengers. Requesting an additional shuttle trip.",
            "priority": "Medium",
            "status": "Resolved",
            "is_anonymous": 0,
            "assigned_to": "Transport Officer",
            "created_at": d_str(15, 9, 10),
            "updates": [
                ("Pending", "Complaint registered.", "System", d_str(15, 9, 10)),
                ("Under Review", "Transport supervisor verified passenger count logs.", "Dr. Rajesh Sharma (Dean)", d_str(14, 12, 0)),
                ("In Progress", "Scheduling a 32-seater mini bus starting from next Monday.", "Transport Officer", d_str(13, 14, 0)),
                ("Resolved", "Supplementary morning bus service deployed on Route 4 successfully.", "Transport Officer", d_str(11, 18, 0))
            ],
            "feedback": (4, "Appreciate the fast action by the transport department.")
        },
        {
            "code": f"CMP-{year}-0006",
            "user_id": student2_id,
            "title": "Request for unauthorized extension of library timings beyond midnight",
            "category": "Library & Study Halls",
            "description": "Please keep the library open 24x7 without any security check for non-hostel outsiders.",
            "priority": "Low",
            "status": "Rejected",
            "is_anonymous": 0,
            "assigned_to": "Chief Librarian",
            "created_at": d_str(12, 16, 30),
            "updates": [
                ("Pending", "Complaint submitted.", "System", d_str(12, 16, 30)),
                ("Under Review", "Reviewed by Library Disciplinary Committee.", "Dr. Rajesh Sharma (Dean)", d_str(11, 11, 30)),
                ("Rejected", "Request violates college safety guidelines. Library remains open until 11:00 PM for all bonafide students with ID cards.", "Chief Librarian", d_str(10, 9, 15))
            ],
            "feedback": None
        },
        {
            "code": f"CMP-{year}-0007",
            "user_id": student1_id,
            "title": "Broken bench and projector flickering in CS Lab 4",
            "category": "Classroom & Labs",
            "description": "Row 3 wooden bench is broken. HDMI cable for projector is faulty causing screen flickering during lab practicals.",
            "priority": "Medium",
            "status": "In Progress",
            "is_anonymous": 0,
            "assigned_to": "CS Lab Technician",
            "created_at": d_str(3, 14, 0),
            "updates": [
                ("Pending", "Complaint registered.", "System", d_str(3, 14, 0)),
                ("Under Review", "Lab in-charge verified physical condition.", "Dr. Rajesh Sharma (Dean)", d_str(2, 9, 30)),
                ("In Progress", "Carpentry requisition raised; new HDMI cable ordered from inventory.", "CS Lab Technician", d_str(1, 11, 0))
            ],
            "feedback": None
        }
    ]

    for c in sample_complaints:
        cur.execute("""
            INSERT INTO complaints (complaint_code, user_id, title, category, description, priority, status, is_anonymous, assigned_to, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (c["code"], c["user_id"], c["title"], c["category"], c["description"], c["priority"], c["status"], c["is_anonymous"], c["assigned_to"], c["created_at"], c["created_at"]))
        complaint_id = cur.lastrowid

        # Insert updates
        for st, remark, updated_by, timestamp in c["updates"]:
            cur.execute("""
                INSERT INTO complaint_updates (complaint_id, status, remark, updated_by, updated_at)
                VALUES (?, ?, ?, ?, ?)
            """, (complaint_id, st, remark, updated_by, timestamp))

        # Insert feedback if present
        if c["feedback"]:
            rating, comment = c["feedback"]
            cur.execute("""
                INSERT INTO feedback (complaint_id, rating, comment, created_at)
                VALUES (?, ?, ?, ?)
            """, (complaint_id, rating, comment, c["created_at"]))

    conn.commit()
    conn.close()
