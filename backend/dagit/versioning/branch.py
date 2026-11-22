from dagit.db.connection import get_db_cursor
from dagit.versioning.metadata import init_metadata_tables


def create_branch(name: str, from_commit_id: int | None = None) -> dict:
    if not name or not name.strip() or len(name) > 128:
        raise ValueError("Branch name must contain 1 to 128 characters")
    name = name.strip()
    init_metadata_tables()

    with get_db_cursor(commit=True) as cursor:
        cursor.execute("SELECT 1 FROM datagit_branches WHERE name = %s;", (name,))
        if cursor.fetchone():
            raise ValueError(f"Branch already exists: {name}")

        if from_commit_id is None:
            cursor.execute("""
                SELECT w.active_branch, w.detached_commit, b.head_commit
                FROM datagit_workspace w
                LEFT JOIN datagit_branches b ON b.name = w.active_branch
                WHERE w.singleton = TRUE;
            """)
            workspace = cursor.fetchone()
            from_commit_id = (
                workspace["head_commit"]
                if workspace["active_branch"] is not None
                else workspace["detached_commit"]
            )
        else:
            cursor.execute(
                "SELECT 1 FROM datagit_commits WHERE commit_id = %s;",
                (from_commit_id,),
            )
            if cursor.fetchone() is None:
                raise ValueError(f"Unknown commit ID: {from_commit_id}")

        cursor.execute(
            "INSERT INTO datagit_branches (name, head_commit) VALUES (%s, %s) "
            "RETURNING name, head_commit, created_at;",
            (name, from_commit_id),
        )
        return dict(cursor.fetchone())


def list_branches() -> list[dict]:
    init_metadata_tables()
    with get_db_cursor() as cursor:
        cursor.execute("""
            SELECT b.name, b.head_commit, b.created_at,
                   (w.active_branch = b.name) AS is_current
            FROM datagit_branches b
            CROSS JOIN datagit_workspace w
            WHERE w.singleton = TRUE
            ORDER BY b.name;
        """)
        return [dict(row) for row in cursor.fetchall()]
