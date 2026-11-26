from datetime import datetime, timedelta, timezone
from io import BytesIO, StringIO
import csv
from typing import Any

from dagit.db.connection import get_db_cursor
from dagit.diff.diff_service import compare_snapshots
from dagit.reports.merge_events import (
    fetch_merge_history,
    get_tracking_start_date,
)
from dagit.versioning.history import get_commit
from dagit.versioning.metadata import init_metadata_tables
from dagit.versioning.storage import load_snapshot_from_storage


# In-memory diff cache to prevent re-computing diffs for immutable commit states
_COMMIT_DIFF_CACHE: dict[int, dict[str, Any]] = {}


def get_reachable_commit_ids(branch_name: str) -> set[int]:
    """Retrieve all commit IDs reachable from a given branch HEAD via commit ancestry."""
    with get_db_cursor() as cursor:
        cursor.execute("SELECT head_commit FROM datagit_branches WHERE name = %s;", (branch_name,))
        row = cursor.fetchone()
        if row is None:
            raise ValueError(f"Unknown branch: {branch_name}")
        head_commit = row["head_commit"]
        if head_commit is None:
            return set()

        cursor.execute("""
            WITH RECURSIVE reachable_commits(commit_id) AS (
                SELECT %s::INTEGER
                UNION
                SELECT p.parent_commit_id
                FROM datagit_commit_parents p
                JOIN reachable_commits reachable ON reachable.commit_id = p.commit_id
            )
            SELECT commit_id FROM reachable_commits;
        """, (head_commit,))
        return {r["commit_id"] for r in cursor.fetchall()}


def get_commit_diff(commit: dict[str, Any]) -> dict[str, Any]:
    """
    Compute or fetch cached diff for a commit.
    Merge commits use their first parent.
    The initial root commit (no parent) is diffed against an empty snapshot,
    so all its initial tables and rows are accounted as net creations/inserts.
    """
    cid = commit["commit_id"]
    if cid in _COMMIT_DIFF_CACHE:
        return _COMMIT_DIFF_CACHE[cid]

    parents = commit.get("parents") or []
    if parents:
        first_parent_id = parents[0]
        parent_meta = get_commit(first_parent_id)
        old_snapshot = load_snapshot_from_storage(parent_meta["state_id"])
    else:
        # Initial root commit: diffed against empty snapshot
        old_snapshot = {"tables": {}, "views": {}, "sequences": {}}

    new_snapshot = load_snapshot_from_storage(commit["state_id"])
    diff_res = compare_snapshots(old_snapshot, new_snapshot)
    _COMMIT_DIFF_CACHE[cid] = diff_res
    return diff_res


def _parse_date_bounds(
    date_range: str,
    start_date: str | None,
    end_date: str | None,
) -> tuple[datetime, datetime]:
    """Calculate normalized UTC date boundaries for reporting."""
    now = datetime.now(timezone.utc)
    if date_range == "weekly":
        start_dt = (now - timedelta(days=7)).replace(hour=0, minute=0, second=0, microsecond=0)
        end_dt = now.replace(hour=23, minute=59, second=59, microsecond=999999)
    elif date_range == "monthly":
        start_dt = (now - timedelta(days=30)).replace(hour=0, minute=0, second=0, microsecond=0)
        end_dt = now.replace(hour=23, minute=59, second=59, microsecond=999999)
    elif date_range == "custom":
        if start_date:
            try:
                start_dt = datetime.fromisoformat(start_date.replace("Z", "+00:00"))
                if start_dt.tzinfo is None:
                    start_dt = start_dt.replace(tzinfo=timezone.utc)
            except Exception:
                start_dt = (now - timedelta(days=30)).replace(hour=0, minute=0, second=0, microsecond=0)
        else:
            start_dt = (now - timedelta(days=30)).replace(hour=0, minute=0, second=0, microsecond=0)

        if end_date:
            try:
                end_dt = datetime.fromisoformat(end_date.replace("Z", "+00:00"))
                if end_dt.tzinfo is None:
                    end_dt = end_dt.replace(tzinfo=timezone.utc)
                if end_dt.hour == 0 and end_dt.minute == 0 and end_dt.second == 0:
                    end_dt = end_dt.replace(hour=23, minute=59, second=59, microsecond=999999)
            except Exception:
                end_dt = now.replace(hour=23, minute=59, second=59, microsecond=999999)
        else:
            end_dt = now.replace(hour=23, minute=59, second=59, microsecond=999999)
    else:
        # Default fallback to monthly
        start_dt = (now - timedelta(days=30)).replace(hour=0, minute=0, second=0, microsecond=0)
        end_dt = now.replace(hour=23, minute=59, second=59, microsecond=999999)

    return start_dt, end_dt


def generate_report(
    mode: str = "activity",
    date_range: str = "monthly",
    start_date: str | None = None,
    end_date: str | None = None,
    branch: str | None = None,
    table: str | None = None,
    workspace_id: str = "default",
    tz_label: str = "UTC",
) -> dict[str, Any]:
    """
    Unified query and aggregation service for DataGit reports.
    Provides consistent totals, chart series, detail rows, and coverage notes
    across dashboard, CSV, and PDF representations.
    """
    init_metadata_tables()
    valid_modes = {"activity", "data_schema", "merge_conflict"}
    if mode not in valid_modes:
        mode = "activity"

    start_dt, end_dt = _parse_date_bounds(date_range, start_date, end_date)
    start_iso = start_dt.strftime("%Y-%m-%d %H:%M:%S")
    end_iso = end_dt.strftime("%Y-%m-%d %H:%M:%S")

    # Determine branch ancestry reachability if branch filter is applied
    reachable_commit_ids: set[int] | None = None
    branch_label = "(All reachable commits)"
    if branch and branch.strip():
        branch = branch.strip()
        reachable_commit_ids = get_reachable_commit_ids(branch)
        branch_label = f"Reachable from branch: {branch}"

    # Query commits in range
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
            WHERE c.timestamp >= %s AND c.timestamp <= %s
            ORDER BY c.timestamp ASC, c.commit_id ASC;
        """, (start_dt, end_dt))
        all_commits_in_range = [dict(row) for row in cursor.fetchall()]

    # Filter commits by branch reachability if applicable
    if reachable_commit_ids is not None:
        commits = [c for c in all_commits_in_range if c["commit_id"] in reachable_commit_ids]
    else:
        commits = all_commits_in_range

    # Tracking start date metadata
    tracking_since = get_tracking_start_date()

    # Coverage notes
    coverage_notes = [
        f"Date boundaries: {start_iso} to {end_iso} ({tz_label}).",
        f"Branch filter: '{branch_label}'. Commit filtering uses commit ancestry ('reachable from branch') because shared commits can appear in several branches.",
        "Commit diffs treat changes as net differences between snapshots. Multi-parent merge commits use the first parent. The initial root commit is diffed against an empty snapshot.",
        f"Merge outcome tracking is recorded from {tracking_since}. Earlier merge attempts reflect successful merges from commit history, while unpersisted rejected attempts prior to this date cannot be retroactively reconstructed.",
    ]

    # Pre-aggregate date buckets for charts (safely capped to at most 366 buckets)
    diff_days = (end_dt.date() - start_dt.date()).days
    if diff_days > 365:
        clamped_start = end_dt.date() - timedelta(days=365)
        num_days = 366
        day_keys = [
            (clamped_start + timedelta(days=i)).strftime("%Y-%m-%d")
            for i in range(num_days)
        ]
    else:
        num_days = max(1, diff_days + 1)
        day_keys = [
            (start_dt.date() + timedelta(days=i)).strftime("%Y-%m-%d")
            for i in range(num_days)
        ]

    # Mode 1: Activity Report
    if mode == "activity":
        activity_by_day = {day: {"date": day, "count": 0, "authors": set()} for day in day_keys}
        author_counts: dict[str, int] = {}
        detail_rows = []

        for c in commits:
            day_str = c["timestamp"].strftime("%Y-%m-%d") if c["timestamp"] else day_keys[0]
            if day_str in activity_by_day:
                activity_by_day[day_str]["count"] += 1
                activity_by_day[day_str]["authors"].add(c["author"])

            author_counts[c["author"]] = author_counts.get(c["author"], 0) + 1
            diff_res = get_commit_diff(c)
            summary = diff_res.get("summary", {})
            impacted_tables = sorted(list({
                ch.get("table") for ch in diff_res.get("row_changes", []) if ch.get("table")
            } | {
                ch.get("table") for ch in diff_res.get("schema_changes", []) if ch.get("table")
            }))

            detail_rows.append({
                "commit_id": c["commit_id"],
                "timestamp": c["timestamp"].isoformat() if c["timestamp"] else "",
                "author": c["author"],
                "message": c["message"],
                "parent_commits": c["parents"] or [],
                "is_merge": len(c["parents"] or []) > 1,
                "tables_impacted_count": len(impacted_tables),
                "tables_impacted": impacted_tables,
                "rows_changed": summary.get("rows_inserted", 0) + summary.get("rows_updated", 0) + summary.get("rows_deleted", 0),
            })

        chart_commit_activity = [
            {"date": day, "count": data["count"], "authors_count": len(data["authors"])}
            for day, data in activity_by_day.items()
        ]
        author_series = [
            {"author": author, "commits": count}
            for author, count in sorted(author_counts.items(), key=lambda x: -x[1])
        ]

        summary_totals = {
            "total_commits": len(commits),
            "unique_authors": len(author_counts),
            "merge_commits": sum(1 for c in commits if len(c["parents"] or []) > 1),
            "avg_commits_per_day": round(len(commits) / num_days, 2),
            "earliest_commit": commits[0]["timestamp"].isoformat() if commits else None,
            "latest_commit": commits[-1]["timestamp"].isoformat() if commits else None,
        }

        return {
            "mode": "activity",
            "filters": {
                "date_range": date_range,
                "start_date": start_iso,
                "end_date": end_iso,
                "branch": branch,
                "branch_label": branch_label,
                "table": table,
                "timezone": tz_label,
                "workspace_id": workspace_id,
            },
            "summary": summary_totals,
            "chart_series": {
                "commit_activity": chart_commit_activity,
                "author_distribution": author_series,
            },
            "details": detail_rows,
            "coverage_notes": coverage_notes,
        }

    # Mode 2: Data & Schema Changes
    elif mode == "data_schema":
        table_changes: dict[str, dict[str, int]] = {}
        daily_changes = {day: {"date": day, "inserts": 0, "updates": 0, "deletes": 0, "schema_changes": 0} for day in day_keys}
        detail_rows = []

        total_inserts = 0
        total_updates = 0
        total_deletes = 0
        total_schema_ops = 0

        for c in commits:
            diff_res = get_commit_diff(c)
            row_changes = diff_res.get("row_changes", [])
            schema_changes = diff_res.get("schema_changes", [])
            day_str = c["timestamp"].strftime("%Y-%m-%d") if c["timestamp"] else day_keys[0]

            for r in row_changes:
                tbl = r.get("table", "unknown")
                if table and tbl != table:
                    continue

                op = r.get("operation")
                if tbl not in table_changes:
                    table_changes[tbl] = {"table": tbl, "inserts": 0, "updates": 0, "deletes": 0, "total": 0}

                if op == "INSERT":
                    table_changes[tbl]["inserts"] += 1
                    total_inserts += 1
                    if day_str in daily_changes:
                        daily_changes[day_str]["inserts"] += 1
                elif op == "UPDATE":
                    table_changes[tbl]["updates"] += 1
                    total_updates += 1
                    if day_str in daily_changes:
                        daily_changes[day_str]["updates"] += 1
                elif op == "DELETE":
                    table_changes[tbl]["deletes"] += 1
                    total_deletes += 1
                    if day_str in daily_changes:
                        daily_changes[day_str]["deletes"] += 1

                table_changes[tbl]["total"] += 1
                detail_rows.append({
                    "commit_id": c["commit_id"],
                    "timestamp": c["timestamp"].isoformat() if c["timestamp"] else "",
                    "author": c["author"],
                    "change_category": "DATA",
                    "table": tbl,
                    "operation": op,
                    "details": str(r.get("key") or r.get("changed_columns") or ""),
                })

            for s in schema_changes:
                tbl = s.get("table", "unknown")
                if table and tbl != table:
                    continue

                total_schema_ops += 1
                if day_str in daily_changes:
                    daily_changes[day_str]["schema_changes"] += 1

                detail_rows.append({
                    "commit_id": c["commit_id"],
                    "timestamp": c["timestamp"].isoformat() if c["timestamp"] else "",
                    "author": c["author"],
                    "change_category": "SCHEMA",
                    "table": tbl,
                    "operation": s.get("operation"),
                    "details": f"{s.get('column') or ''} {s.get('after') or ''}".strip(),
                })

        stacked_table_series = sorted(
            table_changes.values(),
            key=lambda x: -x["total"]
        )

        summary_totals = {
            "rows_inserted": total_inserts,
            "rows_updated": total_updates,
            "rows_deleted": total_deletes,
            "total_row_changes": total_inserts + total_updates + total_deletes,
            "schema_changes_count": total_schema_ops,
            "tables_impacted_count": len(table_changes),
        }

        return {
            "mode": "data_schema",
            "filters": {
                "date_range": date_range,
                "start_date": start_iso,
                "end_date": end_iso,
                "branch": branch,
                "branch_label": branch_label,
                "table": table,
                "timezone": tz_label,
                "workspace_id": workspace_id,
            },
            "summary": summary_totals,
            "chart_series": {
                "table_row_changes": stacked_table_series,
                "daily_changes": list(daily_changes.values()),
            },
            "details": detail_rows,
            "coverage_notes": coverage_notes,
        }

    # Mode 3: Merge & Conflict Report
    else:
        merge_events = fetch_merge_history(
            workspace_id=workspace_id,
            start_dt=start_dt,
            end_dt=end_dt,
            branch=branch,
            reachable_commit_ids=reachable_commit_ids,
        )

        success_count = 0
        conflict_count = 0
        rejected_count = 0
        daily_merges = {day: {"date": day, "success": 0, "conflict": 0, "rejected": 0} for day in day_keys}
        detail_rows = []

        for ev in merge_events:
            outcome = ev.get("outcome", "rejected").lower()
            att_at = ev.get("attempted_at")
            day_str = (
                att_at.strftime("%Y-%m-%d")
                if isinstance(att_at, datetime)
                else str(att_at)[:10] if att_at else day_keys[0]
            )

            if outcome == "success":
                success_count += 1
                if day_str in daily_merges:
                    daily_merges[day_str]["success"] += 1
            elif outcome == "conflict":
                conflict_count += 1
                if day_str in daily_merges:
                    daily_merges[day_str]["conflict"] += 1
            else:
                rejected_count += 1
                if day_str in daily_merges:
                    daily_merges[day_str]["rejected"] += 1

            detail_rows.append({
                "id": ev.get("id"),
                "timestamp": att_at.isoformat() if isinstance(att_at, datetime) else str(att_at),
                "actor": ev.get("actor"),
                "source": ev.get("source_branch") or (f"Commit #{ev['source_commit_id']}" if ev.get("source_commit_id") else "Unknown"),
                "target": ev.get("target_branch") or (f"Commit #{ev['target_commit_id']}" if ev.get("target_commit_id") else "Unknown"),
                "outcome": outcome,
                "merge_commit_id": ev.get("merge_commit_id"),
                "conflict_summary": (
                    f"{len(ev['conflict_details'])} conflict(s)"
                    if ev.get("conflict_details")
                    else ev.get("error_message") or ("Merged successfully" if outcome == "success" else "Rejected")
                ),
                "is_historical_reconstruction": ev.get("is_historical_reconstruction", False),
            })

        total_attempts = len(merge_events)
        success_rate = round((success_count / total_attempts * 100), 1) if total_attempts > 0 else 0.0
        conflict_rate = round((conflict_count / total_attempts * 100), 1) if total_attempts > 0 else 0.0

        summary_totals = {
            "total_attempts": total_attempts,
            "success_count": success_count,
            "conflict_count": conflict_count,
            "rejected_count": rejected_count,
            "success_rate_percent": success_rate,
            "conflict_rate_percent": conflict_rate,
            "tracking_started_at": tracking_since,
        }

        outcome_breakdown = [
            {"status": "Success", "count": success_count, "color": "#10b981"},
            {"status": "Conflict", "count": conflict_count, "color": "#ef4444"},
            {"status": "Rejected", "count": rejected_count, "color": "#f59e0b"},
        ]

        return {
            "mode": "merge_conflict",
            "filters": {
                "date_range": date_range,
                "start_date": start_iso,
                "end_date": end_iso,
                "branch": branch,
                "branch_label": branch_label,
                "table": table,
                "timezone": tz_label,
                "workspace_id": workspace_id,
            },
            "summary": summary_totals,
            "chart_series": {
                "outcome_breakdown": outcome_breakdown,
                "daily_merges": list(daily_merges.values()),
            },
            "details": detail_rows,
            "coverage_notes": coverage_notes,
        }


def generate_csv_report(report_data: dict[str, Any]) -> tuple[str, str]:
    """Format report into CSV representation that reconciles with the dashboard."""
    output = StringIO()
    writer = csv.writer(output)

    mode = report_data["mode"]
    filters = report_data["filters"]
    summary = report_data["summary"]
    details = report_data["details"]

    # Header metadata
    writer.writerow(["# DataGit Dynamic Report Export"])
    writer.writerow(["# Report Mode", mode.upper()])
    writer.writerow(["# Date Range", f"{filters['start_date']} to {filters['end_date']} ({filters['timezone']})"])
    writer.writerow(["# Branch Scope", filters["branch_label"]])
    if filters.get("table"):
        writer.writerow(["# Table Filter", filters["table"]])
    writer.writerow([])

    # Summary Totals
    writer.writerow(["--- SUMMARY TOTALS ---"])
    for k, v in summary.items():
        writer.writerow([k, v])
    writer.writerow([])

    # Details Table
    writer.writerow(["--- DETAIL ROWS ---"])
    if details:
        headers = list(details[0].keys())
        writer.writerow(headers)
        for row in details:
            writer.writerow([row.get(h, "") for h in headers])
    else:
        writer.writerow(["No matching records found for active filters."])

    writer.writerow([])
    writer.writerow(["--- COVERAGE NOTES ---"])
    for note in report_data.get("coverage_notes", []):
        writer.writerow(["#", note])

    filename = f"datagit_report_{mode}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.csv"
    return output.getvalue(), filename


def generate_pdf_report(report_data: dict[str, Any]) -> tuple[bytes, str]:
    """Generate high-fidelity PDF report with active filters, summary totals, charts, and details."""
    from reportlab.lib.pagesizes import letter
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.platypus import (
        SimpleDocTemplate,
        Paragraph,
        Spacer,
        Table,
        TableStyle,
        KeepTogether,
        HRFlowable,
    )
    from reportlab.graphics.shapes import Drawing, Rect, String, Line, Group

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        leftMargin=36,
        rightMargin=36,
        topMargin=36,
        bottomMargin=36,
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "DocTitle",
        parent=styles["Heading1"],
        fontSize=20,
        leading=24,
        textColor=colors.HexColor("#111827"),
    )
    subtitle_style = ParagraphStyle(
        "DocSubTitle",
        parent=styles["Normal"],
        fontSize=10,
        leading=14,
        textColor=colors.HexColor("#4b5563"),
    )
    heading2_style = ParagraphStyle(
        "DocH2",
        parent=styles["Heading2"],
        fontSize=13,
        leading=17,
        textColor=colors.HexColor("#111827"),
        spaceBefore=12,
        spaceAfter=6,
    )
    cell_style = ParagraphStyle(
        "DocCell",
        parent=styles["Normal"],
        fontSize=8,
        leading=10,
        textColor=colors.HexColor("#1f2937"),
    )
    note_style = ParagraphStyle(
        "DocNote",
        parent=styles["Normal"],
        fontSize=7.5,
        leading=10,
        textColor=colors.HexColor("#4b5563"),
    )

    elements = []

    # Title Banner
    mode = report_data["mode"]
    mode_titles = {
        "activity": "Commit Activity & Lineage Report",
        "data_schema": "Data & Schema Changes Report",
        "merge_conflict": "Merge Outcomes & Conflict Analysis Report",
    }
    elements.append(Paragraph(f"DataGit — {mode_titles.get(mode, 'Dynamic Report')}", title_style))
    elements.append(Paragraph("Enterprise PostgreSQL Version Control Intelligence & Analytics", subtitle_style))
    elements.append(Spacer(1, 10))
    elements.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor("#e5e7eb"), spaceAfter=12))

    # Scope & Filters Table
    filters = report_data["filters"]
    filter_data = [
        [
            Paragraph("<b>Report Mode:</b> " + mode.upper(), cell_style),
            Paragraph("<b>Date Range:</b> " + filters["date_range"], cell_style),
            Paragraph("<b>Timezone:</b> " + filters["timezone"], cell_style),
        ],
        [
            Paragraph("<b>Window:</b> " + f"{filters['start_date']} to {filters['end_date']}", cell_style),
            Paragraph("<b>Branch Scope:</b> " + filters["branch_label"], cell_style),
            Paragraph("<b>Table Filter:</b> " + (filters.get("table") or "(All tables)"), cell_style),
        ],
    ]
    filter_table = Table(filter_data, colWidths=[180, 200, 160])
    filter_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f8fafc")),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
    ]))
    elements.append(filter_table)
    elements.append(Spacer(1, 12))

    # Summary KPI Cards Table
    elements.append(Paragraph("Executive Summary Totals", heading2_style))
    summary = report_data["summary"]
    summary_items = list(summary.items())
    kpi_rows = []
    chunk_size = 3
    for i in range(0, len(summary_items), chunk_size):
        chunk = summary_items[i:i + chunk_size]
        row_cells = []
        for k, v in chunk:
            label = k.replace("_", " ").title()
            val_str = str(v)
            content = f"<b>{label}</b><br/><font size='13' color='#1e40af'><b>{val_str}</b></font>"
            row_cells.append(Paragraph(content, cell_style))
        while len(row_cells) < chunk_size:
            row_cells.append(Paragraph("", cell_style))
        kpi_rows.append(row_cells)

    kpi_table = Table(kpi_rows, colWidths=[180, 180, 180])
    kpi_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f0fdf4")),
        ("BOX", (0, 0), (-1, -1), 1, colors.HexColor("#86efac")),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#bbf7d0")),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    elements.append(kpi_table)
    elements.append(Spacer(1, 12))

    # Visual Charts
    charts = report_data.get("chart_series", {})
    if mode == "activity" and "commit_activity" in charts:
        elements.append(Paragraph("Commit Activity Trend (Commits over Time)", heading2_style))
        series = charts["commit_activity"]
        d = Drawing(540, 110)
        d.add(Rect(0, 0, 540, 110, fillColor=colors.HexColor("#f8fafc"), strokeColor=colors.HexColor("#e2e8f0"), strokeWidth=1))

        counts = [item["count"] for item in series]
        max_c = max(counts) if counts and max(counts) > 0 else 1
        n = len(series)
        x_step = 500 / max(1, n - 1) if n > 1 else 250

        # Axes & labels
        d.add(Line(30, 20, 530, 20, strokeColor=colors.HexColor("#94a3b8"), strokeWidth=1))
        d.add(Line(30, 20, 30, 100, strokeColor=colors.HexColor("#94a3b8"), strokeWidth=1))
        d.add(String(8, 18, "0", fontSize=7, fillColor=colors.HexColor("#64748b")))
        d.add(String(8, 95, str(max_c), fontSize=7, fillColor=colors.HexColor("#64748b")))

        points = []
        for idx, item in enumerate(series):
            cx = 30 + (idx * x_step if n > 1 else 250)
            cy = 20 + ((item["count"] / max_c) * 75)
            points.append((cx, cy))

        for idx in range(len(points) - 1):
            p1 = points[idx]
            p2 = points[idx + 1]
            d.add(Line(p1[0], p1[1], p2[0], p2[1], strokeColor=colors.HexColor("#2563eb"), strokeWidth=2))

        for idx, (px, py) in enumerate(points):
            d.add(Rect(px - 3, py - 3, 6, 6, fillColor=colors.HexColor("#1d4ed8"), strokeColor=colors.white, strokeWidth=1))
            if n <= 10 or idx % max(1, n // 6) == 0 or idx == n - 1:
                date_label = series[idx]["date"][-5:]
                d.add(String(px - 10, 8, date_label, fontSize=6.5, fillColor=colors.HexColor("#64748b")))

        elements.append(d)
        elements.append(Spacer(1, 10))

    elif mode == "data_schema" and "table_row_changes" in charts:
        elements.append(Paragraph("Data Changes by Table (Stacked Inserts, Updates, Deletes)", heading2_style))
        tbl_series = charts["table_row_changes"][:8]  # top 8
        d = Drawing(540, 120)
        d.add(Rect(0, 0, 540, 120, fillColor=colors.HexColor("#f8fafc"), strokeColor=colors.HexColor("#e2e8f0"), strokeWidth=1))

        # Legend
        d.add(Rect(140, 105, 10, 8, fillColor=colors.HexColor("#10b981"), strokeColor=None))
        d.add(String(155, 106, "Inserts", fontSize=7.5, fillColor=colors.HexColor("#334155")))
        d.add(Rect(220, 105, 10, 8, fillColor=colors.HexColor("#f59e0b"), strokeColor=None))
        d.add(String(235, 106, "Updates", fontSize=7.5, fillColor=colors.HexColor("#334155")))
        d.add(Rect(300, 105, 10, 8, fillColor=colors.HexColor("#ef4444"), strokeColor=None))
        d.add(String(315, 106, "Deletes", fontSize=7.5, fillColor=colors.HexColor("#334155")))

        max_tot = max([item["total"] for item in tbl_series], default=1) or 1
        y_pos = 85
        bar_height = 9
        for item in tbl_series:
            d.add(String(10, y_pos, item["table"][:18], fontSize=7.5, fillColor=colors.HexColor("#0f172a")))
            tot_w = (item["total"] / max_tot) * 360
            ins_w = (item["inserts"] / item["total"]) * tot_w if item["total"] else 0
            upd_w = (item["updates"] / item["total"]) * tot_w if item["total"] else 0
            del_w = (item["deletes"] / item["total"]) * tot_w if item["total"] else 0

            cur_x = 120
            if ins_w > 0:
                d.add(Rect(cur_x, y_pos - 1, ins_w, bar_height, fillColor=colors.HexColor("#10b981"), strokeColor=None))
                cur_x += ins_w
            if upd_w > 0:
                d.add(Rect(cur_x, y_pos - 1, upd_w, bar_height, fillColor=colors.HexColor("#f59e0b"), strokeColor=None))
                cur_x += upd_w
            if del_w > 0:
                d.add(Rect(cur_x, y_pos - 1, del_w, bar_height, fillColor=colors.HexColor("#ef4444"), strokeColor=None))
                cur_x += del_w

            d.add(String(cur_x + 5, y_pos, str(item["total"]), fontSize=7, fillColor=colors.HexColor("#64748b")))
            y_pos -= 12

        elements.append(d)
        elements.append(Spacer(1, 10))

    elif mode == "merge_conflict" and "outcome_breakdown" in charts:
        elements.append(Paragraph("Merge Outcomes Breakdown", heading2_style))
        breakdown = charts["outcome_breakdown"]
        d = Drawing(540, 70)
        d.add(Rect(0, 0, 540, 70, fillColor=colors.HexColor("#f8fafc"), strokeColor=colors.HexColor("#e2e8f0"), strokeWidth=1))

        tot_m = sum(item["count"] for item in breakdown) or 1
        cur_x = 20
        for item in breakdown:
            w = (item["count"] / tot_m) * 500
            pct = round((item["count"] / tot_m) * 100, 1) if tot_m > 0 else 0
            color = colors.HexColor(item.get("color", "#64748b"))
            if w > 0:
                d.add(Rect(cur_x, 30, w, 22, fillColor=color, strokeColor=colors.white, strokeWidth=1))
                d.add(String(cur_x + 4, 37, f"{item['status']}: {item['count']} ({pct}%)", fontSize=7.5, fillColor=colors.white))
                cur_x += w

        d.add(String(20, 12, f"Total Attempted Merges: {sum(item['count'] for item in breakdown)}", fontSize=8, fillColor=colors.HexColor("#334155")))
        elements.append(d)
        elements.append(Spacer(1, 10))

    # Coverage Notes Box
    elements.append(Paragraph("Governance & Coverage Methodology Notes", heading2_style))
    notes = report_data.get("coverage_notes", [])
    note_rows = [[Paragraph(f"• {n}", note_style)] for n in notes]
    note_table = Table(note_rows, colWidths=[540])
    note_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#fffbeb")),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#fcd34d")),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    elements.append(note_table)
    elements.append(Spacer(1, 12))

    # Detail Table
    elements.append(Paragraph("Detailed Records", heading2_style))
    details = report_data.get("details", [])
    if details:
        if mode == "activity":
            table_headers = ["Commit #", "Timestamp", "Author", "Merge?", "Tables", "Rows Changed", "Message"]
            col_widths = [45, 80, 75, 40, 45, 60, 195]
            rows = [[Paragraph(f"<b>{h}</b>", cell_style) for h in table_headers]]
            for row in details[:40]:  # Up to 40 detail rows on PDF
                msg = row.get("message", "")[:45] + ("..." if len(row.get("message", "")) > 45 else "")
                rows.append([
                    Paragraph(str(row.get("commit_id")), cell_style),
                    Paragraph(str(row.get("timestamp"))[:19], cell_style),
                    Paragraph(str(row.get("author")), cell_style),
                    Paragraph("Yes" if row.get("is_merge") else "No", cell_style),
                    Paragraph(str(row.get("tables_impacted_count")), cell_style),
                    Paragraph(str(row.get("rows_changed")), cell_style),
                    Paragraph(msg, cell_style),
                ])
        elif mode == "data_schema":
            table_headers = ["Commit #", "Timestamp", "Author", "Type", "Table", "Operation", "Details"]
            col_widths = [45, 80, 70, 45, 75, 65, 160]
            rows = [[Paragraph(f"<b>{h}</b>", cell_style) for h in table_headers]]
            for row in details[:40]:
                det = row.get("details", "")[:40] + ("..." if len(row.get("details", "")) > 40 else "")
                rows.append([
                    Paragraph(str(row.get("commit_id")), cell_style),
                    Paragraph(str(row.get("timestamp"))[:19], cell_style),
                    Paragraph(str(row.get("author")), cell_style),
                    Paragraph(str(row.get("change_category")), cell_style),
                    Paragraph(str(row.get("table")), cell_style),
                    Paragraph(str(row.get("operation")), cell_style),
                    Paragraph(det, cell_style),
                ])
        else:
            table_headers = ["ID", "Timestamp", "Actor", "Source", "Target", "Outcome", "Summary"]
            col_widths = [40, 80, 70, 70, 70, 55, 155]
            rows = [[Paragraph(f"<b>{h}</b>", cell_style) for h in table_headers]]
            for row in details[:40]:
                sm = row.get("conflict_summary", "")[:40] + ("..." if len(row.get("conflict_summary", "")) > 40 else "")
                rows.append([
                    Paragraph(str(row.get("id")), cell_style),
                    Paragraph(str(row.get("timestamp"))[:19], cell_style),
                    Paragraph(str(row.get("actor")), cell_style),
                    Paragraph(str(row.get("source")), cell_style),
                    Paragraph(str(row.get("target")), cell_style),
                    Paragraph(str(row.get("outcome")).upper(), cell_style),
                    Paragraph(sm, cell_style),
                ])

        detail_table = Table(rows, colWidths=col_widths, repeatRows=1)
        detail_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f1f5f9")),
            ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
            ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#e2e8f0")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]))
        elements.append(detail_table)
    else:
        elements.append(Paragraph("<i>No detail records found for the selected filter combination.</i>", subtitle_style))

    doc.build(elements)
    filename = f"datagit_report_{mode}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.pdf"
    return buffer.getvalue(), filename
