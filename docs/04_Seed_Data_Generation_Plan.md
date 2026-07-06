# PrecisionForge Technologies Inc.
## Seed Data Generation Plan – Version 1.0

**Project:** ForgeForce Procurement Agents  
**Date:** June 30, 2026  
**Version:** 1.0  
**Status:** Draft

---

### Purpose

This document outlines **how** we will generate realistic seed data for the database. Good seed data is critical because the quality of the Agent Force’s reasoning depends heavily on having varied, realistic supplier performance, inventory levels, and historical context.

We want to avoid "toy data" (e.g., all suppliers perfect, all inventory high). Instead, we want enough variation so the agent has to make real trade-off decisions.

---

### Data Generation Strategy Overview

| Table                        | Generation Method                  | Realism Level | Notes |
|-----------------------------|------------------------------------|---------------|-------|
| `products`                  | Hardcoded (from BOM document)      | High          | Only 6 records |
| `bom_lines`                 | Hardcoded (from BOM document)      | High          | ~45 records |
| `items`                     | Script + manual curation           | High          | 35–45 items |
| `suppliers`                 | Script with categories             | High          | 20 suppliers with varied profiles |
| `supplier_performance`      | Script (multiple periods)          | High          | Most important for agent reasoning |
| `inventory`                 | Script with variation              | Medium-High   | Some low stock, some healthy |
| `users`                     | Hardcoded                          | Medium        | 8–10 users with roles |
| `work_orders`               | Script                             | Medium        | 15–25 records |
| `supplier_item_pricing`     | Script (mix of contracted + spot)  | High          | Key for pricing behavior |
| `activity_log`              | Generated during testing           | —             | Populated as we test agents |

---

### 1. Suppliers (20 Suppliers)

We will create 20 suppliers across 5 segments:

| Segment                  | Count | Characteristics |
|--------------------------|-------|-----------------|
| Premium / Global Tier-1  | 4     | High quality, reliable, higher price, mostly US/Europe |
| US Regional / Mid-tier   | 6     | Good balance, reliable lead times |
| Mexico Nearshoring       | 3     | Competitive price + faster logistics than Asia |
| Asia Cost-Optimized      | 5     | Lowest price, higher variability in quality & lead time |
| Local / Strategic        | 2     | Within 200 miles, used for urgent needs |

**Data to generate per supplier:**
- Name, country, city/state, segment
- Average lead time
- Payment terms
- Overall reliability score (we will derive detailed performance later)

---

### 2. Supplier Performance (Most Important Table)

This table will have **multiple records per supplier** (different time periods + item-specific where relevant).

**Strategy:**
- For each supplier, create 6–10 performance records.
- Mix of:
  - Overall performance (last 6 months)
  - Recent performance (last 30–60 days)
  - Item/category specific issues (especially for bearings, castings, seals)
- Vary:
  - `on_time_delivery_pct` (75% – 98%)
  - `quality_rejection_pct` (0.5% – 6%)
  - `recent_issues` (text field with realistic notes)
  - `capacity_status` (Normal / Constrained / Available)
  - `current_expected_lead_time_days` (can be significantly higher than historical for international suppliers)
  - `delay_risk_level` (Low / Medium / High) — especially for suppliers affected by shipping/port issues
  - `current_risk_notes` (free text explaining current delays, e.g., "Port congestion + Red Sea rerouting. Expected +7–12 days delay")

**Goal:** Some suppliers look good historically but currently have elevated delay risk. This forces the agent to balance price, historical reliability, **and current risk** when making recommendations. Not all suppliers need high risk — only a few (especially international ones) should have elevated `delay_risk_level`.

---

### 3. Items Master (35–45 items)

We will create items across these categories:

- Bearings (8–10 types)
- Raw Materials – Steel, Aluminum (6–8)
- Castings & Forgings (5–6)
- Fasteners & Hardware (8–10)
- Seals, Gaskets, Elastomers (4–5)
- Other (motors, sensors, packaging, consumables)

For each item:
- Name, category, unit, average cost
- Whether it is "critical"
- Average lead time
- Safety stock level

---

### 4. Inventory

We want **variation**:
- Some items: Healthy stock (well above safety stock)
- Some items: Low stock (triggering procurement need)
- Some items: Very low / stockout risk
- Mix of `on_order_qty` (some items already on order)

This creates realistic scenarios where the agent sometimes recommends expediting vs normal ordering.

---

### 5. Supplier Item Pricing (Contracted vs Spot)

This is key for showing intelligent behavior.

**Approach:**
- For ~60–70% of supplier-item combinations, create a contracted price record.
- Remaining combinations only have spot pricing (agent has to decide whether to use spot or find another supplier with contract).
- Contracted prices are generally 8–15% lower than spot.
- Some contracts are expired (`is_active = False`) to test agent logic.

---

### 6. Work Orders & Demand

We will create 15–25 work orders linked to our 6 products with varying:
- Quantities
- Required dates (some urgent, some normal)
- Status

These will drive the PR creation scenarios during testing.

---

### 7. Users

Hardcode 8–10 users with realistic roles and approval limits:

- PPC Lead, Maintenance Lead, NPD Engineer, Quality Engineer
- Procurement Executive, Procurement Manager, Plant Head, Director

---

### Tools & Approach for Data Generation

- Use **Python script** (pandas + sqlite3 or Faker library)
- One main script: `generate_seed_data.py`
- Separate functions for each table
- Seed with fixed random seed for reproducibility during development
- Final data will be committed as `seed_data.db` or SQL dump

---

### Realism Priorities (Ranked)

| Priority | Table                        | Why it matters |
|----------|------------------------------|----------------|
| 1        | `supplier_performance`       | Core of intelligent supplier selection |
| 2        | `supplier_item_pricing`      | Enables contracted vs spot reasoning |
| 3        | `inventory`                  | Creates real procurement triggers |
| 4        | `suppliers`                  | Foundation for segmentation |
| 5        | `items` + `bom_lines`        | Accurate requirement calculation |

---

### Version History

| Version | Date          | Changes                  | Author |
|---------|---------------|--------------------------|--------|
| 1.0     | June 30, 2026 | Initial seed data plan   | Grok   |

---

**End of Document**