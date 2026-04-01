from __future__ import annotations

import pandas as pd
import streamlit as st

from adobe_influencer.core.config import AppSettings
from adobe_influencer.pipelines.runner import PipelineRunner
from adobe_influencer.storage.database import DatabaseManager
from adobe_influencer.storage.repositories import Repository


st.set_page_config(page_title="Adobe Influencer Intelligence", layout="wide", initial_sidebar_state="expanded")


def get_settings() -> AppSettings:
    settings = AppSettings()
    settings.ensure_paths()
    return settings


def get_repo(settings: AppSettings) -> Repository:
    db = DatabaseManager(settings.database_url)
    db.create_all()
    return Repository(db)


def run_analysis(urls: list[str], use_mock_data: bool, enable_media_pipeline: bool, max_videos_per_creator: int) -> list:
    settings = get_settings()
    settings.use_mock_data = use_mock_data
    settings.enable_media_pipeline = enable_media_pipeline
    settings.max_videos_per_creator = max_videos_per_creator
    with PipelineRunner(settings) as runner:
        return runner.run(creator_urls=urls)


def inject_styles() -> None:
    """Load separate CSS files for sidebar and main content"""
    from pathlib import Path
    
    # Get the directory where this file is located
    current_dir = Path(__file__).parent
    
    # Load sidebar CSS
    sidebar_css_path = current_dir / "styles_sidebar.css"
    if sidebar_css_path.exists():
        sidebar_css = sidebar_css_path.read_text(encoding='utf-8')
    else:
        sidebar_css = ""
    
    # Load main content CSS
    main_css_path = current_dir / "styles_main.css"
    if main_css_path.exists():
        main_css = main_css_path.read_text(encoding='utf-8')
    else:
        main_css = ""
    
    # Inject both stylesheets
    st.markdown(
        f"""
        <style>
        /* ===== SIDEBAR STYLES ===== */
        {sidebar_css}
        
        /* ===== MAIN CONTENT STYLES ===== */
        {main_css}
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_hero() -> None:
    st.markdown(
        """
        <div class="hero">
            <h1>Adobe Influencer Intelligence</h1>
            <p>Run automated creator analysis from Instagram and YouTube links, merge live platform evidence, and rank creators for Adobe Creative Cloud and Adobe Acrobat fit.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_metrics(recommendations: list) -> None:
    if not recommendations:
        return
    top = recommendations[0]
    total_citations = sum(len(item.evidence_snippets) for item in recommendations)
    cols = st.columns(4)
    cards = [
        ("Creators Ranked", str(len(recommendations))),
        ("Top Creator", top.creator_name),
        ("Top Brand Fit", f"{top.overall_brand_fit:.1f}"),
        ("Evidence Citations", str(total_citations)),
    ]
    for column, (label, value) in zip(cols, cards):
        column.markdown(
            f"""
            <div class="metric-card">
                <div class="metric-label">{label}</div>
                <div class="metric-value">{value}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )


def render_run_controls() -> None:
    st.sidebar.header("Pipeline Controls")
    st.sidebar.caption("✨ **Quick Start:** The demo data is already loaded below. Click 'Run Analysis' to reprocess it.")
    st.sidebar.caption("🔍 **Live Mode:** Uncheck 'Use mock demo data' to analyze real Instagram/YouTube URLs.")


def run_form() -> tuple[list[str], bool, bool, int, bool]:
    # Move the mock data toggle OUTSIDE the form so it updates immediately
    use_mock_data = st.sidebar.checkbox(
        "Use mock demo data", 
        value=st.session_state.get("use_mock_data", True),
        key="use_mock_data_toggle"
    )
    
    if use_mock_data:
        st.sidebar.info("💡 Uncheck above to enable custom URL input")
    else:
        st.sidebar.success("✅ Custom URL mode enabled - enter URLs below")
    
    st.sidebar.markdown("---")
    
    with st.sidebar.form("run_pipeline_form"):
        enable_media_pipeline = st.checkbox("Enable media downloads + transcription", value=st.session_state.get("enable_media_pipeline", False))
        max_videos_per_creator = st.slider("Max videos per creator", min_value=1, max_value=15, value=st.session_state.get("max_videos_per_creator", 5))
        
        raw_urls = st.text_area(
            "Creator URLs (one per line)",
            value=st.session_state.get("creator_urls_text", ""),
            height=180,
            placeholder="https://www.instagram.com/creator/\nhttps://www.youtube.com/@creator",
            disabled=use_mock_data,
            help="Enter Instagram profile URLs or YouTube channel URLs. Disabled when using mock data."
        )
        submitted = st.form_submit_button("Run Analysis", use_container_width=True)

    urls = [line.strip() for line in raw_urls.splitlines() if line.strip()]
    st.session_state["use_mock_data"] = use_mock_data
    st.session_state["enable_media_pipeline"] = enable_media_pipeline
    st.session_state["max_videos_per_creator"] = max_videos_per_creator
    st.session_state["creator_urls_text"] = raw_urls
    return urls, use_mock_data, enable_media_pipeline, max_videos_per_creator, submitted


def render_rankings(recommendations: list) -> None:
    if not recommendations:
        st.info("Run the pipeline from the sidebar to populate creator rankings.")
        return

    frame = pd.DataFrame([item.model_dump() for item in recommendations])
    ranking_frame = frame[
        ["creator_name", "handle", "overall_brand_fit", "acrobat_fit", "creative_cloud_fit", "recommended_campaign_angle"]
    ].rename(
        columns={
            "creator_name": "Creator",
            "handle": "Handle",
            "overall_brand_fit": "Overall",
            "acrobat_fit": "Acrobat",
            "creative_cloud_fit": "Creative Cloud",
            "recommended_campaign_angle": "Campaign Angle",
        }
    )

    col_left, col_right = st.columns([1.6, 1])
    with col_left:
        st.subheader("Ranked Creators")
        st.dataframe(ranking_frame, use_container_width=True, hide_index=True)
    with col_right:
        st.subheader("Score Comparison")
        # Only render chart if we have valid score data
        if len(frame) > 0 and all(col in frame.columns for col in ["overall_brand_fit", "acrobat_fit", "creative_cloud_fit"]):
            chart_df = frame.set_index("creator_name")[["overall_brand_fit", "acrobat_fit", "creative_cloud_fit"]]
            # Filter out any NaN or infinite values
            chart_df = chart_df.replace([float('inf'), float('-inf')], 0).fillna(0)
            st.bar_chart(chart_df)
        else:
            st.info("No chart data available")


def render_creator_detail(recommendations: list) -> None:
    if not recommendations:
        return

    st.subheader("Creator Explorer")
    options = {f"{item.creator_name} ({item.handle})": item for item in recommendations}
    selected_label = st.selectbox("Inspect creator", list(options.keys()))
    selected = options[selected_label]

    top_left, top_right = st.columns([1.2, 1])
    with top_left:
        st.markdown('<div class="section-card">', unsafe_allow_html=True)
        st.markdown(f"### {selected.creator_name}")
        st.write(selected.audience_sentiment_summary)
        st.write(f"**Recommended angle:** {selected.recommended_campaign_angle}")
        st.write(f"**Risk flags:** {', '.join(selected.risk_flags) if selected.risk_flags else 'None'}")
        st.markdown("</div>", unsafe_allow_html=True)
    with top_right:
        st.markdown('<div class="section-card">', unsafe_allow_html=True)
        st.write("**Score breakdown**")
        score_df = pd.DataFrame(
            [{"Component": key.replace("_", " ").title(), "Score": value} for key, value in selected.score_breakdown.items()]
        )
        st.dataframe(score_df, use_container_width=True, hide_index=True)
        st.markdown("</div>", unsafe_allow_html=True)

    tab_overview, tab_themes, tab_evidence = st.tabs(["Questions", "Themes", "Evidence"])
    with tab_overview:
        if selected.recurring_audience_questions:
            for question in selected.recurring_audience_questions:
                st.write(f"- {question}")
        else:
            st.write("No recurring audience questions were captured in this run.")

    with tab_themes:
        if selected.content_theme_map:
            theme_frame = pd.DataFrame(selected.content_theme_map)
            st.dataframe(theme_frame, use_container_width=True, hide_index=True)
        else:
            st.write("No themes detected.")

    with tab_evidence:
        if selected.evidence_snippets:
            for snippet in selected.evidence_snippets:
                st.markdown(f"- {snippet}")
        else:
            st.write("No citation snippets available.")


def main() -> None:
    settings = get_settings()
    repo = get_repo(settings)
    inject_styles()
    render_hero()
    render_run_controls()

    urls, use_mock_data, enable_media_pipeline, max_videos_per_creator, submitted = run_form()
    if submitted:
        if not use_mock_data and not urls:
            st.sidebar.error("Provide at least one creator URL for live analysis.")
        else:
            with st.spinner("Running ingestion, scoring, evidence indexing, and report generation..."):
                recommendations = run_analysis(
                    urls=urls,
                    use_mock_data=use_mock_data,
                    enable_media_pipeline=enable_media_pipeline,
                    max_videos_per_creator=max_videos_per_creator,
                )
            st.session_state["latest_run_count"] = len(recommendations)
            st.success(f"Pipeline complete. Ranked {len(recommendations)} creators.")

    recommendations = repo.list_recommendations()
    render_metrics(recommendations)
    st.write("")
    render_rankings(recommendations)
    st.write("")
    render_creator_detail(recommendations)


if __name__ == "__main__":
    main()
