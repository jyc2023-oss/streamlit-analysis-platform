from __future__ import annotations

import html

import streamlit as st


def render_global_theme() -> None:
    """Apply the shared visual system before rendering any application page."""
    st.html(
        """
        <style>
        :root {
            --app-ink: #102a2a;
            --app-muted: #607474;
            --app-faint: #879797;
            --app-accent: #0f766e;
            --app-accent-strong: #0b5f59;
            --app-accent-soft: #dff3ef;
            --app-canvas: #f3f7f6;
            --app-surface: #fbfdfc;
            --app-surface-raised: #ffffff;
            --app-line: #d8e3e1;
            --app-line-strong: #c3d2cf;
            --app-danger: #b42318;
            --app-radius-panel: 1rem;
            --app-radius-control: 0.58rem;
            --app-shadow: 0 1rem 2.8rem rgba(35, 76, 72, 0.075);
        }

        html { scroll-behavior: smooth; }
        body, [data-testid="stAppViewContainer"] {
            color: var(--app-ink);
            font-family: "Segoe UI Variable Text", "Microsoft YaHei UI",
                         "Microsoft YaHei", sans-serif;
        }
        [data-testid="stAppViewContainer"] {
            background:
                radial-gradient(circle at 8% -8%, rgba(15, 118, 110, 0.09), transparent 28rem),
                radial-gradient(circle at 94% 12%, rgba(65, 116, 110, 0.055), transparent 24rem),
                var(--app-canvas);
        }
        [data-testid="stHeader"] {
            background: rgba(243, 247, 246, 0.82);
            border-bottom: 1px solid rgba(195, 210, 207, 0.72);
            backdrop-filter: blur(18px) saturate(140%);
        }
        [data-testid="stToolbar"] { color: var(--app-muted); }
        .stMainBlockContainer, .block-container {
            max-width: 1840px;
            padding-top: 1.15rem;
            padding-bottom: 3.5rem;
        }

        h1, h2, h3, h4 {
            color: var(--app-ink);
            font-family: "Segoe UI Variable Display", "Microsoft YaHei UI", sans-serif;
            letter-spacing: -0.035em;
            text-wrap: balance;
        }
        h1 { font-size: clamp(2rem, 2.5vw, 3.15rem) !important; line-height: 1.04 !important; }
        h2 { letter-spacing: -0.025em; }
        h3, h4 { letter-spacing: -0.015em; }
        p, [data-testid="stCaptionContainer"] { text-wrap: pretty; }
        [data-testid="stCaptionContainer"] {
            color: var(--app-muted);
            font-size: 0.9rem;
            line-height: 1.55;
        }
        code, pre, [data-testid="stMetricValue"], [data-testid="stDataFrame"] {
            font-variant-numeric: tabular-nums;
        }
        code, pre {
            font-family: "Cascadia Mono", "SFMono-Regular", Consolas, monospace;
        }

        div[data-testid="stVerticalBlockBorderWrapper"] {
            background: rgba(251, 253, 252, 0.94);
            border: 1px solid var(--app-line);
            border-radius: var(--app-radius-panel);
            box-shadow: var(--app-shadow);
            overflow: hidden;
        }
        div[data-testid="stVerticalBlockBorderWrapper"] > div {
            background: transparent;
        }
        div[data-testid="stMetric"] {
            background: linear-gradient(145deg, #ffffff, #f6faf9);
            border: 1px solid var(--app-line);
            border-radius: 0.8rem;
            box-shadow: 0 0.45rem 1.5rem rgba(35, 76, 72, 0.045);
            min-height: 6.15rem;
            padding: 0.85rem 1rem;
        }
        [data-testid="stMetricLabel"] {
            color: var(--app-muted);
            font-size: 0.8rem;
            font-weight: 600;
            letter-spacing: 0.025em;
        }
        [data-testid="stMetricValue"] {
            color: var(--app-ink);
            font-family: "Cascadia Mono", "Segoe UI Variable Display", sans-serif;
            font-size: clamp(1.35rem, 1.65vw, 2.05rem);
            letter-spacing: -0.045em;
        }

        .stButton > button, .stDownloadButton > button,
        [data-testid="stFormSubmitButton"] > button {
            border-color: var(--app-line-strong);
            border-radius: var(--app-radius-control);
            box-shadow: 0 0.25rem 0.75rem rgba(35, 76, 72, 0.035);
            font-weight: 600;
            min-height: 2.65rem;
            transition: background-color 180ms ease, border-color 180ms ease,
                        box-shadow 180ms ease, color 180ms ease, transform 120ms ease;
        }
        .stButton > button:hover, .stDownloadButton > button:hover,
        [data-testid="stFormSubmitButton"] > button:hover {
            border-color: var(--app-accent);
            color: var(--app-accent-strong);
            box-shadow: 0 0.55rem 1.4rem rgba(15, 118, 110, 0.12);
            transform: translateY(-1px);
        }
        .stButton > button:active, .stDownloadButton > button:active,
        [data-testid="stFormSubmitButton"] > button:active {
            transform: translateY(1px) scale(0.99);
        }
        .stButton > button:focus-visible, .stDownloadButton > button:focus-visible,
        [data-testid="stFormSubmitButton"] > button:focus-visible {
            outline: 3px solid rgba(15, 118, 110, 0.22);
            outline-offset: 2px;
        }
        button[kind="primary"] {
            background: var(--app-accent) !important;
            border-color: var(--app-accent) !important;
            color: #ffffff !important;
        }
        button[kind="primary"]:hover {
            background: var(--app-accent-strong) !important;
            color: #ffffff !important;
        }

        [data-baseweb="input"] > div, [data-baseweb="base-input"],
        [data-baseweb="select"] > div, [data-testid="stNumberInputContainer"] {
            background: rgba(255, 255, 255, 0.88) !important;
            border-color: var(--app-line-strong) !important;
            border-radius: var(--app-radius-control) !important;
            transition: border-color 180ms ease, box-shadow 180ms ease;
        }
        [data-baseweb="input"] > div:focus-within, [data-baseweb="select"] > div:focus-within,
        [data-testid="stNumberInputContainer"]:focus-within {
            border-color: var(--app-accent) !important;
            box-shadow: 0 0 0 3px rgba(15, 118, 110, 0.12) !important;
        }
        label, [data-testid="stWidgetLabel"] {
            color: #405c59 !important;
            font-size: 0.86rem !important;
            font-weight: 600 !important;
        }

        [data-testid="stDataFrame"], [data-testid="stTable"] {
            border: 1px solid var(--app-line);
            border-radius: 0.8rem;
            box-shadow: 0 0.65rem 2rem rgba(35, 76, 72, 0.045);
            overflow: hidden;
        }
        [data-testid="stPlotlyChart"] {
            border-radius: 0.8rem;
            overflow: hidden;
        }
        details {
            background: rgba(251, 253, 252, 0.82);
            border: 1px solid var(--app-line) !important;
            border-radius: 0.8rem !important;
        }
        details summary { font-weight: 600; }
        hr { border-color: var(--app-line) !important; }

        [data-testid="stAlert"] {
            border-radius: 0.72rem;
            border-width: 1px;
        }
        [data-testid="stSpinner"] { color: var(--app-accent); }
        [data-testid="stPills"] button, [role="radiogroup"] label {
            transition: transform 120ms ease, background-color 180ms ease, border-color 180ms ease;
        }
        [data-testid="stPills"] button:hover, [role="radiogroup"] label:hover {
            transform: translateY(-1px);
        }

        .app-wordmark {
            color: var(--app-ink);
            font-family: "Segoe UI Variable Display", "Microsoft YaHei UI", sans-serif;
            font-size: 1rem;
            font-weight: 700;
            letter-spacing: -0.02em;
            line-height: 2.4rem;
        }
        .app-wordmark span {
            color: var(--app-accent);
            font-family: "Cascadia Mono", monospace;
            font-size: 0.72rem;
            font-weight: 600;
            letter-spacing: 0.06em;
            margin-left: 0.55rem;
        }
        .page-intro {
            margin: 0.25rem 0 1.5rem;
            max-width: 58rem;
        }
        .page-intro h1 {
            font-size: clamp(2rem, 2.5vw, 3.15rem);
            margin: 0;
        }
        .page-intro p {
            color: var(--app-muted);
            font-size: 0.98rem;
            line-height: 1.65;
            margin: 0.55rem 0 0;
            max-width: 65ch;
        }
        .section-heading {
            color: var(--app-ink);
            font-size: 1.08rem;
            font-weight: 700;
            letter-spacing: -0.015em;
            margin: 0.1rem 0 0.75rem;
        }

        @keyframes app-rise {
            from { opacity: 0; transform: translateY(8px); }
            to { opacity: 1; transform: translateY(0); }
        }
        .page-intro, div[data-testid="stVerticalBlockBorderWrapper"], [data-testid="stDataFrame"] {
            animation: app-rise 320ms cubic-bezier(.22, .8, .32, 1) both;
        }

        @media (prefers-reduced-motion: reduce) {
            *, *::before, *::after {
                animation-duration: 0.01ms !important;
                transition-duration: 0.01ms !important;
                scroll-behavior: auto !important;
            }
        }
        @media (max-width: 900px) {
            .stMainBlockContainer, .block-container { padding-top: 0.75rem; }
            .account-bar-label { text-align: left !important; }
            .app-wordmark span { display: none; }
        }
        </style>
        """
    )


def render_page_intro(title: str, description: str) -> None:
    """Render a consistent wide page heading with restrained supporting copy."""
    st.markdown(
        f"""
        <section class="page-intro">
          <h1>{html.escape(title)}</h1>
          <p>{html.escape(description)}</p>
        </section>
        """,
        unsafe_allow_html=True,
    )
