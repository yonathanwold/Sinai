"""Streamlit dashboard for AgriSense AI."""

from __future__ import annotations

import sys
from html import escape
from pathlib import Path

import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.services.ai_recommender import AIRecommendationService
from app.services.crop_engine import CropScoringEngine
from app.services.normalization import normalize_environment
from app.services.sensor_ingestion import REGION_PROFILES, SensorIngestionService
from app.utils.config import get_config
from app.utils.formatting import fmt_number, humanize_label


st.set_page_config(
    page_title="AgriSense AI",
    page_icon="A",
    layout="wide",
    initial_sidebar_state="expanded",
)


def inject_styles() -> None:
    st.markdown(
        """
        <style>
          :root {
            --surface: #ffffff;
            --page: #f3f6ef;
            --text: #172017;
            --muted: #5c675b;
            --line: #dfe6d8;
            --primary: #2f6f44;
            --primary-soft: #e1eee3;
            --warning: #b86b20;
            --danger: #9d342f;
          }

          .stApp {
            background: var(--page);
            color: var(--text);
            font-family: Aptos, "IBM Plex Sans", Calibri, sans-serif;
          }

          [data-testid="stSidebar"] {
            background: #fbfcf8;
            border-right: 1px solid var(--line);
          }

          h1, h2, h3 {
            color: var(--text);
            letter-spacing: 0;
          }

          div[data-testid="stMetric"] {
            background: var(--surface);
            border: 1px solid var(--line);
            border-radius: 8px;
            padding: 16px;
            min-height: 116px;
          }

          .section {
            background: var(--surface);
            border: 1px solid var(--line);
            border-radius: 8px;
            padding: 22px;
            margin: 12px 0 18px 0;
          }

          .crop-row {
            border: 1px solid var(--line);
            border-radius: 8px;
            padding: 16px;
            background: #fbfcf8;
            min-height: 260px;
          }

          .crop-name {
            font-size: 1.08rem;
            font-weight: 700;
            margin-bottom: 4px;
          }

          .muted {
            color: var(--muted);
          }

          .status-pill {
            display: inline-block;
            border-radius: 6px;
            padding: 3px 7px;
            background: var(--primary-soft);
            color: var(--primary);
            font-size: 0.82rem;
            font-weight: 700;
            margin-right: 6px;
          }

          .price {
            border: 1px solid var(--line);
            border-radius: 8px;
            padding: 18px;
            background: #ffffff;
            min-height: 188px;
          }

          .price strong {
            font-size: 1.2rem;
          }

          .stButton button {
            border-radius: 8px;
            border: 1px solid var(--primary);
          }
        </style>
        """,
        unsafe_allow_html=True,
    )


def html_list(items: list[str]) -> str:
    return "".join(f"<li>{escape(item)}</li>" for item in items)


def condition_metric(label: str, value: str, help_text: str) -> None:
    st.metric(label=label, value=value, help=help_text)


def render_crop(score_item, rank: int) -> None:
    crop = score_item.crop
    category = ", ".join(humanize_label(item) for item in crop.category)
    caution_items = score_item.cautions or ["No major cautions for this site profile."]
    st.markdown(
        f"""
        <div class="crop-row">
          <div class="crop-name">{rank}. {escape(crop.name)}</div>
          <div class="muted">{escape(category)} | {crop.time_to_harvest_days} days to harvest | resilience {crop.resilience_rating}/5</div>
          <p><strong>Use case:</strong> {escape(score_item.suggested_use_case)}</p>
          <p><strong>Suitability score:</strong> {score_item.score_percent}/100</p>
          <p><strong>Why this ranks well:</strong></p>
          <ul>{html_list(score_item.reasons[:3])}</ul>
          <p><strong>Cautions:</strong></p>
          <ul>{html_list(caution_items)}</ul>
        </div>
        """,
        unsafe_allow_html=True,
    )


def main() -> None:
    inject_styles()

    config = get_config()
    sensor_service = SensorIngestionService(config)
    crop_engine = CropScoringEngine.from_json()
    recommender = AIRecommendationService(config)

    with st.sidebar:
        st.header("Deployment")
        organization = st.selectbox(
            "Customer profile",
            [
                "International NGO",
                "County emergency management",
                "Agricultural cooperative",
                "Public health agency",
            ],
        )
        site_name = st.text_input("Deployment site", "Sinai Edge Node A-17")
        region = st.selectbox("Field region", list(REGION_PROFILES.keys()))
        disaster_context = st.selectbox(
            "Planning context",
            [
                "Hurricane recovery",
                "Flood disruption",
                "Conflict supply interruption",
                "Heat and drought response",
                "General resilience planning",
            ],
        )
        data_mode_label = st.radio(
            "Data source",
            ["Demo/mock mode", "Live sensor mode"],
            index=0,
        )
        st.caption(
            "Live mode reads the Pi sensors when available and fills missing values with mock data for demo safety."
        )
        if st.button("Refresh reading", use_container_width=True):
            st.rerun()

    mode = "mock" if data_mode_label == "Demo/mock mode" else "live"
    snapshot = sensor_service.read_environment(mode=mode, site_name=site_name, region=region)
    environment = normalize_environment(snapshot)
    ranked_crops = crop_engine.rank_crops(environment)
    emergency_crops = crop_engine.emergency_candidates()
    narrative = recommender.recommend(
        environment=environment,
        ranked_crops=ranked_crops,
        emergency_crop_names=[crop.name for crop in emergency_crops[:4]],
        disaster_context=disaster_context,
    )

    st.title("AgriSense AI")
    st.subheader("Disaster-Resilient Food Intelligence Platform")
    st.write(
        f"{organization} deployment for {site_name}. Local sensor data is converted into crop decisions "
        "that can keep working when internet access or supply chains fail."
    )

    source_label = "Mock data" if snapshot.source == "mock" else snapshot.source
    st.markdown(
        f"""
        <span class="status-pill">{escape(source_label)}</span>
        <span class="status-pill">{escape(region)}</span>
        <span class="status-pill">{escape(disaster_context)}</span>
        """,
        unsafe_allow_html=True,
    )

    st.markdown("### Current environmental conditions")
    cols = st.columns(5)
    with cols[0]:
        condition_metric(
            "Temperature",
            f"{environment.temperature_label.title()} | {fmt_number(snapshot.temperature_c, ' C')}",
            "cold <10, cool 10-17, warm 18-29, hot 30+",
        )
    with cols[1]:
        condition_metric(
            "Light",
            f"{environment.light_label.title()} | {fmt_number(snapshot.light_lux, ' lux', 0)}",
            "low <1k lux, medium 1k-10k, high 10k+",
        )
    with cols[2]:
        condition_metric(
            "UV",
            f"{environment.uv_label.title()} | {fmt_number(snapshot.uv_index, '', 1)}",
            "low <3, medium 3-5.9, high 6+",
        )
    with cols[3]:
        condition_metric(
            "Air quality",
            f"{environment.air_quality_label.title()} | {fmt_number(snapshot.air_quality_eco2_ppm, ' ppm', 0)}",
            "eCO2 and TVOC are converted into good, fair, or poor.",
        )
    with cols[4]:
        condition_metric(
            "Pressure",
            f"{environment.pressure_trend.title()} | {fmt_number(snapshot.pressure_hpa, ' hPa', 1)}",
            "trend compares the recent pressure history.",
        )

    left, right = st.columns([1.35, 0.95], gap="large")

    with left:
        st.markdown("### Recommended crops")
        crop_cols = st.columns(3)
        for idx, item in enumerate(ranked_crops[:3], start=1):
            with crop_cols[idx - 1]:
                render_crop(item, idx)

        st.markdown("### Rationale")
        st.markdown(
            f"""
            <div class="section">
              <p>{escape(narrative.overview)}</p>
              <ul>{html_list(narrative.top_crop_explanations)}</ul>
            </div>
            """,
            unsafe_allow_html=True,
        )

        st.markdown("### Emergency crop suggestions")
        emergency_cols = st.columns(4)
        for idx, crop in enumerate(emergency_crops[:4]):
            with emergency_cols[idx]:
                st.markdown(
                    f"""
                    <div class="section">
                      <strong>{escape(crop.name)}</strong><br>
                      <span class="muted">{crop.time_to_harvest_days} days | resilience {crop.resilience_rating}/5</span>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

    with right:
        st.markdown("### Resilience insights")
        st.markdown(
            f'<div class="section"><ul>{html_list(narrative.resilience_insights)}</ul></div>',
            unsafe_allow_html=True,
        )

        st.markdown("### Cautions")
        st.markdown(
            f'<div class="section"><ul>{html_list(narrative.cautions)}</ul></div>',
            unsafe_allow_html=True,
        )

        st.markdown("### Why this matters")
        st.markdown(
            """
            <div class="section">
              <p>
                AgriSense AI is designed for NGOs, governments, agricultural co-ops,
                and disaster agencies that need local food decisions when central
                supply chains, cloud dashboards, or field connectivity are unreliable.
              </p>
              <p>
                Each deployment site can run as an edge node, combining local sensing
                with AI-ready recommendations and fleet analytics when connectivity returns.
              </p>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.markdown("### SaaS packaging mock")
    pricing_cols = st.columns(3)
    pricing = [
        ("Starter", "$199/site/mo", "Single edge deployment, mock analytics, crop recommendations."),
        ("Pro", "$799/site/mo", "Multi-site monitoring, local model support, exports for relief teams."),
        ("Enterprise", "Custom", "Government and NGO fleet management, sensor kits, implementation support."),
    ]
    for col, (name, price, description) in zip(pricing_cols, pricing):
        with col:
            st.markdown(
                f"""
                <div class="price">
                  <strong>{escape(name)}</strong>
                  <h3>{escape(price)}</h3>
                  <p>{escape(description)}</p>
                </div>
                """,
                unsafe_allow_html=True,
            )

    with st.expander("Sensor diagnostics"):
        st.json(snapshot.to_display_dict())
        if snapshot.warnings:
            st.warning(" | ".join(snapshot.warnings))
        else:
            st.success("All selected readings available.")


if __name__ == "__main__":
    main()
