from typing import Any
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field

from dagit.api.security import DirtyWorkspaceError, verify_read_access, verify_write_access
from dagit.assistant.assistant_service import ask_datagit, get_suggested_questions
from dagit.db.connection import get_db_cursor
from dagit.diff.diff_service import compare_commits, compare_snapshots
from dagit.reports.merge_events import get_tracking_start_date
from dagit.reports.report_service import (
    generate_csv_report,
    generate_pdf_report,
    generate_report,
)
from dagit.versioning.branch import create_branch, list_branches
from dagit.versioning.checkout import checkout_branch, checkout_commit
from dagit.versioning.commit import create_commit
from dagit.versioning.demo_scenarios import DEMO_SCENARIOS, execute_demo_scenario
from dagit.versioning.history import get_commit, get_history
from dagit.versioning.merge import MergeConflictError, merge_branch, merge_commits
from dagit.versioning.metadata import init_metadata_tables
from dagit.versioning.rollback import rollback
from dagit.versioning.snapshot import compute_snapshot_hash, generate_database_snapshot
from dagit.versioning.storage import load_snapshot_from_storage
from dagit.versioning.storage_benchmark import (
    benchmark_commits,
    benchmark_snapshots,
    generate_synthetic_snapshots,
)


router = APIRouter(prefix="/api")


class CommitRequest(BaseModel):
    message: str = Field(min_length=1)
    author: str = Field(min_length=1, max_length=100)
    parent_commit_id: int | None = None


class BranchRequest(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    from_commit_id: int | None = None


class RollbackRequest(BaseModel):
    commit_id: int | None = None
    author: str = Field(default="DataGit", min_length=1, max_length=100)
    allow_dirty: bool = False


class MergeRequest(BaseModel):
    source_commit_id: int | None = None
    source_branch: str | None = None
    author: str = Field(default="DataGit", min_length=1, max_length=100)
    message: str | None = None
    is_preview: bool = False
    workspace_id: str = "default"


class SyntheticWorkloadRequest(BaseModel):
    table_count: int = Field(default=3, ge=1, le=20)
    rows_per_table: int = Field(default=50, ge=1, le=1000)
    snapshot_count: int = Field(default=10, ge=1, le=100)
    change_ratio: float = Field(default=0.1, ge=0.0, le=1.0)


class StorageBenchmarkRequest(BaseModel):
    commit_ids: list[int] | None = Field(default=None, min_length=1, max_length=100)
    iterations: int = Field(default=1, ge=1, le=20)
    synthetic_workload: SyntheticWorkloadRequest | None = None


class DemoSimulateRequest(BaseModel):
    scenario: str = Field(default="flash_sale")
    custom_sql: str | None = None


@router.post("/commits", status_code=201, dependencies=[Depends(verify_write_access)])
def post_commit(request: CommitRequest):
    try:
        commit_id = create_commit(
            request.message, request.author, request.parent_commit_id
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return {"commit_id": commit_id}


@router.get("/commits/{commit_id}", dependencies=[Depends(verify_read_access)])
def read_commit(commit_id: int):
    try:
        return get_commit(commit_id)
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.get("/history", dependencies=[Depends(verify_read_access)])
def read_history(branch: str | None = None, limit: int | None = None):
    try:
        return get_history(branch, limit)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.get("/branches", dependencies=[Depends(verify_read_access)])
def read_branches():
    return list_branches()


@router.post("/branches", status_code=201, dependencies=[Depends(verify_write_access)])
def post_branch(request: BranchRequest):
    try:
        return create_branch(request.name, request.from_commit_id)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.post("/checkout/commits/{commit_id}", dependencies=[Depends(verify_write_access)])
def post_checkout_commit(commit_id: int, allow_dirty: bool = False):
    try:
        checkout_commit(commit_id, allow_dirty=allow_dirty)
    except DirtyWorkspaceError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    return {"commit_id": commit_id, "detached": True}


@router.post("/checkout/branches/{name:path}", dependencies=[Depends(verify_write_access)])
def post_checkout_branch(name: str, allow_dirty: bool = False):
    try:
        head_commit = checkout_branch(name, allow_dirty=allow_dirty)
    except DirtyWorkspaceError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    return {"branch": name, "head_commit": head_commit}


@router.post("/rollback", dependencies=[Depends(verify_write_access)])
def post_rollback(request: RollbackRequest):
    try:
        commit_id = rollback(
            request.commit_id, request.author, allow_dirty=request.allow_dirty
        )
    except DirtyWorkspaceError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return {"rollback_commit_id": commit_id}


@router.get("/diff/{from_commit_id}/{to_commit_id}", dependencies=[Depends(verify_read_access)])
def read_diff(from_commit_id: int, to_commit_id: int):
    try:
        return compare_commits(from_commit_id, to_commit_id)
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.get("/schema", dependencies=[Depends(verify_read_access)])
def read_schema(commit_id: int | None = None, branch: str | None = None):
    """Inspect the database schema, tables, constraints, indexes, and views for any branch, commit, or current database."""
    try:
        if commit_id is not None:
            commit_meta = get_commit(commit_id)
            state_id = commit_meta["state_id"]
            snapshot = load_snapshot_from_storage(state_id)
            target = f"Commit #{commit_id}: {commit_meta.get('message', '')}"
        elif branch is not None:
            branches = {b["name"]: b for b in list_branches()}
            if branch not in branches:
                raise ValueError(f"Unknown branch: {branch}")
            head_id = branches[branch]["head_commit"]
            if head_id is None:
                return {
                    "target": f"Branch '{branch}' (Empty)",
                    "branch": branch,
                    "tables": {},
                    "views": {},
                    "sequences": {},
                    "total_tables": 0,
                    "total_views": 0,
                    "total_sequences": 0,
                }
            commit_meta = get_commit(head_id)
            state_id = commit_meta["state_id"]
            snapshot = load_snapshot_from_storage(state_id)
            target = f"Branch '{branch}' (HEAD #{head_id})"
        else:
            snapshot = generate_database_snapshot()
            target = "Current Working Database (Live Workspace)"

        tables_summary = {}
        for tbl_name, tbl_data in snapshot.get("tables", {}).items():
            cols = tbl_data.get("columns", [])
            constrs = tbl_data.get("constraints", [])
            pk_cols = set()
            fk_links = []
            for c in constrs:
                if c.get("type") == "p":
                    pk_cols.update(c.get("columns") or [])
                elif c.get("type") == "f":
                    fk_links.append({
                        "name": c.get("name"),
                        "columns": c.get("columns", []),
                        "referenced_table": c.get("referenced_table"),
                        "referenced_columns": c.get("referenced_columns", []),
                    })

            enriched_cols = []
            for col in cols:
                enriched_cols.append({
                    **col,
                    "is_pk": col.get("name") in pk_cols,
                })

            tables_summary[tbl_name] = {
                "columns": enriched_cols,
                "constraints": constrs,
                "foreign_keys": fk_links,
                "indexes": tbl_data.get("indexes", []),
                "row_count": len(tbl_data.get("rows", [])),
            }

        return {
            "target": target,
            "commit_id": commit_id,
            "branch": branch,
            "tables": tables_summary,
            "views": snapshot.get("views", {}),
            "sequences": snapshot.get("sequences", {}),
            "total_tables": len(tables_summary),
            "total_views": len(snapshot.get("views", {})),
            "total_sequences": len(snapshot.get("sequences", {})),
        }
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.post("/merge", dependencies=[Depends(verify_write_access)])
def post_merge(request: MergeRequest):
    if (request.source_commit_id is None) == (request.source_branch is None):
        raise HTTPException(
            status_code=422,
            detail="Provide exactly one of source_commit_id or source_branch",
        )
    try:
        if request.source_branch is not None:
            commit_id = merge_branch(
                request.source_branch,
                request.author,
                request.message,
                workspace_id=request.workspace_id,
                is_preview=request.is_preview,
            )
        elif request.source_commit_id is not None:
            commit_id = merge_commits(
                request.source_commit_id,
                request.author,
                request.message,
                source_branch=None,
                workspace_id=request.workspace_id,
                is_preview=request.is_preview,
            )
        else:
            raise HTTPException(
                status_code=422,
                detail="Provide exactly one of source_commit_id or source_branch",
            )
    except MergeConflictError as error:
        raise HTTPException(
            status_code=409,
            detail={"message": str(error), "conflicts": error.conflicts},
        ) from error
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return {"merge_commit_id": commit_id}


@router.post("/storage/benchmark", dependencies=[Depends(verify_write_access)])
def post_storage_benchmark(request: StorageBenchmarkRequest):
    if (request.commit_ids is None) == (request.synthetic_workload is None):
        raise HTTPException(
            status_code=422,
            detail="Provide exactly one of commit_ids or synthetic_workload",
        )
    try:
        if request.commit_ids is not None:
            return benchmark_commits(request.commit_ids, iterations=request.iterations)
        workload = request.synthetic_workload
        snapshots = generate_synthetic_snapshots(
            table_count=workload.table_count,
            rows_per_table=workload.rows_per_table,
            snapshot_count=workload.snapshot_count,
            change_ratio=workload.change_ratio,
        )
        result = benchmark_snapshots(snapshots, iterations=request.iterations)
        return {"synthetic_workload": workload.model_dump(), **result}
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.get("/workspace/status", dependencies=[Depends(verify_read_access)])
def read_workspace_status():
    """Detect if uncommitted changes exist in PostgreSQL compared to active branch HEAD."""
    init_metadata_tables()
    with get_db_cursor() as cursor:
        cursor.execute("""
            SELECT w.active_branch, w.detached_commit, b.head_commit
            FROM datagit_workspace w
            LEFT JOIN datagit_branches b ON b.name = w.active_branch
            WHERE w.singleton = TRUE;
        """)
        workspace = cursor.fetchone()
        current_head = (
            workspace["head_commit"]
            if workspace and workspace["active_branch"] is not None
            else (workspace["detached_commit"] if workspace else None)
        )
        active_branch = workspace["active_branch"] if workspace else None

        if current_head is None:
            return {
                "is_dirty": False,
                "current_head": None,
                "active_branch": active_branch,
                "summary": None,
                "schema_changes": [],
                "row_changes": [],
            }

        cursor.execute(
            "SELECT state_id FROM datagit_commits WHERE commit_id = %s;",
            (current_head,),
        )
        head_row = cursor.fetchone()
        if head_row is None:
            return {
                "is_dirty": False,
                "current_head": current_head,
                "active_branch": active_branch,
                "summary": None,
                "schema_changes": [],
                "row_changes": [],
            }

        head_snapshot = load_snapshot_from_storage(head_row["state_id"])
        current_snapshot = generate_database_snapshot(cursor=cursor)
        import json
        current_snapshot_norm = json.loads(json.dumps(current_snapshot, default=str))

        diff_res = compare_snapshots(head_snapshot, current_snapshot_norm)
        is_dirty = bool(
            (diff_res.get("schema_changes") and len(diff_res["schema_changes"]) > 0) or
            (diff_res.get("row_changes") and len(diff_res["row_changes"]) > 0)
        )
        head_hash = compute_snapshot_hash(head_snapshot)
        current_hash = compute_snapshot_hash(current_snapshot_norm)

        return {
            "is_dirty": is_dirty,
            "current_head": current_head,
            "active_branch": active_branch,
            "head_hash": head_hash,
            "current_hash": current_hash,
            "summary": diff_res["summary"] if diff_res else {
                "tables_added": 0, "tables_dropped": 0, "tables_altered": 0,
                "rows_inserted": 0, "rows_deleted": 0, "rows_updated": 0,
            },
            "schema_changes": diff_res["schema_changes"] if diff_res else [],
            "row_changes": diff_res["row_changes"] if diff_res else [],
        }


@router.get("/demo/scenarios", dependencies=[Depends(verify_read_access)])
def read_demo_scenarios():
    """List available e-commerce database manipulation scenarios for live demonstrations."""
    scenarios = []
    for key, item in DEMO_SCENARIOS.items():
        scenarios.append({
            "key": key,
            "title": item["title"],
            "description": item["description"],
            "suggested_commit_message": item["suggested_commit_message"],
            "sql": item["sql"].strip(),
        })
    return {
        "scenarios": scenarios,
        "can_reset": True,
    }


@router.post("/demo/simulate", dependencies=[Depends(verify_write_access)])
def post_demo_simulate(request: DemoSimulateRequest):
    """Execute a live demo manipulation scenario or custom SQL on PostgreSQL."""
    try:
        result = execute_demo_scenario(request.scenario, custom_sql=request.custom_sql)
        status = read_workspace_status()
        return {**result, "workspace_status": status}
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.get("/reports", dependencies=[Depends(verify_read_access)])
def read_report(
    mode: str = Query("activity", pattern="^(activity|data_schema|merge_conflict)$"),
    date_range: str = Query("monthly", pattern="^(weekly|monthly|custom)$"),
    start_date: str | None = None,
    end_date: str | None = None,
    branch: str | None = None,
    table: str | None = None,
    timezone: str = "UTC",
    workspace_id: str = "default",
):
    """Generate dynamic analytics report for activity, data/schema changes, or merge outcomes."""
    try:
        return generate_report(
            mode=mode,
            date_range=date_range,
            start_date=start_date,
            end_date=end_date,
            branch=branch,
            table=table,
            workspace_id=workspace_id,
            tz_label=timezone,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.get("/reports/export/csv", dependencies=[Depends(verify_read_access)])
def export_report_csv(
    mode: str = Query("activity", pattern="^(activity|data_schema|merge_conflict)$"),
    date_range: str = Query("monthly", pattern="^(weekly|monthly|custom)$"),
    start_date: str | None = None,
    end_date: str | None = None,
    branch: str | None = None,
    table: str | None = None,
    timezone: str = "UTC",
    workspace_id: str = "default",
):
    """Export the dynamic report as CSV reconciling with the dashboard query."""
    try:
        report_data = generate_report(
            mode=mode,
            date_range=date_range,
            start_date=start_date,
            end_date=end_date,
            branch=branch,
            table=table,
            workspace_id=workspace_id,
            tz_label=timezone,
        )
        csv_content, filename = generate_csv_report(report_data)
        return Response(
            content=csv_content,
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.get("/reports/export/pdf", dependencies=[Depends(verify_read_access)])
def export_report_pdf(
    mode: str = Query("activity", pattern="^(activity|data_schema|merge_conflict)$"),
    date_range: str = Query("monthly", pattern="^(weekly|monthly|custom)$"),
    start_date: str | None = None,
    end_date: str | None = None,
    branch: str | None = None,
    table: str | None = None,
    timezone: str = "UTC",
    workspace_id: str = "default",
):
    """Export the dynamic report as PDF with active filters, summary totals, charts, and details."""
    try:
        report_data = generate_report(
            mode=mode,
            date_range=date_range,
            start_date=start_date,
            end_date=end_date,
            branch=branch,
            table=table,
            workspace_id=workspace_id,
            tz_label=timezone,
        )
        pdf_bytes, filename = generate_pdf_report(report_data)
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.get("/reports/meta", dependencies=[Depends(verify_read_access)])
def read_reports_metadata():
    """Retrieve metadata about report capabilities and historical tracking start date."""
    return {
        "modes": ["activity", "data_schema", "merge_conflict"],
        "date_ranges": ["weekly", "monthly", "custom"],
        "merge_outcome_tracking_started_at": get_tracking_start_date(),
    }


class AssistantAskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=1000)
    context_filters: dict[str, Any] | None = None
    workspace_id: str = "default"
    timezone: str = "UTC"


@router.post("/assistant/ask", dependencies=[Depends(verify_read_access)])
def post_assistant_ask(request: AssistantAskRequest):
    """Ask DataGit: Read-only RAG assistant for repository statistics, evidence, and explanations."""
    try:
        return ask_datagit(
            question=request.question,
            context_filters=request.context_filters,
            workspace_id=request.workspace_id,
            tz_label=request.timezone,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.get("/assistant/suggestions", dependencies=[Depends(verify_read_access)])
def read_assistant_suggestions():
    """Return categorized suggested questions for Ask DataGit."""
    return {"suggestions": get_suggested_questions()}
