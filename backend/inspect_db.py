#!/usr/bin/env python3
"""
Inspect the live PostgreSQL database directly to prove database integrity.
Shows actual PostgreSQL catalog, tables, row counts, and sample records.
"""
import sys
from dagit.db.connection import get_db_cursor, DB_HOST, DB_PORT, DB_NAME, DB_USER

def inspect_database():
    print("=" * 72)
    print("  🐘 POSTGRESQL LIVE DATABASE INSPECTOR (Proof of Real Database)")
    print(f"  Target: postgresql://{DB_USER}@{DB_HOST}:{DB_PORT}/{DB_NAME}")
    print("=" * 72)

    with get_db_cursor() as cur:
        # 1. PostgreSQL Version & Database info
        cur.execute("SELECT version(), current_database(), pg_size_pretty(pg_database_size(current_database())) as size;")
        db_info = cur.fetchone()
        print(f"\n[1] PostgreSQL Engine & Database:")
        print(f"    Version:  {db_info['version'].split(' on ')[0]}")
        print(f"    Database: {db_info['current_database']}")
        print(f"    DB Size:  {db_info['size']}")

        # 2. List all actual base tables in schema public
        cur.execute("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
            ORDER BY table_name;
        """)
        tables = [row["table_name"] for row in cur.fetchall()]
        print(f"\n[2] Real Physical Tables in 'public' schema ({len(tables)} tables):")
        
        # 3. Print row counts and sizes for each table
        for tbl in tables:
            cur.execute(f"SELECT COUNT(*) as count FROM {tbl};")
            count = cur.fetchone()["count"]
            cur.execute(f"SELECT pg_size_pretty(pg_total_relation_size('{tbl}')) as size;")
            size = cur.fetchone()["size"]
            print(f"    • {tbl:<24} {count:>5} rows  (Disk size: {size})")

        # 4. Show live data from key e-commerce tables
        if "products" in tables:
            print(f"\n[3] Actual 'products' Table Content (Live PostgreSQL Query):")
            cur.execute("SELECT id, name, category_id, price, stock_quantity, tags FROM products ORDER BY id LIMIT 5;")
            rows = cur.fetchall()
            print(f"    {'ID':<4} | {'Name':<32} | {'Price':<10} | {'Stock':<6} | {'Tags'}")
            print("    " + "-" * 72)
            for r in rows:
                print(f"    {r['id']:<4} | {r['name'][:32]:<32} | ${str(r['price']):<9} | {r['stock_quantity']:<6} | {r['tags']}")

        if "customers" in tables:
            print(f"\n[4] Actual 'customers' Table Content (Live PostgreSQL Query):")
            cur.execute("SELECT id, full_name, email, loyalty_tier FROM customers ORDER BY id LIMIT 5;")
            rows = cur.fetchall()
            print(f"    {'ID':<4} | {'Customer Name':<22} | {'Tier':<12} | {'Email'}")
            print("    " + "-" * 72)
            for r in rows:
                print(f"    {r['id']:<4} | {r['full_name'][:22]:<22} | {r['loyalty_tier']:<12} | {r['email']}")

        if "orders" in tables:
            print(f"\n[5] Actual 'orders' Table Content (Live PostgreSQL Query):")
            cur.execute("SELECT id, order_number, customer_id, total_amount, status FROM orders ORDER BY id DESC LIMIT 5;")
            rows = cur.fetchall()
            print(f"    {'ID':<4} | {'Order Number':<18} | {'Customer':<10} | {'Total':<10} | {'Status'}")
            print("    " + "-" * 72)
            for r in rows:
                print(f"    {r['id']:<4} | {r['order_number']:<18} | {r['customer_id']:<10} | ${str(r['total_amount']):<9} | {r['status']}")

    print("\n" + "=" * 72)
    print("  ✅ Real PostgreSQL database query complete.")
    print("=" * 72 + "\n")

if __name__ == "__main__":
    inspect_database()
