from __future__ import annotations

from pathlib import Path
import sys

CURRENT_DIR = Path(__file__).resolve().parent
SRC_DIR = CURRENT_DIR.parent

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import streamlit as st

from architecture_explorer.app import (
    render_architecture_explorer,
)


st.set_page_config(
    page_title="ForgeForce Architecture Explorer",
    page_icon="🧭",
    layout="wide",
)

render_architecture_explorer()
