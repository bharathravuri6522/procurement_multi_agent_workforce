"""
Demand & Inventory Analyst Agent

This agent is responsible for:
1. Taking a product request
2. Exploding the BOM to get required items
3. Checking inventory status for each item
4. Calculating net procurement requirement per item
5. Returning structured analysis

This follows the Item-level + BOM-aware approach.
"""

from typing import Dict, Any, List, Optional
from datetime import datetime

from agent_tools import (
    get_product_details,
    get_bom_items,
    get_inventory_status,
    calculate_net_requirement
)


def analyze_demand_and_inventory(
    product_id: str,
    demand_forecast: Optional[float] = None,
    required_date: Optional[str] = None
) -> Dict[str, Any]:
    """
    Main function for the Demand & Inventory Analyst agent.
    
    Performs full analysis at ITEM level after exploding the BOM.
    
    Args:
        product_id: The product the user wants to procure
        demand_forecast: Optional forecasted demand (if not provided, will try to infer)
        required_date: Target date for procurement (ISO format)
    
    Returns:
        Structured analysis containing:
        - product info
        - list of items with inventory status and net requirement
        - summary of total items requiring procurement
    """
    
    analysis = {
        "product_id": product_id,
        "analysis_timestamp": datetime.now().isoformat(),
        "required_date": required_date,
        "product_details": None,
        "bom_items": [],
        "item_analysis": [],
        "items_requiring_procurement": [],
        "summary": {}
    }
    
    # Step 1: Get product details
    product_info = get_product_details(product_id)
    analysis["product_details"] = product_info
    
    if not product_info:
        analysis["error"] = f"Product {product_id} not found in database."
        return analysis
    
    # Step 2: Explode BOM to get list of items
    bom_items = get_bom_items(product_id)
    analysis["bom_items"] = bom_items
    
    if not bom_items:
        analysis["warning"] = (
            f"No BOM found for product {product_id}. "
            "Treating product_id as a single item."
        )
        # Fallback: treat the product itself as an item
        bom_items = [{
            "item_id": product_id,
            "item_name": product_info.get("name", product_id),
            "quantity": 1.0,
            "unit": "EA",
            "buffer_pct": 0.0,
            "safety_stock": 0
        }]
    
    # Step 3 & 4: Analyze each item
    total_net_requirement = 0.0
    items_needing_buy = []
    
    for bom_item in bom_items:
        item_id = bom_item["item_id"]
        
        # Get current inventory status
        inv_status = get_inventory_status(item_id)
        
        if not inv_status:
            inv_status = {
                "item_id": item_id,
                "current_stock": 0,
                "reserved_qty": 0,
                "on_order_qty": 0,
                "available_qty": 0,
                "safety_stock": bom_item.get("safety_stock", 0),
                "lead_time_days": bom_item.get("lead_time_days", 0)
            }
        
        # Calculate required quantity for this item (BOM qty * demand + buffer/error rate)
        bom_qty = bom_item.get("quantity", 1.0)
        buffer_pct = bom_item.get("buffer_pct", 0) or 0.0   # e.g. 0.025 = 2.5%
        
        # Base requirement = demand × BOM quantity
        if demand_forecast is None:
            base_requirement = bom_qty
        else:
            base_requirement = demand_forecast * bom_qty
        
        # Add buffer for rejection / defect / error rate
        buffer_requirement = base_requirement * buffer_pct
        gross_requirement = base_requirement + buffer_requirement   # Final demand after buffer
        
        # Ensure gross_requirement is always a whole number (ceiling)
        import math
        gross_requirement = math.ceil(gross_requirement)
        
        safety_stock = inv_status.get("safety_stock", 0) or 0
        current_stock = inv_status.get("current_stock", 0) or 0
        on_order = inv_status.get("on_order_qty", 0) or 0
        
        # Net Requirement = Gross Requirement (after buffer) + Safety Stock - Available Stock - On Order
        net_req = calculate_net_requirement(
            demand_forecast=gross_requirement,
            current_stock=current_stock,
            safety_stock=safety_stock,
            on_order_qty=on_order
        )
        
        item_result = {
            "item_id": item_id,
            "item_name": bom_item.get("item_name", item_id),
            "bom_quantity": bom_qty,
            "base_requirement": base_requirement,
            "buffer_pct": buffer_pct,
            "buffer_requirement": buffer_requirement,
            "gross_requirement": gross_requirement,
            "inventory_status": inv_status,
            "net_requirement": net_req,
            "needs_procurement": net_req > 0
        }
        
        analysis["item_analysis"].append(item_result)
        
        if net_req > 0:
            items_needing_buy.append(item_result)
            total_net_requirement += net_req
    
    analysis["items_requiring_procurement"] = items_needing_buy
    
    # Summary
    analysis["summary"] = {
        "total_items_in_bom": len(bom_items),
        "items_requiring_procurement": len(items_needing_buy),
        "total_net_requirement_across_items": round(total_net_requirement, 2),
        "has_sufficient_inventory": len(items_needing_buy) == 0
    }
    
    return analysis


# ============================================================
# Helper function for quick testing
# ============================================================

if __name__ == "__main__":
    print("=== Demand & Inventory Analyst - Test (via Supervisor) ===\n")
    
    from supervisor import run_procurement_workflow
    
    final_state = run_procurement_workflow(
        product_id="RS-240",
        demand_forecast=80,
        required_date="2026-07-15"
    )
    
    print("Workflow executed via Supervisor.")
    print("Demand Analysis completed and stored in state.")
    print("Full result available in final_state['demand_analysis']")
    print(f"  Current Stock: {item['inventory_status'].get('current_stock', 'N/A')}")
    print(f"  On Order: {item['inventory_status'].get('on_order_qty', 'N/A')}")