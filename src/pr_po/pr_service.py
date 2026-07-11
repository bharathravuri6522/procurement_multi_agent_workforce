from __future__ import annotations
import json, uuid
from datetime import date, datetime, timedelta
from pr_po.db import get_connection

class PRServiceError(ValueError): pass
def _new_pr_id(): return f"PR-{datetime.now().year}-{uuid.uuid4().hex[:8].upper()}"

def get_existing_pr_for_run(session_id, run_id):
    with get_connection() as conn:
        row=conn.execute("""SELECT * FROM purchase_requisitions WHERE source_session_id=? AND source_run_id=? ORDER BY created_at DESC LIMIT 1""",(session_id,run_id)).fetchone()
    return dict(row) if row else None

def build_pr_preview(session_id,run_id,requester_user_id,department,product_id,demand_forecast,required_date,effective_decision):
    plan=effective_decision.get("effective_plan") or []
    metrics=effective_decision.get("effective_metrics") or {}
    human_decision=effective_decision.get("human_decision") or {}
    if not plan: raise PRServiceError("The effective procurement plan is empty.")
    lines=[]
    for item in plan:
        qty=float(item.get("order_quantity") or 0)
        total=float(item.get("total_cost") or 0)
        unit_cost=total/qty if qty else 0
        lead=int(item.get("lead_time_days") or 0)
        lines.append({
            "item_id":item.get("item_id"),"item_name":item.get("item_name"),
            "supplier_id":item.get("selected_supplier_id"),"supplier_name":item.get("selected_supplier_name"),
            "procurement_strategy":item.get("strategy"),"quantity":qty,"unit":item.get("unit") or "EA",
            "estimated_unit_cost_usd":round(unit_cost,6),"line_total_usd":round(total,2),
            "lead_time_days":lead,"estimated_delivery_date":(date.today()+timedelta(days=lead)).isoformat(),
            "reasoning_snapshot":item.get("reasoning")
        })
    return {
        "session_id":session_id,"run_id":run_id,"requester_user_id":requester_user_id,
        "department":department,"product_id":product_id,"demand_forecast":demand_forecast,
        "required_date":required_date,"effective_strategy":human_decision.get("final_strategy"),
        "total_estimated_usd":round(float(metrics.get("total_procurement_cost") or 0),2),
        "critical_path_days":metrics.get("critical_path_days"),"lines":lines
    }

def create_purchase_requisition(preview):
    existing=get_existing_pr_for_run(preview["session_id"],preview["run_id"])
    if existing: return existing
    pr_id=_new_pr_id()
    with get_connection() as conn:
        conn.execute("""
            INSERT INTO purchase_requisitions(
                pr_id,requested_by,department,status,total_estimated_usd,required_date,
                source_session_id,source_run_id,product_id,demand_forecast,effective_strategy
            ) VALUES (?,?,?,'Pending Approval',?,?,?,?,?,?,?)
        """,(pr_id,preview["requester_user_id"],preview["department"],preview["total_estimated_usd"],
             preview["required_date"],preview["session_id"],preview["run_id"],preview["product_id"],
             preview["demand_forecast"],preview["effective_strategy"]))
        for line in preview["lines"]:
            conn.execute("""
                INSERT INTO pr_lines(
                    pr_id,item_id,quantity,unit,estimated_unit_cost_usd,notes,supplier_id,supplier_name,
                    procurement_strategy,lead_time_days,estimated_delivery_date,line_total_usd,reasoning_snapshot
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,(pr_id,line["item_id"],line["quantity"],line["unit"],line["estimated_unit_cost_usd"],
                 line["item_name"],line["supplier_id"],line["supplier_name"],line["procurement_strategy"],
                 line["lead_time_days"],line["estimated_delivery_date"],line["line_total_usd"],line["reasoning_snapshot"]))
        conn.execute("""INSERT INTO pr_execution_log(pr_id,action,actor_user_id,details_json) VALUES (?,'pr_created',?,?)""",
                     (pr_id,preview["requester_user_id"],json.dumps({"session_id":preview["session_id"],"run_id":preview["run_id"],"line_count":len(preview["lines"])})))
        conn.commit()
    return get_purchase_requisition(pr_id)

def list_purchase_requisitions(status=None):
    query="""SELECT pr.*,u.name AS requester_name FROM purchase_requisitions pr LEFT JOIN users u ON u.user_id=pr.requested_by"""
    params=[]
    if status and status!="All":
        query+=" WHERE pr.status=?"; params.append(status)
    query+=" ORDER BY pr.created_at DESC"
    with get_connection() as conn: rows=conn.execute(query,params).fetchall()
    return [dict(r) for r in rows]

def get_purchase_requisition(pr_id):
    with get_connection() as conn:
        header=conn.execute("""
            SELECT pr.*,req.name AS requester_name,app.name AS approver_name
            FROM purchase_requisitions pr
            LEFT JOIN users req ON req.user_id=pr.requested_by
            LEFT JOIN users app ON app.user_id=pr.approved_by
            WHERE pr.pr_id=?
        """,(pr_id,)).fetchone()
        if not header: raise PRServiceError("Purchase Requisition was not found.")
        lines=conn.execute("SELECT * FROM pr_lines WHERE pr_id=? ORDER BY pr_line_id",(pr_id,)).fetchall()
    result=dict(header); result["lines"]=[dict(r) for r in lines]; return result
