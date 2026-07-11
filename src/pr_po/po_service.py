from __future__ import annotations
import json, uuid
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pr_po.db import get_connection
from pr_po.execution_supervisor import determine_next_action
from pr_po.pr_service import get_purchase_requisition

class POServiceError(ValueError): pass
def _utc_now(): return datetime.now(timezone.utc).isoformat()
def _new_po_id(): return f"PO-{datetime.now().year}-{uuid.uuid4().hex[:8].upper()}"

def list_purchase_orders_for_pr(pr_id):
    with get_connection() as conn:
        rows=conn.execute("""
            SELECT po.*,s.name AS supplier_name FROM purchase_orders po
            LEFT JOIN suppliers s ON s.supplier_id=po.supplier_id
            WHERE po.pr_id=? ORDER BY po.created_at
        """,(pr_id,)).fetchall()
    return [dict(r) for r in rows]

def generate_purchase_orders(pr_id):
    pr=get_purchase_requisition(pr_id)
    existing=list_purchase_orders_for_pr(pr_id)
    decision=determine_next_action(pr_id,pr["status"],bool(existing))
    if decision.next_action=="completed": return existing
    if decision.next_action!="generate_purchase_orders": raise POServiceError(decision.reason)
    grouped=defaultdict(list)
    for line in pr["lines"]:
        if not line.get("supplier_id"): raise POServiceError(f"PR line {line['pr_line_id']} has no supplier_id.")
        grouped[line["supplier_id"]].append(line)
    created=[]
    with get_connection() as conn:
        for supplier_id, lines in grouped.items():
            po_id=_new_po_id()
            total=round(sum(float(x.get("line_total_usd") or 0) for x in lines),2)
            max_lead=max(int(x.get("lead_time_days") or 0) for x in lines)
            expected=(date.today()+timedelta(days=max_lead)).isoformat()
            conn.execute("""INSERT INTO purchase_orders(po_id,supplier_id,pr_id,status,total_usd,expected_delivery,created_by_agent) VALUES (?,?,?,'Created',?,?,1)""",
                         (po_id,supplier_id,pr_id,total,expected))
            for line in lines:
                conn.execute("""INSERT INTO po_lines(po_id,item_id,quantity,unit_cost_usd,line_total_usd) VALUES (?,?,?,?,?)""",
                             (po_id,line["item_id"],line["quantity"],line["estimated_unit_cost_usd"],line["line_total_usd"]))
            created.append(po_id)
        conn.execute("""UPDATE purchase_requisitions SET status='PO Created',po_created_at=? WHERE pr_id=?""",(_utc_now(),pr_id))
        conn.execute("""INSERT INTO pr_execution_log(pr_id,action,details_json) VALUES (?,'purchase_orders_created',?)""",
                     (pr_id,json.dumps({"po_ids":created,"supplier_count":len(grouped)})))
        conn.commit()
    return list_purchase_orders_for_pr(pr_id)
