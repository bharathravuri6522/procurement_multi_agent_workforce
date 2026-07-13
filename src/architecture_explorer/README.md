# ForgeForce Architecture Explorer

A standalone, metadata-driven Streamlit application that explains the internal
mechanism of ForgeForce Procurement AI.

It does not invoke, import, or modify the production procurement, conversation,
persistence, LangGraph, or PR/PO business workflows.

## Install

Copy the complete folder into:

```text
src/architecture_explorer/
```

## Run

From the project `src` directory:

```powershell
streamlit run architecture_explorer/page.py
```

## Views

- Procurement Workflow
- Conversation Workflow
- PR → PO Workflow
- Shared Platform Services

The procurement view is supervisor-centered. It explains:

- why the Supervisor routes to each node;
- which Agent State fields the node reads;
- which database data it uses;
- its tools and calculations;
- the Agent State fields it updates;
- where control returns;
- the Supervisor's possible next routes.

## Isolation

This first version is intentionally independent. No changes are required in
`streamlit_app.py` or any production module.
