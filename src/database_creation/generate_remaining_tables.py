"""
ForgeForce Procurement Agents - Generate Remaining Tables (Inventory, Users, Work Orders, Pricing)
"""

import sqlite3
import random
from pathlib import Path
from datetime import datetime, timedelta

DB_PATH = Path("data/forgeforce_procurement.db")

random.seed(42)

def get_connection():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn

def table_has_data(conn, table_name):
    cursor = conn.cursor()
    cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
    return cursor.fetchone()[0] > 0

def generate_remaining_tables(conn):
    cursor = conn.cursor()
    
    # 1. Users (RBAC)
    if not table_has_data(conn, "users"):
        users = [
            ("U001", "Sarah Patel", "PPC_Lead", "Production", 5000),
            ("U002", "Mike Chen", "Maintenance_Lead", "Maintenance", 2000),
            ("U003", "Priya Sharma", "NPD_Engineer", "NPD", 10000),
            ("U004", "John Ramirez", "Procurement_Executive", "Procurement", 8000),
            ("U005", "Aisha Khan", "Procurement_Manager", "Procurement", 25000),
            ("U006", "Robert Kim", "Plant_Head", "Operations", 50000),
            ("U007", "Elena Vargas", "Quality_Engineer", "Quality", 3000),
            ("U008", "David Thompson", "Director", "Management", 100000),
        ]
        cursor.executemany("""
            INSERT INTO users (user_id, name, role, department, can_approve_up_to_usd)
            VALUES (?, ?, ?, ?, ?)
        """, users)
        print("Inserted 8 users.")
    else:
        print("Users already populated.")

    # 2. Inventory (Varied stock levels for all items)
    if not table_has_data(conn, "inventory"):
        cursor.execute("SELECT item_id FROM items")
        item_ids = [row[0] for row in cursor.fetchall()]
        inventory_data = []
        for item_id in item_ids:
            reserved = random.randint(0, 50)
            current_stock = random.randint(reserved, 200)
            on_order = random.randint(0, 100)
            inventory_data.append((item_id, current_stock, reserved, on_order))
        cursor.executemany("""
            INSERT INTO inventory (item_id, current_stock, reserved_qty, on_order_qty)
            VALUES (?, ?, ?, ?)
        """, inventory_data)
        print(f"Inserted inventory for {len(item_ids)} items.")

    # 3. Work Orders
    if not table_has_data(conn, "work_orders"):
        work_orders = [
            ("WO-001", "RS-240", 80, "2026-07-15", "Released"),
            ("WO-002", "GH-450", 50, "2026-07-20", "Planned"),
            ("WO-003", "BHU-6205", 60, "2026-07-10", "Released"),
            ("WO-004", "EMB-240", 100, "2026-07-25", "Planned"),
            ("WO-005", "HG-80-M2", 30, "2026-07-18", "Released"),
            ("WO-006", "IMP-150", 45, "2026-07-12", "Released"),
        ]
        cursor.executemany("""
            INSERT INTO work_orders (work_order_id, product_id, quantity, required_date, status)
            VALUES (?, ?, ?, ?, ?)
        """, work_orders)
        print("Inserted sample work orders.")

    # 4. Supplier Item Pricing (Contracted + Spot + MOQ) - Aligned with supplier_performance (v2.1)
    if not table_has_data(conn, "supplier_item_pricing"):
        # Generate pricing ONLY for supplier-item combinations that exist in supplier_performance
        cursor.execute("""
            SELECT DISTINCT sp.supplier_id, sp.item_id, i.unit_cost_usd
            FROM supplier_performance sp
            LEFT JOIN items i ON i.item_id = sp.item_id
        """)
        pairs = cursor.fetchall()
        
        pricing_data = []
        for supplier_id, item_id, unit_cost in pairs:
            if unit_cost is None or unit_cost <= 0:
                unit_cost = random.uniform(5, 50)  # fallback if missing
            
            # Generate contracted price around the item's unit cost
            contracted_variation = random.uniform(0.90, 1.10)
            contracted = round(unit_cost * contracted_variation, 2)
            
            # Generate spot price (can be slightly higher or lower than contracted)
            spot_variation = random.uniform(0.95, 1.15)
            spot = round(contracted * spot_variation, 2)
            
            moq = random.choice([1, 5, 10, 20, 50, 100])
            volume_discount = round(random.choice([0, 3, 5, 8, 10, 12]), 1)
            volume_threshold = random.choice([50, 100, 200, 500]) if volume_discount > 0 else 0
            
            pricing_data.append((
                supplier_id, 
                item_id, 
                contracted,      # contracted_price_usd
                spot,            # spot_price_usd
                moq, 
                volume_discount, 
                volume_threshold, 
                "2025-01-01", 
                "2026-12-31", 
                1
            ))
        
        cursor.executemany("""
            INSERT INTO supplier_item_pricing 
            (supplier_id, item_id, contracted_price_usd, spot_price_usd, moq, 
             volume_discount_pct, volume_threshold, valid_from, valid_to, is_active)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, pricing_data)
        
        print(f"Inserted {len(pricing_data)} supplier item pricing records (aligned with supplier_performance).")
        print("  - Prices are now generated relative to each item's unit_cost_usd")
        print("  - Each supplier-item now has contracted_price + spot_price + MOQ")

    conn.commit()

if __name__ == "__main__":
    conn = get_connection()
    generate_remaining_tables(conn)
    conn.close()
    print("Remaining tables generation completed.")