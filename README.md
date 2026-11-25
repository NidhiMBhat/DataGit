# DataGit: PostgreSQL Version Control

DataGit is a PostgreSQL version-control backend. It records content-addressed snapshots and commit history, compares snapshots, and can navigate, restore, and merge database versions.

## Requirements and setup

- Python 3.10+
- PostgreSQL 14+
- Node.js 18+ and npm (for frontend development & building)

From the repository root:

```powershell
python -m pip install -r requirements.txt
python -m pip install -e .\backend
npm install --prefix frontend
```

Create `backend/.env`:

```dotenv
DB_HOST=localhost
DB_PORT=5432
DB_NAME=datagit_db
DB_USER=postgres
DB_PASSWORD=your_password
```

Create the `datagit_db` database in PostgreSQL before using DataGit. Keep real credentials out of version control.

## Authentication and operational safeguards

Optional environment variables harden API endpoints for shared or production-like environments:

| Variable | Purpose |
|---|---|
| `DATAGIT_API_KEY` | Admin/write API key required for all `GET` and `POST` endpoints when set (via `X-API-Key` or `Authorization: Bearer`) |
| `DATAGIT_READ_API_KEY` | Read-only API key permitted on `GET` endpoints; rejected with `403` on mutating `POST` endpoints |
| `DATAGIT_REQUIRE_AUTH` | Set to `true` to fail closed (`401`) if no API key environment variables are configured |
| `DATAGIT_READ_ONLY` | Set to `true` to block all mutating `POST` endpoints with `403` |
| `DATAGIT_PROTECT_UNCOMMITTED` | Set to `true` to refuse `checkout` and `rollback` with `409` when uncommitted working database changes exist unless `allow_dirty=true` is passed |

When none of the authentication variables are set, endpoints remain open for local development.

## Backend API

Start the API from the repository root:

```powershell
$env:PYTHONPATH = "backend"
python -m uvicorn dagit.api.app:app --reload
```

FastAPI's interactive API documentation is available at `http://127.0.0.1:8000/docs`.

The complete **DataGit Web UI Dashboard** is served automatically at the root address `http://127.0.0.1:8000/`.

## Full Stack Architecture & Frontend (React + Vite)

DataGit features a full stack architecture combining a FastAPI PostgreSQL engine with a modern **React 19 + TypeScript + Vite** frontend.

### Development workflow

1. **Start the backend API:**
   ```powershell
   $env:PYTHONPATH = "backend"
   python -m uvicorn dagit.api.app:app --reload
   ```
   FastAPI runs on `http://127.0.0.1:8000`.

2. **Seed test database with rich schema, commits, and branches:**
   ```powershell
   python backend/populate_demo_db.py
   # or
   npm run seed
   ```
   Populates `datagit_db` with e-commerce tables (`categories`, `customers`, `products`, `orders`, `order_items`, `user_sessions`, `telemetry_events`, `coupon_discounts`), constraints, sequences, views, indexes, multiple commits, and feature branches (`feature/analytics`, `feature/discounts`, `hotfix/pricing-adjustments`, and a 3-way merge on `main`).

3. **Start the Vite dev server with hot reload:**
   ```powershell
   npm run dev
   ```
   Vite runs on `http://localhost:5173` with automatic reverse proxying of `/api` requests directly to `http://127.0.0.1:8000`.

4. **Production build:**
   ```powershell
   npm run build
   ```
   Compiles the React application into `frontend/dist`. When running `uvicorn dagit.api.app:app`, FastAPI automatically serves this optimized production bundle directly at `http://127.0.0.1:8000/`.

### Dashboard capabilities

- **History & Timeline:** interactive DAG visualization showing chronological commits, author, timestamp, parent lineage, SHA-256 hash copying, and quick-action buttons (compare against HEAD/parent, checkout commit in detached HEAD mode, branch from here, and rollback).
- **Snapshot & Commit Creator:** capture PostgreSQL `public` base tables, relational constraints, rows, indexes, user triggers, privileges, views, and standalone sequences into a content-addressed snapshot.
- **Branch Management:** view all branches and their active HEAD commits, switch branches with transactional restoration, and create new branches from active HEAD or a specific commit.
- **Diff Inspector:** inspect schema changes (added, dropped, altered tables/columns/constraints and extended objects) and row changes (inserted, deleted, updated with before/after diffs) between any two commits.
- **3-Way Merge & Conflict Resolution:** merge a source branch or commit into the active branch with automatic ancestor resolution; displays conflict reports (HTTP `409`) detailing colliding rows, schema incompatibilities, and relational constraints when merges cannot be cleanly combined.
- **Storage & Performance Benchmark Dashboard:** run multi-iteration benchmarks comparing JSONB Full Snapshots, Delta persistence chains, and Shared Tables against existing commits or configurable synthetic workloads; visualizes payload sizes, relation/TOAST overheads (`pg_total_relation_size`), write/read/reconstruction timings, SHA-256 integrity verification, and storage recommendations.
- **Time-Travel & Rollback Station:** atomically revert the live PostgreSQL database to any historical snapshot state with transactional safety guarantees and uncommitted workspace safeguards (`allow_dirty`).
- **Auth & Operational Safeguards Modal:** configure `X-API-Key` or Bearer tokens, view read-only mode warnings, and manage default workspace protection settings directly in the UI.

The API is mounted at `/api`:

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/api/commits` | Snapshot the current database and create a commit |
| `GET` | `/api/commits/{commit_id}` | Retrieve commit metadata |
| `GET` | `/api/history` | Read all commits reachable from HEAD; accepts optional `branch` and `limit` |
| `GET` | `/api/branches` | List branch names, heads, and the active branch |
| `POST` | `/api/branches` | Create a branch from the active head or a selected commit |
| `POST` | `/api/checkout/commits/{commit_id}` | Restore a commit and enter detached-HEAD mode; accepts optional `allow_dirty` query flag |
| `POST` | `/api/checkout/branches/{name}` | Restore and switch to a branch; accepts optional `allow_dirty` query flag |
| `POST` | `/api/rollback` | Restore a target (or previous) commit and record a new rollback commit |
| `GET` | `/api/diff/{from_commit_id}/{to_commit_id}` | Compare row and schema changes |
| `POST` | `/api/merge` | Merge exactly one source commit or branch into the active branch |
| `POST` | `/api/storage/benchmark` | Compare JSONB snapshot, delta, and shared-table storage for `commit_ids` or a `synthetic_workload` across 1-20 `iterations` |

Example request bodies:

```json
{"message": "Add customer", "author": "Nidhi"}
```

```json
{"name": "feature/customer"}
```

```json
{"source_branch": "feature/customer", "author": "Nidhi"}
```

```json
{"commit_ids": [1, 2, 3], "iterations": 3}
```

```json
{
  "iterations": 3,
  "synthetic_workload": {
    "table_count": 3,
    "rows_per_table": 50,
    "snapshot_count": 10,
    "change_ratio": 0.1
  }
}
```

Merge conflicts and dirty-workspace rejections are returned with HTTP `409`.

## Snapshot, checkout, and merge behavior

Snapshots cover objects in PostgreSQL's `public` schema, excluding DataGit's own metadata tables. They record base tables (columns, primary/foreign/unique/check constraints, rows, non-constraint indexes, user triggers, and table privileges), views, and standalone sequences (including `last_value` and `is_called` state). SHA-256 hashes identify snapshot contents; JSON snapshot objects are stored under `backend/.datagit_storage/`.

Checkout and rollback use **exact restoration**: all application views, standalone sequences, and base tables in `public` are replaced by the selected snapshot, including dropping objects absent from that snapshot. DataGit metadata tables are preserved. PostgreSQL applies restoration in a transaction, so a failed restore is rolled back. Use a disposable database or back up important data before checking out or rolling back.

Merges use a common ancestor, combine non-overlapping row, schema, index, trigger, privilege, view, and sequence changes, and reject incompatible edits, missing foreign-key dependencies, and primary/unique-key conflicts. The merged state and two-parent commit are applied in one database transaction. A merge is refused if the working database differs from the active branch head.

This is not a full cluster-level backup/restore tool: database roles, extensions, and trigger function bodies are assumed to exist in the target database. A dependent object that prevents replacement causes the transaction to fail rather than being silently dropped.

## Tests

Run the backend tests from the repository root:

```powershell
$env:PYTHONPATH = "backend"
python -m pytest backend\tests -v
```

Diff, merge, delta-reconstruction, and API security/route tests run locally without a live database. The versioning, restoration, storage-benchmark, and end-to-end integration workflow tests require the configured PostgreSQL database.

## Storage evaluation

Normal commits currently store full JSON snapshots as content-addressed local files. The benchmark endpoint and `storage_benchmark` module compare full snapshots, deltas (a base snapshot plus subsequent diffs with full chain reconstruction), and shared table payloads using temporary PostgreSQL JSONB tables. They report `payload_bytes` (`pg_column_size`), `total_relation_bytes` (`pg_total_relation_size` including heap, TOAST, and index overhead), multi-iteration write/read/reconstruction timings, SHA-256 reconstruction verification, compression ratios, and a strategy recommendation; temporary tables are rolled back and do not persist.

## What's done so far

- **Full Stack React + Vite Application:** modern, type-safe React 19 + TypeScript frontend built with Vite, modular custom components, tabbed views, interactive commit DAG timeline, deep visual diff inspector, 3-way merge conflict reporter, real-time storage benchmark visualizations, transactional rollback station, and persistent auth/safeguards management; seamlessly integrated with FastAPI via reverse proxy in development and optimized static asset serving in production.
- **Snapshots and commits:** capture `public` tables, supported constraints, rows, non-constraint indexes, user triggers, table privileges, views, and standalone sequences; hash snapshots with SHA-256 and store them as local JSON files.
- **Row and schema diffs:** compare snapshots and report inserts, updates, deletes, table/column/constraint changes, table metadata (indexes, triggers, privileges), views, and sequences.
- **History and branches:** retrieve commit history, create branches, and track active branch heads and merge parents.
- **Checkout and rollback:** restore a selected snapshot transactionally, with exact object replacement while preserving DataGit metadata and optional uncommitted-change protection.
- **Conflict-aware merges:** merge non-overlapping changes across tables, rows, views, sequences, indexes, triggers, and privileges, and report conflicts; successful merges create two-parent commits.
- **Storage evaluation:** support multi-iteration PostgreSQL JSONB benchmarks, relation/index overhead (`pg_total_relation_size`), synthetic workload generation, deterministic delta and shared-table reconstruction with SHA-256 verification, and storage strategy recommendations.
- **API security and safeguards:** add `X-API-Key` / Bearer read vs. write authentication, read-only mode (`DATAGIT_READ_ONLY`), and dirty-workspace protection (`DATAGIT_PROTECT_UNCOMMITTED` / `allow_dirty`).
- **Tests:** unit, API security, frontend root/asset serving, CORS preflight, PostgreSQL restoration, storage-benchmark, and end-to-end PostgreSQL integration workflow coverage across branching, checkout, detached HEAD, rollback, merges, conflicts, and transaction rollbacks.

## What's pending

- **Storage backend migration (optional):** adopt delta or shared-table persistence for normal commits if benchmark findings for target production workloads justify moving beyond content-addressed full JSON files.
