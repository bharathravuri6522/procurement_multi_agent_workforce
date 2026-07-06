"""
Supplier Intelligence Agent

This agent is responsible for:
1. Taking the output from Demand & Inventory Analyst
2. For each item that needs procurement, fetching supplier options
3. Analyzing and recommending the best supplier(s) per item
4. Providing clear reasoning for each recommendation

Focus areas: Risk, Lead Time, On-time Performance, Quality, Capacity, MOQ
"""

from typing import Dict, Any, List, Optional
from datetime import datetime

from agent_tools import get_supplier_options, get_supplier_details


def calculate_supplier_costs(supplier: dict, gross_requirement: float) -> dict:
    """
    Pre-calculates realistic ordering costs considering:
    - MOQ as batch size
    - Bulk discount on Contracted Price only (if volume_threshold is met)
    """
    contracted = supplier.get('contracted_price', 0) or 0
    spot = supplier.get('spot_price', 0) or 0
    moq = supplier.get('moq', 1) or 1
    volume_discount = supplier.get('volume_discount_pct', 0) or 0
    volume_threshold = supplier.get('volume_threshold', 0) or 0

    # Recommended order quantity using MOQ as batch size
    if moq > 0:
        recommended_qty = ((gross_requirement + moq - 1) // moq) * moq
    else:
        recommended_qty = gross_requirement

    # Contracted Price with bulk discount (if applicable)
    if recommended_qty >= volume_threshold and volume_discount > 0:
        discounted_price = contracted * (1 - volume_discount / 100)
        total_contracted = recommended_qty * discounted_price
        bulk_discount_applied = True
        bulk_discount_amount = recommended_qty * contracted * (volume_discount / 100)
    else:
        discounted_price = contracted
        total_contracted = recommended_qty * contracted
        bulk_discount_applied = False
        bulk_discount_amount = 0

    # Spot Price (no discount)
    total_spot = recommended_qty * spot

    # Overage calculations
    overage_qty = max(0, recommended_qty - gross_requirement)
    overage_cost = overage_qty * discounted_price

    # Effective unit price
    effective_unit_contracted = total_contracted / recommended_qty if recommended_qty > 0 else 0

    return {
        "recommended_order_quantity": recommended_qty,
        "total_cost_contracted": round(total_contracted, 2),
        "total_cost_spot": round(total_spot, 2),
        "effective_unit_price_contracted": round(effective_unit_contracted, 2),
        "overage_quantity": overage_qty,
        "overage_cost_contracted": round(overage_cost, 2),
        "bulk_discount_applied": bulk_discount_applied,
        "bulk_discount_amount": round(bulk_discount_amount, 2)
    }


def recommend_suppliers(analysis_result: Dict[str, Any]) -> Dict[str, Any]:
    """
    Supplier Intelligence Node (Data Collector Only)
    
    - Collects all suppliers for each item that needs procurement
    - Returns raw data with performance + pricing + item thresholds
    - Does NOT do any scoring or recommendation
    - This data will be passed to the Reasoning Node
    """
    output = {
        "product_id": analysis_result.get("product_id"),
        "analysis_timestamp": datetime.now().isoformat(),
        "items_analyzed": [],
        "summary": {}
    }
    
    item_analysis = analysis_result.get("item_analysis", [])
    items_needing_procurement = [item for item in item_analysis if item.get("needs_procurement")]
    
    if not items_needing_procurement:
        output["summary"] = {"message": "No items require procurement."}
        return output
    
    for item in items_needing_procurement:
        item_id = item["item_id"]
        gross_req = item.get("gross_requirement", item.get("net_requirement", 0))
        
        suppliers = get_supplier_options(item_id)
        
        item_result = {
            "item_id": item_id,
            "item_name": item.get("item_name"),
            "gross_requirement": gross_req,
            "suppliers": suppliers,
            "item_unit_cost": suppliers[0].get("item_unit_cost") if suppliers else None,
            "item_spot_price_threshold": suppliers[0].get("item_spot_price_threshold") if suppliers else None
        }
        
        output["items_analyzed"].append(item_result)
    
    output["summary"] = {
        "total_items_needing_procurement": len(items_needing_procurement),
        "message": f"Collected supplier data for {len(output['items_analyzed'])} items."
    }
    
    return output



# ============================================================
# Quick test
# ============================================================

if __name__ == "__main__":
    from demand_inventory_analyst import analyze_demand_and_inventory
    
    print("=== Supplier Intelligence Node - Test (with Cost Calculations) ===\n")
    
    demand_analysis = analyze_demand_and_inventory(
        product_id="RS-240",
        demand_forecast=80,
        required_date="2026-07-15"
    )
    
    supplier_output = recommend_suppliers(demand_analysis)
    
    print(f"Product: {supplier_output['product_id']}")
    print(f"Items needing procurement: {supplier_output['summary']['total_items_needing_procurement']}")
    
    for item_data in supplier_output["items_analyzed"]:
        print(f"\n{'='*70}")
        print(f"Item: {item_data['item_id']} | {item_data['item_name']}")
        print(f"Gross Requirement: {item_data['gross_requirement']}")
        
        print(f"\n--- Suppliers Available ({len(item_data['suppliers'])} total) ---")
        
        for sup in item_data['suppliers']:
            costs = calculate_supplier_costs(sup, item_data['gross_requirement'])
            
            print(f"\n  Supplier: {sup.get('supplier_name')} | Risk: {sup.get('risk_level', 'N/A')}")
            print(f"    Original → Contracted: {sup.get('contracted_price')} | Spot: {sup.get('spot_price')} | MOQ: {sup.get('moq')}")
            print(f"    Calculated → Order Qty: {costs['recommended_order_quantity']} | "
                  f"Total Cost (Contracted): {costs['total_cost_contracted']} | "
                  f"Total Cost (Spot): {costs['total_cost_spot']}")
            print(f"                 Effective Unit Price: {costs['effective_unit_price_contracted']} | "
                  f"Overage: {costs['overage_quantity']} | Bulk Discount: {costs['bulk_discount_applied']}")
        
        print(f"\nItem Thresholds → Unit Cost: {item_data.get('item_unit_cost', 'N/A')} | "
              f"Spot Price Threshold: {item_data.get('item_spot_price_threshold', 'N/A')}")
    
    # ============================================================
    # Use Supervisor as single entry point (recommended)
    # ============================================================
    from supervisor import run_procurement_workflow
    import json
    
    final_state = run_procurement_workflow(
        product_id="RS-240",
        demand_forecast=80,
        required_date="2026-07-15"
    )
    
    print("\n\n=== SUPERVISOR WORKFLOW RESULT ===\n")
    print(json.dumps({
        "contracted_reasoning": final_state.get("contracted_reasoning"),
        "spot_reasoning": final_state.get("spot_reasoning"),
        "reasoning_trace": final_state.get("reasoning_trace", [])
    }, indent=2, default=str))