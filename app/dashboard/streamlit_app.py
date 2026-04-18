"""Streamlit dashboard for Sinai."""

from __future__ import annotations

import sys
from html import escape
from pathlib import Path
import socket

import pandas as pd
import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.services.ai_recommender import AIRecommendationService
from app.services.crop_engine import CropScoringEngine
from app.services.local_ai_advisor import LocalAIAdvisorService
from app.services.normalization import normalize_environment
from app.services.sensor_ingestion import REGION_PROFILES, SensorIngestionService
from app.utils.config import AppConfig, get_config
from app.utils.formatting import fmt_number, humanize_label


st.set_page_config(
    page_title="Sinai",
    page_icon="S",
    layout="wide",
    initial_sidebar_state="expanded",
)


def inject_styles() -> None:
    st.markdown(
        """
        <style>
          :root {
            --bg: #e8f3e5;
            --bg-soft: #f6fbf3;
            --surface: #ffffff;
            --surface-soft: #f3f9ef;
            --ink: #131913;
            --muted: #566656;
            --line: #ccdccb;
            --green: #2f8c56;
            --green-dark: #1f5f37;
            --green-soft: #e4f2df;
          }

          [data-testid="stAppViewContainer"] {
            background:
              linear-gradient(180deg, rgba(255,255,255,0.72) 0%, rgba(255,255,255,0.2) 42%, rgba(255,255,255,0) 100%),
              linear-gradient(124deg, #e1efdd 0%, #eef7ea 46%, #e5f1e1 100%);
            position: relative;
            overflow-x: clip;
          }

          [data-testid="stAppViewContainer"]::before {
            content: "";
            position: fixed;
            top: -14vh;
            left: -10vw;
            width: 58vw;
            height: 42vh;
            background:
              radial-gradient(circle at 20% 38%, rgba(77, 154, 93, 0.22) 0%, rgba(77, 154, 93, 0) 54%),
              radial-gradient(circle at 74% 20%, rgba(114, 173, 126, 0.18) 0%, rgba(114, 173, 126, 0) 50%);
            pointer-events: none;
            z-index: 0;
            animation: ambientShiftA 24s ease-in-out infinite alternate;
          }

          [data-testid="stAppViewContainer"]::after {
            content: "";
            position: fixed;
            right: -15vw;
            bottom: -16vh;
            width: 60vw;
            height: 44vh;
            background:
              radial-gradient(circle at 36% 70%, rgba(93, 165, 110, 0.2) 0%, rgba(93, 165, 110, 0) 52%),
              radial-gradient(circle at 76% 22%, rgba(156, 197, 140, 0.16) 0%, rgba(156, 197, 140, 0) 52%);
            pointer-events: none;
            z-index: 0;
            animation: ambientShiftB 26s ease-in-out infinite alternate;
          }

          .stApp {
            color: var(--ink);
            font-family: Aptos, "IBM Plex Sans", Calibri, "Noto Sans", sans-serif;
            position: relative;
            z-index: 2;
          }

          .block-container {
            max-width: 1340px;
            padding-top: 0.56rem;
            padding-bottom: 1.6rem;
            position: relative;
            z-index: 3;
          }

          [data-testid="stSidebar"] {
            background: linear-gradient(180deg, #f8fcf6 0%, #eef8eb 100%);
            border-right: 1px solid var(--line);
          }

          [data-testid="stSidebar"] .block-container {
            padding-top: 0.5rem !important;
            padding-bottom: 1rem !important;
          }

          [data-testid="stSidebar"] h1,
          [data-testid="stSidebar"] h2,
          [data-testid="stSidebar"] h3,
          [data-testid="stSidebar"] p,
          [data-testid="stSidebar"] span,
          [data-testid="stSidebar"] label {
            color: var(--ink) !important;
          }

          [data-testid="stSidebar"] [data-testid="stWidgetLabel"] p {
            color: var(--ink) !important;
            font-weight: 600;
            margin-bottom: 4px;
          }

          [data-testid="stSidebar"] [data-baseweb="select"] > div,
          [data-testid="stSidebar"] [data-baseweb="input"] > div {
            background: #ffffff !important;
            border: 1px solid var(--line) !important;
            border-radius: 8px !important;
            box-shadow: none !important;
            min-height: 42px;
            transition: border-color 0.2s ease, box-shadow 0.2s ease;
          }

          [data-testid="stSidebar"] [data-baseweb="select"] > div:hover,
          [data-testid="stSidebar"] [data-baseweb="input"] > div:hover {
            border-color: #a9c7ae !important;
          }

          [data-testid="stSidebar"] [data-baseweb="select"] div,
          [data-testid="stSidebar"] [data-baseweb="input"] input {
            color: var(--ink) !important;
          }

          [data-testid="stSidebar"] [data-baseweb="select"] svg {
            fill: var(--muted) !important;
          }

          [data-testid="stSidebar"] .stCaption {
            color: var(--muted) !important;
          }

          h1, h2, h3 {
            color: var(--ink);
            letter-spacing: 0;
          }

          .reveal {
            opacity: 0;
            transform: translateY(12px);
            animation: revealUp 680ms cubic-bezier(0.2, 0.72, 0.2, 1) forwards;
          }

          .hero {
            display: grid;
            grid-template-columns: 1.05fr 0.95fr;
            gap: 14px;
            border: 1px solid var(--line);
            border-radius: 8px;
            background: linear-gradient(140deg, rgba(255,255,255,0.95) 0%, rgba(246,252,243,0.92) 100%);
            padding: 18px;
            margin-bottom: 10px;
            box-shadow: 0 10px 24px rgba(41, 84, 47, 0.08);
          }

          .hero-title {
            margin: 0;
            font-size: 1.86rem;
            line-height: 1.12;
            font-weight: 700;
            color: var(--ink);
          }

          .hero-copy {
            margin-top: 8px;
            margin-bottom: 10px;
            color: var(--muted);
            font-size: 1rem;
            line-height: 1.45;
          }

          .hero-chip-row {
            margin-top: 6px;
          }

          .chip {
            display: inline-block;
            margin-right: 6px;
            margin-bottom: 6px;
            border-radius: 6px;
            border: 1px solid var(--line);
            background: rgba(255,255,255,0.9);
            color: var(--ink);
            font-size: 0.79rem;
            font-weight: 600;
            padding: 4px 8px;
            transition: transform 0.2s ease, border-color 0.2s ease;
          }

          .chip:hover {
            transform: translateY(-1px);
            border-color: #b4cfb7;
          }

          .chip-green {
            border-color: #b3d0b8;
            background: #e4f2df;
            color: #255f38;
          }

          .hero-grid {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 9px;
          }

          .hero-info {
            border: 1px solid #d0e0cf;
            border-radius: 8px;
            padding: 10px 12px;
            background: rgba(250,255,247,0.86);
          }

          .hero-info-label {
            color: var(--muted);
            font-size: 0.79rem;
            margin-bottom: 3px;
          }

          .hero-info-value {
            color: var(--ink);
            font-size: 0.93rem;
            font-weight: 600;
          }

          .image-strip {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 10px;
            margin-bottom: 10px;
          }

          .image-card {
            border: 1px solid var(--line);
            border-radius: 8px;
            overflow: hidden;
            background: var(--surface);
            box-shadow: 0 2px 10px rgba(41, 84, 47, 0.07);
          }

          .image-frame {
            height: 162px;
            background-size: cover;
            background-position: center;
          }

          .image-meta {
            padding: 10px 12px;
          }

          .image-title {
            color: var(--ink);
            font-weight: 700;
            margin-bottom: 3px;
          }

          .image-copy {
            color: var(--muted);
            font-size: 0.86rem;
            line-height: 1.42;
          }

          .section-kicker {
            margin-top: 6px;
            margin-bottom: 6px;
            color: var(--ink);
            font-size: 1.05rem;
            font-weight: 700;
          }

          .action-strip {
            border: 1px solid var(--line);
            border-radius: 8px;
            background: linear-gradient(140deg, rgba(255,255,255,0.95) 0%, rgba(244,251,241,0.92) 100%);
            padding: 10px;
            margin: 2px 0 8px 0;
          }

          .condition-card {
            border: 1px solid var(--line);
            border-radius: 8px;
            background: linear-gradient(180deg, rgba(255,255,255,0.96) 0%, rgba(245,251,242,0.96) 100%);
            min-height: 116px;
            padding: 12px;
            box-shadow: 0 2px 10px rgba(44, 90, 50, 0.06);
            transition: transform 0.22s ease, border-color 0.22s ease, box-shadow 0.22s ease;
          }

          .condition-card:hover {
            transform: translateY(-2px);
            border-color: #a9c7ad;
            box-shadow: 0 10px 22px rgba(44, 90, 50, 0.12);
          }

          .condition-label {
            color: var(--muted);
            font-size: 0.8rem;
            margin-bottom: 7px;
          }

          .condition-value {
            color: var(--ink);
            font-size: 1.16rem;
            font-weight: 700;
            margin-bottom: 5px;
          }

          .condition-detail {
            color: var(--muted);
            font-size: 0.82rem;
            line-height: 1.34;
          }

          .panel {
            border: 1px solid var(--line);
            border-radius: 8px;
            background: linear-gradient(180deg, rgba(255,255,255,0.96) 0%, rgba(245,251,242,0.96) 100%);
            padding: 14px 16px;
            margin-bottom: 12px;
            box-shadow: 0 2px 10px rgba(41, 84, 47, 0.06);
          }

          .panel-title {
            margin: 0 0 8px 0;
            color: var(--ink);
            font-size: 1.03rem;
            font-weight: 700;
          }

          .panel-copy {
            color: var(--muted);
            margin: 0;
            line-height: 1.5;
          }

          .crop-card {
            border: 1px solid var(--line);
            border-radius: 8px;
            background: linear-gradient(180deg, rgba(252,255,250,0.96) 0%, rgba(240,248,236,0.96) 100%);
            min-height: 276px;
            padding: 12px;
            box-shadow: 0 2px 10px rgba(41, 84, 47, 0.05);
            transition: transform 0.22s ease, border-color 0.22s ease, box-shadow 0.22s ease;
          }

          .crop-card:hover {
            transform: translateY(-3px);
            border-color: #a9c7ad;
            box-shadow: 0 11px 23px rgba(41, 84, 47, 0.13);
          }

          .crop-rank {
            color: var(--muted);
            font-size: 0.78rem;
            margin-bottom: 2px;
            font-weight: 700;
          }

          .crop-name {
            color: var(--ink);
            font-size: 1.06rem;
            font-weight: 700;
            margin-bottom: 4px;
          }

          .crop-meta {
            color: var(--muted);
            font-size: 0.82rem;
            margin-bottom: 8px;
          }

          .score-line {
            display: flex;
            justify-content: space-between;
            color: var(--ink);
            font-size: 0.84rem;
            margin-bottom: 5px;
            font-weight: 600;
          }

          .score-rail {
            width: 100%;
            height: 7px;
            border-radius: 6px;
            background: #dce8d9;
            overflow: hidden;
            margin-bottom: 10px;
          }

          .score-fill {
            height: 7px;
            background: linear-gradient(90deg, #2f8c56 0%, #4aa86c 50%, #72bf83 100%);
            background-size: 200% 100%;
            animation: scoreFlow 4s linear infinite;
          }

          .crop-label {
            color: var(--ink);
            font-size: 0.83rem;
            font-weight: 700;
            margin-top: 5px;
            margin-bottom: 4px;
          }

          .crop-card ul {
            margin: 0 0 0 18px;
            color: var(--muted);
            font-size: 0.82rem;
            line-height: 1.4;
          }

          .emergency-tile {
            border: 1px solid var(--line);
            border-radius: 8px;
            background: linear-gradient(180deg, rgba(255,255,255,0.96) 0%, rgba(245,251,242,0.96) 100%);
            min-height: 108px;
            padding: 12px;
            transition: transform 0.2s ease, border-color 0.2s ease;
          }

          .emergency-tile:hover {
            transform: translateY(-2px);
            border-color: #a9c7ad;
          }

          .emergency-name {
            color: var(--ink);
            font-weight: 700;
            margin-bottom: 4px;
          }

          .emergency-meta {
            color: var(--muted);
            font-size: 0.84rem;
          }

          .pricing-card {
            border: 1px solid var(--line);
            border-radius: 8px;
            background: linear-gradient(180deg, rgba(255,255,255,0.98) 0%, rgba(245,251,242,0.96) 100%);
            min-height: 222px;
            padding: 16px;
            box-shadow: 0 2px 10px rgba(41, 84, 47, 0.05);
            position: relative;
            overflow: hidden;
            transition: transform 0.22s ease, border-color 0.22s ease, box-shadow 0.22s ease;
          }

          .pricing-card::before {
            content: "";
            position: absolute;
            top: 0;
            left: 0;
            right: 0;
            height: 3px;
            background: linear-gradient(90deg, #2f8c56 0%, #79b98a 100%);
          }

          .pricing-card:hover {
            transform: translateY(-3px);
            border-color: #abc8ae;
            box-shadow: 0 12px 24px rgba(41, 84, 47, 0.13);
          }

          .pricing-name {
            color: var(--ink);
            font-weight: 700;
            margin-bottom: 4px;
          }

          .pricing-price {
            font-size: 1.47rem;
            font-weight: 700;
            margin-bottom: 8px;
            color: var(--ink);
          }

          .pricing-copy {
            color: var(--muted);
            font-size: 0.9rem;
            line-height: 1.45;
          }

          .insight-list ul {
            margin: 0 0 0 18px;
            color: var(--muted);
            font-size: 0.9rem;
            line-height: 1.48;
          }

          .advisor-shell {
            border: 1px solid var(--line);
            border-radius: 8px;
            background: linear-gradient(180deg, rgba(255,255,255,0.98) 0%, rgba(245,251,242,0.96) 100%);
            padding: 14px 16px;
            margin-bottom: 10px;
            box-shadow: 0 2px 10px rgba(41, 84, 47, 0.06);
          }

          .advisor-note {
            color: var(--muted);
            line-height: 1.5;
            margin: 0;
          }

          .advisor-chip {
            display: inline-block;
            margin: 4px 6px 4px 0;
            border-radius: 6px;
            border: 1px solid #c8dbc7;
            background: #eef7eb;
            color: #255f38;
            font-size: 0.78rem;
            font-weight: 600;
            padding: 4px 8px;
          }

          .chat-card {
            border: 1px solid var(--line);
            border-radius: 8px;
            background: #ffffff;
            padding: 12px 14px;
            margin-bottom: 8px;
          }

          .chat-q {
            color: var(--ink);
            font-weight: 700;
            margin-bottom: 6px;
          }

          .chat-a {
            color: var(--muted);
            white-space: pre-wrap;
            line-height: 1.5;
          }

          .source-pill {
            display: inline-block;
            margin-top: 8px;
            border-radius: 6px;
            border: 1px solid #c8dbc7;
            background: #eef7eb;
            color: #255f38;
            font-size: 0.74rem;
            font-weight: 700;
            padding: 3px 7px;
          }

          .status-row {
            display: flex;
            align-items: center;
            gap: 8px;
            margin: 6px 0 4px;
            color: var(--ink);
            font-weight: 600;
          }

          .status-dot {
            width: 10px;
            height: 10px;
            border-radius: 999px;
            display: inline-block;
            box-shadow: 0 0 0 4px rgba(47, 140, 86, 0.11);
          }

          .status-good {
            background: #2f8c56;
          }

          .status-warn {
            background: #c57f2e;
            box-shadow: 0 0 0 4px rgba(197, 127, 46, 0.12);
          }

          .ops-grid {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 10px;
            margin-bottom: 10px;
          }

          .ops-card {
            border: 1px solid var(--line);
            border-radius: 8px;
            background: linear-gradient(180deg, rgba(255,255,255,0.98) 0%, rgba(245,251,242,0.96) 100%);
            padding: 12px;
            min-height: 124px;
          }

          .ops-title {
            color: var(--ink);
            font-weight: 700;
            margin-bottom: 4px;
          }

          .ops-copy {
            color: var(--muted);
            font-size: 0.9rem;
            line-height: 1.45;
            margin: 0;
          }

          .stButton button {
            border-radius: 8px;
            border: none;
            color: #ffffff;
            font-weight: 700;
            background: linear-gradient(90deg, #2f8c56 0%, #47a667 100%);
            background-size: 180% 100%;
            box-shadow: 0 10px 20px rgba(46, 122, 68, 0.2);
            transition: transform 0.22s ease, box-shadow 0.22s ease, filter 0.22s ease;
            animation: btnFlow 6.4s linear infinite;
          }

          .stButton button:hover {
            transform: translateY(-2px);
            box-shadow: 0 14px 25px rgba(46, 122, 68, 0.25);
            filter: saturate(1.04);
          }

          .stButton button:active {
            transform: translateY(0);
          }

          [data-testid="stDataFrame"] {
            border: 1px solid var(--line);
            border-radius: 8px;
            overflow: hidden;
            box-shadow: 0 2px 10px rgba(41, 84, 47, 0.05);
          }

          @keyframes revealUp {
            from {
              opacity: 0;
              transform: translateY(12px);
            }
            to {
              opacity: 1;
              transform: translateY(0);
            }
          }

          @keyframes ambientShiftA {
            0% { transform: translate3d(0, 0, 0) scale(1); }
            100% { transform: translate3d(3vw, 2.2vh, 0) scale(1.04); }
          }

          @keyframes ambientShiftB {
            0% { transform: translate3d(0, 0, 0) scale(1); }
            100% { transform: translate3d(-2.8vw, -2vh, 0) scale(1.05); }
          }

          @keyframes scoreFlow {
            0% { background-position: 0% 0%; }
            100% { background-position: 200% 0%; }
          }

          @keyframes btnFlow {
            0% { background-position: 0% 0%; }
            100% { background-position: 180% 0%; }
          }

          @media (prefers-reduced-motion: reduce) {
            .reveal,
            .score-fill,
            .stButton button,
            [data-testid="stAppViewContainer"]::before,
            [data-testid="stAppViewContainer"]::after {
              animation: none !important;
              opacity: 1 !important;
              transform: none !important;
            }
          }

          @media (max-width: 980px) {
            .hero {
              grid-template-columns: 1fr;
              padding: 15px 14px;
            }
            .hero-grid {
              grid-template-columns: 1fr 1fr;
              gap: 8px;
            }
            .hero-title {
              font-size: 1.52rem;
            }
            .image-strip {
              grid-template-columns: 1fr;
            }
            .ops-grid {
              grid-template-columns: 1fr;
            }
            .block-container {
              padding-top: 0.45rem;
            }
          }
        </style>
        """,
        unsafe_allow_html=True,
    )


def html_list(items: list[str]) -> str:
    return "".join(f"<li>{escape(item)}</li>" for item in items)


def delay_attr(delay_ms: int) -> str:
    return f' style="animation-delay:{delay_ms}ms;"'


def local_network_urls(port: int = 8501) -> list[str]:
    """Build likely URLs teammates can use on the same local network."""
    hosts: set[str] = {"localhost", "127.0.0.1"}
    try:
        hostname = socket.gethostname()
        hosts.add(hostname)
        for ip in socket.gethostbyname_ex(hostname)[2]:
            if ip and not ip.startswith("127."):
                hosts.add(ip)
    except OSError:
        pass

    ordered_hosts: list[str] = []
    for host in ("localhost", "127.0.0.1"):
        if host in hosts:
            ordered_hosts.append(host)
    ordered_hosts.extend(sorted(host for host in hosts if host not in {"localhost", "127.0.0.1"}))
    return [f"http://{host}:{port}" for host in ordered_hosts]


def render_header(
    organization: str,
    site_name: str,
    region: str,
    disaster_context: str,
    source_label: str,
) -> None:
    st.markdown(
        f"""
        <section class="hero reveal"{delay_attr(60)}>
          <div>
            <h1 class="hero-title">Sinai Local Food Intelligence</h1>
            <p class="hero-copy">
              Human-centered, disaster-ready crop guidance for communities that need fast and local food decisions.
            </p>
            <div class="hero-chip-row">
              <span class="chip chip-green">Source: {escape(source_label)}</span>
              <span class="chip">Sinai deployment profile</span>
              <span class="chip">Offline-ready mode</span>
              <span class="chip">AI recommendations enabled</span>
            </div>
          </div>
          <div class="hero-grid">
            <div class="hero-info">
              <div class="hero-info-label">Customer Profile</div>
              <div class="hero-info-value">{escape(organization)}</div>
            </div>
            <div class="hero-info">
              <div class="hero-info-label">Deployment Site</div>
              <div class="hero-info-value">{escape(site_name)}</div>
            </div>
            <div class="hero-info">
              <div class="hero-info-label">Region</div>
              <div class="hero-info-value">{escape(region)}</div>
            </div>
            <div class="hero-info">
              <div class="hero-info-label">Planning Context</div>
              <div class="hero-info-value">{escape(disaster_context)}</div>
            </div>
          </div>
        </section>
        """,
        unsafe_allow_html=True,
    )


def render_image_strip() -> None:
    st.markdown(
        """
        <section class="image-strip reveal" style="animation-delay:110ms;">
          <article class="image-card">
            <div class="image-frame" style="background-image:url('https://images.unsplash.com/photo-1464226184884-fa280b87c399?auto=format&fit=crop&w=1400&q=80');"></div>
            <div class="image-meta">
              <div class="image-title">Nature-Aligned Planning</div>
              <div class="image-copy">Prioritize crops that match local light, heat, and air conditions to reduce failure risk.</div>
            </div>
          </article>
          <article class="image-card">
            <div class="image-frame" style="background-image:url('https://images.unsplash.com/photo-1501004318641-b39e6451bec6?auto=format&fit=crop&w=1400&q=80');"></div>
            <div class="image-meta">
              <div class="image-title">Community-Centered Outcomes</div>
              <div class="image-copy">Use emergency and resilient crop mixes to protect food access for families during disruption windows.</div>
            </div>
          </article>
        </section>
        """,
        unsafe_allow_html=True,
    )


def render_condition_card(title: str, label: str, raw_value: str, rule_hint: str, delay_ms: int) -> None:
    st.markdown(
        f"""
        <div class="condition-card reveal"{delay_attr(delay_ms)}>
          <div class="condition-label">{escape(title)}</div>
          <div class="condition-value">{escape(label)}</div>
          <div class="condition-detail">{escape(raw_value)}</div>
          <div class="condition-detail">{escape(rule_hint)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_action_strip() -> None:
    st.markdown(
        '<div class="section-kicker reveal" style="animation-delay:140ms;">Field Actions</div>',
        unsafe_allow_html=True,
    )
    st.markdown('<div class="action-strip reveal" style="animation-delay:170ms;">', unsafe_allow_html=True)
    action_cols = st.columns(4)
    actions = [
        ("Run 72h Drill", "Prepared a 72-hour disruption scenario brief for this site."),
        ("Export Site Brief", "Site recommendation summary is ready for stakeholders."),
        ("Dispatch Seed Plan", "Emergency planting list queued for local teams."),
        ("Sync Offline Cache", "Latest recommendations pinned for low-connectivity operations."),
    ]
    for idx, (label, message) in enumerate(actions):
        with action_cols[idx]:
            if st.button(label, key=f"action_{idx}", use_container_width=True):
                st.toast(message)
    st.markdown("</div>", unsafe_allow_html=True)


def render_crop_card(score_item, rank: int, delay_ms: int) -> None:
    crop = score_item.crop
    category = ", ".join(humanize_label(item) for item in crop.category)
    cautions = score_item.cautions or ["No major cautions for current field profile."]
    st.markdown(
        f"""
        <div class="crop-card reveal"{delay_attr(delay_ms)}>
          <div class="crop-rank">Rank {rank}</div>
          <div class="crop-name">{escape(crop.name)}</div>
          <div class="crop-meta">{escape(category)} | {crop.time_to_harvest_days} days | resilience {crop.resilience_rating}/5</div>
          <div class="score-line">
            <span>Suitability Score</span><span>{score_item.score_percent}/100</span>
          </div>
          <div class="score-rail"><div class="score-fill" style="width: {score_item.score_percent}%;"></div></div>
          <div class="crop-label">Recommended use case</div>
          <div class="crop-meta">{escape(score_item.suggested_use_case)}</div>
          <div class="crop-label">Why this crop</div>
          <ul>{html_list(score_item.reasons[:3])}</ul>
          <div class="crop-label">Cautions</div>
          <ul>{html_list(cautions[:2])}</ul>
        </div>
        """,
        unsafe_allow_html=True,
    )


def build_ranking_table(ranked_crops: list) -> pd.DataFrame:
    rows: list[dict[str, str | int]] = []
    for idx, item in enumerate(ranked_crops[:10], start=1):
        rows.append(
            {
                "Rank": idx,
                "Crop": item.crop.name,
                "Score": item.score_percent,
                "Harvest (days)": item.crop.time_to_harvest_days,
                "Resilience": item.crop.resilience_rating,
                "Use Case": item.suggested_use_case.title(),
            }
        )
    return pd.DataFrame(rows)


def build_llm_context(environment, ranked_crops, narrative) -> dict[str, object]:
    return {
        "environment": environment.labels(),
        "top_crops": [
            {
                "name": item.crop.name,
                "score": item.score_percent,
                "harvest_days": item.crop.time_to_harvest_days,
                "use_case": item.suggested_use_case,
            }
            for item in ranked_crops[:3]
        ],
        "cautions": narrative.cautions,
    }


def render_local_ai_tab(
    advisor_service: LocalAIAdvisorService,
    config: AppConfig,
    context: dict[str, object],
    environment,
    ranked_crops,
    narrative,
) -> None:
    status_ok, status_message = advisor_service.health()
    status_class = "status-good" if status_ok else "status-warn"
    status_label = "Local model online" if status_ok else "Fallback mode active"
    st.markdown(
        f"""
        <div class="advisor-shell reveal" style="animation-delay:70ms;">
          <h3 class="panel-title">Local LLM Advisor</h3>
          <p class="advisor-note">
            Ask Sinai Local AI how to interpret your site profile and convert it into practical field actions.
          </p>
          <div class="status-row">
            <span class="status-dot {status_class}"></span>
            <span>{status_label}</span>
          </div>
          <p class="advisor-note">{escape(status_message)}</p>
          <span class="advisor-chip">Works with local model when available</span>
          <span class="advisor-chip">Falls back to deterministic offline guidance</span>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if not status_ok:
        st.caption(
            "Tip: install a lightweight local model on the Pi with "
            "`ollama pull llama3.2:1b`, then set `OLLAMA_HOST` and `OLLAMA_MODEL`."
        )
    elif config.ollama_host:
        st.caption(
            f"Connected to `{config.ollama_host}` with model target `{config.ollama_model}`."
        )

    prompt_cols = st.columns(3)
    suggested_prompts = [
        "How should we prioritize crops for the next two weeks?",
        "What should field teams do first if weather gets worse?",
        "How do we explain this plan to community partners?",
    ]
    for idx, prompt in enumerate(suggested_prompts):
        with prompt_cols[idx]:
            if st.button(prompt, key=f"prompt_{idx}", use_container_width=True):
                st.session_state["advisor_question"] = prompt

    question = st.text_area(
        "Ask Sinai Local AI",
        key="advisor_question",
        height=110,
        placeholder="Example: We have a flood recovery zone with limited labor. What should we plant first and why?",
    )

    ask_col, clear_col = st.columns([0.7, 0.3])
    with ask_col:
        ask_now = st.button("Ask Local AI", key="ask_local_ai", use_container_width=True)
    with clear_col:
        clear_history = st.button("Clear History", key="clear_local_ai", use_container_width=True)

    if clear_history:
        st.session_state["advisor_history"] = []
        st.session_state["advisor_question"] = ""
        st.rerun()

    if ask_now:
        answer, source = advisor_service.ask(
            question=question,
            environment=environment,
            top_scores=ranked_crops[:3],
            cautions=narrative.cautions,
        )
        st.session_state["advisor_history"].append(
            {
                "question": question.strip(),
                "answer": answer,
                "source": source,
            }
        )
        st.session_state["advisor_question"] = ""
        st.rerun()

    if st.session_state["advisor_history"]:
        st.markdown("### Recent AI Guidance")
        for item in reversed(st.session_state["advisor_history"]):
            source_label = "Local LLM" if item["source"] == "local_llm" else "Offline fallback"
            st.markdown(
                f"""
                <div class="chat-card">
                  <div class="chat-q">Question: {escape(item["question"])}</div>
                  <div class="chat-a">{escape(item["answer"])}</div>
                  <span class="source-pill">{escape(source_label)}</span>
                </div>
                """,
                unsafe_allow_html=True,
            )
    else:
        st.info("No questions asked yet. Use a suggested prompt or type your own question.")

    st.markdown("### Current context sent to advisor")
    st.json(context)


def render_edge_deployment_tab(
    advisor_service: LocalAIAdvisorService,
    config: AppConfig,
    site_name: str,
) -> None:
    llm_online, llm_message = advisor_service.health()
    status_class = "status-good" if llm_online else "status-warn"
    status_label = "Ollama mini ready" if llm_online else "LLM fallback only"

    st.markdown(
        f"""
        <div class="panel reveal"{delay_attr(80)}>
          <h3 class="panel-title">Portable Offline Deployment</h3>
          <p class="panel-copy">
            Sinai can run as a local decision platform on one Raspberry Pi:
            sensors + crop scoring + local LLM + browser dashboard for nearby users.
          </p>
          <div class="status-row">
            <span class="status-dot {status_class}"></span>
            <span>{status_label}</span>
          </div>
          <p class="panel-copy">{escape(llm_message)}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown(
        """
        <div class="ops-grid reveal" style="animation-delay:150ms;">
          <article class="ops-card">
            <div class="ops-title">What Users Experience</div>
            <p class="ops-copy">
              Teams connect to the Pi over local Wi-Fi or hotspot mode, open Sinai in a browser,
              review live conditions, and ask the Local LLM Advisor for planning guidance.
            </p>
          </article>
          <article class="ops-card">
            <div class="ops-title">Reliability Model</div>
            <p class="ops-copy">
              Sensor ingestion and crop scoring remain deterministic. The local LLM explains the decision logic
              and supports field Q&A, while fallback guidance stays available if the model is offline.
            </p>
          </article>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown("### Device Access URLs")
    st.caption("Open one of these from phones/laptops connected to the same network as the Pi.")
    for url in local_network_urls(port=8501):
        st.code(url, language="text")

    st.markdown("### Raspberry Pi Quick Setup (Ollama mini + Sinai)")
    st.code(
        """sudo apt update && sudo apt upgrade -y
curl -fsSL https://ollama.com/install.sh | sh
ollama pull llama3.2:1b

python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -r requirements-hardware.txt

export OLLAMA_HOST=http://127.0.0.1:11434
export OLLAMA_MODEL=llama3.2:1b
export SINAI_FORCE_MOCK=false
streamlit run app/dashboard/streamlit_app.py --server.address 0.0.0.0 --server.port 8501""",
        language="bash",
    )

    st.markdown("### Optional service mode (boots automatically)")
    st.code(
        f"""# /etc/systemd/system/sinai-dashboard.service
[Unit]
Description=Sinai Streamlit Dashboard
After=network-online.target ollama.service
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=/home/pi/Sinai
Environment=OLLAMA_HOST=http://127.0.0.1:11434
Environment=OLLAMA_MODEL={config.ollama_model}
Environment=SINAI_FORCE_MOCK=false
ExecStart=/home/pi/Sinai/.venv/bin/streamlit run app/dashboard/streamlit_app.py --server.address 0.0.0.0 --server.port 8501
Restart=always
User=pi

[Install]
WantedBy=multi-user.target""",
        language="ini",
    )
    st.info(
        f"Site '{site_name}' can now be presented as a multi-user offline intelligence node for NGOs, co-ops, and response teams."
    )


def render_dashboard_tab(
    snapshot,
    environment,
    ranked_crops,
    emergency_crops,
    narrative,
    organization: str,
    site_name: str,
    region: str,
    disaster_context: str,
) -> None:
    source_label = "Mock data" if snapshot.source == "mock" else snapshot.source
    render_header(
        organization=organization,
        site_name=site_name,
        region=region,
        disaster_context=disaster_context,
        source_label=source_label,
    )
    render_image_strip()
    render_action_strip()

    st.markdown(
        '<div class="section-kicker reveal" style="animation-delay:210ms;">Operational Environment Snapshot</div>',
        unsafe_allow_html=True,
    )
    metric_cols = st.columns(5)
    with metric_cols[0]:
        render_condition_card(
            "Temperature",
            environment.temperature_label.title(),
            f"Current: {fmt_number(snapshot.temperature_c, ' C')}",
            "Bands: cold <10, cool 10-17, warm 18-29, hot 30+",
            250,
        )
    with metric_cols[1]:
        render_condition_card(
            "Light",
            environment.light_label.title(),
            f"Current: {fmt_number(snapshot.light_lux, ' lux', 0)}",
            "Bands: low <1k, medium 1k-10k, high 10k+",
            290,
        )
    with metric_cols[2]:
        render_condition_card(
            "UV",
            environment.uv_label.title(),
            f"Current: {fmt_number(snapshot.uv_index, '', 1)}",
            "Bands: low <3, medium 3-5.9, high 6+",
            330,
        )
    with metric_cols[3]:
        render_condition_card(
            "Air Quality",
            environment.air_quality_label.title(),
            f"Current eCO2: {fmt_number(snapshot.air_quality_eco2_ppm, ' ppm', 0)}",
            "Derived from eCO2 and TVOC tolerance bands",
            370,
        )
    with metric_cols[4]:
        render_condition_card(
            "Pressure Trend",
            environment.pressure_trend.title(),
            f"Current: {fmt_number(snapshot.pressure_hpa, ' hPa', 1)}",
            "Trend from recent pressure history samples",
            410,
        )

    main_col, side_col = st.columns([1.5, 0.95], gap="large")

    with main_col:
        st.markdown(
            '<div class="section-kicker reveal" style="animation-delay:430ms;">Top Crop Strategy</div>',
            unsafe_allow_html=True,
        )
        crop_cols = st.columns(3)
        for idx, item in enumerate(ranked_crops[:3], start=1):
            with crop_cols[idx - 1]:
                render_crop_card(item, idx, 460 + (idx * 45))

        st.markdown(
            '<div class="section-kicker reveal" style="animation-delay:600ms;">Portfolio Ranking</div>',
            unsafe_allow_html=True,
        )
        ranking_table = build_ranking_table(ranked_crops)
        st.dataframe(ranking_table, use_container_width=True, hide_index=True)

        st.markdown(
            '<div class="section-kicker reveal" style="animation-delay:640ms;">Emergency Planting Options</div>',
            unsafe_allow_html=True,
        )
        emergency_cols = st.columns(4)
        for idx, crop in enumerate(emergency_crops[:4]):
            with emergency_cols[idx]:
                st.markdown(
                    f"""
                    <div class="emergency-tile reveal"{delay_attr(670 + (idx * 40))}>
                      <div class="emergency-name">{escape(crop.name)}</div>
                      <div class="emergency-meta">{crop.time_to_harvest_days} days to harvest</div>
                      <div class="emergency-meta">Resilience {crop.resilience_rating}/5</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

        st.markdown(
            '<div class="section-kicker reveal" style="animation-delay:810ms;">Recommendation Rationale</div>',
            unsafe_allow_html=True,
        )
        st.markdown(
            f"""
            <div class="panel insight-list reveal"{delay_attr(840)}>
              <h3 class="panel-title">Top decision logic for this site</h3>
              <p class="panel-copy">{escape(narrative.overview)}</p>
              <ul>{html_list(narrative.top_crop_explanations)}</ul>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with side_col:
        st.markdown(
            '<div class="section-kicker reveal" style="animation-delay:500ms;">Resilience Insights</div>',
            unsafe_allow_html=True,
        )
        st.markdown(
            f"""
            <div class="panel insight-list reveal"{delay_attr(530)}>
              <h3 class="panel-title">Operational guidance</h3>
              <ul>{html_list(narrative.resilience_insights)}</ul>
            </div>
            """,
            unsafe_allow_html=True,
        )

        st.markdown(
            f"""
            <div class="panel insight-list reveal"{delay_attr(600)}>
              <h3 class="panel-title">Current cautions</h3>
              <ul>{html_list(narrative.cautions)}</ul>
            </div>
            """,
            unsafe_allow_html=True,
        )

        st.markdown(
            """
            <div class="panel insight-list reveal" style="animation-delay:670ms;">
              <h3 class="panel-title">People-First Guidance</h3>
              <ul>
                <li>Prioritize quick-harvest crops for households with immediate food pressure.</li>
                <li>Coordinate planting windows with local volunteers and water access reliability.</li>
                <li>Use the Local LLM Advisor tab to translate data into clear action plans for non-technical teams.</li>
              </ul>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.markdown(
        '<div class="section-kicker reveal" style="animation-delay:900ms;">SaaS Packaging Mock</div>',
        unsafe_allow_html=True,
    )
    pricing_cols = st.columns(3)
    pricing = [
        (
            "Starter",
            "$199/site/mo",
            "Single deployment with mock analytics, sensor dashboard, and baseline recommendation engine.",
        ),
        (
            "Pro",
            "$799/site/mo",
            "Multi-site monitoring, offline reporting, local AI integration, and export workflows for field teams.",
        ),
        (
            "Enterprise",
            "Custom",
            "Fleet governance, procurement support, implementation services, and agency-grade deployment operations.",
        ),
    ]
    for idx, (col, (name, price, copy)) in enumerate(zip(pricing_cols, pricing)):
        with col:
            st.markdown(
                f"""
                <div class="pricing-card reveal"{delay_attr(930 + (idx * 55))}>
                  <div class="pricing-name">{escape(name)}</div>
                  <div class="pricing-price">{escape(price)}</div>
                  <div class="pricing-copy">{escape(copy)}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

    with st.expander("Sensor diagnostics and raw payload"):
        st.json(snapshot.to_display_dict())
        if snapshot.warnings:
            st.warning(" | ".join(snapshot.warnings))
        else:
            st.success("All selected readings are available.")


def main() -> None:
    inject_styles()

    if "advisor_history" not in st.session_state:
        st.session_state["advisor_history"] = []
    if "advisor_question" not in st.session_state:
        st.session_state["advisor_question"] = ""

    config = get_config()
    sensor_service = SensorIngestionService(config)
    crop_engine = CropScoringEngine.from_json()
    recommender = AIRecommendationService(config)
    advisor_service = LocalAIAdvisorService(config)

    with st.sidebar:
        st.header("Sinai Controls")
        st.caption("Local-first food intelligence for disruption response and multi-user field access.")
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
        data_mode_label = st.selectbox(
            "Data source mode",
            ["Demo/mock mode", "Live sensor mode"],
        )
        st.caption(
            "Live sensor mode attempts Pi hardware reads first, then backfills missing signals with mock values."
        )
        if st.button("Refresh deployment reading", use_container_width=True, key="refresh_main"):
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

    dashboard_tab, advisor_tab, deployment_tab = st.tabs(
        ["Sinai Dashboard", "Local LLM Advisor", "Edge Deployment"]
    )

    with dashboard_tab:
        render_dashboard_tab(
            snapshot=snapshot,
            environment=environment,
            ranked_crops=ranked_crops,
            emergency_crops=emergency_crops,
            narrative=narrative,
            organization=organization,
            site_name=site_name,
            region=region,
            disaster_context=disaster_context,
        )

    with advisor_tab:
        context = build_llm_context(environment, ranked_crops, narrative)
        render_local_ai_tab(
            advisor_service=advisor_service,
            config=config,
            context=context,
            environment=environment,
            ranked_crops=ranked_crops,
            narrative=narrative,
        )

    with deployment_tab:
        render_edge_deployment_tab(
            advisor_service=advisor_service,
            config=config,
            site_name=site_name,
        )


if __name__ == "__main__":
    main()
