"""AIBEF Streamlit Dashboard."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import streamlit as st
import pandas as pd
import json
from datetime import datetime

from core.config import CONFIG, FrameworkConfig
from pipelines.orchestrator import PipelineOrchestrator


st.set_page_config(
    page_title="AIBEF - AI Bibliometric Dataset Engineering Framework",
    page_icon="bibliometrics",
    layout="wide",
)

st.title("AIBEF - AI Bibliometric Dataset Engineering Framework")
st.markdown("---")

# Sidebar
st.sidebar.header("Configuration")
input_dir = st.sidebar.text_input("Input Directory", str(CONFIG.input_dir))
output_dir = st.sidebar.text_input("Output Directory", str(CONFIG.output_dir))

if st.sidebar.button("Run Full Pipeline", type="primary"):
    st.session_state["running"] = True
    st.session_state["input_dir"] = input_dir
    st.session_state["output_dir"] = output_dir

# Main content
tab1, tab2, tab3, tab4 = st.tabs(["Pipeline", "Results", "Validation", "Logs"])

with tab1:
    st.header("Pipeline Status")
    if st.session_state.get("running"):
        config = FrameworkConfig()
        config.input_dir = Path(st.session_state.get("input_dir", str(CONFIG.input_dir)))
        config.output_dir = Path(st.session_state.get("output_dir", str(CONFIG.output_dir)))
        
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        steps = [
            "Import", "Merge", "Deduplicate", "Validate",
            "Clean & Harmonize", "Bibliometrix Compat",
            "Bibliometrix Validation", "PRISMA", "Synchronization",
            "Quality Check", "Export"
        ]
        
        try:
            orchestrator = PipelineOrchestrator(config)
            state = orchestrator.run()
            st.session_state["state"] = state
            st.session_state["running"] = False
            progress_bar.progress(100)
            status_text.text("Pipeline complete!")
            st.success("Pipeline completed successfully!")
        except Exception as e:
            st.error(f"Pipeline failed: {e}")
            st.session_state["running"] = False
    else:
        st.info("Configure settings and click 'Run Full Pipeline' to start.")

with tab2:
    st.header("Results")
    state = st.session_state.get("state")
    if state:
        col1, col2, col3 = st.columns(3)
        col1.metric("Total Imported", state.stats.total_imported)
        col2.metric("After Merge", state.stats.after_merge)
        col3.metric("Final Dataset", state.stats.final_count)
        
        col4, col5, col6 = st.columns(3)
        col4.metric("Duplicates Removed", state.stats.duplicates_removed)
        col5.metric("Validation Issues", state.stats.validation_issues)
        col6.metric("Synchronized", "Yes" if state.stats.synchronized else "No")
        
        if state.validated_dataset is not None:
            st.subheader("Bibliometrix Compatible Dataset Preview")
            display_df = state.validated_dataset.head(20)
            internal_cols = [c for c in display_df.columns if c.startswith("__")]
            display_df = display_df.drop(columns=internal_cols, errors="ignore")
            st.dataframe(display_df, use_container_width=True)
    else:
        st.info("Run the pipeline to see results.")

with tab3:
    st.header("Validation Report")
    state = st.session_state.get("state")
    if state and state.prisma_data.get("quality_report"):
        qr = state.prisma_data["quality_report"]
        st.metric("Quality Score", f"{qr.get('overall_score', 'N/A')}/100")
        st.write(f"Grade: {qr.get('grade', 'N/A')}")
        
        checks = qr.get("checks", {})
        for name, data in checks.items():
            with st.expander(f"{name.replace('_', ' ').title()} - {data.get('status', 'N/A')}"):
                st.json(data)
    else:
        st.info("Run the pipeline to see validation results.")

with tab4:
    st.header("Pipeline Logs")
    state = st.session_state.get("state")
    if state and state.stage_log:
        for entry in reversed(state.stage_log):
            agent = entry.get("agent", "unknown")
            msg = entry.get("message", "")
            ts = entry.get("timestamp", "")
            st.text(f"[{ts}] {agent}: {msg}")
    else:
        st.info("No logs available yet.")

# Footer
st.markdown("---")
st.markdown("AIBEF v1.0.0 | AI Bibliometric Dataset Engineering Framework")
st.markdown("Fully local - No external APIs required")
