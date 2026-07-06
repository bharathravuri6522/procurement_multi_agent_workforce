"""
ForgeForce Procurement Agents - Seed Data Generation Script
Generates realistic seed data for the project.

Features:
- Creates database and tables if they don't exist
- Only seeds data if tables are empty (preserves existing data across runs)
- Starts with Suppliers + Supplier Performance (including risk fields)
"""

import sqlite3
import random
from datetime import datetime, timedelta
from pathlib import Path

DB_PATH = Path("data/forgeforce_procurement.db")

# Set seed for reproducibility during development
random.seed(42)

def get_connection():
    """Get database connection. Creates directory if needed."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn

def table_has_data(conn, table_name: str) -> bool:
    """Check if a table already has data."""
    cursor = conn.cursor()
    cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
    count = cursor.fetchone()[0]
    return count > 0

def create_tables_if_not_exist(conn):
    """Create all tables if they don't exist (idempotent)."""
    cursor = conn.cursor()
    
    # This is a simplified version - in production we'd use the full create_database.py logic
    # For now we assume create_database.py was run first, or we can call it.
    print("Ensuring tables exist...")
    # For simplicity in this script, we rely on create_database.py having been run.
    # You can also import and call create_database() here if needed.

def generate_suppliers(conn):
    """Generate 20 realistic suppliers across different segments."""
    if table_has_data(conn, "suppliers"):
        print("Suppliers table already has data. Skipping...")
        return

    suppliers = [
        # Premium / Global Tier-1 (4)
        ("SUP-001", "SKF USA Inc.", "USA", "Premium", "Lansdale, PA", "procurement@skf.com", 12, "Net 45"),
        ("SUP-002", "Timken Company", "USA", "Premium", "North Canton, OH", "sales@timken.com", 14, "Net 30"),
        ("SUP-003", "Bosch Rexroth USA", "USA", "Premium", "Charlotte, NC", "info@boschrexroth.com", 15, "Net 45"),
        ("SUP-004", "NSK Americas", "USA", "Premium", "Ann Arbor, MI", "sales@nsk.com", 13, "Net 30"),
        
        # US Regional / Mid-tier (6)
        ("SUP-005", "Midwest Precision Castings", "USA", "US_Regional", "Indianapolis, IN", "quotes@mpc.com", 18, "Net 30"),
        ("SUP-006", "Ohio Bearing Solutions", "USA", "US_Regional", "Cleveland, OH", "orders@ohiobearing.com", 10, "Net 30"),
        ("SUP-007", "Illinois Fastener Corp", "USA", "US_Regional", "Chicago, IL", "sales@ilfastener.com", 8, "Net 15"),
        ("SUP-008", "Wisconsin Steel Bar Co.", "USA", "US_Regional", "Milwaukee, WI", "procure@wsb.com", 20, "Net 45"),
        ("SUP-009", "Michigan Machined Components", "USA", "US_Regional", "Grand Rapids, MI", "info@mmc.com", 16, "Net 30"),
        ("SUP-010", "Indiana Aluminum Castings", "USA", "US_Regional", "Columbus, IN", "sales@iacast.com", 22, "Net 30"),
        
        # Mexico Nearshoring (3)
        ("SUP-011", "Monterrey Precision Parts", "Mexico", "Mexico_Nearshore", "Monterrey, NL", "ventas@mpp.com.mx", 11, "Net 30"),
        ("SUP-012", "Queretaro Bearings SA", "Mexico", "Mexico_Nearshore", "Queretaro, QT", "compras@qb.mx", 13, "Net 45"),
        ("SUP-013", "Tijuana Metal Solutions", "Mexico", "Mexico_Nearshore", "Tijuana, BC", "sales@tms.mx", 9, "Net 30"),
        
        # Asia Cost-Optimized (5)
        ("SUP-014", "Shanghai Bearing Group", "China", "Asia_Cost", "Shanghai", "export@shbearing.cn", 35, "Net 60"),
        ("SUP-015", "Dongguan Fasteners Ltd", "China", "Asia_Cost", "Dongguan", "sales@dgfast.cn", 28, "Net 45"),
        ("SUP-016", "Vietnam Precision Castings", "Vietnam", "Asia_Cost", "Ho Chi Minh City", "info@vpc.vn", 32, "Net 45"),
        ("SUP-017", "India Steel Components", "India", "Asia_Cost", "Pune", "export@isc.in", 38, "Net 60"),
        ("SUP-018", "Shenzhen Seals Technology", "China", "Asia_Cost", "Shenzhen", "sales@szseals.cn", 30, "Net 45"),
        
        # Local / Strategic (2)
        ("SUP-019", "Columbus Industrial Supply", "USA", "Local_Strategic", "Columbus, IN", "orders@cis-indy.com", 5, "Net 15"),
        ("SUP-020", "Central Indiana Bearings", "USA", "Local_Strategic", "Indianapolis, IN", "sales@cibearings.com", 4, "Net 15"),
    ]
    
    cursor = conn.cursor()
    cursor.executemany("""
        INSERT INTO suppliers 
        (supplier_id, name, country, segment, city_state, contact_email, avg_lead_time_days, payment_terms)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, suppliers)
    
    conn.commit()
    print(f"Inserted {len(suppliers)} suppliers.")

def generate_supplier_performance(conn):
    """
    Generate supplier performance records with separate manufacturing and shipping lead times.
    
    Rules enforced:
    - delay_risk_level is never NULL (always Low / Medium / High)
    - Lead times are never NULL (minimum 5 days total)
    - International suppliers get significantly higher shipping_lead_time_days
    - Every BOM item gets 4-5 suppliers
    """
    if table_has_data(conn, "supplier_performance"):
        print("Supplier Performance table already has data. Skipping...")
        return

    cursor = conn.cursor()
    
    # Get suppliers
    cursor.execute("SELECT supplier_id, segment FROM suppliers")
    suppliers = cursor.fetchall()
    supplier_dict = {s[0]: s[1] for s in suppliers}
    all_supplier_ids = list(supplier_dict.keys())
    
    # Get BOM items
    cursor.execute("SELECT DISTINCT item_id FROM bom_lines")
    bom_item_ids = [row[0] for row in cursor.fetchall()]
    
    # Get some non-BOM items
    cursor.execute("""
        SELECT item_id FROM items 
        WHERE item_id NOT IN (SELECT item_id FROM bom_lines)
        LIMIT 20
    """)
    other_item_ids = [row[0] for row in cursor.fetchall()]
    
    performance_records = []
    used_combinations = set()
    
    def get_lead_time_breakdown(segment, risk_level):
        """Generate realistic manufacturing + shipping lead time based on segment and risk."""
        if segment == "Premium":
            manufacturing = random.randint(8, 18)
            shipping = random.randint(1, 4)          # Very low shipping for Premium domestic
        elif segment == "US_Regional":
            manufacturing = random.randint(7, 16)
            shipping = random.randint(2, 5)
        elif segment == "Mexico_Nearshore":
            manufacturing = random.randint(8, 15)
            shipping = random.randint(5, 12)         # Moderate shipping
        else:  # Asia_Cost
            manufacturing = random.randint(18, 32)
            shipping = random.randint(15, 28)        # High shipping for Asia
        
        # Adjust manufacturing time based on risk
        if risk_level == "High":
            manufacturing += random.randint(5, 12)
        elif risk_level == "Medium":
            manufacturing += random.randint(2, 6)
        
        total_lead = manufacturing + shipping
        # Ensure minimum 5 days total
        if total_lead < 5:
            total_lead = 5
            manufacturing = max(3, total_lead - shipping)
        
        return manufacturing, shipping, total_lead
    
    def get_risk_and_performance(segment):
        """Generate risk level and performance metrics."""
        if segment == "Premium":
            risk_level = "Low"
            on_time = round(random.uniform(94, 99), 1)
            rejection = round(random.uniform(0.3, 1.2), 1)
            capacity = random.choice(["Normal", "Available"])
        elif segment == "US_Regional":
            risk_level = random.choice(["Low", "Medium"])
            on_time = round(random.uniform(88, 96), 1)
            rejection = round(random.uniform(0.8, 2.5), 1)
            capacity = random.choice(["Normal", "Constrained", "Available"])
        elif segment == "Mexico_Nearshore":
            risk_level = "Low"
            on_time = round(random.uniform(85, 94), 1)
            rejection = round(random.uniform(1.0, 3.0), 1)
            capacity = random.choice(["Normal", "Available"])
        else:  # Asia_Cost
            if random.random() < 0.35:
                risk_level = random.choice(["Medium", "High"])
            else:
                risk_level = "Low"
            on_time = round(random.uniform(78, 92), 1)
            rejection = round(random.uniform(1.5, 5.5), 1)
            capacity = random.choice(["Normal", "Constrained"])
        
        return risk_level, on_time, rejection, capacity
    
    # === Generate for BOM items (4-5 suppliers each) ===
    for item_id in bom_item_ids:
        num_suppliers = random.randint(4, 5)
        selected_suppliers = random.sample(all_supplier_ids, min(num_suppliers, len(all_supplier_ids)))
        
        for supplier_id in selected_suppliers:
            if (supplier_id, item_id) in used_combinations:
                continue
            
            segment = supplier_dict[supplier_id]
            period = random.choice(["2025-Q3", "2025-Q4", "2026-Q1", "Last_6_Months", "Recent"])
            
            risk_level, on_time, rejection, capacity = get_risk_and_performance(segment)
            manufacturing_lt, shipping_lt, total_lt = get_lead_time_breakdown(segment, risk_level)
            
            # Risk notes
            risk_notes = ""
            if risk_level == "High":
                risk_notes = random.choice([
                    "Multiple late deliveries in recent months",
                    "Quality issues reported on recent shipments",
                    "Capacity constraints affecting lead times"
                ])
            elif risk_level == "Medium":
                risk_notes = random.choice([
                    "Occasional delays observed",
                    "Capacity constraints reported for Q2"
                ])
            
            recent_issues = ""
            if rejection > 3.5:
                recent_issues = random.choice([
                    "Quality issues reported on 3 shipments in Q1",
                    "Dimensional deviations on recent lots"
                ])
            elif capacity == "Constrained":
                recent_issues = "Capacity constraints reported for Q2"
            
            performance_records.append((
                supplier_id,
                item_id,
                period,
                on_time,
                rejection,
                recent_issues,
                capacity,
                manufacturing_lt,
                shipping_lt,
                total_lt,
                risk_level,
                risk_notes
            ))
            used_combinations.add((supplier_id, item_id))
    
    # === Generate for some non-BOM items ===
    for item_id in other_item_ids:
        num_suppliers = random.randint(1, 2)
        selected_suppliers = random.sample(all_supplier_ids, min(num_suppliers, len(all_supplier_ids)))
        
        for supplier_id in selected_suppliers:
            if (supplier_id, item_id) in used_combinations:
                continue
            
            segment = supplier_dict[supplier_id]
            risk_level, on_time, rejection, capacity = get_risk_and_performance(segment)
            manufacturing_lt, shipping_lt, total_lt = get_lead_time_breakdown(segment, risk_level)
            
            risk_notes = ""
            if risk_level != "Low":
                risk_notes = "Occasional performance concerns"
            
            performance_records.append((
                supplier_id,
                item_id,
                "Recent",
                on_time,
                rejection,
                "",
                capacity,
                manufacturing_lt,
                shipping_lt,
                total_lt,
                risk_level,
                risk_notes
            ))
            used_combinations.add((supplier_id, item_id))
    
    if performance_records:
        cursor.executemany("""
            INSERT INTO supplier_performance 
            (supplier_id, item_id, period, on_time_delivery_pct, quality_rejection_pct, 
             recent_issues, capacity_status, 
             manufacturing_lead_time_days, shipping_lead_time_days, current_expected_lead_time_days,
             delay_risk_level, current_risk_notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, performance_records)
        
        conn.commit()
        print(f"Inserted {len(performance_records)} supplier performance records (v2.0 schema).")
        print(f"  - BOM items have 4-5 suppliers with separated lead times")
        print(f"  - International suppliers have higher shipping_lead_time_days")
    else:
        print("No supplier performance records generated.")

def main():
    print("=" * 60)
    print("ForgeForce Seed Data Generator")
    print("=" * 60)
    
    conn = get_connection()
    
    # Ensure tables exist (run create_database.py first if needed)
    create_tables_if_not_exist(conn)
    
    # Generate data (only if empty)
    generate_suppliers(conn)
    generate_supplier_performance(conn)
    
    conn.close()
    print("\nSeed data generation completed (or skipped where data existed).")

if __name__ == "__main__":
    main()