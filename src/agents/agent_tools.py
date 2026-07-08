"""
Agent Tools for the Multi-Agent Procurement System (Item-level + BOM-aware).

These tools support an item-level procurement approach:
- Products are exploded via BOM into items/components
- Inventory, net requirement, and supplier analysis happen per item
- Different items can be sourced from different suppliers

In a production environment, these would be replaced with calls to ERP APIs
(SAP, Oracle, Dynamics, etc.) while keeping the same interface.
"""

import sqlite3
from typing import Optional, List, Dict, Any
from datetime import datetime
from pathlib import Path
import os

# ============================================================
# DATABASE CONNECTION (Robust Path Resolution)
# ============================================================

def _get_database_path() -> Path:
    """
    Dynamically find the database path.
    Works in both:
    - Local development (your machine)
    - This sandbox environment
    """
    current_file = Path(__file__).resolve()
    
    # Strategy 1: Walk up the directory tree and look for 'data/forgeforce_procurement.db'
    for parent in current_file.parents:
        candidate = parent / "data" / "forgeforce_procurement.db"
        if candidate.exists():
            return candidate
    
    # Strategy 2: Fallback for sandbox environment
    sandbox_path = Path("/home/workdir/artifacts/forgeforce_procurement/data/forgeforce_procurement.db")
    if sandbox_path.exists():
        return sandbox_path
    
    # Strategy 3: Last resort - assume standard project layout
    # (project_root / data / forgeforce_procurement.db)
    project_root = current_file.parents[2]   # agents/ -> src/ -> project_root/
    return project_root / "data" / "forgeforce_procurement.db"


DB_PATH = _get_database_path()


def get_db_connection():
    """Create and return a database connection."""
    if not DB_PATH.exists():
        raise FileNotFoundError(
            f"Database file not found at: {DB_PATH}\n"
            f"Please check your folder structure or run the database setup scripts."
        )
    
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row  # Return rows as dictionaries
    return conn


# For debugging - you can uncomment this temporarily
# print(f"[agent_tools] Using database at: {DB_PATH}")


# ============================================================
# INVENTORY & DEMAND TOOLS (Item-level)
# ============================================================

def get_product_details(product_id: str) -> Optional[Dict[str, Any]]:
    """
    Get basic product/item information.
    
    Args:
        product_id: The product or item identifier (e.g., 'SUP-001')
    
    Returns:
        Dictionary with product details or None if not found.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Try products table first
    cursor.execute("""
        SELECT product_id, name, category, description, typical_order_qty
        FROM products 
        WHERE product_id = ?
    """, (product_id,))
    row = cursor.fetchone()
    
    if row:
        conn.close()
        return dict(row)
    
    # Fallback to items table
    cursor.execute("""
        SELECT item_id as product_id, name, category, unit as description, 
               NULL as typical_order_qty
        FROM items 
        WHERE item_id = ?
    """, (product_id,))
    row = cursor.fetchone()
    conn.close()
    
    return dict(row) if row else None


def get_inventory_status(item_id: str) -> Optional[Dict[str, Any]]:
    """
    Get current inventory status for an ITEM (component).
    
    IMPORTANT: This works at item level (not product level).
    Use get_bom_items() first if you have a product_id.
    
    Returns current stock, reserved quantity, on-order quantity,
    available quantity, safety stock, and lead time.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT 
            i.item_id,
            i.current_stock,
            i.reserved_qty,
            i.on_order_qty,
            COALESCE(it.safety_stock, 0) as safety_stock,
            it.lead_time_days
        FROM inventory i
        LEFT JOIN items it ON i.item_id = it.item_id
        WHERE i.item_id = ?
    """, (item_id,))
    
    row = cursor.fetchone()
    conn.close()
    
    if not row:
        return None
    
    data = dict(row)
    data["available_qty"] = data["current_stock"] - data["reserved_qty"]
    data["net_position"] = data["available_qty"] + data["on_order_qty"]
    
    return data


def get_safety_stock(product_id: str) -> Optional[int]:
    """Get safety stock level for a product/item."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT safety_stock FROM items WHERE item_id = ?
        UNION
        SELECT NULL FROM products WHERE product_id = ?
    """, (product_id, product_id))
    
    row = cursor.fetchone()
    conn.close()
    
    return row[0] if row and row[0] is not None else None


# ============================================================
# BOM (Bill of Materials) TOOLS - Item-level + BOM-aware support
# ============================================================

def get_bom_items(product_id: str) -> List[Dict[str, Any]]:
    """
    Get the list of items (components) required to make/produce a product.
    
    This is critical for the item-level + BOM-aware approach.
    Returns each item along with the required quantity from the BOM.
    
    Args:
        product_id: The finished product identifier
    
    Returns:
        List of items with their required quantity, unit, and buffer percentage.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT 
            bl.item_id,
            i.name as item_name,
            bl.quantity,
            bl.unit,
            bl.buffer_pct,
            bl.notes,
            COALESCE(i.safety_stock, 0) as safety_stock,
            i.lead_time_days
        FROM bom_lines bl
        LEFT JOIN items i ON bl.item_id = i.item_id
        WHERE bl.product_id = ?
        ORDER BY bl.item_id
    """, (product_id,))
    
    rows = cursor.fetchall()
    conn.close()
    
    return [dict(row) for row in rows]


# ============================================================
# SUPPLIER INTELLIGENCE TOOLS
# ============================================================

def get_supplier_options(item_id: str) -> List[Dict[str, Any]]:
    """
    Get suppliers who actually supply this ITEM along with their performance data + pricing/MOQ.
    
    This version uses a two-step approach for reliability:
    1. Get suppliers from supplier_performance.
    2. For each supplier, fetch pricing separately (more robust against data misalignment).
    
    Returns both supplier-specific data and item-level thresholds for the Reasoning Node.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Step 1: Get all suppliers that have performance data for this item
    cursor.execute("""
        SELECT 
            sp.supplier_id,
            s.name as supplier_name,
            s.country,
            s.segment,
            s.avg_lead_time_days as contracted_lead_time,
            
            -- Lead Time Breakdown
            sp.manufacturing_lead_time_days,
            sp.shipping_lead_time_days,
            sp.current_expected_lead_time_days as current_lead_time,
            
            sp.delay_risk_level,
            sp.current_risk_notes,
            sp.on_time_delivery_pct,
            sp.quality_rejection_pct,
            sp.capacity_status
        FROM supplier_performance sp
        INNER JOIN suppliers s ON s.supplier_id = sp.supplier_id
        WHERE sp.item_id = ?
        ORDER BY 
            CASE sp.delay_risk_level 
                WHEN 'Low' THEN 1 
                WHEN 'Medium' THEN 2 
                WHEN 'High' THEN 3 
                ELSE 4 
            END,
            sp.on_time_delivery_pct DESC
    """, (item_id,))
    
    performance_rows = cursor.fetchall()
    
    suppliers = []
    
    for perf_row in performance_rows:
        supplier = dict(perf_row)
        
        # Step 2: Try to get pricing for this supplier + item (separate query for reliability)
        cursor.execute("""
            SELECT 
                contracted_price_usd as contracted_price,
                spot_price_usd as spot_price,
                moq,
                volume_discount_pct,
                volume_threshold
            FROM supplier_item_pricing
            WHERE supplier_id = ? AND item_id = ? AND is_active = 1
            LIMIT 1
        """, (supplier['supplier_id'], item_id))
        
        pricing_row = cursor.fetchone()
        
        if pricing_row:
            supplier.update(dict(pricing_row))
        else:
            supplier['contracted_price'] = "Not available"
            supplier['spot_price'] = "Not available"
            supplier['moq'] = 1
            supplier['volume_discount_pct'] = 0
            supplier['volume_threshold'] = 0
        
        # Step 3: Get item-level pricing thresholds
        cursor.execute("""
            SELECT 
                unit_cost_usd as item_unit_cost,
                spot_price_usd as item_spot_price_threshold,
                lead_time_days as item_standard_lead_time_days
            FROM items
            WHERE item_id = ?
            LIMIT 1
        """, (item_id,))
        
        item_row = cursor.fetchone()
        if item_row:
            supplier.update(dict(item_row))
        else:
            supplier['item_unit_cost'] = "Not available"
            supplier['item_spot_price_threshold'] = "Not available"
            supplier['item_standard_lead_time_days'] = "Not available"
        
        # Normalize field name for consistency downstream (use risk_level)
        supplier['risk_level'] = supplier.get('delay_risk_level')
        
        suppliers.append(supplier)
    
    conn.close()
    return suppliers


def get_supplier_details(supplier_id: str) -> Optional[Dict[str, Any]]:
    """Get detailed information about a specific supplier."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT supplier_id, name, country, segment, city_state, 
               contact_email, avg_lead_time_days, payment_terms
        FROM suppliers 
        WHERE supplier_id = ?
    """, (supplier_id,))
    
    row = cursor.fetchone()
    conn.close()
    
    return dict(row) if row else None


def get_supplier_performance(supplier_id: str, item_id: str) -> Optional[Dict[str, Any]]:
    """Get the latest performance metrics for a supplier-item combination."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT 
            supplier_id,
            item_id,
            period,
            on_time_delivery_pct,
            quality_rejection_pct,
            recent_issues,
            capacity_status,
            current_expected_lead_time_days,
            delay_risk_level,
            current_risk_notes,
            updated_at
        FROM supplier_performance 
        WHERE supplier_id = ? AND item_id = ?
        ORDER BY updated_at DESC
        LIMIT 1
    """, (supplier_id, item_id))
    
    row = cursor.fetchone()
    conn.close()
    
    return dict(row) if row else None


# ============================================================
# PROCUREMENT EXECUTION TOOLS
# ============================================================

def create_purchase_requisition(
    product_id: str,
    supplier_id: str,
    quantity: float,
    required_date: str,
    notes: Optional[str] = None
) -> Dict[str, Any]:
    """
    Create a Purchase Requisition (PR) in the system.
    
    In production, this would call the ERP API to create a real PR.
    Currently, this is a simulation that returns a PR number.
    
    Returns:
        Dictionary with PR details including generated PR number.
    """
    pr_number = f"PR-{datetime.now().strftime('%Y%m%d%H%M%S')}"
    
    # In a real system, we would insert into a purchase_requisitions table
    # and trigger workflow. For now, we simulate success.
    
    result = {
        "status": "success",
        "pr_number": pr_number,
        "product_id": product_id,
        "supplier_id": supplier_id,
        "quantity": quantity,
        "required_date": required_date,
        "notes": notes,
        "created_at": datetime.now().isoformat(),
        "message": f"Purchase Requisition {pr_number} created successfully (simulated)"
    }
    
    return result


def create_purchase_order(
    pr_number: str,
    supplier_id: str,
    product_id: str,
    quantity: float,
    unit_price: Optional[float] = None,
    notes: Optional[str] = None
) -> Dict[str, Any]:
    """
    Create a Purchase Order (PO) from an approved Purchase Requisition.
    
    In production, this would call the ERP to convert PR → PO.
    """
    po_number = f"PO-{datetime.now().strftime('%Y%m%d%H%M%S')}"
    
    result = {
        "status": "success",
        "po_number": po_number,
        "pr_number": pr_number,
        "supplier_id": supplier_id,
        "product_id": product_id,
        "quantity": quantity,
        "unit_price": unit_price,
        "total_value": (unit_price * quantity) if unit_price else None,
        "created_at": datetime.now().isoformat(),
        "message": f"Purchase Order {po_number} created successfully from {pr_number} (simulated)"
    }
    
    return result


# ============================================================
# HELPER / UTILITY TOOLS
# ============================================================

def calculate_net_requirement(
    demand_forecast: float,
    current_stock: float,
    safety_stock: float,
    on_order_qty: float = 0
) -> float:
    """
    Calculate the net requirement for procurement.
    
    Formula: Net Requirement = Demand + Safety Stock - Current Stock - On Order
    """
    net_req = demand_forecast + safety_stock - current_stock - on_order_qty
    return max(0, round(net_req, 2))


# ============================================================
# MAIN (for quick testing)
# ============================================================

if __name__ == "__main__":
    print("=== Testing Agent Tools (Item-level + BOM-aware) ===\n")
    
    test_product = "SUP-001"
    
    print(f"1. Get BOM for product: {test_product}")
    bom_items = get_bom_items(test_product)
    print(f"   Found {len(bom_items)} items in BOM")
    for item in bom_items[:3]:
        print(f"   - {item['item_id']}: qty={item['quantity']}, safety_stock={item.get('safety_stock')}")
    
    if bom_items:
        first_item = bom_items[0]['item_id']
        print(f"\n2. Inventory status for first item ({first_item}):")
        inv = get_inventory_status(first_item)
        print(inv)
        
        print(f"\n3. Supplier options for item ({first_item}):")
        suppliers = get_supplier_options(first_item)
        print(f"   Found {len(suppliers)} suppliers")
    else:
        print("\n   (No BOM data found - tables may be empty)")