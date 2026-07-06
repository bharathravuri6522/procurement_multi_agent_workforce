# PrecisionForge Technologies Pvt. Ltd.
## Company Context Document (Version 1.1)

**Project:** ForgeForce Procurement Agents – Multi-Agent Digital Workforce for Intelligent PR-to-PO Automation  
**Date:** June 29, 2026  
**Version:** 1.1  
**Status:** Finalized for Schema & Agent Design

---

### Purpose of This Document

This document provides the complete business context for the simulated company **PrecisionForge Technologies Pvt. Ltd.** It serves as the single source of truth for designing:

- The mock ERP database schema and seed data (items, suppliers, inventory, performance history, etc.)
- Realistic procurement scenarios and agent reasoning logic
- Role-based validation (RBAC) rules
- Demo use cases that can be credibly explained to mentors, interviewers, or stakeholders

All design decisions (tables, relationships, agent behavior, and evaluation criteria) will be derived from or validated against this document.

---

### 1. Company Overview

**PrecisionForge Technologies Inc.** is a mid-sized precision engineering and manufacturing company based in Columbus, Indiana, USA (strong automotive and industrial manufacturing region in the Midwest).

- **Established**: 2012
- **Annual Turnover**: $12–15 Million USD
- **Employees**: ~85
- **Core Capabilities**: CNC turning, milling, grinding, and light assembly of high-precision components (tolerances typically ±0.0005" to ±0.002")
- **Certifications**: IATF 16949 (Automotive Quality Management)
- **Business Model**: Primarily Make-to-Order with some Make-to-Stock for high-running components
- **ERP Landscape**: Uses a full-featured ERP system (modeled after SAP)

The company focuses on quality, on-time delivery, and cost competitiveness for mid-to-high complexity precision components.

---

### 2. Products Manufactured

PrecisionForge does **not** manufacture complete machines or end products. It produces **critical precision components and sub-assemblies** that become part of its customers’ products.

**Key Product Categories:**

| Category                    | Example Products                          | Typical Tolerance | Primary End Use                     | Complexity |
|----------------------------|-------------------------------------------|-------------------|-------------------------------------|----------|
| Rotating Components        | Precision shafts, spindles, rotor shafts  | ±0.01 – 0.02mm   | Automotive, Pumps, Textile machinery | High     |
| Housings & Enclosures      | Gearbox housings, motor end shields, valve bodies | ±0.03mm     | Industrial machinery, Hydraulics   | Medium-High |
| Bearing Assemblies         | Integrated bearing housing units          | ±0.02mm          | Automotive, Material handling      | Medium   |
| Custom Brackets & Mounts   | Engine mounts, sensor brackets            | ±0.05mm          | Automotive (ICE + EV), Machinery   | Medium   |
| Gears & Power Transmission | Spur gears, helical gears, spline shafts  | ±0.015mm         | Industrial gearboxes               | High     |
| Fluid Handling Components  | Impellers, pump shafts, valve stems       | ±0.02mm          | Pumps & Valves                     | Medium-High |

---

### 3. Customers & Demand Flow

**Customer Segments (Revenue Mix):**

- **Automotive Tier-1 Suppliers**: 45%
- **Industrial Machinery OEMs**: 25%
- **Pump & Valve Manufacturers**: 20%
- **Direct Exports** (Europe & Middle East): 10%

**How Demand Reaches PrecisionForge:**

1. Customer sends **Purchase Order**, **Annual Rate Contract**, or monthly **Forecast**.
2. Internal **Work Order** is created in the ERP.
3. MRP (Material Requirements Planning) run identifies shortages in raw materials and bought-out components.
4. **Purchase Requisitions (PRs)** are generated (system-suggested or manually created by PPC/Maintenance/NPD teams).
5. Procurement team analyzes and converts approved PRs into **Purchase Orders**.

This flow creates the need for intelligent PR-to-PO processing — the core workflow our Agent Force will support.

---

### 4. What Products Require (Bill of Materials – Simplified)

Most products require a combination of:
- **Raw materials** (bought and machined in-house)
- **Bought-out components** (bearings, castings, fasteners, seals, etc.)

**Examples:**

- **Precision Shaft** typically requires:
  - Alloy steel bar (raw material)
  - Specific deep groove or tapered roller bearing
  - Circlips / retaining rings
  - Surface treatment (outsourced process)

- **Gearbox Housing** typically requires:
  - Aluminum or Cast Iron casting (from foundry supplier)
  - Multiple bearings
  - Oil seals and gaskets
  - High-tensile fasteners

- **Integrated Bearing Housing Unit** typically requires:
  - Machined housing
  - Deep groove ball bearings (often from premium suppliers)
  - Grease and end covers

This dependency on external suppliers for critical components makes procurement performance directly impact delivery reliability and quality.

---

### 5. Procurement Categories & Key Items

PrecisionForge procures approximately 180–200 active SKUs. For this project we will simulate a focused but realistic subset of **25–35 key items** across the following categories:

- **Bearings & Power Transmission**
- **Castings & Forgings** (Aluminum, CI, Steel)
- **Raw Materials** (Alloy steel bars, Stainless steel, Aluminum sections)
- **Fasteners & Hardware** (High tensile bolts, studs, dowel pins, circlips)
- **Seals, Gaskets & Elastomers**
- **Electrical & Mechatronics** (Small motors, sensors, connectors)
- **MRO & Consumables** (Cutting tools, abrasives, lubricants, packaging)

---

### 6. Supplier Base (20 Suppliers)

We will model **20 suppliers** with realistic diversity in geography, capability, reliability, and commercial terms — adapted for a US-based Midwest manufacturer:

**Supplier Segmentation (planned):**
- **Premium / Global Tier-1** (US operations or North American hubs of SKF, Timken, Bosch, NSK, etc. + select European/Japanese direct) — Higher price, excellent quality & consistency
- **Strong US Regional / Mid-tier** (Indiana, Michigan, Ohio, Illinois, Wisconsin manufacturing clusters) — Good quality-price balance, reliable lead times
- **Nearshoring / Mexico-based** (Growing trend for US companies — faster logistics than Asia, improving quality) — Competitive pricing with better lead times than Asia
- **Cost-optimized / Asia** (primarily China, with some Vietnam/India for non-critical or high-volume commodity items) — Lowest price but higher variability in lead time and quality
- **Local / Strategic Suppliers** (within 150–200 miles radius in the Midwest) — Used for urgent requirements, VMI arrangements, and Just-In-Time support

Each supplier will have differentiated profiles across:
- On-time delivery performance
- Quality rejection / return rate
- Recent issues (quality, documentation, capacity constraints)
- Contracted pricing vs current spot market
- Lead time variability and current capacity signals

This diversity enables the Agent Force to demonstrate intelligent, multi-criteria decision making (e.g., trading off price vs lead time vs reliability vs nearshoring risk) rather than simple rule-based selection.

---

### 7. Internal Organization, PR Raising & Approval Authority (RBAC + Workflow Context)

In a real company, different people/roles have authority to **raise** Purchase Requisitions, but there is also a formal **approval process** before a PR can be converted into a Purchase Order. This is typically governed by Release Strategies in ERP systems (value-based + category-based).

#### 7.1 Who Can Raise PRs (Department Scope)

| Department                  | Typical PR Scope                                      | Authority to Raise |
|-----------------------------|-------------------------------------------------------|--------------------|
| Production Planning (PPC)   | Production items (bearings, castings, raw material for current work orders) | Yes (High volume) |
| Maintenance                 | Spares, MRO items, breakdown / preventive maintenance requirements | Yes |
| New Product Development (NPD) | Prototype parts, new component development, samples | Yes |
| Quality / Metrology         | Inspection equipment, gauges, consumables             | Yes (Limited) |

Our Agent Force will include **lightweight role-based validation** to check that the requester’s department is authorized to raise PRs for that item category.

#### 7.2 PR Approval Matrix (Who Approves PRs)

Not everyone who raises a PR can approve it. PrecisionForge uses a simple value + criticality-based approval matrix (common in mid-sized manufacturing companies):

| PR Value / Type                          | Typical Approver                       | Notes |
|------------------------------------------|----------------------------------------|-------|
| < $2,500 + Standard / Non-critical item  | PPC Lead or Procurement Executive      | Fast track for routine items |
| $2,500 – $12,000 or Critical production item | Procurement Manager                 | Most common approval level |
| > $12,000 or New development / New supplier | Plant Head / Operations Head        | Higher scrutiny required |
| Very High Value (> $30,000) or Strategic items | Director / Managing Director       | Rare but exists in policy |

**How this will be used in the project:**
- The Agent Force will validate the PR and propose the best supplier + PO.
- We will simulate PR status (`Draft → Submitted → Approved / Rejected`).
- The agent will only proceed to final PO creation after the PR reaches "Approved" status (or clearly flag it for human approval).
- This adds realism to the workflow and demonstrates that the system respects organizational controls.

This approval layer makes the simulation much closer to how real ERP + procurement workflows operate.

---

### 8. Typical End-to-End Demand & Procurement Flow

1. **Customer Order / Forecast** received
2. **Work Order** created in ERP
3. **MRP Run** → Material shortage identified
4. **Purchase Requisition (PR)** created
5. **Intelligent PR-to-PO Process** (this is where our Agent Force operates):
   - Validate request context & requester authority
   - Check current inventory + open orders
   - Analyze supplier options using performance, pricing, lead time, and recent issues
   - Recommend best supplier(s) with full reasoning
   - Create Purchase Order (after human approval gate)
6. **Supplier Delivery** → Goods Receipt → Quality Inspection → Stock Update

---

### Version History

| Version | Date          | Changes                                                                 | Author          |
|---------|---------------|-------------------------------------------------------------------------|-----------------|
| 1.0     | June 29, 2026 | Initial draft                                                           | Grok            |
| 1.1     | June 29, 2026 | Finalized after user review; added Purpose section & minor refinements  | Grok + Bharath  |
| 1.2     | June 29, 2026 | Enhanced Section 7 with PR Approval Matrix (who approves PRs + workflow) | Grok + Bharath  |
| 1.3     | June 29, 2026 | Updated company to USA (Indiana), changed currency to USD, adjusted turnover/employees/tolerances | Grok + Bharath  |
| 1.4     | June 29, 2026 | Revised Supplier Base section for US context (more US regional + Mexico nearshoring, reduced India focus) | Grok + Bharath  |

---

**End of Document**

This document is now the approved foundation for all subsequent design work (database schema, seed data, agent architecture, and demo scenarios).