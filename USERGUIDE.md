# DataGit User Guide & Feature Walkthrough

Welcome to **DataGit** — the version control system for PostgreSQL databases. DataGit brings Git-like versioning, content-addressed snapshots, branching, 3-way merging, schema and row-level diffing, transactional time-travel rollback, and multi-strategy storage benchmarks to relational databases.

---

## Table of Contents

1. [Quick Start (3-Minute Setup)](#quick-start-3-minute-setup)
2. [Interface Overview (Design System)](#interface-overview-design-system)
3. [Walkthrough: Exploring DataGit Features](#walkthrough-exploring-datagit-features)
   - [1. Timeline & Commit Lineage](#1-timeline--commit-lineage)
   - [2. Visual Database Schema Explorer](#2-visual-database-schema-explorer)
   - [3. Snapshot & Commit Creator](#3-snapshot--commit-creator)
   - [4. Branch Management & Switching](#4-branch-management--switching)
   - [5. Snapshot & Schema Diff Inspector](#5-snapshot--schema-diff-inspector)
   - [6. 3-Way Merging & Conflict Resolution](#6-3-way-merging--conflict-resolution)
   - [7. Storage & Performance Benchmark](#7-storage--performance-benchmark)
   - [8. Time-Travel & Rollback Station](#8-time-travel--rollback-station)
   - [9. Settings, API Keys & Operational Safeguards](#9-settings-api-keys--operational-safeguards)
4. [Backend API Reference](#backend-api-reference)
5. [Troubleshooting & FAQ](#troubleshooting--faq)

---

## Quick Start (3-Minute Setup)

### 1. Prerequisites
- **Python 3.10+** (with virtualenv)
- **PostgreSQL 14+** running locally (e.g. port `5432` or via socket `/tmp`)
- **Node.js 18+** & npm

### 2. Configure Database
Create a database named `datagit_db` in PostgreSQL:
```sql
CREATE DATABASE datagit_db;
```

Configure `backend/.env`:
```dotenv
DB_HOST=/tmp
DB_PORT=5432
DB_NAME=datagit_db
DB_USER=postgres
DB_PASSWORD=password
```
*(On macOS, setting `DB_HOST=/tmp` connects directly via local Unix domain socket).*

### 3. Seed Demo Database
Populate the database with a rich e-commerce schema, multiple branches, 8 commits, and a 3-way merge:
```bash
npm run seed
```
This populates:
- **Tables**: `categories`, `customers`, `products`, `orders`, `order_items`, `user_sessions`, `telemetry_events`, `coupon_discounts`
- **Data Types**: `SERIAL`, `VARCHAR`, `TEXT`, `NUMERIC`, `JSONB`, `DATE`, `TIMESTAMPTZ`, `TEXT[]`, `CHECK` constraints, foreign keys
- **Extended Objects**: Sequences (`order_tracking_seq`), indexes, and summary views (`customer_spending_summary`)
- **Branches**: `main` (active, HEAD #7), `feature/discounts` (HEAD #4), `feature/analytics` (HEAD #5), `hotfix/pricing-adjustments` (HEAD #8)

### 4. Launch the Application
Start the backend and frontend development servers:

```bash
# Terminal 1 - Start FastAPI Backend Server (Port 8000)
npm run backend

# Terminal 2 - Start Vite Dev Server with Hot-Reload (Port 5173)
npm run dev
```

Open your browser at **`http://localhost:5173`** (or **`http://127.0.0.1:8000/`** for the compiled production build).

---

## Interface Overview (Design System)

DataGit features an ultra-modern UI inspired by RonDesignLab / Sugar CRM:
- **Slim Left Icon Rail**: Fast navigation between features with a vertical capsule theme toggle at the bottom.
- **Top Navigation Bar**: Horizontal pill-segmented navigation (active item shown with a solid pill), live connection indicator (`Online`), active branch badge (`🌿 main`), current HEAD badge (`HEAD #7`), and quick action buttons.
- **Large Floating Canvas Card**: 28px rounded corners, soft drop shadows, and clean card surfaces.
- **Light & Dark Themes**:
  - **Light Mode**: Crisp white panels (`#ffffff`) over cloud grey canvas (`#edf0f5`).
  - **Neutral Grey-Black Dark Mode**: Deep neutral zinc/black palette (`#09090b` canvas, `#161619` panels, `#1d1d21` cards, `#2e2e34` borders) with **strictly zero blue or navy tint**.

---

## Walkthrough: Exploring DataGit Features

### 1. Timeline & Commit Lineage
**Tab: `Timeline`**

The Timeline view displays the chronological DAG (Directed Acyclic Graph) of commits reachable from the current branch.
- **Commit Cards**: Each card displays the commit sequence number (e.g. `#7`), commit message, author name, timestamp, and active badges (`HEAD`, `🌿 branch`, `3-Way Merge`).
- **Parent Links**: Shows single-parent links (e.g. `🔗 Parent: #6`) or two-parent merge links (e.g. `🔗 Parents: #6, #4`).
- **SHA-256 Hash**: Click the hash pill (e.g. `#a82b01fc...`) to copy the snapshot's 256-bit cryptographic digest.
- **Action Buttons**:
  - `Compare with HEAD`: Instantly opens the Diff Inspector comparing that commit against HEAD.
  - `Diff vs Parent`: Diffs the commit directly against its immediate predecessor.
  - `Checkout (Detached)`: Restores PostgreSQL tables to that exact commit in detached HEAD mode.
  - `Branch from Here`: Navigates to Branches tab with that commit pre-selected.

---

### 2. Visual Database Schema Explorer
**Tab: `Schema`**

The Schema Explorer allows you to inspect the relational schema of any database version.
1. **Context Switcher**:
   - `Live Database`: Shows the real-time structure of your current PostgreSQL working workspace.
   - `Branch HEAD`: Shows the schema at the tip of any branch (`main`, `feature/discounts`, `feature/analytics`, `hotfix/pricing-adjustments`).
   - `Historic Commit`: Select any commit snapshot (#1 to #8) to time-travel inspect historical schemas.
2. **Schema Metrics Grid**:
   - Displays total table count, column count, foreign key count, total row count, and views/sequences.
3. **Table Cards Grid**:
   - Each card represents a table with its row count, column definitions, data types, nullable status, and `🔑 PK` badges.
   - Shows foreign key references at the bottom of the card (e.g. `category_id → categories(id)`).
   - Lists non-primary indexes (e.g. `idx_products_category_price`).
4. **Entity Relationships View**:
   - Switch to the **Entity Relationships** subtab to see visual relational arrows connecting tables via foreign keys.
5. **Views & Sequences View**:
   - Inspect SQL definitions of database views (`customer_spending_summary`) and sequence parameters (`order_tracking_seq`).

---

### 3. Snapshot & Commit Creator
**Tab: `Snapshot`**

Create a new version-controlled commit from the current state of PostgreSQL:
1. Make any change in PostgreSQL (via `psql` or your database GUI), such as inserting a record or creating a table.
2. In the **Snapshot** tab:
   - Enter a **Commit Message** (e.g. *"Add VIP loyalty tier to customers"*).
   - Specify your **Author Name** (defaults to your configured author profile).
   - Optionally choose a custom parent commit.
3. Click **Record Snapshot & Create Commit**.
4. DataGit atomically captures all `public` tables, constraints, rows, indexes, triggers, privileges, views, and sequences into a content-addressed snapshot file.

---

### 4. Branch Management & Switching
**Tab: `Branches`**

Manage multiple parallel lines of database development:
1. **View Branches**: View all branches with their current HEAD commit IDs, created timestamps, and the active working branch indicator.
2. **Switch Branches**: Click **Switch to Branch** on any branch (e.g. `feature/discounts`). DataGit transactionally updates the PostgreSQL database to match that branch's HEAD commit.
3. **Create Branch**:
   - Enter a new branch name (e.g. `feature/loyalty-rewards`).
   - Select the starting commit (defaults to current HEAD).
   - Click **Create Branch**.

---

### 5. Snapshot & Schema Diff Inspector
**Tab: `Diff`**

Compare schema modifications and row content deltas between any two commits:
1. **Quick Presets**: Click any preset pill at the top for instant comparisons:
   - `🔀 Pre-Merge vs 3-Way Merge (#6 → #7)`: See the additions introduced by the 3-way merge.
   - `🚀 Initial Schema vs Full DB (#1 → #7)`: See the full evolution from empty tables to seeded database.
   - `📦 Catalog vs Orders & Views (#2 → #3)`: Inspect order creation, indexes, and summary view.
   - `🌿 Main vs Feature/Discounts (#3 → #4)`: Inspect coupon discount tables and customer updates.
   - `🔥 Main vs Hotfix Pricing (#7 → #8)`: Inspect altered columns (`discount_eligible`, `phone_number`) and price changes.
2. **Summary Pills Bar**:
   - Live metrics indicating tables added, tables dropped, tables altered, rows inserted, rows deleted, and rows updated.
3. **Diff Views**:
   - **Schema & Metadata Diff**: Displays added tables (+CREATED), dropped tables (-DROPPED), and column additions/alterations.
   - **Row-Level Content Diff**: Grouped by table, showing green `+` inserted rows, red `-` deleted rows, and amber `~` updated rows with exact before & after values for modified columns.
   - **Raw JSON**: Full machine-readable diff payload.

---

### 6. 3-Way Merging & Conflict Resolution
**Tab: `Merge`**

Combine independent branches with automated common-ancestor resolution:
1. **Execute a Clean Merge**:
   - Select the source branch or commit to merge into your active branch.
   - Enter an author and optional merge message.
   - Click **Execute 3-Way Merge**.
   - If changes are disjoint, DataGit combines table, column, constraint, and row changes and creates a **two-parent commit**.
2. **Conflict Detection & Safeguards**:
   - If two branches modify the same row with conflicting column values or violate foreign keys, DataGit refuses the merge with **HTTP 409 Conflict**.
   - The UI presents a detailed conflict breakdown highlighting the colliding table, row keys, and conflicting columns.

---

### 7. Storage & Performance Benchmark
**Tab: `Benchmark`**

Evaluate and compare database version storage strategies in PostgreSQL:
1. **Workload Modes**:
   - **Synthetic Workload**: Generate configurable multi-table workloads (e.g. 3 tables, 50 rows, 8 snapshots, 15% change ratio).
   - **Existing Commits**: Benchmark actual commits from your repository history (e.g. `1, 2, 3, 4, 6, 7`).
2. **Iterations**: Run 1 to 10 iterations to average out timing noise.
3. **Evaluated Strategies**:
   - **Full JSONB Snapshot**: Full document per commit. Instant reconstruction, higher disk storage.
   - **Delta Persistence**: Base snapshot + forward diff chains. Minimal byte payload, CPU reconstruction cost.
   - **Shared Table Storage**: Table-level deduplication across snapshots.
4. **Benchmark Results**:
   - **Recommendation Card**: Automatically suggests the optimal storage strategy based on space savings and TOAST overhead.
   - **Relation Overhead**: Measures true on-disk footprint using `pg_total_relation_size` (heap + TOAST + index pages).
   - **Performance Table**: Compares write time, read time, and reconstruction latency in milliseconds.
   - **100% SHA-256 Integrity Verification**: Confirms that reconstructed snapshots match the original hashes.

---

### 8. Time-Travel & Rollback Station
**Tab: `Rollback`**

Revert the PostgreSQL database safely to any point in history:
1. Select **Previous Commit (HEAD~1)** or specify a **Target Historic Commit**.
2. Check **Allow Dirty Workspace** if you wish to override uncommitted change safeguards.
3. Click **Execute Safe Rollback**.
4. DataGit transactionally replaces all public database objects with the target snapshot and records a new rollback commit for full auditability.

---

### 9. Settings, API Keys & Operational Safeguards
**Settings Modal (Gear Icon or Avatar)**

Configure authentication and operational protection:
- **Default Author Profile**: Sets the author name recorded with commits, merges, and rollbacks.
- **Admin Write API Key**: Sent in requests as `X-API-Key` or `Authorization: Bearer <key>` when write protection is active.
- **Read-Only API Key**: Grants read access while preventing mutations.
- **Default Allow Dirty**: When unchecked, protects against accidentally overwriting uncommitted working data.

---

## Backend API Reference

All versioning features are accessible via HTTP REST endpoints at `/api`:

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/schema` | Inspect live or historical database schema (`?commit_id=X` or `?branch=Y`) |
| `GET` | `/api/history` | List reachable commits (`?branch=X&limit=N`) |
| `GET` | `/api/commits/{commit_id}` | Retrieve specific commit metadata and parent links |
| `POST` | `/api/commits` | Create a snapshot commit (`{ message, author, parent_commit_id }`) |
| `GET` | `/api/branches` | List all branches and active HEADs |
| `POST` | `/api/branches` | Create a new branch (`{ name, from_commit_id }`) |
| `POST` | `/api/checkout/commits/{commit_id}` | Checkout commit in detached HEAD mode (`?allow_dirty=true`) |
| `POST` | `/api/checkout/branches/{name}` | Switch to branch and restore database (`?allow_dirty=true`) |
| `GET` | `/api/diff/{from_id}/{to_id}` | Compute schema and row changes between two commits |
| `POST` | `/api/merge` | Execute 3-way merge (`{ source_branch, author, message }`) |
| `POST` | `/api/storage/benchmark` | Run storage benchmark on commits or synthetic workload |
| `POST` | `/api/rollback` | Rollback to target commit (`{ commit_id, author, allow_dirty }`) |

---

## Troubleshooting & FAQ

#### Q: The Diff tab shows 0 tables changed and 0 rows changed.
- **Cause**: Both From and To were set to the same commit ID, or the inputs were empty.
- **Fix**: Use the **Quick Presets** at the top of the Diff tab (e.g. `#6 → #7` or `#1 → #7`), or select two different commit IDs from the dropdowns.

#### Q: How do I switch between Light and Dark mode?
- Click the vertical pill switcher at the bottom-left of the icon rail. The top icon is **Sun (Light mode)**, and the bottom icon is **Moon (Dark mode)**.

#### Q: Why is my dark mode pure grey/black instead of navy blue?
- By design, DataGit uses a neutral grey-black zinc palette (`#09090b` / `#161619` / `#1d1d21`) with zero blue or slate cast for improved visual contrast and eye comfort during long database sessions.

#### Q: How do I re-seed or reset the demo database?
- Run `npm run seed` or `python backend/populate_demo_db.py` from the project root. This recreates the sample tables, branches, and commits cleanly.
