# PrecisionForge Technologies Inc.
## Database Schema Design – Version 1.0

**Project:** ForgeForce Procurement Agents – Multi-Agent Digital Workforce  
**Date:** June 29, 2026  
**Version:** 1.0  
**Status:** Draft for Review

---

### Purpose of This Document

This document defines the complete database schema for the mock ERP system used in this project. It translates the business context and product/BOM information into concrete tables, columns, and relationships.

The schema is designed to support:
- Product and BOM management
- Supplier intelligence (performance, issues, pricing, capacity)
- Inventory visibility
- Purchase Requisition (PR) creation and approval workflow
- Purchase Order (PO) creation
- Realistic multi-factor reasoning by the Agent Force

The schema balances **realism** with **simplicity** so it can be fully implemented within the 3-day sprint.

---

### Design Principles

- Use **SQLite** as the database (simple, file-based, sufficient for demo, easy to inspect).
- Prefer **normalized design** where it adds clarity (especially for BOM and supplier performance).
- Keep number of tables reasonable (target: 8–10 core tables).
- Include fields that enable **intelligent agent reasoning** (performance history, recent issues, capacity signals, contracted vs spot pricing).
- Support **lightweight RBAC + approval workflow** simulation.
- Make it easy to query using Python (pandas + sqlite3 or SQLAlchemy).

---

### Core Tables Overview

| Table Name                  | Purpose                                      | Key Relationships                  | Expected Rows (Demo) |
|-----------------------------|----------------------------------------------|------------------------------------|----------------------|
| `products`                  | Master list of manufactured products         | —                                  | 6                    |
| `bom_lines`                 | Bill of Materials lines                      | → `products`, → `items`            | ~40–50               |
| `items`                     | Master data for all procured items           | —                                  | 35–45                |
| `suppliers`                 | Supplier master (20 suppliers)               | —                                  | 20                   |
| `supplier_performance`      | Performance metrics + recent issues          | → `suppliers`, → `items` (optional) | 150–200            |
| `inventory`                 | Current stock levels                         | → `items`                          | 35–45                |
| `purchase_requisitions`     | PR header                                    | → `users` (requester)              | 30–50 (demo)         |
| `pr_lines`                  | PR line items                                | → `purchase_requisitions`, → `items` | 80–120            |
| `purchase_orders`           | PO header                                    | → `suppliers`, → `purchase_requisitions` | 20–40         |
| `po_lines`                  | PO line items                                | → `purchase_orders`, → `items`     | 60–100               |
| `work_orders`               | Internal demand / work orders                | → `products`                       | 15–25                |
| `supplier_item_pricing`     | Contracted pricing per supplier-item         | → `suppliers`, → `items`           | 60–80                |
| `activity_log`              | Audit trail of actions & reasoning           | —                                  | 100+                 |
| `users`                     | Requesters / Approvers (for RBAC)            | —                                  | 8–10                 |

---

### Detailed Table Definitions

#### 1. `products`

| Column              | Type      | Notes                                      |
|---------------------|-----------|--------------------------------------------|
| `product_id`        | TEXT      | Primary Key (e.g., "RS-240")               |
| `name`              | TEXT      | e.g., "Precision Rotor Shaft"              |
| `category`          | TEXT      | One of 6 categories                        |
| `description`       | TEXT      | Short description                          |
| `typical_order_qty` | INTEGER   | Typical batch size                         |
| `created_at`        | TIMESTAMP | —                                          |

#### 2. `bom_lines`

| Column           | Type      | Notes                                           |
|------------------|-----------|-------------------------------------------------|
| `bom_line_id`    | INTEGER   | Primary Key (auto-increment)                    |
| `product_id`     | TEXT      | Foreign Key → `products.product_id`             |
| `item_id`        | TEXT      | Foreign Key → `items.item_id`                   |
| `quantity`       | REAL      | Quantity required per unit of product           |
| `unit`           | TEXT      | pcs, kg, g, set, lot, ml                        |
| `buffer_pct`     | REAL      | Specific buffer % for this line (default 0.03)  |
| `notes`          | TEXT      | e.g., "Critical – long lead time"               |

#### 3. `items` (Procured Items Master)

| Column              | Type      | Notes                                              |
|---------------------|-----------|----------------------------------------------------|
| `item_id`           | TEXT      | Primary Key (e.g., "BR-6205", "RM-4140")           |
| `name`              | TEXT      | e.g., "Deep Groove Ball Bearing 6205"              |
| `category`          | TEXT      | Bearings, Raw Material, Fasteners, Castings, etc.  |
| `unit`              | TEXT      | pcs, kg, set                                       |
| `unit_cost_usd`     | REAL      | Average / standard cost                            |
| `is_critical`       | BOOLEAN   | True for bearings, seals, critical castings        |
| `lead_time_days`    | INTEGER   | Average lead time                                  |
| `safety_stock`      | INTEGER   | Minimum stock level                                |
| `created_at`        | TIMESTAMP | —                                                  |

#### 4. `suppliers`

| Column                | Type      | Notes                                              |
|-----------------------|-----------|----------------------------------------------------|
| `supplier_id`         | TEXT      | Primary Key (e.g., "SUP-001")                      |
| `name`                | TEXT      | Company name                                       |
| `country`             | TEXT      | USA, Mexico, China, Germany, etc.                  |
| `segment`             | TEXT      | Premium, US_Regional, Mexico_Nearshore, Asia_Cost  |
| `city_state`          | TEXT      | e.g., "Indianapolis, IN" or "Monterrey, Mexico"    |
| `contact_email`       | TEXT      | —                                                  |
| `avg_lead_time_days`  | INTEGER   | —                                                  |
| `payment_terms`       | TEXT      | Net 30, Net 45, etc.                               |
| `created_at`          | TIMESTAMP | —                                                  |

#### 5. `supplier_performance`

This is one of the **most important tables** for intelligent agent reasoning.

| Column                    | Type      | Notes                                                              |
|---------------------------|-----------|--------------------------------------------------------------------|
| `performance_id`          | INTEGER   | Primary Key                                                        |
| `supplier_id`             | TEXT      | Foreign Key → `suppliers.supplier_id`                              |
| `item_id`                 | TEXT      | Foreign Key → `items.item_id` (optional – can be category level)   |
| `period`                  | TEXT      | e.g., "2025-Q4", "Last_6_Months", "Recent"                         |
| `on_time_delivery_pct`    | REAL      | e.g., 94.5                                                           |
| `quality_rejection_pct`   | REAL      | e.g., 1.8                                                            |
| `recent_issues`                 | TEXT      | Free text or structured notes (e.g., "Late 3 times in Q2 on bearings") |
| `capacity_status`               | TEXT      | Normal / Constrained / Available                                   |
| `current_expected_lead_time_days` | INTEGER | Current expected lead time (can differ from historical average)    |
| `delay_risk_level`              | TEXT      | Low / Medium / High                                                |
| `current_risk_notes`            | TEXT      | e.g., "Port congestion in Shanghai + vessel delays. Expected +8-12 days" |
| `updated_at`                    | TIMESTAMP | —                                                                  |

#### 6. `inventory`

| Column           | Type      | Notes                                      |
|------------------|-----------|--------------------------------------------|
| `inventory_id`   | INTEGER   | Primary Key                                |
| `item_id`        | TEXT      | Foreign Key → `items.item_id`              |
| `current_stock`  | INTEGER   | Current available quantity                 |
| `reserved_qty`   | INTEGER   | Already allocated to open work orders      |
| `on_order_qty`   | INTEGER   | Quantity already ordered but not yet received |
| `last_updated`   | TIMESTAMP | —                                          |

#### 7. `users` (for RBAC simulation)

| Column         | Type      | Notes                                      |
|----------------|-----------|--------------------------------------------|
| `user_id`      | TEXT      | Primary Key                                |
| `name`         | TEXT      | e.g., "Sarah Patel"                        |
| `role`         | TEXT      | PPC_Lead, Maintenance_Lead, NPD_Engineer, Procurement_Manager, Plant_Head |
| `department`   | TEXT      | Production, Maintenance, NPD, Quality      |
| `can_approve_up_to_usd` | REAL | Approval limit                             |

#### 8. `purchase_requisitions` (PR Header)

| Column                | Type      | Notes                                              |
|-----------------------|-----------|----------------------------------------------------|
| `pr_id`               | TEXT      | Primary Key (e.g., "PR-2026-0042")                 |
| `requested_by`        | TEXT      | Foreign Key → `users.user_id`                      |
| `department`          | TEXT      | —                                                  |
| `status`              | TEXT      | Draft, Submitted, Approved, Rejected               |
| `total_estimated_usd` | REAL      | —                                                  |
| `required_date`       | DATE      | Needed by date                                   |
| `created_at`          | TIMESTAMP | —                                                  |
| `approved_by`         | TEXT      | Foreign Key → `users.user_id` (nullable)           |
| `approved_at`         | TIMESTAMP | Nullable                                           |

#### 9. `pr_lines`

| Column           | Type      | Notes                                      |
|------------------|-----------|--------------------------------------------|
| `pr_line_id`     | INTEGER   | Primary Key                                |
| `pr_id`          | TEXT      | Foreign Key → `purchase_requisitions.pr_id`|
| `item_id`        | TEXT      | Foreign Key → `items.item_id`              |
| `quantity`       | INTEGER   | Requested quantity                         |
| `unit`           | TEXT      | —                                          |
| `estimated_unit_cost_usd` | REAL | —                                    |
| `notes`          | TEXT      | —                                          |

#### 10. `purchase_orders` (PO Header)

| Column             | Type      | Notes                                              |
|--------------------|-----------|----------------------------------------------------|
| `po_id`            | TEXT      | Primary Key (e.g., "PO-2026-0087")                 |
| `supplier_id`      | TEXT      | Foreign Key → `suppliers.supplier_id`              |
| `pr_id`            | TEXT      | Foreign Key → `purchase_requisitions.pr_id` (nullable) |
| `status`           | TEXT      | Created, Sent, Acknowledged, Received, Closed      |
| `total_usd`        | REAL      | —                                                  |
| `expected_delivery`| DATE      | —                                                  |
| `created_by_agent` | BOOLEAN   | True if created by Agent Force                     |
| `created_at`       | TIMESTAMP | —                                                  |

#### 11. `po_lines`

| Column           | Type      | Notes                                      |
|------------------|-----------|--------------------------------------------|
| `po_line_id`     | INTEGER   | Primary Key                                |
| `po_id`          | TEXT      | Foreign Key → `purchase_orders.po_id`      |
| `item_id`        | TEXT      | Foreign Key → `items.item_id`              |
| `quantity`       | INTEGER   | Ordered quantity                           |
| `unit_cost_usd`  | REAL      | Agreed unit price                          |
| `line_total_usd` | REAL      | quantity × unit_cost_usd                   |

#### 12. `work_orders` (New)

| Column                | Type      | Notes                                              |
|-----------------------|-----------|----------------------------------------------------|
| `work_order_id`       | TEXT      | Primary Key                                        |
| `product_id`          | TEXT      | Foreign Key → `products.product_id`                |
| `quantity`            | INTEGER   | Required quantity                                  |
| `required_date`       | DATE      | When the finished goods are needed                 |
| `status`              | TEXT      | Planned, Released, Completed                       |
| `created_at`          | TIMESTAMP | —                                                  |

#### 13. `supplier_item_pricing` (New - Lightweight)

| Column                | Type      | Notes                                                              |
|-----------------------|-----------|--------------------------------------------------------------------|
| `pricing_id`          | INTEGER   | Primary Key                                                        |
| `supplier_id`         | TEXT      | Foreign Key → `suppliers.supplier_id`                              |
| `item_id`             | TEXT      | Foreign Key → `items.item_id`                                      |
| `contracted_price_usd`| REAL      | Price as per contract (if exists)                                  |
| `valid_from`          | DATE      | Contract validity start                                            |
| `valid_to`            | DATE      | Contract validity end                                              |
| `is_active`           | BOOLEAN   | Whether this contracted price is currently active                  |

#### 14. `activity_log` (New - For Observability)

| Column           | Type      | Notes                                                              |
|------------------|-----------|--------------------------------------------------------------------|
| `log_id`         | INTEGER   | Primary Key                                                        |
| `timestamp`      | TIMESTAMP | When the action happened                                           |
| `actor`          | TEXT      | "Agent:SupplierIntelligence", "User:Sarah Patel", "System"         |
| `action`         | TEXT      | e.g., "Created PR", "Recommended Supplier X", "Approved PO"        |
| `entity_type`    | TEXT      | "PR", "PO", "Inventory", etc.                                      |
| `entity_id`      | TEXT      | ID of the affected record                                          |
| `details`        | TEXT      | JSON or text explaining what happened and why                      |

---

### Key Relationships Summary

- `bom_lines` connects `products` ←→ `items`
- `pr_lines` and `po_lines` connect to `items`
- `purchase_requisitions` links to `users` (requester + approver)
- `purchase_orders` links to `suppliers` and optionally to `purchase_requisitions`
- `supplier_performance` links `suppliers` to `items` (for item-specific performance)

---

### Data Volume for Demo (Realistic but Small)

- `products`: 6
- `bom_lines`: ~45
- `items`: ~40
- `suppliers`: 20
- `supplier_performance`: ~180 records (multiple periods per supplier)
- `inventory`: 40
- `users`: 8
- `purchase_requisitions`: 25–40 (with varying status)
- `pr_lines`: ~100
- `purchase_orders`: 20–30

This volume is small enough to manage easily but rich enough for meaningful agent reasoning and demo scenarios.

---

### How Agents Will Interact With This Schema

- **Inventory & Demand Analyst Agent**: Queries `inventory` + `bom_lines` + `pr_lines`
- **Supplier Intelligence Agent**: Heavy use of `suppliers` + `supplier_performance` + `items`
- **PO Creator Agent**: Reads from `pr_lines`, writes to `purchase_orders` + `po_lines`, updates `inventory` (projected)
- **Supervisor**: Orchestrates and maintains overall state using data from multiple tables

---

### Version History

| Version | Date          | Changes                              | Author |
|---------|---------------|--------------------------------------|--------|
| 1.0     | June 29, 2026 | Initial schema design                                      | Grok           |
| 1.1     | June 30, 2026 | Added work_orders, supplier_item_pricing, activity_log + on_order_qty to inventory | Grok + Bharath |
| 1.2     | June 30, 2026 | Added current_expected_lead_time_days, delay_risk_level, current_risk_notes to supplier_performance | Grok + Bharath |

---

**End of Document**

This schema is ready for review. Once approved, we can move to data generation scripts and agent tool development.