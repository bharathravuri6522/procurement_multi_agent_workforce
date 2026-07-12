# ForgeForce Procurement AI

<p align="center">

**Production-Grade Multi-Agent Procurement Intelligence Platform**

_Combining deterministic procurement planning, AI-powered supplier reasoning, human-in-the-loop decision making, and enterprise workflow orchestration._

</p>

<p align="center">

![Python](https://img.shields.io/badge/Python-3.11-blue)
![LangGraph](https://img.shields.io/badge/LangGraph-Multi--Agent-success)
![OpenAI](https://img.shields.io/badge/OpenAI-GPT--4o-green)
![Streamlit](https://img.shields.io/badge/Streamlit-UI-red)
![SQLite](https://img.shields.io/badge/SQLite-Persistence-blue)
![LangSmith](https://img.shields.io/badge/LangSmith-Observability-purple)
![Status](https://img.shields.io/badge/Status-Production%20Ready-success)

</p>

---

## High-Level Architecture

<p align="center">

![ForgeForce Architecture](docs/images/high_level_architecture.png)

</p>

---

# Overview

ForgeForce Procurement AI is a production-style procurement intelligence platform that demonstrates how deterministic business workflows, Large Language Models (LLMs), and human expertise can work together to support enterprise purchasing decisions.

Rather than allowing an LLM to make procurement decisions directly, the platform combines deterministic planning algorithms with explainable AI reasoning. Business-critical calculations—including inventory planning, supplier enrichment, procurement strategy selection, purchase requisition generation, and purchase order creation—are performed through deterministic logic, while LLMs are responsible only for evaluating trade-offs, explaining recommendations, and supporting human decision-making.

The system follows a Human-in-the-Loop (HITL) architecture where every AI recommendation remains immutable for auditability. Procurement specialists may review, approve, or override recommendations before Purchase Requisitions (PRs) are generated. Every change is persisted, fully traceable, and preserved throughout the procurement lifecycle.

In addition to the procurement workflow, ForgeForce includes a stateful conversational assistant capable of answering procurement questions, explaining supplier recommendations, retrieving workflow history, and providing contextual assistance using persistent conversation memory.

The result is an end-to-end procurement platform that combines:

- Deterministic procurement planning
- Multi-agent workflow orchestration
- Explainable AI reasoning
- Human review and approval
- Persistent conversation intelligence
- Enterprise auditability
- Production observability

---

# Platform Highlights

| Capability                          | Description                                                                                                                     | Status |
| ----------------------------------- | ------------------------------------------------------------------------------------------------------------------------------- | :----: |
| 🤖 Multi-Agent Procurement Workflow | End-to-end AI workflow for demand planning, supplier intelligence, reasoning, review, PR creation, approval, and PO generation. |   ✅   |
| 🧠 Deterministic + AI Architecture  | Business calculations remain deterministic while LLMs perform explainable reasoning and decision support.                       |   ✅   |
| ⚡ Parallel Supplier Reasoning      | Contracted and Spot procurement strategies execute concurrently for every required item.                                        |   ✅   |
| 🎯 Critical Path Optimization       | Hybrid procurement minimizes production delays while balancing procurement cost.                                                |   ✅   |
| 👨‍💼 Human-in-the-Loop Review         | Reviewers can approve AI recommendations or override strategy and suppliers with complete audit history.                        |   ✅   |
| 💾 Persistent Procurement Sessions  | Procurement analyses, conversations, and review decisions survive refreshes and application restarts.                           |   ✅   |
| 💬 Stateful Procurement Assistant   | LangGraph-powered conversational assistant with contextual retrieval, memory, and procurement-specific Q&A.                     |   ✅   |
| 📋 Purchase Requisition Workflow    | Converts reviewed procurement recommendations into enterprise Purchase Requisitions.                                            |   ✅   |
| 📦 Purchase Order Generation        | Approved Purchase Requisitions automatically generate supplier-specific Purchase Orders.                                        |   ✅   |
| 📈 LangSmith Observability          | End-to-end workflow tracing with nested execution visibility and performance insights.                                          |   ✅   |
| 📝 Structured JSON Logging          | Production-grade centralized logging with audit-friendly event tracking.                                                        |   ✅   |
| 🔍 Enterprise Audit Trail           | Preserves immutable AI recommendations alongside all human decisions and overrides.                                             |   ✅   |

# Why ForgeForce?

Traditional AI procurement demonstrations typically generate supplier recommendations directly from an LLM. While impressive, those approaches often lack determinism, traceability, and governance—qualities that are essential in enterprise procurement.

ForgeForce addresses these challenges by separating deterministic business logic from AI reasoning.

Business rules determine **what is possible**, while AI helps explain **what is preferable**.

This architectural separation produces procurement recommendations that are:

- Explainable
- Repeatable
- Auditable
- Human-reviewable
- Enterprise-ready

The platform demonstrates how AI can augment procurement professionals instead of replacing existing procurement governance.

---

# Key Features

## Multi-Agent Procurement Workflow

- Demand and inventory analysis
- Supplier intelligence enrichment
- Risk and complexity planning
- Parallel contracted supplier reasoning
- Parallel spot supplier reasoning
- Critical-path-aware hybrid procurement
- Deterministic decision aggregation

---

## Human-in-the-Loop Decision Making

- Immutable AI recommendations
- Strategy overrides
- Item-level supplier overrides
- Reviewer comments
- Complete audit trail
- Persistent decision history

---

## Enterprise Procurement Lifecycle

- Purchase Recommendation generation
- Purchase Requisition creation
- Approval workflow
- Purchase Order generation
- Execution supervision
- Deterministic PR → PO orchestration

---

## Conversational Procurement Assistant

- Stateful conversation memory
- Context-aware procurement Q&A
- Workflow explanation
- Supplier reasoning explanation
- Session persistence
- Entity-aware retrieval
- Conversation summarization

---

## Enterprise Engineering

- LangGraph orchestration
- LangSmith observability
- Structured JSON logging
- SQLite persistence
- Modular architecture
- Production-grade error handling
- Smoke-test coverage
- Fully deterministic execution

---

## Platform at a Glance

ForgeForce uses a LangGraph-based Supervisor Agent to orchestrate the procurement workflow. Deterministic agents prepare and enrich procurement data, LLM-powered reasoning evaluates supplier trade-offs, and human reviewers retain final decision authority before PR and PO execution.

```mermaid
flowchart TD
    USER["Procurement User"] --> UI["Streamlit Application"]

    UI --> SUP["Supervisor Agent<br/>LangGraph Orchestrator"]

    subgraph PROCUREMENT["Procurement Intelligence Workflow"]
        SUP --> DEMAND["Demand & Inventory Analyst"]
        DEMAND --> SUPPLIER["Supplier Intelligence Agent"]
        SUPPLIER --> PLANNER["Risk & Complexity Planner"]

        PLANNER --> EXECUTOR["Parallel Strategy Executor"]
        EXECUTOR --> CONTRACTED["Contracted Supplier Reasoning"]
        EXECUTOR --> SPOT["Spot Supplier Reasoning"]

        CONTRACTED --> AGGREGATOR["Decision Aggregator"]
        SPOT --> AGGREGATOR
    end

    AGGREGATOR --> REVIEW["Human Decision Review"]
    REVIEW --> PR["Purchase Requisition"]

    PR --> APPROVAL["Approval Workflow"]
    APPROVAL --> PO["Supplier-Specific Purchase Orders"]

    UI --> CONVERSATION["Conversation Workflow"]
    CONVERSATION --> QUERY["Query Analyzer"]
    QUERY --> CONTEXT["Selective Context Builder"]
    CONTEXT --> ANSWER["Answer Generator"]
    ANSWER --> MEMORY["Conversation Memory & Summarization"]

    REVIEW -.-> DATABASE[("SQLite Persistence")]
    PR -.-> DATABASE
    PO -.-> DATABASE
    MEMORY -.-> DATABASE

    SUP -.-> OBSERVABILITY["LangSmith Tracing"]
    PR -.-> LOGGING["Structured JSON Logging"]
    PO -.-> LOGGING
```

---

# Procurement Workflow

The procurement workflow combines deterministic planning with AI-assisted reasoning. Business calculations are performed through rule-based logic, while LLMs evaluate supplier trade-offs and produce explainable recommendations.

```mermaid
flowchart LR
A[Demand & Inventory Analysis] --> B[Supplier Intelligence]
B --> C[Risk & Complexity Planner]
C --> D[Parallel Strategy Executor]
D --> E[Contracted Reasoning]
D --> F[Spot Reasoning]
E --> G[Decision Aggregator]
F --> G
G --> H[Human Review]
H --> I[Purchase Requisition]
I --> J[Manager Approval]
J --> K[Purchase Orders]
```

The workflow begins by calculating net procurement requirements from demand forecasts, inventory, safety stock and open purchase orders. Supplier intelligence enriches each required item with pricing, lead times, capacity and risk. Contracted and spot procurement strategies are evaluated in parallel before a deterministic decision aggregator builds the recommended procurement plan. Human reviewers can approve or override recommendations before downstream execution.

---

# Conversation Workflow

```mermaid
flowchart LR
A[User Question] --> B[Query Analyzer]
B --> C[Context Builder]
C --> D[Answer Generator]
D --> E[Conversation Memory]
E --> F[Response]
```

The conversation engine analyzes user intent, retrieves only the most relevant procurement context, generates grounded responses, and continuously summarizes conversation history.

---

# Human Review Workflow

```mermaid
flowchart LR
A[AI Recommendation] --> B[Human Review]
B --> C{Override?}
C -->|No| D[Approve]
C -->|Yes| E[Strategy / Supplier Override]
D --> F[Effective Plan]
E --> F
F --> G[Persist Decision]
G --> H[Create Purchase Requisition]
```

AI recommendations remain immutable. Human decisions are stored separately and combined into an effective procurement plan used for execution.

---

# Purchase Requisition to Purchase Order Lifecycle

```mermaid
flowchart LR
A[Reviewed Plan] --> B[Purchase Requisition]
B --> C[Manager Approval]
C -->|Approved| D[Generate Purchase Orders]
C -->|Rejected| E[Return for Review]
D --> F[Supplier-specific Purchase Orders]
```

---

# Repository Structure

```text
src/
├── agents/
├── conversation/
├── core/
├── pr_po/
├── ui/
├── scripts/
├── persistence.py
└── streamlit_app.py
```

---

# Technology Stack

| Layer         | Technology                  |
| ------------- | --------------------------- |
| UI            | Streamlit                   |
| Workflow      | LangGraph                   |
| LLM           | OpenAI GPT-4o / GPT-4o-mini |
| AI Framework  | LangChain                   |
| Database      | SQLite                      |
| Observability | LangSmith                   |
| Logging       | Structured JSON             |
| Language      | Python 3.11                 |

---

# Installation

```bash
git clone <repository-url>
cd procurement_multi_agent_workforce

python -m venv venv
```

Windows

```bash
venv\Scripts\activate
```

Linux / macOS

```bash
source venv/bin/activate
```

Install dependencies

```bash
pip install -r requirements.txt
```

---

# Configuration

```env
OPENAI_API_KEY=
LANGCHAIN_API_KEY=
LANGCHAIN_TRACING_V2=true
LANGCHAIN_PROJECT=ForgeForce Procurement AI
DATABASE_PATH=data/forgeforce.db
LOG_LEVEL=INFO
```

---

# Database Initialization

```bash
python -m src.setup_database
python -m pr_po.schema_migration
```

Run once for a new database.

---

# Running the Application

```bash
streamlit run src/streamlit_app.py
```

---

# Screenshots

Include screenshots of the Dashboard, Procurement Analysis, Human Review, Conversation Assistant, Purchase Requisition, Purchase Orders and LangSmith traces.

---

# License

This project is intended for educational, research and portfolio purposes unless otherwise specified by the repository license.
