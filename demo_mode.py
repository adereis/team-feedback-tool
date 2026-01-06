"""
Demo mode functionality for cloud deployment.

Provides session-based database isolation so each visitor gets their own sandbox.
Uses pre-built template databases for consistent demo experience.
"""
import os
import uuid
import time
import threading
import shutil
from datetime import datetime
from pathlib import Path
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from flask import request, g


def _log(message):
    """Log with timestamp and worker PID for debugging."""
    timestamp = datetime.now().strftime('%H:%M:%S.%f')[:-3]
    pid = os.getpid()
    print(f"[{timestamp}] [pid:{pid}] [Demo] {message}")


# Configuration
SESSION_TIMEOUT_SECONDS = int(os.getenv('SESSION_TIMEOUT_SECONDS', 3600))  # 1 hour default
SESSION_CLEANUP_INTERVAL = int(os.getenv('SESSION_CLEANUP_INTERVAL', 300))  # 5 min default
SESSION_COOKIE_NAME = 'demo_session_id'
SESSION_DB_DIR_BASE = os.getenv('SESSION_DB_DIR', '/tmp/demo_sessions')

# Server instance ID - ensures multiple server instances don't share session files
# Each server instance gets its own subdirectory under SESSION_DB_DIR_BASE
def _get_server_instance_id():
    env_id = os.getenv('SERVER_INSTANCE_ID')
    if env_id:
        return env_id
    # Use parent PID - consistent across all workers under same Gunicorn master
    return f'ppid_{os.getppid()}'


SERVER_INSTANCE_ID = _get_server_instance_id()
SESSION_DB_DIR = os.path.join(SESSION_DB_DIR_BASE, f'instance_{SERVER_INSTANCE_ID}')

# Path to pre-built template database
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATE_DB_PATH = os.path.join(SCRIPT_DIR, 'demo-templates', 'demo.db')

# Session tracking
_session_engines = {}
_session_last_access = {}
_session_db_mtime = {}  # Track DB file modification time to detect changes from other workers
_cleanup_lock = threading.Lock()


def get_session_id():
    """Get or create a session ID from cookie.

    Uses Flask's g object to cache the session ID within a single request,
    ensuring all calls return the same value (critical for cookie consistency).
    """
    # Return cached session ID if we already generated one this request
    if hasattr(g, '_demo_session_id'):
        return g._demo_session_id

    session_id = request.cookies.get(SESSION_COOKIE_NAME)
    if not session_id:
        session_id = str(uuid.uuid4())

    # Cache for this request so all calls return the same ID
    g._demo_session_id = session_id
    return session_id


def get_session_db_path(session_id):
    """Get the database file path for a session."""
    Path(SESSION_DB_DIR).mkdir(parents=True, exist_ok=True)
    return os.path.join(SESSION_DB_DIR, f'session_{session_id}.db')


def session_has_data(session_id):
    """Check if a session already has a database with data."""
    db_path = get_session_db_path(session_id)
    # Check if database exists and has reasonable size (not just schema)
    return os.path.exists(db_path) and os.path.getsize(db_path) > 10000


def _remove_session_files(db_path):
    """Remove a session database and its WAL mode files (.db-wal, .db-shm)."""
    for suffix in ['', '-wal', '-shm']:
        file_path = db_path + suffix if suffix else db_path
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
            except Exception as e:
                _log(f"Error removing {file_path}: {e}")


def initialize_session_from_template(session_id):
    """
    Initialize a session database by copying the template.

    Uses atomic rename to prevent race conditions where another worker
    might create an empty database during the copy operation.

    Args:
        session_id: The session ID

    Returns:
        bool: True if successful, False otherwise
    """
    global _session_engines, _session_db_mtime

    db_path = get_session_db_path(session_id)

    # Check template exists first
    if not os.path.exists(TEMPLATE_DB_PATH):
        _log(f"Template not found: {TEMPLATE_DB_PATH}")
        return False

    # Close existing engine if any
    if session_id in _session_engines:
        try:
            _session_engines[session_id].dispose()
        except Exception:
            pass
        del _session_engines[session_id]

    # Clear mtime tracking so next access creates fresh engine
    if session_id in _session_db_mtime:
        del _session_db_mtime[session_id]

    try:
        # Use atomic approach: copy to temp, then rename
        temp_path = db_path + '.tmp'

        # Copy template to temp file
        shutil.copy(TEMPLATE_DB_PATH, temp_path)

        # Remove old database AND its WAL files
        _remove_session_files(db_path)

        # Atomic rename (on Linux, rename is atomic within same filesystem)
        os.rename(temp_path, db_path)

        # Ensure mtime is current so other workers detect the change
        os.utime(db_path, None)

        _log(f"Session {session_id[:8]}: initialized from template ({os.path.getsize(db_path)} bytes)")
        return True
    except Exception as e:
        _log(f"Error copying template: {e}")
        # Clean up temp file if it exists
        if os.path.exists(db_path + '.tmp'):
            try:
                os.remove(db_path + '.tmp')
            except Exception:
                pass
        return False


def _create_sqlite_engine(db_path):
    """Create a SQLite engine with settings optimized for concurrency.

    Uses WAL (Write-Ahead Logging) mode for better concurrent access:
    - Multiple readers can access simultaneously
    - Writers don't block readers
    - Better performance under Gunicorn with multiple workers
    """
    engine = create_engine(
        f'sqlite:///{db_path}',
        echo=False,
        connect_args={"check_same_thread": False},  # Required for multi-threaded access
        pool_pre_ping=True,  # Verify connections before using
    )

    # Enable WAL mode for better concurrency
    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=5000")  # Wait up to 5s for locks
        cursor.close()

    return engine


def get_session_engine(session_id):
    """Get or create a SQLAlchemy engine for a session.

    Handles multi-worker scenarios by checking if the database file has been
    modified since we created the engine (e.g., by another Gunicorn worker
    copying a template). If so, we recreate the engine to pick up the changes.

    Auto-initializes from template if no database exists.
    """
    global _session_engines, _session_last_access, _session_db_mtime

    db_path = get_session_db_path(session_id)

    sid = session_id[:8]
    has_cached = session_id in _session_engines
    file_exists = os.path.exists(db_path)

    # Auto-initialize from template if database doesn't exist
    if not file_exists:
        _log(f"Session {sid}: no DB found, initializing from template")
        if not initialize_session_from_template(session_id):
            # If template copy fails, create empty database
            _log(f"Session {sid}: template init failed, creating empty DB")

    # Check if we need to recreate the engine (file was modified or deleted externally)
    if has_cached:
        if not os.path.exists(db_path):
            # File was deleted (possibly during atomic template copy)
            _log(f"Session {sid}: file missing, invalidating cached engine")
            try:
                _session_engines[session_id].dispose()
            except Exception:
                pass
            del _session_engines[session_id]
            if session_id in _session_db_mtime:
                del _session_db_mtime[session_id]
            has_cached = False
        else:
            current_mtime = os.path.getmtime(db_path)
            cached_mtime = _session_db_mtime.get(session_id, 0)
            if current_mtime > cached_mtime:
                # Database was modified by another worker, recreate engine
                _log(f"Session {sid}: mtime changed, recreating engine")
                try:
                    _session_engines[session_id].dispose()
                except Exception:
                    pass
                del _session_engines[session_id]
                has_cached = False

    if session_id not in _session_engines:
        # If database doesn't exist after init attempt, create empty schema
        if not os.path.exists(db_path):
            _log(f"Session {sid}: creating NEW empty DB")
            engine = _create_sqlite_engine(db_path)
            from models import Base
            Base.metadata.create_all(bind=engine)
            _session_engines[session_id] = engine
        else:
            # Database exists, just create engine
            file_size = os.path.getsize(db_path)
            _log(f"Session {sid}: creating engine for existing DB ({file_size} bytes)")
            engine = _create_sqlite_engine(db_path)
            _session_engines[session_id] = engine

        # Track the file's mtime so we can detect changes
        if os.path.exists(db_path):
            mtime = os.path.getmtime(db_path)
            _session_db_mtime[session_id] = mtime

    # Update last access time
    _session_last_access[session_id] = time.time()

    return _session_engines[session_id]


def get_demo_db():
    """Get a database session for the current demo session."""
    session_id = get_session_id()
    engine = get_session_engine(session_id)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    return SessionLocal()


def reset_session_data(session_id):
    """
    Reset a session's database to a fresh template.

    Args:
        session_id: The session ID

    Returns:
        bool: True if successful
    """
    return initialize_session_from_template(session_id)


def cleanup_stale_sessions():
    """Remove session databases that haven't been accessed recently."""
    global _session_engines, _session_last_access

    with _cleanup_lock:
        current_time = time.time()
        stale_sessions = []

        for session_id, last_access in list(_session_last_access.items()):
            if current_time - last_access > SESSION_TIMEOUT_SECONDS:
                stale_sessions.append(session_id)

        for session_id in stale_sessions:
            try:
                # Close and remove engine
                if session_id in _session_engines:
                    _session_engines[session_id].dispose()
                    del _session_engines[session_id]

                # Remove database and WAL files
                db_path = get_session_db_path(session_id)
                _remove_session_files(db_path)

                # Remove from tracking
                if session_id in _session_last_access:
                    del _session_last_access[session_id]
                if session_id in _session_db_mtime:
                    del _session_db_mtime[session_id]

                _log(f"Cleaned up stale session: {session_id[:8]}...")
            except Exception as e:
                _log(f"Error cleaning session {session_id[:8]}: {e}")


def start_cleanup_thread():
    """Start background thread for session cleanup."""
    def cleanup_loop():
        while True:
            time.sleep(SESSION_CLEANUP_INTERVAL)
            cleanup_stale_sessions()

    thread = threading.Thread(target=cleanup_loop, daemon=True)
    thread.start()
    _log(f"Instance {SERVER_INSTANCE_ID}: cleanup thread started (interval={SESSION_CLEANUP_INTERVAL}s, timeout={SESSION_TIMEOUT_SECONDS}s)")


def demo_response_wrapper(response):
    """Add session cookie to response if needed."""
    session_id = get_session_id()

    # Only set cookie if it wasn't already in the request
    if SESSION_COOKIE_NAME not in request.cookies:
        response.set_cookie(
            SESSION_COOKIE_NAME,
            session_id,
            max_age=SESSION_TIMEOUT_SECONDS,
            httponly=True,
            samesite='Lax'
        )

    return response


def get_active_session_count():
    """Get the number of active demo sessions."""
    return len(_session_engines)
