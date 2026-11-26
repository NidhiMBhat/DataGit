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

            CREATE TABLE IF NOT EXISTS datagit_merge_events (
                id SERIAL PRIMARY KEY,
                workspace_id VARCHAR(64) NOT NULL DEFAULT 'default',
                actor VARCHAR(100) NOT NULL,
                source_branch VARCHAR(128),
                source_commit_id INT,
                target_branch VARCHAR(128),
                target_commit_id INT,
                outcome VARCHAR(32) NOT NULL,
                conflict_details JSONB,
                error_message TEXT,
                merge_commit_id INT REFERENCES datagit_commits(commit_id) ON DELETE SET NULL,
                is_preview BOOLEAN NOT NULL DEFAULT FALSE,
                attempted_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE INDEX IF NOT EXISTS idx_datagit_merge_events_attempted_at ON datagit_merge_events(attempted_at);
            CREATE INDEX IF NOT EXISTS idx_datagit_merge_events_workspace ON datagit_merge_events(workspace_id);

            CREATE TABLE IF NOT EXISTS datagit_tracking_meta (
                key VARCHAR(64) PRIMARY KEY,
                value TEXT NOT NULL,
                created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
            );

            INSERT INTO datagit_tracking_meta (key, value)
            VALUES ('merge_outcome_tracking_started_at', CURRENT_TIMESTAMP::text)
            ON CONFLICT (key) DO NOTHING;

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