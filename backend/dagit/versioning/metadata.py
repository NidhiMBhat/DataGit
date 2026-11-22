from dagit.db.connection import get_db_cursor

def init_metadata_tables():
    """Create and initialize DataGit's internal metadata tables."""
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

            CREATE TABLE IF NOT EXISTS datagit_branches (
                name VARCHAR(128) PRIMARY KEY,
                head_commit INT REFERENCES datagit_commits(commit_id),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS datagit_workspace (
                singleton BOOLEAN PRIMARY KEY DEFAULT TRUE CHECK (singleton),
                active_branch VARCHAR(128) REFERENCES datagit_branches(name),
                detached_commit INT REFERENCES datagit_commits(commit_id)
            );

            CREATE TABLE IF NOT EXISTS datagit_commit_parents (
                commit_id INT NOT NULL REFERENCES datagit_commits(commit_id) ON DELETE CASCADE,
                parent_commit_id INT NOT NULL REFERENCES datagit_commits(commit_id),
                parent_order SMALLINT NOT NULL CHECK (parent_order > 0),
                PRIMARY KEY (commit_id, parent_order),
                UNIQUE (commit_id, parent_commit_id)
            );

            INSERT INTO datagit_branches (name, head_commit)
            SELECT 'main', (SELECT MAX(commit_id) FROM datagit_commits)
            WHERE NOT EXISTS (SELECT 1 FROM datagit_branches WHERE name = 'main');

            INSERT INTO datagit_workspace (singleton, active_branch, detached_commit)
            VALUES (TRUE, 'main', NULL)
            ON CONFLICT (singleton) DO NOTHING;

            INSERT INTO datagit_commit_parents (commit_id, parent_commit_id, parent_order)
            SELECT commit_id, parent_commit, 1
            FROM datagit_commits
            WHERE parent_commit IS NOT NULL
            ON CONFLICT (commit_id, parent_order) DO NOTHING;
        """)