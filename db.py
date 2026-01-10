import os
import psycopg
from psycopg.rows import dict_row
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv('DATABASE_URL')

def get_connection():
    if not DATABASE_URL:
        return None
    try:
        return psycopg.connect(DATABASE_URL, autocommit=False)
    except Exception as e:
        print(f"Database connection error: {e}")
        return None

def init_db():
    conn = get_connection()
    if not conn:
        return
    try:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS runs (
                    id SERIAL PRIMARY KEY,
                    run_number INT NOT NULL,
                    started_at TIMESTAMP NOT NULL,
                    completed_at TIMESTAMP,
                    total_duration_seconds FLOAT,
                    status VARCHAR(20) DEFAULT 'running',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS region_results (
                    id SERIAL PRIMARY KEY,
                    run_id INT REFERENCES runs(id) ON DELETE CASCADE,
                    region VARCHAR(10) NOT NULL,
                    total_accounts INT NOT NULL,
                    success_count INT NOT NULL,
                    failed_count INT NOT NULL,
                    timed_out_count INT DEFAULT 0,
                    success_rate FLOAT NOT NULL,
                    duration_seconds FLOAT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
            conn.commit()
    except Exception as e:
        print(f"Database initialization error: {e}")
    finally:
        conn.close()

def save_run(run_number, started_at, status='running'):
    conn = get_connection()
    if not conn:
        return None
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO runs (run_number, started_at, status) VALUES (%s, %s, %s) RETURNING id",
                (run_number, started_at, status)
            )
            run_id = cur.fetchone()[0]
            conn.commit()
            return run_id
    except Exception as e:
        print(f"Error saving run: {e}")
        return None
    finally:
        conn.close()

def update_run_completion(run_id, completed_at, duration, status='completed'):
    conn = get_connection()
    if not conn:
        return
    try:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE runs SET completed_at = %s, total_duration_seconds = %s, status = %s WHERE id = %s",
                (completed_at, duration, status, run_id)
            )
            conn.commit()
    except Exception as e:
        print(f"Error updating run: {e}")
    finally:
        conn.close()

def save_region_result(run_id, region, total, success, failed, timed_out, success_rate, duration):
    conn = get_connection()
    if not conn:
        return
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO region_results (run_id, region, total_accounts, success_count, failed_count, timed_out_count, success_rate, duration_seconds) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                (run_id, region, total, success, failed, timed_out, success_rate, duration)
            )
            conn.commit()
    except Exception as e:
        print(f"Error saving region result: {e}")
    finally:
        conn.close()

def get_history(limit=10):
    conn = get_connection()
    if not conn:
        return []
    try:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("""
                SELECT r.id, r.run_number, r.started_at, r.completed_at, r.total_duration_seconds as elapsed, r.status
                FROM runs r
                ORDER BY r.started_at DESC
                LIMIT %s
            """, (limit,))
            runs = cur.fetchall()
            
            # Convert to list of dicts (psycopg3 returns Row objects)
            runs = [dict(run) for run in runs]
            
            for run in runs:
                cur.execute("""
                    SELECT region, total_accounts as total, success_count as success, failed_count as failed, 
                           timed_out_count as timed_out, success_rate, duration_seconds as duration
                    FROM region_results
                    WHERE run_id = %s
                """, (run['id'],))
                results = cur.fetchall()
                run['result'] = {'results': [dict(r) for r in results]}
                # Convert datetime to ISO string for JSON serialization
                if run['started_at']:
                    run['started_at'] = run['started_at'].isoformat()
                if run['completed_at']:
                    run['completed_at'] = run['completed_at'].isoformat()
                
            return runs
    except Exception as e:
        print(f"Error fetching history: {e}")
        return []
    finally:
        conn.close()
