-- ==========================================================
-- College Complaint Registration & Resolution Tracking Portal
-- Database Schema for SQLite3
-- ==========================================================

-- Enable foreign keys constraint
PRAGMA foreign_keys = ON;

-- 1. Users Table (Stores Admin and Student credentials & profile info)
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    email TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL CHECK(role IN ('admin', 'student')),
    roll_no TEXT,
    department TEXT,
    is_active INTEGER NOT NULL DEFAULT 1, -- 1: Active, 0: Blocked/Inactive
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 2. Departments Table (Hostel, Mess, Academics, Library, etc.)
CREATE TABLE IF NOT EXISTS departments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL
);

-- 3. Complaints Table (Core complaint records)
CREATE TABLE IF NOT EXISTS complaints (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    complaint_code TEXT UNIQUE NOT NULL, -- e.g. CMP-2026-0001
    user_id INTEGER NOT NULL,
    title TEXT NOT NULL,
    category TEXT NOT NULL,
    description TEXT NOT NULL,
    priority TEXT NOT NULL DEFAULT 'Medium' CHECK(priority IN ('Low', 'Medium', 'High', 'Urgent')),
    status TEXT NOT NULL DEFAULT 'Pending' CHECK(status IN ('Pending', 'Under Review', 'In Progress', 'Resolved', 'Rejected')),
    attachment TEXT, -- Stored filename in static/uploads
    is_anonymous INTEGER NOT NULL DEFAULT 0, -- 1: Anonymous, 0: Public to admin
    assigned_to TEXT, -- Staff / Department in charge
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

-- 4. Complaint Updates Table (Used for vertical stepper tracking timeline)
CREATE TABLE IF NOT EXISTS complaint_updates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    complaint_id INTEGER NOT NULL,
    status TEXT NOT NULL,
    remark TEXT NOT NULL,
    updated_by TEXT NOT NULL, -- Admin or User name
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (complaint_id) REFERENCES complaints(id) ON DELETE CASCADE
);

-- 5. Feedback Table (Post-resolution student satisfaction rating)
CREATE TABLE IF NOT EXISTS feedback (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    complaint_id INTEGER UNIQUE NOT NULL,
    rating INTEGER NOT NULL CHECK(rating >= 1 AND rating <= 5),
    comment TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (complaint_id) REFERENCES complaints(id) ON DELETE CASCADE
);

-- Create helpful indexes for performance
CREATE INDEX IF NOT EXISTS idx_complaints_code ON complaints(complaint_code);
CREATE INDEX IF NOT EXISTS idx_complaints_user_id ON complaints(user_id);
CREATE INDEX IF NOT EXISTS idx_complaints_status ON complaints(status);
CREATE INDEX IF NOT EXISTS idx_complaints_category ON complaints(category);
CREATE INDEX IF NOT EXISTS idx_updates_complaint_id ON complaint_updates(complaint_id);
