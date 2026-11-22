from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from dagit.diff.diff_service import compare_commits
from dagit.versioning.branch import create_branch, list_branches
from dagit.versioning.checkout import checkout_branch, checkout_commit
from dagit.versioning.commit import create_commit
from dagit.versioning.history import get_commit, get_history
from dagit.versioning.merge import MergeConflictError, merge_branch, merge_commits
from dagit.versioning.rollback import rollback
from dagit.versioning.storage_benchmark import benchmark_commits


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


class MergeRequest(BaseModel):
    source_commit_id: int | None = None
    source_branch: str | None = None
    author: str = Field(default="DataGit", min_length=1, max_length=100)
    message: str | None = None


class StorageBenchmarkRequest(BaseModel):
    commit_ids: list[int] = Field(min_length=1, max_length=100)


@router.post("/commits", status_code=201)
def post_commit(request: CommitRequest):
    try:
        commit_id = create_commit(
            request.message, request.author, request.parent_commit_id
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return {"commit_id": commit_id}


@router.get("/commits/{commit_id}")
def read_commit(commit_id: int):
    try:
        return get_commit(commit_id)
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.get("/history")
def read_history(branch: str | None = None, limit: int | None = None):
    try:
        return get_history(branch, limit)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.get("/branches")
def read_branches():
    return list_branches()


@router.post("/branches", status_code=201)
def post_branch(request: BranchRequest):
    try:
        return create_branch(request.name, request.from_commit_id)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.post("/checkout/commits/{commit_id}")
def post_checkout_commit(commit_id: int):
    try:
        checkout_commit(commit_id)
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    return {"commit_id": commit_id, "detached": True}


@router.post("/checkout/branches/{name:path}")
def post_checkout_branch(name: str):
    try:
        head_commit = checkout_branch(name)
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    return {"branch": name, "head_commit": head_commit}


@router.post("/rollback")
def post_rollback(request: RollbackRequest):
    try:
        commit_id = rollback(request.commit_id, request.author)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return {"rollback_commit_id": commit_id}


@router.get("/diff/{from_commit_id}/{to_commit_id}")
def read_diff(from_commit_id: int, to_commit_id: int):
    try:
        return compare_commits(from_commit_id, to_commit_id)
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.post("/merge")
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


@router.post("/storage/benchmark")
def post_storage_benchmark(request: StorageBenchmarkRequest):
    try:
        return benchmark_commits(request.commit_ids)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
