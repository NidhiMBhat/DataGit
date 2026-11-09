from dagit.db.connection import get_db_cursor

def init_metadata_tables():
    """Creates the internal metadata tracking tables inside PostgreSQL."""
    with get_db_cursor(commit=True) as cursor:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS datagit_states (
                state_id VARCHAR(64) PRIMARY KEY,
                storage_reference TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            
            CREATE TABLE IF NOT EXISTS datagit_commits (
                commit_id SERIAL PRIMARY KEY,
                parent_commit INT REFERENCES datagit_commits(commit_id),
                state_id VARCHAR(64) REFERENCES datagit_states(state_id),
                message TEXT NOT NULL,
                author VARCHAR(100) NOT NULL,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)