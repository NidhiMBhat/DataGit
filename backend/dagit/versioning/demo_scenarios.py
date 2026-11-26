"""
Live Demo Scenarios for DataGit E-commerce Database
Provides deterministic, high-impact database modifications for live presentations.
"""

from dagit.db.connection import get_db_cursor
from dagit.versioning.checkout import checkout_commit
from dagit.versioning.metadata import init_metadata_tables
from dagit.versioning.restore import restore_snapshot_in_cursor
from dagit.versioning.storage import load_snapshot_from_storage


DEMO_SCENARIOS = {
    "flash_sale": {
        "title": "Flash Sale: 25% Discount on Electronics",
        "description": "Reduces prices by 25% across all electronics products and appends 'flash-sale-25' tag.",
        "suggested_commit_message": "Promo: Apply 25% Flash Sale discount on electronics catalog",
        "sql": """
            UPDATE products
            SET price = ROUND(price * 0.75, 2),
                tags = array_append(tags, 'flash-sale-25')
            WHERE category_id = 1;
        """,
    },
    "new_order": {
        "title": "Customer Checkout: $948.99 Order & Loyalty Upgrade",
        "description": "Places high-value order ORD-99001, deducts 2 units of stock, and promotes Alice Chen to Platinum tier.",
        "suggested_commit_message": "Order Fulfillment: Place ORD-99001 ($948.99), deduct stock, upgrade loyalty",
        "sql": """
            -- Insert high value order
            INSERT INTO orders (order_number, customer_id, total_amount, status)
            VALUES ('ORD-99001', 1, 948.99, 'completed')
            ON CONFLICT (order_number) DO UPDATE SET total_amount = orders.total_amount + 50.00;

            -- Deduct stock
            UPDATE products SET stock_quantity = GREATEST(stock_quantity - 2, 0) WHERE sku = 'TECH-001';

            -- Upgrade customer loyalty
            UPDATE customers
            SET loyalty_points = loyalty_points + 950,
                loyalty_tier = 'platinum'
            WHERE id = 1;
        """,
    },
    "product_launch": {
        "title": "Product Launch & Schema Evolution: Smart Wearables",
        "description": "Adds 'warranty_months' column to products, creates 'Smart Wearables' category, and launches AcousticPro Vision AR Glasses.",
        "suggested_commit_message": "Feature Launch: Add Smart Wearables category, AR Glasses product, and warranty column",
        "sql": """
            -- Add warranty column if not exists
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns 
                    WHERE table_name = 'products' AND column_name = 'warranty_months'
                ) THEN
                    ALTER TABLE products ADD COLUMN warranty_months INT DEFAULT 12;
                END IF;
            END $$;

            -- Insert new category
            INSERT INTO categories (name, slug, description)
            VALUES ('Smart Wearables', 'smart-wearables', 'Wearables, smartwatches, and spatial AR gear')
            ON CONFLICT (name) DO NOTHING;

            -- Insert new product
            INSERT INTO products (sku, name, category_id, price, cost_price, stock_quantity, tags, attributes, warranty_months)
            VALUES (
                'WEAR-001',
                'AcousticPro Vision AR Glasses',
                (SELECT id FROM categories WHERE slug = 'smart-wearables' LIMIT 1),
                799.00,
                410.00,
                50,
                ARRAY['ar', 'smart-glasses', 'oled'],
                '{"display": "Dual Micro-OLED", "battery_hours": 8}',
                24
            )
            ON CONFLICT (sku) DO UPDATE SET price = 749.00;
        """,
    },
}


def execute_demo_scenario(scenario_key: str, custom_sql: str | None = None) -> dict:
    """Execute a predefined scenario or custom SQL against the active database."""
    init_metadata_tables()

    if scenario_key == "reset_clean":
        with get_db_cursor(commit=True) as cursor:
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
            if current_head is None:
                raise ValueError("No active HEAD commit found to restore to.")

            cursor.execute("SELECT state_id FROM datagit_commits WHERE commit_id = %s;", (current_head,))
            head_row = cursor.fetchone()
            if head_row is None:
                raise ValueError(f"State not found for HEAD #{current_head}")

            snapshot = load_snapshot_from_storage(head_row["state_id"])
            restore_snapshot_in_cursor(cursor, snapshot)

        return {
            "scenario": "reset_clean",
            "title": "Reset Workspace to Clean HEAD",
            "description": f"Restored active database cleanly to HEAD #{current_head}.",
            "executed_sql": "-- Database restored cleanly to HEAD snapshot",
            "suggested_commit_message": "",
        }

    if scenario_key == "custom_sql":
        if not custom_sql or not custom_sql.strip():
            raise ValueError("custom_sql must be non-empty")
        sql_to_run = custom_sql.strip()
        scenario_info = {
            "title": "Custom SQL Live Execution",
            "description": "Executed custom SQL statement on PostgreSQL.",
            "suggested_commit_message": "Live Demo: Manual SQL database manipulation",
        }
    elif scenario_key in DEMO_SCENARIOS:
        scenario_info = DEMO_SCENARIOS[scenario_key]
        sql_to_run = scenario_info["sql"]
    else:
        raise ValueError(f"Unknown demo scenario: {scenario_key}. Available: {list(DEMO_SCENARIOS.keys())} or 'reset_clean', 'custom_sql'")

    with get_db_cursor(commit=True) as cursor:
        cursor.execute(sql_to_run)

    return {
        "scenario": scenario_key,
        "title": scenario_info["title"],
        "description": scenario_info["description"],
        "executed_sql": sql_to_run.strip(),
        "suggested_commit_message": scenario_info["suggested_commit_message"],
    }
