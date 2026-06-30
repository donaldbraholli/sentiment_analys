import streamlit as st


DASHBOARD_THEMES = {
    "Clean Professional": {
        "primary": "#2563EB",
        "card": "#F8FAFC",
        "border": "#E5E7EB",
        "soft": "#EFF6FF"
    },
    "Corporate Red": {
        "primary": "#C1121F",
        "card": "#FFF7F7",
        "border": "#F3C4C4",
        "soft": "#FDECEC"
    },
    "Executive Blue": {
        "primary": "#1D4ED8",
        "card": "#F8FAFC",
        "border": "#D8DEE9",
        "soft": "#EAF1FF"
    },
    "Emerald Business": {
        "primary": "#047857",
        "card": "#F6FEF9",
        "border": "#B7E4C7",
        "soft": "#ECFDF5"
    },
    "Premium Purple": {
        "primary": "#6D28D9",
        "card": "#FAF7FF",
        "border": "#DDD6FE",
        "soft": "#F3E8FF"
    },
    "Warm Neutral": {
        "primary": "#B45309",
        "card": "#FFFBF5",
        "border": "#FED7AA",
        "soft": "#FFF7ED"
    }
}


def apply_dashboard_theme(theme_name):
    theme = DASHBOARD_THEMES.get(
        theme_name,
        DASHBOARD_THEMES["Clean Professional"]
    )

    primary = theme["primary"]
    card = theme["card"]
    border = theme["border"]
    soft = theme["soft"]

    st.markdown(
        f"""
        <style>
            /*
            Safe dashboard theming.
            We do NOT override the whole app background or all text colors.
            That avoids invisible text in Streamlit widgets.
            */

            div[data-testid="stMetric"] {{
                background-color: {card};
                border: 1px solid {border};
                border-left: 5px solid {primary};
                padding: 14px;
                border-radius: 14px;
                box-shadow: 0 1px 4px rgba(0,0,0,0.06);
            }}

            div[data-testid="stMetricValue"] {{
                color: {primary};
            }}

            div[data-testid="stExpander"] {{
                border: 1px solid {border};
                border-radius: 12px;
            }}

            .stButton > button {{
                background-color: {primary};
                color: white;
                border-radius: 8px;
                border: none;
            }}

            .stButton > button:hover {{
                background-color: {primary};
                color: white;
                opacity: 0.92;
            }}

            div[data-testid="stAlert"] {{
                border-left: 5px solid {primary};
            }}

            hr {{
                border-color: {border};
            }}

            .dashboard-section-card {{
                background-color: {soft};
                border: 1px solid {border};
                border-radius: 14px;
                padding: 16px;
                margin-bottom: 16px;
            }}

            .dashboard-section-title {{
                color: {primary};
                font-weight: 700;
                font-size: 1.05rem;
                margin-bottom: 6px;
            }}
        </style>
        """,
        unsafe_allow_html=True
    )