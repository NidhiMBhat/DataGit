from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from dagit.api.security import DirtyWorkspaceError, verify_read_access, verify_write_access
from dagit.diff.diff_service import compare_commits
from dagit.versioning.branch import create_branch, list_branches
from dagit.versioning.checkout import checkout_branch, checkout_commit
from dagit.versioning.commit import create_commit
from dagit.versioning.history import get_commit, get_history
from dagit.versioning.merge import MergeConflictError, merge_branch, merge_commits
from dagit.versioning.rollback import rollback
from dagit.versioning.snapshot import generate_database_snapshot
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


class SyntheticWorkloadRequest(BaseModel):
    table_count: int = Field(default=3, ge=1, le=20)
    rows_per_table: int = Field(default=50, ge=1, le=1000)
    snapshot_count: int = Field(default=10, ge=1, le=100)
    change_ratio: float = Field(default=0.1, ge=0.0, le=1.0)


class StorageBenchmarkRequest(BaseModel):
    commit_ids: list[int] | None = Field(default=None, min_length=1, max_length=100)
    iterations: int = Field(default=1, ge=1, le=20)
    synthetic_workload: SyntheticWorkloadRequest | None = None


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
                request.source_branch, request.author, request.message
            )
        elif request.source_commit_id is not None:
            commit_id = merge_commits(
                request.source_commit_id, request.author, request.message
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
