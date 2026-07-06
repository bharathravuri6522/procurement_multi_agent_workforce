"""
Generate Products table data.
"""

import sqlite3
from pathlib import Path

DB_PATH = Path("data/forgeforce_procurement.db")

def get_connection():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn

def table_has_data(conn, table_name):
    cursor = conn.cursor()
    cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
    return cursor.fetchone()[0] > 0

def generate_products(conn):
    cursor = conn.cursor()
    
    if not table_has_data(conn, "products"):
        products = [
            ("RS-240", "Precision Rotor Shaft", "Rotating Components", "High-precision rotor shaft for motors and pumps", 100),
            ("GH-450", "Gearbox Housing – Model GH-450", "Housings & Enclosures", "Cast aluminum gearbox housing for speed reducers", 50),
            ("BHU-6205", "Integrated Bearing Housing Unit", "Bearing Assemblies", "Pre-assembled bearing housing unit for conveyors", 80),
            ("EMB-240", "Engine Mounting Bracket", "Custom Brackets & Mounts", "Heavy-duty engine mounting bracket for commercial vehicles", 120),
            ("HG-80-M2", "Helical Gear – Module 2", "Gears & Power Transmission", "Precision helical gear for industrial gearboxes", 40),
            ("IMP-150", "Centrifugal Pump Impeller", "Fluid Handling Components", "Precision machined closed impeller for centrifugal pumps", 60),
        ]
        cursor.executemany("""
            INSERT INTO products (product_id, name, category, description, typical_order_qty)
            VALUES (?, ?, ?, ?, ?)
        """, products)
        print("Inserted 6 products.")
    else:
        print("Products already populated.")

    conn.commit()

if __name__ == "__main__":
    conn = get_connection()
    generate_products(conn)
    conn.close()
    print("Products generation completed.")