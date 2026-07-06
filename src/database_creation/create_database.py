"""
ForgeForce Procurement Agents - Database Creation Script
Creates the SQLite database and all tables based on the schema design (v1.2)
"""

import sqlite3
from pathlib import Path

DB_PATH = Path("data/forgeforce_procurement.db")

def create_database():
    """Create SQLite database and all tables."""
    
    # Ensure data directory exists
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    print("Creating database tables...")
    
    # Enable foreign keys
    cursor.execute("PRAGMA foreign_keys = ON;")
    
    # 1. products
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS products (
            product_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            category TEXT NOT NULL,
            description TEXT,
            typical_order_qty INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # 2. items
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS items (
            item_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            category TEXT NOT NULL,
            unit TEXT NOT NULL,
            unit_cost_usd REAL,
            spot_price_usd REAL,
            is_critical BOOLEAN DEFAULT 0,
            lead_time_days INTEGER,
            safety_stock INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # 3. bom_lines
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS bom_lines (
            bom_line_id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id TEXT NOT NULL,
            item_id TEXT NOT NULL,
            quantity REAL NOT NULL,
            unit TEXT NOT NULL,
            buffer_pct REAL DEFAULT 0.03,
            notes TEXT,
            FOREIGN KEY (product_id) REFERENCES products(product_id),
            FOREIGN KEY (item_id) REFERENCES items(item_id)
        )
    """)
    
    # 4. suppliers
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS suppliers (
            supplier_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            country TEXT,
            segment TEXT,
            city_state TEXT,
            contact_email TEXT,
            avg_lead_time_days INTEGER,
            payment_terms TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # 5. supplier_performance (Updated v2.0 - Separate manufacturing & shipping lead time)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS supplier_performance (
            performance_id INTEGER PRIMARY KEY AUTOINCREMENT,
            supplier_id TEXT NOT NULL,
            item_id TEXT,
            period TEXT,
            
            -- Performance Metrics
            on_time_delivery_pct REAL,
            quality_rejection_pct REAL,
            recent_issues TEXT,
            capacity_status TEXT,
            
            -- Lead Time Breakdown (Recommended Structure)
            manufacturing_lead_time_days INTEGER,     -- Time to produce the item
            shipping_lead_time_days INTEGER,          -- Freight / customs / shipping time
            current_expected_lead_time_days INTEGER,  -- Total = manufacturing + shipping
            
            -- Risk
            delay_risk_level TEXT CHECK(delay_risk_level IN ('Low', 'Medium', 'High')),
            current_risk_notes TEXT,
            
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            
            FOREIGN KEY (supplier_id) REFERENCES suppliers(supplier_id),
            FOREIGN KEY (item_id) REFERENCES items(item_id)
        )
    """)
    
    # 6. inventory
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS inventory (
            inventory_id INTEGER PRIMARY KEY AUTOINCREMENT,
            item_id TEXT NOT NULL,
            current_stock INTEGER DEFAULT 0,
            reserved_qty INTEGER DEFAULT 0,
            on_order_qty INTEGER DEFAULT 0,
            last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (item_id) REFERENCES items(item_id)
        )
    """)
    
    # 7. users
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            role TEXT NOT NULL,
            department TEXT,
            can_approve_up_to_usd REAL
        )
    """)
    
    # 8. work_orders
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS work_orders (
            work_order_id TEXT PRIMARY KEY,
            product_id TEXT NOT NULL,
            quantity INTEGER NOT NULL,
            required_date DATE,
            status TEXT DEFAULT 'Planned',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (product_id) REFERENCES products(product_id)
        )
    """)
    
    # 9. supplier_item_pricing (Updated v2.0 - Added spot_price_usd)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS supplier_item_pricing (
            pricing_id INTEGER PRIMARY KEY AUTOINCREMENT,
            supplier_id TEXT NOT NULL,
            item_id TEXT NOT NULL,
            
            -- Pricing
            contracted_price_usd REAL,           -- Negotiated / Contracted price
            spot_price_usd REAL,                 -- Spot market price (per supplier per item)
            
            -- Order Constraints
            moq INTEGER DEFAULT 1,
            volume_discount_pct REAL DEFAULT 0,
            volume_threshold INTEGER DEFAULT 0,
            
            valid_from DATE,
            valid_to DATE,
            is_active BOOLEAN DEFAULT 1,
            
            FOREIGN KEY (supplier_id) REFERENCES suppliers(supplier_id),
            FOREIGN KEY (item_id) REFERENCES items(item_id)
        )
    """)
    
    # 10. purchase_requisitions
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS purchase_requisitions (
            pr_id TEXT PRIMARY KEY,
            requested_by TEXT NOT NULL,
            department TEXT,
            status TEXT DEFAULT 'Draft',
            total_estimated_usd REAL,
            required_date DATE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            approved_by TEXT,
            approved_at TIMESTAMP,
            FOREIGN KEY (requested_by) REFERENCES users(user_id),
            FOREIGN KEY (approved_by) REFERENCES users(user_id)
        )
    """)
    
    # 11. pr_lines
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS pr_lines (
            pr_line_id INTEGER PRIMARY KEY AUTOINCREMENT,
            pr_id TEXT NOT NULL,
            item_id TEXT NOT NULL,
            quantity INTEGER NOT NULL,
            unit TEXT,
            estimated_unit_cost_usd REAL,
            notes TEXT,
            FOREIGN KEY (pr_id) REFERENCES purchase_requisitions(pr_id),
            FOREIGN KEY (item_id) REFERENCES items(item_id)
        )
    """)
    
    # 12. purchase_orders
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS purchase_orders (
            po_id TEXT PRIMARY KEY,
            supplier_id TEXT NOT NULL,
            pr_id TEXT,
            status TEXT DEFAULT 'Created',
            total_usd REAL,
            expected_delivery DATE,
            created_by_agent BOOLEAN DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (supplier_id) REFERENCES suppliers(supplier_id),
            FOREIGN KEY (pr_id) REFERENCES purchase_requisitions(pr_id)
        )
    """)
    
    # 13. po_lines
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS po_lines (
            po_line_id INTEGER PRIMARY KEY AUTOINCREMENT,
            po_id TEXT NOT NULL,
            item_id TEXT NOT NULL,
            quantity INTEGER NOT NULL,
            unit_cost_usd REAL,
            line_total_usd REAL,
            FOREIGN KEY (po_id) REFERENCES purchase_orders(po_id),
            FOREIGN KEY (item_id) REFERENCES items(item_id)
        )
    """)
    
    # 14. activity_log
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS activity_log (
            log_id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            actor TEXT,
            action TEXT,
            entity_type TEXT,
            entity_id TEXT,
            details TEXT
        )
    """)
    
    conn.commit()
    conn.close()
    
    print(f"Database created successfully at: {DB_PATH}")
    return DB_PATH

if __name__ == "__main__":
    create_database()