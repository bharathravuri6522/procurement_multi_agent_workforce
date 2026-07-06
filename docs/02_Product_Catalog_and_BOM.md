# PrecisionForge Technologies Inc.
## Product Catalog & Bill of Materials (Simplified) – Version 1

**Project:** ForgeForce Procurement Agents  
**Date:** June 29, 2026  
**Version:** 1.0  
**Status:** Draft for Review

---

### Purpose of This Document

This document defines the **6 core products** that PrecisionForge Technologies manufactures (one representative product from each major category). For each product, it provides a **simplified single-level Bill of Materials (BOM)** with specific quantities.

This serves as the foundation for:
- Designing the `items` master table and `bom` / `bom_lines` tables in the database
- Agent logic for requirement calculation (Work Order qty × BOM qty + yield buffer)
- Creating realistic demo scenarios
- Inventory checking and net requirement calculation

We are keeping the BOMs at **medium depth** — realistic enough to demonstrate intelligent agent behavior, but simple enough to implement within the 3-day sprint.

---

### Product Selection Strategy

We have selected **one product per category** (total 6 products) to keep the scope manageable while covering all major product types.

| # | Category                    | Selected Product                          | Code          | Complexity |
|---|-----------------------------|-------------------------------------------|---------------|------------|
| 1 | Rotating Components         | Precision Rotor Shaft                     | RS-240        | High       |
| 2 | Housings & Enclosures       | Gearbox Housing – Model GH-450            | GH-450        | Medium-High|
| 3 | Bearing Assemblies          | Integrated Bearing Housing Unit           | BHU-6205      | Medium     |
| 4 | Custom Brackets & Mounts    | Engine Mounting Bracket                   | EMB-240       | Medium     |
| 5 | Gears & Power Transmission  | Helical Gear – Module 2                   | HG-80-M2      | High       |
| 6 | Fluid Handling Components   | Centrifugal Pump Impeller                 | IMP-150       | Medium-High|

---

### 1. Precision Rotor Shaft (RS-240)

**Category:** Rotating Components  
**Description:** High-precision rotor shaft used in electric motors and pumps. Tight tolerance on bearing journals and keyways.  
**Typical Order Quantity:** 50 – 200 units per batch

**Bill of Materials (per unit):**

| Item Code | Item Name                          | Type              | Qty per Unit | Unit  | Notes                              |
|-----------|------------------------------------|-------------------|--------------|-------|------------------------------------|
| RM-4140   | Alloy Steel Bar 4140 (Ø45mm)       | Raw Material      | 0.85         | kg    | Main shaft material                |
| BR-6205   | Deep Groove Ball Bearing 6205      | Bought-out        | 2            | pcs   | Critical – long lead time          |
| BR-6305   | Deep Groove Ball Bearing 6305      | Bought-out        | 1            | pcs   | Drive end bearing                  |
| FT-M6-20  | Hex Socket Head Cap Screw M6×20    | Bought-out        | 4            | pcs   | For coupling attachment            |
| FT-M5-CIR | External Circlip M5                | Bought-out        | 2            | pcs   | Bearing retention                  |
| PK-001    | VCI Packaging + Label              | Packaging         | 1            | set   | Export compliant                   |

**Yield / Buffer Note:** Agent should calculate gross requirement with **+2.5%** buffer for machining scrap and handling damage on bearings.

---

### 2. Gearbox Housing – Model GH-450

**Category:** Housings & Enclosures  
**Description:** Cast aluminum gearbox housing for industrial speed reducers. Requires precision machining on mounting faces and bearing bores.  
**Typical Order Quantity:** 20 – 80 units per batch

**Bill of Materials (per unit):**

| Item Code | Item Name                              | Type              | Qty per Unit | Unit  | Notes                              |
|-----------|----------------------------------------|-------------------|--------------|-------|------------------------------------|
| CS-AL-450 | Aluminum Sand Casting (GH-450)         | Bought-out        | 1            | pcs   | From approved foundry supplier     |
| BR-6208   | Deep Groove Ball Bearing 6208          | Bought-out        | 2            | pcs   | Input shaft bearings               |
| BR-32208  | Tapered Roller Bearing 32208           | Bought-out        | 2            | pcs   | Output shaft bearings              |
| FT-M8-25  | Hex Head Bolt M8×25 Grade 8.8          | Bought-out        | 8            | pcs   | Housing assembly                   |
| GS-450    | Cork + Rubber Gasket Set               | Bought-out        | 1            | set   | Sealing between halves             |
| PK-002    | Rust Preventive Oil + VCI Bag          | Packaging         | 1            | set   | —                                  |

**Yield / Buffer Note:** +3% buffer recommended on bearings and fasteners due to higher handling volume.

---

### 3. Integrated Bearing Housing Unit (BHU-6205)

**Category:** Bearing Assemblies  
**Description:** Pre-assembled bearing housing unit with integrated shaft and seals. Used in conveyor and material handling systems.  
**Typical Order Quantity:** 30 – 150 units

**Bill of Materials (per unit):**

| Item Code | Item Name                          | Type              | Qty per Unit | Unit | Notes                              |
|-----------|------------------------------------|-------------------|--------------|------|------------------------------------|
| HS-6205   | Machined Housing (Cast Iron)       | Bought-out        | 1            | pcs  | From approved casting supplier     |
| BR-6205   | Deep Groove Ball Bearing 6205      | Bought-out        | 2            | pcs  | Critical item                      |
| SL-35-52  | Oil Seal 35×52×7                   | Bought-out        | 2            | pcs  | Both sides sealing                 |
| FT-M6-16  | Socket Head Cap Screw M6×16        | Bought-out        | 4            | pcs  | End cover fastening                |
| GR-001    | Lithium Grease (High Temp)         | Bought-out        | 25           | g    | Pre-filled during assembly         |
| CV-6205   | End Cover / Cap                    | Bought-out        | 2            | pcs  | —                                  |

**Yield / Buffer Note:** Bearings and seals are high-value — apply **+2%** buffer. Grease has higher tolerance.

---

### 4. Engine Mounting Bracket (EMB-240)

**Category:** Custom Brackets & Mounts  
**Description:** Heavy-duty engine mounting bracket for commercial vehicle applications. Requires welding + machining.  
**Typical Order Quantity:** 40 – 200 units

**Bill of Materials (per unit):**

| Item Code | Item Name                          | Type              | Qty per Unit | Unit | Notes                              |
|-----------|------------------------------------|-------------------|--------------|------|------------------------------------|
| PL-240    | Laser Cut Plate (S355 Steel)       | Bought-out        | 1            | pcs  | From laser cutting vendor          |
| BR-6204   | Deep Groove Ball Bearing 6204      | Bought-out        | 1            | pcs  | For pivot point                    |
| FT-M10-30 | High Tensile Bolt M10×30           | Bought-out        | 4            | pcs  | Grade 10.9                         |
| FT-M8-NUT | Hex Nut M8 Grade 8                 | Bought-out        | 4            | pcs  | —                                  |
| WS-001    | Welding Consumables (Allowance)    | Consumable        | 1            | lot  | Internal + external welding        |
| PK-003    | Black Paint + Protective Film      | Packaging         | 1            | set  | —                                  |

**Yield / Buffer Note:** +4% buffer on fasteners due to higher consumption in assembly.

---

### 5. Helical Gear – Module 2 (HG-80-M2)

**Category:** Gears & Power Transmission  
**Description:** Precision helical gear (80 teeth, Module 2) used in industrial gearboxes. Requires high-accuracy hobbing + grinding.  
**Typical Order Quantity:** 15 – 60 units (lower volume, high value)

**Bill of Materials (per unit):**

| Item Code | Item Name                          | Type              | Qty per Unit | Unit | Notes                              |
|-----------|------------------------------------|-------------------|--------------|------|------------------------------------|
| RM-8620   | Alloy Steel Round Bar 8620         | Raw Material      | 2.8          | kg   | Gear blank material                |
| BR-6207   | Deep Groove Ball Bearing 6207      | Bought-out        | 1            | pcs  | For gear shaft support             |
| FT-M5-KEY | Woodruff Key 5×10                  | Bought-out        | 1            | pcs  | Shaft mounting                     |
| GR-002    | Gear Oil (ISO 220) – Sample        | Bought-out        | 50           | ml   | For testing                        |
| PK-004    | Anti-rust Paper + Wooden Crate     | Packaging         | 1            | set  | Export quality                     |

**Yield / Buffer Note:** Raw material has higher scrap rate during hobbing/grinding. Apply **+5%** on steel bar. Bearings: +2%.

---

### 6. Centrifugal Pump Impeller (IMP-150)

**Category:** Fluid Handling Components  
**Description:** Precision machined closed impeller for centrifugal pumps (150mm diameter). Critical for hydraulic performance.  
**Typical Order Quantity:** 25 – 100 units

**Bill of Materials (per unit):**

| Item Code | Item Name                          | Type              | Qty per Unit | Unit | Notes                              |
|-----------|------------------------------------|-------------------|--------------|------|------------------------------------|
| CS-SS-150 | Stainless Steel Investment Casting | Bought-out        | 1            | pcs  | From approved foundry              |
| BR-6203   | Deep Groove Ball Bearing 6203      | Bought-out        | 2            | pcs  | Impeller shaft support             |
| SL-17-30  | Mechanical Seal 17×30              | Bought-out        | 1            | pcs  | Critical sealing component         |
| FT-M4-12  | Socket Set Screw M4×12             | Bought-out        | 2            | pcs  | Impeller locking                   |
| PK-005    | Protective Sleeve + Label          | Packaging         | 1            | set  | —                                  |

**Yield / Buffer Note:** Mechanical seals are expensive and fragile — apply **+3%** buffer. Castings: +2.5%.

---

### Yield, Scrap & Safety Buffer Policy (Lightweight)

For this project, we will apply a **simple rule-based buffer** at the agent level rather than storing complex yield data per operation:

- **Standard items** (fasteners, packaging, grease): +2%
- **Critical / High-value items** (bearings, mechanical seals, precision castings): +2.5% to +3%
- **Raw material with machining** (steel bars, plates): +4% to +5% (depending on product)

The agent will calculate:
> **Gross Requirement = (Work Order Quantity × BOM Quantity) × (1 + Buffer %)**

This keeps the logic understandable while still demonstrating realistic manufacturing considerations.

---

### How This Will Be Used by the Agent Force

1. User / Work Order triggers a requirement for **X units of Product Code XXX**.
2. Agent looks up the BOM for that product.
3. Calculates gross material/component requirement (with buffer).
4. Checks current inventory levels.
5. Calculates **net requirement** for each item.
6. Proceeds to supplier intelligence & PO creation workflow for the net required items.

---

### Version History

| Version | Date          | Changes                                      | Author     |
|---------|---------------|----------------------------------------------|------------|
| 1.0     | June 29, 2026 | Initial draft – 6 products with simplified BOMs | Grok       |

---

**End of Document**

This document is ready for review. Once approved, we can move to Database Schema Design with clear understanding of what items and relationships we need.