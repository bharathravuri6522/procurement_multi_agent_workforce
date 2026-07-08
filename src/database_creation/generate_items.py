"""
Generate Items master data (~40 items).
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

def generate_items(conn):
    cursor = conn.cursor()
    
    if not table_has_data(conn, "items"):
        items = [
            # Bearings (10)
            ("BR-6205", "Deep Groove Ball Bearing 6205", "Bearings", "pcs", 8.5, 12.75, 1, 8, 30),
            ("BR-6305", "Deep Groove Ball Bearing 6305", "Bearings", "pcs", 9.8, 12.75, 1, 8, 30),
            ("BR-6208", "Deep Groove Ball Bearing 6208", "Bearings", "pcs", 11.5, 16.1, 1, 8, 25),
            ("BR-32208", "Tapered Roller Bearing 32208", "Bearings", "pcs", 22.0, 26.4, 1, 9, 20),
            ("BR-6203", "Deep Groove Ball Bearing 6203", "Bearings", "pcs", 6.5, 9.75, 1, 6, 40),
            ("BR-6303", "Deep Groove Ball Bearing 6303", "Bearings", "pcs", 7.2, 9.36, 1, 6, 35),
            ("BR-6204", "Deep Groove Ball Bearing 6204", "Bearings", "pcs", 7.8, 11.7, 1, 7, 30),
            ("BR-6005", "Deep Groove Ball Bearing 6005", "Bearings", "pcs", 9.0, 10.8, 1, 8, 25),
            ("BR-6207", "Deep Groove Ball Bearing 6207", "Bearings", "pcs", 10.5, 14.7, 1, 11, 28),
            ("BR-6308", "Deep Groove Ball Bearing 6308", "Bearings", "pcs", 14.5, 17.4, 1, 10, 22),
            # Raw Materials (8)
            ("RM-4140", "Alloy Steel Bar 4140 (Ø45mm)", "Raw Material", "kg", 5.2, 7.8, 1, 12, 50),
            ("RM-8620", "Alloy Steel Round Bar 8620", "Raw Material", "kg", 6.8, 8.84, 1, 14, 40),
            ("RM-S355", "S355 Steel Plate (10mm)", "Raw Material", "kg", 4.5, 6.75, 0, 10, 60),
            ("RM-AL-6061", "Aluminum Bar 6061", "Raw Material", "kg", 5.8, 7.54, 0, 12, 45),
            ("RM-SS304", "Stainless Steel Bar 304", "Raw Material", "kg", 8.5, 10.2, 1, 15, 35),
            ("RM-CI", "Cast Iron Bar", "Raw Material", "kg", 3.8, 5.7, 0, 10, 55),
            ("RM-AL-Extr", "Aluminum Extrusion 6063", "Raw Material", "kg", 4.2, 6.3, 0, 11, 50),
            ("RM-Copper", "Copper Bar", "Raw Material", "kg", 12.5, 17.5, 1, 10, 25),
            # Castings & Forgings (6)
            ("CS-AL-450", "Aluminum Sand Casting (GH-450)", "Castings", "pcs", 45.0, 54.0, 1, 10, 20),
            ("CS-SS-150", "Stainless Steel Investment Casting", "Castings", "pcs", 68.0, 81.6, 1, 14, 15),
            ("FG-001", "Cast Iron Casting", "Castings", "pcs", 32.0, 41.6, 1, 12, 25),
            ("FG-002", "Steel Forging", "Forgings", "pcs", 28.0, 36.4, 1, 6, 18),
            ("CS-AL-150", "Aluminum Casting for Impeller", "Castings", "pcs", 38.0, 45.6, 1, 9, 20),
            ("FG-003", "Steel Forged Shaft Blank", "Forgings", "pcs", 42.0, 54.6, 1, 12, 22),
            # Fasteners & Hardware (8)
            ("FT-M6-20", "Hex Socket Head Cap Screw M6×20", "Fasteners", "pcs", 0.25, 0.38, 0, 5, 500),
            ("FT-M8-25", "Hex Head Bolt M8×25 Grade 8.8", "Fasteners", "pcs", 0.45, 0.65, 0, 5, 400),
            ("FT-M10-30", "High Tensile Bolt M10×30", "Fasteners", "pcs", 0.65, 0.85, 0, 6, 300),
            ("FT-M5-CIR", "External Circlip M5", "Fasteners", "pcs", 0.15, 0.26, 0, 4, 600),
            ("FT-M8-NUT", "Hex Nut M8 Grade 8", "Fasteners", "pcs", 0.12, 0.18, 0, 4, 700),
            ("FT-Dowel", "Dowel Pin 8x30", "Fasteners", "pcs", 0.35, 0.45, 0, 6, 250),
            ("FT-Stud", "Threaded Stud M10x50", "Fasteners", "pcs", 0.55, 0.60, 0, 7, 200),
            ("FT-Washer", "Flat Washer M10", "Fasteners", "pcs", 0.08, 0.09, 0, 3, 800),
            # Seals & Gaskets (5)
            ("SL-35-52", "Oil Seal 35×52×7", "Seals", "pcs", 3.2, 3.6, 1, 8, 100),
            ("GS-450", "Cork + Rubber Gasket Set", "Seals", "set", 4.5, 4.9, 0, 10, 80),
            ("SL-17-30", "Mechanical Seal 17×30", "Seals", "pcs", 28.0, 34.2, 1, 11, 25),
            ("GS-150", "O-Ring Kit for Impeller", "Seals", "set", 2.8, 2.95, 0, 8, 120),
            ("SL-25-40", "Oil Seal 25×40×7", "Seals", "pcs", 2.5, 2.78, 1, 10, 90),
            # Packaging & Consumables (5)
            ("PK-001", "VCI Packaging + Label", "Packaging", "set", 1.2, 1.34, 0, 3, 200),
            ("GR-001", "Lithium Grease (High Temp)", "Consumables", "g", 0.08, 0.09, 0, 5, 500),
            ("AB-001", "Grinding Wheel", "Consumables", "pcs", 15.0, 18.2, 0, 20, 30),
            ("CT-001", "Cutting Tool Set", "Consumables", "set", 85.0, 92.8, 0, 30, 15),
            ("PK-002", "Protective Sleeve + Label", "Packaging", "set", 0.95, 0.99, 0, 4, 180),
        ]
        cursor.executemany("""
            INSERT INTO items (item_id, name, category, unit, unit_cost_usd, spot_price_usd, is_critical, lead_time_days, safety_stock)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, items)
        print(f"Inserted {len(items)} items.")
    else:
        print("Items already populated.")

    conn.commit()

if __name__ == "__main__":
    conn = get_connection()
    generate_items(conn)
    conn.close()
    print("Items generation completed.")