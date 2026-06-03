import os
import sqlite3
import json
from datetime import datetime, timezone

DB_PATH = os.path.join(os.path.dirname(__file__), "call_sessions.db")

def get_connection():
    """Create and return a SQLite connection."""
    conn = sqlite3.connect(DB_PATH)
    # Enable dict-like row access
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Initialize the SQLite database and create tables if not exists."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS call_sessions (
            id TEXT PRIMARY KEY,
            started_at TEXT NOT NULL,
            ended_at TEXT,
            caller_id TEXT NOT NULL,
            transcript TEXT NOT NULL DEFAULT '[]',
            order_summary TEXT DEFAULT '{}',
            drift_detected INTEGER DEFAULT 0,
            drift_log TEXT DEFAULT '[]'
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            email TEXT PRIMARY KEY,
            password_hash TEXT NOT NULL,
            display_name TEXT,
            is_active INTEGER DEFAULT 0,
            otp TEXT,
            otp_expires TEXT
        )
    """)
    conn.commit()
    conn.close()

def create_user(email: str, password_hash: str, display_name: str, otp: str, otp_expires: str):
    """Create a new user in the database (initially inactive)."""
    init_db()
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT OR REPLACE INTO users (email, password_hash, display_name, is_active, otp, otp_expires)
        VALUES (?, ?, ?, 0, ?, ?)
    """, (email, password_hash, display_name, otp, otp_expires))
    conn.commit()
    conn.close()

def get_user(email: str) -> dict:
    """Retrieve user details by email."""
    init_db()
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE email = ?", (email,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return {
            "email": row["email"],
            "password_hash": row["password_hash"],
            "display_name": row["display_name"],
            "is_active": bool(row["is_active"]),
            "otp": row["otp"],
            "otp_expires": row["otp_expires"]
        }
    return None

def update_user_otp(email: str, otp: str, otp_expires: str):
    """Update user's OTP and its expiration."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE users
        SET otp = ?, otp_expires = ?
        WHERE email = ?
    """, (otp, otp_expires, email))
    conn.commit()
    conn.close()

def activate_user(email: str):
    """Mark a user as active and clear the OTP."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE users
        SET is_active = 1, otp = NULL, otp_expires = NULL
        WHERE email = ?
    """, (email,))
    conn.commit()
    conn.close()

def update_user_password(email: str, password_hash: str):
    """Update user password and clear OTP."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE users
        SET password_hash = ?, otp = NULL, otp_expires = NULL
        WHERE email = ?
    """, (password_hash, email))
    conn.commit()
    conn.close()

def start_session(session_id: str, caller_id: str):
    """Start a new call session and save it in the database."""
    init_db()
    conn = get_connection()
    cursor = conn.cursor()
    
    started_at = datetime.now(timezone.utc).isoformat()
    
    cursor.execute("""
        INSERT INTO call_sessions (id, started_at, caller_id, transcript, order_summary, drift_detected, drift_log)
        VALUES (?, ?, ?, '[]', '{}', 0, '[]')
    """, (session_id, started_at, caller_id))
    
    conn.commit()
    conn.close()

def end_session(session_id: str, transcript: list, order_summary: dict, drift_detected: bool, drift_log: list):
    """End a call session and update its details in the database."""
    conn = get_connection()
    cursor = conn.cursor()
    
    ended_at = datetime.now(timezone.utc).isoformat()
    
    cursor.execute("""
        UPDATE call_sessions
        SET ended_at = ?,
            transcript = ?,
            order_summary = ?,
            drift_detected = ?,
            drift_log = ?
        WHERE id = ?
    """, (
        ended_at,
        json.dumps(transcript),
        json.dumps(order_summary),
        1 if drift_detected else 0,
        json.dumps(drift_log),
        session_id
    ))
    
    conn.commit()
    conn.close()

def get_session(session_id: str) -> dict:
    """Retrieve details of a single call session."""
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM call_sessions WHERE id = ?", (session_id,))
    row = cursor.fetchone()
    conn.close()
    
    if row:
        return {
            "id": row["id"],
            "started_at": row["started_at"],
            "ended_at": row["ended_at"],
            "caller_id": row["caller_id"],
            "transcript": json.loads(row["transcript"]),
            "order_summary": json.loads(row["order_summary"]),
            "drift_detected": bool(row["drift_detected"]),
            "drift_log": json.loads(row["drift_log"])
        }
    return None

def list_sessions() -> list:
    """List all call sessions in descending order of started_at."""
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM call_sessions ORDER BY started_at DESC")
    rows = cursor.fetchall()
    conn.close()
    
    sessions = []
    for row in rows:
        sessions.append({
            "id": row["id"],
            "started_at": row["started_at"],
            "ended_at": row["ended_at"],
            "caller_id": row["caller_id"],
            "transcript": json.loads(row["transcript"]),
            "order_summary": json.loads(row["order_summary"]),
            "drift_detected": bool(row["drift_detected"]),
            "drift_log": json.loads(row["drift_log"])
        })
    return sessions
