#!/usr/bin/env python3
"""
DataGit Demo Database Populator
Creates a rich e-commerce PostgreSQL schema with diverse data types, constraints,
indexes, views, sequences, and multiple branches and commits (including 3-way merges).
"""

import os
import sys

# Ensure backend directory is in python path
backend_dir = os.path.dirname(os.path.abspath(__file__))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from dagit.db.connection import get_db_cursor
from dagit.versioning.metadata import init_metadata_tables
from dagit.versioning.commit import create_commit
from dagit.versioning.branch import create_branch, list_branches
from dagit.versioning.checkout import checkout_branch
from dagit.versioning.merge import merge_branch


def run_sql(sql: str, params=None):
    with get_db_cursor(commit=True) as cursor:
        cursor.execute(sql, params)


def populate():
    print("🚀 Initializing fresh DataGit demo repository...")
    run_sql("""
        DROP TABLE IF EXISTS datagit_commit_parents CASCADE;
        DROP TABLE IF EXISTS datagit_workspace CASCADE;
        DROP TABLE IF EXISTS datagit_branches CASCADE;
        DROP TABLE IF EXISTS datagit_commits CASCADE;
        DROP TABLE IF EXISTS datagit_states CASCADE;
    """)
    init_metadata_tables()

    print("\n📦 Step 1: Creating initial core e-commerce schema on 'main' branch...")
    # Drop existing demo application tables if they exist
    run_sql("""
        DROP VIEW IF EXISTS customer_spending_summary CASCADE;
        DROP TABLE IF EXISTS order_items CASCADE;
        DROP TABLE IF EXISTS orders CASCADE;
        DROP TABLE IF EXISTS products CASCADE;
        DROP TABLE IF EXISTS categories CASCADE;
        DROP TABLE IF EXISTS customers CASCADE;
        DROP TABLE IF EXISTS user_sessions CASCADE;
        DROP TABLE IF EXISTS telemetry_events CASCADE;
        DROP TABLE IF EXISTS coupon_discounts CASCADE;
        DROP SEQUENCE IF EXISTS order_tracking_seq CASCADE;
    """)

    # 1. Categories table
    run_sql("""
        CREATE TABLE categories (
            id SERIAL PRIMARY KEY,
            name VARCHAR(100) UNIQUE NOT NULL,
            slug VARCHAR(120) UNIQUE NOT NULL,
            description TEXT,
            is_active BOOLEAN NOT NULL DEFAULT true
        );
    """)

    # 2. Customers table (VARCHAR, INT, JSONB, DATE, CHECK)
    run_sql("""
        CREATE TABLE customers (
            id SERIAL PRIMARY KEY,
            email VARCHAR(150) UNIQUE NOT NULL,
            full_name VARCHAR(120) NOT NULL,
            loyalty_tier VARCHAR(20) DEFAULT 'bronze' CHECK (loyalty_tier IN ('bronze', 'silver', 'gold', 'platinum')),
            loyalty_points INT DEFAULT 0 CHECK (loyalty_points >= 0),
            address JSONB,
            registered_date DATE DEFAULT CURRENT_DATE
        );
    """)

    # 3. Products table (NUMERIC, TEXT[], JSONB, TIMESTAMPTZ, FK)
    run_sql("""
        CREATE TABLE products (
            id SERIAL PRIMARY KEY,
            sku VARCHAR(50) UNIQUE NOT NULL,
            name VARCHAR(200) NOT NULL,
            category_id INT REFERENCES categories(id) ON DELETE SET NULL,
            price NUMERIC(10, 2) NOT NULL CHECK (price >= 0),
            cost_price NUMERIC(10, 2) CHECK (cost_price >= 0),
            stock_quantity INT NOT NULL DEFAULT 0 CHECK (stock_quantity >= 0),
            tags TEXT[],
            attributes JSONB,
            created_at TIMESTAMPTZ DEFAULT NOW()
        );
    """)

    # 4. Orders table
    run_sql("""
        CREATE TABLE orders (
            id SERIAL PRIMARY KEY,
            order_number VARCHAR(32) UNIQUE NOT NULL,
            customer_id INT NOT NULL REFERENCES customers(id),
            total_amount NUMERIC(12, 2) NOT NULL DEFAULT 0.00,
            status VARCHAR(30) NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'processing', 'completed', 'cancelled')),
            created_at TIMESTAMPTZ DEFAULT NOW()
        );
    """)

    # 5. Order items table
    run_sql("""
        CREATE TABLE order_items (
            id SERIAL PRIMARY KEY,
            order_id INT NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
            product_id INT NOT NULL REFERENCES products(id),
            quantity INT NOT NULL CHECK (quantity > 0),
            unit_price NUMERIC(10, 2) NOT NULL CHECK (unit_price >= 0)
        );
    """)

    c1 = create_commit(
        message="Initial schema: categories, customers, products, orders, order_items",
        author="Architecture Lead"
    )
    print(f"  ✓ Commit #{c1} created on main")

    # Step 2: Seed initial catalog & customer data
    print("\n🌱 Step 2: Seeding initial catalog and customer records...")
    run_sql("""
        INSERT INTO categories (name, slug, description) VALUES
            ('Electronics', 'electronics', 'Gadgets, devices, and accessories'),
            ('Home & Kitchen', 'home-kitchen', 'Appliances and kitchenware'),
            ('Books & Media', 'books-media', 'Hardcovers, paperbacks, and digital');

        INSERT INTO customers (email, full_name, loyalty_tier, loyalty_points, address) VALUES
            ('alice@example.com', 'Alice Chen', 'gold', 1450, '{"city": "San Francisco", "state": "CA", "zip": "94105"}'),
            ('bob@example.com', 'Bob Smith', 'silver', 520, '{"city": "Seattle", "state": "WA", "zip": "98101"}'),
            ('charlie@example.com', 'Charlie Patel', 'bronze', 120, '{"city": "Austin", "state": "TX", "zip": "78701"}');

        INSERT INTO products (sku, name, category_id, price, cost_price, stock_quantity, tags, attributes) VALUES
            ('TECH-001', 'Noise-Canceling Headphones', 1, 249.99, 110.00, 75, ARRAY['wireless', 'audio', 'bluetooth'], '{"brand": "AcousticPro", "bluetooth_version": "5.3"}'),
            ('TECH-002', 'Mechanical Keyboard 75%', 1, 129.50, 60.00, 120, ARRAY['keyboard', 'mechanical', 'rgb'], '{"switches": "Gateron Brown", "layout": "ANSI"}'),
            ('HOME-001', 'Precision Coffee Grinder', 2, 89.00, 42.00, 45, ARRAY['coffee', 'kitchen', 'espresso'], '{"burrs": "stainless steel conical", "steps": 30}'),
            ('BOOK-001', 'Designing Data-Intensive Applications', 3, 44.99, 22.00, 200, ARRAY['software', 'distributed systems', 'database'], '{"pages": 616, "edition": 1}');
    """)

    c2 = create_commit(
        message="Seed initial product catalog, categories, and customer records",
        author="Data Engineer"
    )
    print(f"  ✓ Commit #{c2} created on main")

    # Step 3: Add sequence, index, view, and sample orders
    print("\n🔍 Step 3: Adding indexes, sequence, order records, and summary view...")
    run_sql("""
        CREATE SEQUENCE order_tracking_seq START WITH 10001 INCREMENT BY 1;

        CREATE INDEX idx_products_category_price ON products (category_id, price);
        CREATE INDEX idx_orders_customer_status ON orders (customer_id, status);

        INSERT INTO orders (order_number, customer_id, total_amount, status) VALUES
            ('ORD-10001', 1, 379.49, 'completed'),
            ('ORD-10002', 2, 89.00, 'processing'),
            ('ORD-10003', 1, 44.99, 'completed');

        INSERT INTO order_items (order_id, product_id, quantity, unit_price) VALUES
            (1, 1, 1, 249.99),
            (1, 2, 1, 129.50),
            (2, 3, 1, 89.00),
            (3, 4, 1, 44.99);

        CREATE VIEW customer_spending_summary AS
            SELECT
                c.id AS customer_id,
                c.full_name,
                c.email,
                c.loyalty_tier,
                COUNT(o.id) AS total_orders,
                COALESCE(SUM(o.total_amount), 0.00) AS total_spent
            FROM customers c
            LEFT JOIN orders o ON c.id = o.customer_id
            GROUP BY c.id, c.full_name, c.email, c.loyalty_tier;
    """)

    c3 = create_commit(
        message="Add order_tracking_seq, performance indexes, and customer_spending_summary view",
        author="Database Admin"
    )
    print(f"  ✓ Commit #{c3} created on main")

    # Step 4: Branch 'feature/discounts'
    print("\n🌿 Step 4: Creating and switching to branch 'feature/discounts'...")
    create_branch("feature/discounts", from_commit_id=c3)
    checkout_branch("feature/discounts")

    run_sql("""
        CREATE TABLE coupon_discounts (
            id SERIAL PRIMARY KEY,
            coupon_code VARCHAR(30) UNIQUE NOT NULL,
            discount_percent NUMERIC(5, 2) NOT NULL CHECK (discount_percent > 0 AND discount_percent <= 100),
            min_purchase_amount NUMERIC(10, 2) DEFAULT 0.00,
            is_active BOOLEAN DEFAULT true,
            valid_until DATE NOT NULL
        );

        INSERT INTO coupon_discounts (coupon_code, discount_percent, min_purchase_amount, valid_until) VALUES
            ('SUMMER20', 20.00, 50.00, '2027-08-31'),
            ('BLACKFRIDAY', 30.00, 100.00, '2027-11-30'),
            ('WELCOME10', 10.00, 0.00, '2028-12-31');
    """)

    c4 = create_commit(
        message="Add coupon_discounts table and promotional discount codes",
        author="Promo Team"
    )
    print(f"  ✓ Commit #{c4} created on feature/discounts")

    # Step 5: Branch 'feature/analytics' (from c3)
    print("\n📊 Step 5: Creating and switching to branch 'feature/analytics'...")
    create_branch("feature/analytics", from_commit_id=c3)
    checkout_branch("feature/analytics")

    run_sql("""
        CREATE TABLE user_sessions (
            id SERIAL PRIMARY KEY,
            session_token VARCHAR(64) UNIQUE NOT NULL,
            customer_id INT REFERENCES customers(id) ON DELETE SET NULL,
            ip_address VARCHAR(45),
            user_agent TEXT,
            started_at TIMESTAMPTZ DEFAULT NOW(),
            last_activity_at TIMESTAMPTZ DEFAULT NOW()
        );

        CREATE TABLE telemetry_events (
            id SERIAL PRIMARY KEY,
            session_id INT REFERENCES user_sessions(id) ON DELETE CASCADE,
            event_name VARCHAR(100) NOT NULL,
            page_url TEXT NOT NULL,
            payload JSONB,
            occurred_at TIMESTAMPTZ DEFAULT NOW()
        );

        INSERT INTO user_sessions (session_token, customer_id, ip_address, user_agent) VALUES
            ('sess_tok_9918237', 1, '192.168.1.101', 'Mozilla/5.0 (Macintosh; Intel Mac OS X)'),
            ('sess_tok_4412891', 2, '192.168.1.102', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)');

        INSERT INTO telemetry_events (session_id, event_name, page_url, payload) VALUES
            (1, 'page_view', '/products/TECH-001', '{"referrer": "google.com", "dwell_time_sec": 42}'),
            (1, 'add_to_cart', '/cart', '{"sku": "TECH-001", "quantity": 1}'),
            (2, 'search', '/search?q=coffee', '{"query": "coffee", "results_count": 8}');
    """)

    c5 = create_commit(
        message="Add user_sessions and telemetry_events tables with JSONB analytics payload",
        author="Analytics Engineer"
    )
    print(f"  ✓ Commit #{c5} created on feature/analytics")

    # Step 6: Switch back to 'main' and merge 'feature/discounts' (3-Way Merge)
    print("\n🔀 Step 6: Switching to 'main' and executing 3-way merge of 'feature/discounts'...")
    checkout_branch("main")

    # Add a slight update to main to make the merge interesting (updating product stock)
    run_sql("""
        UPDATE products SET stock_quantity = 70 WHERE sku = 'TECH-001';
    """)
    c6 = create_commit(
        message="Update stock levels after warehouse count",
        author="Inventory Manager"
    )
    print(f"  ✓ Commit #{c6} created on main")

    # Merge feature/discounts into main
    merge_commit_id = merge_branch(
        "feature/discounts",
        author="Release Lead",
        message="Merge branch 'feature/discounts' into main"
    )
    print(f"  ✓ Two-parent 3-Way Merge Commit #{merge_commit_id} created on main!")

    # Step 7: Create a hotfix branch from main
    print("\n🔥 Step 7: Creating 'hotfix/pricing-adjustments' branch...")
    create_branch("hotfix/pricing-adjustments", from_commit_id=merge_commit_id)
    checkout_branch("hotfix/pricing-adjustments")

    run_sql("""
        UPDATE products SET price = 119.99 WHERE sku = 'TECH-002';
        ALTER TABLE products ADD COLUMN discount_eligible BOOLEAN DEFAULT true;
    """)
    c7 = create_commit(
        message="Hotfix: Adjust mechanical keyboard price and add discount_eligible column",
        author="Pricing Specialist"
    )
    print(f"  ✓ Commit #{c7} created on hotfix/pricing-adjustments")

    # Switch back to main as the active working branch
    print("\n🏁 Step 8: Returning to active branch 'main'...")
    checkout_branch("main")

    branches = list_branches()
    print("\n✅ Demo Database Population Complete!")
    print(f"Total branches: {len(branches)}")
    for b in branches:
        current_marker = "👈 (ACTIVE)" if b.get("is_current") else ""
        print(f"  • {b['name']}: HEAD #{b.get('head_commit_id') or b.get('head_commit')} {current_marker}")


if __name__ == "__main__":
    populate()
