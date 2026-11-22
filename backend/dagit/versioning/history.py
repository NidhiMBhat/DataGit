from dagit.db.connection import get_db_cursor
from dagit.versioning.metadata import init_metadata_tables


def get_history(branch: str | None = None, limit: int | None = None) -> list[dict]:
    """Return all commits reachable from a branch or current HEAD, newest-first."""
    if limit is not None and limit < 1:
        raise ValueError("History limit must be a positive integer")
    init_metadata_tables()

    with get_db_cursor() as cursor:
        if branch is None:
            cursor.execute("""
                SELECT w.active_branch, w.detached_commit, b.head_commit
                FROM datagit_workspace w
                LEFT JOIN datagit_branches b ON b.name = w.active_branch
                WHERE w.singleton = TRUE;
            """)
            workspace = cursor.fetchone()
            head_commit = (
                workspace["head_commit"]
                if workspace["active_branch"] is not None
                else workspace["detached_commit"]
            )
        else:
            cursor.execute("SELECT head_commit FROM datagit_branches WHERE name = %s;", (branch,))
            result = cursor.fetchone()
            if result is None:
                raise ValueError(f"Unknown branch: {branch}")
            head_commit = result["head_commit"]

        if head_commit is None:
            return []

        query = """
            WITH RECURSIVE reachable_commits(commit_id) AS (
                SELECT %s::INTEGER
                UNION
                SELECT p.parent_commit_id
                FROM datagit_commit_parents p
                JOIN reachable_commits reachable ON reachable.commit_id = p.commit_id
            )
            SELECT c.commit_id, c.parent_commit, c.state_id, c.message, c.author, c.timestamp,
                   ARRAY(
                       SELECT p.parent_commit_id
                       FROM datagit_commit_parents p
                       WHERE p.commit_id = c.commit_id
                       ORDER BY p.parent_order
                   ) AS parents
            FROM datagit_commits c
            JOIN reachable_commits reachable ON reachable.commit_id = c.commit_id
            ORDER BY c.commit_id DESC
        """
        params = (head_commit,)
        if limit is not None:
            query += " LIMIT %s"
            params += (limit,)
        cursor.execute(query, params)
        commits = [dict(row) for row in cursor.fetchall()]
        return commits


def get_commit(commit_id: int) -> dict:
    init_metadata_tables()
    with get_db_cursor() as cursor:
        cursor.execute("""
            SELECT c.commit_id, c.parent_commit, c.state_id, c.message, c.author, c.timestamp,
                   ARRAY(
                       SELECT p.parent_commit_id
                       FROM datagit_commit_parents p
                       WHERE p.commit_id = c.commit_id
                       ORDER BY p.parent_order
                   ) AS parents
            FROM datagit_commits c
            WHERE c.commit_id = %s;
        """, (commit_id,))
        result = cursor.fetchone()
        if result is None:
            raise ValueError(f"Unknown commit ID: {commit_id}")
        return dict(result)
