"""
Generate BOM Lines for all 6 products.
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

def generate_bom_lines(conn):
    cursor = conn.cursor()
    
    if not table_has_data(conn, "bom_lines"):
        bom_lines = [
            # RS-240
            ("RS-240", "RM-4140", 0.85, "kg", 0.025, "Main shaft material"),
            ("RS-240", "BR-6205", 2, "pcs", 0.025, "Critical bearing"),
            ("RS-240", "BR-6305", 1, "pcs", 0.025, "Drive end bearing"),
            ("RS-240", "FT-M6-20", 4, "pcs", 0.02, "Coupling attachment"),
            ("RS-240", "FT-M5-CIR", 2, "pcs", 0.02, "Bearing retention"),
            # GH-450
            ("GH-450", "CS-AL-450", 1, "pcs", 0.03, "From approved foundry"),
            ("GH-450", "BR-6208", 2, "pcs", 0.025, "Input shaft bearings"),
            ("GH-450", "BR-32208", 2, "pcs", 0.025, "Output shaft bearings"),
            ("GH-450", "FT-M8-25", 8, "pcs", 0.02, "Housing assembly"),
            ("GH-450", "GS-450", 1, "set", 0.02, "Sealing between halves"),
            # BHU-6205
            ("BHU-6205", "BR-6205", 2, "pcs", 0.025, "Critical bearing"),
            ("BHU-6205", "SL-35-52", 2, "pcs", 0.03, "Both sides sealing"),
            ("BHU-6205", "FT-M6-20", 4, "pcs", 0.02, "End cover fastening"),
            ("BHU-6205", "GR-001", 25, "g", 0.01, "Pre-filled grease"),
            # EMB-240
            ("EMB-240", "RM-S355", 1, "pcs", 0.04, "Laser cut plate"),
            ("EMB-240", "BR-6204", 1, "pcs", 0.025, "Pivot point bearing"),
            ("EMB-240", "FT-M10-30", 4, "pcs", 0.02, "Grade 10.9"),
            ("EMB-240", "FT-M8-NUT", 4, "pcs", 0.02, "Hex nut"),
            # HG-80-M2
            ("HG-80-M2", "RM-8620", 2.8, "kg", 0.05, "Gear blank material"),
            ("HG-80-M2", "BR-6207", 1, "pcs", 0.025, "Gear shaft support"),
            ("HG-80-M2", "FT-M5-CIR", 1, "pcs", 0.02, "Shaft mounting"),
            # IMP-150
            ("IMP-150", "CS-SS-150", 1, "pcs", 0.03, "From approved foundry"),
            ("IMP-150", "BR-6203", 2, "pcs", 0.025, "Impeller shaft support"),
            ("IMP-150", "SL-17-30", 1, "pcs", 0.03, "Critical sealing component"),
            ("IMP-150", "FT-M6-20", 2, "pcs", 0.02, "Impeller locking"),
        ]
        cursor.executemany("""
            INSERT INTO bom_lines (product_id, item_id, quantity, unit, buffer_pct, notes)
            VALUES (?, ?, ?, ?, ?, ?)
        """, bom_lines)
        print(f"Inserted {len(bom_lines)} BOM lines.")
    else:
        print("BOM lines already populated.")

    conn.commit()

if __name__ == "__main__":
    conn = get_connection()
    generate_bom_lines(conn)
    conn.close()
    print("BOM lines generation completed.")