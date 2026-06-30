import streamlit as st

from database import init_db

from tabs.data_sources import render_data_sources_tab
from tabs.register_brand import render_register_brand_tab
from tabs.brands import render_brands_tab
from tabs.database_editor import render_database_editor_tab
from tabs.mentions_test import render_mentions_test_tab
from tabs.dashboard import render_dashboard_tab


def main():
    st.set_page_config(
        page_title="Customer Sentiment",
        layout="wide"
    )

    init_db()

    st.title("Customer Sentiment")

    tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
        "Register Brand",
        "Brands",
        "Database Editor",
        "Mentions / Sentiment Test",
        "Dashboard",
        "Data Sources"
    ])

    with tab1:
        render_register_brand_tab()

    with tab2:
        render_brands_tab()

    with tab3:
        render_database_editor_tab()

    with tab4:
        render_mentions_test_tab()

    with tab5:
        render_dashboard_tab()

    with tab6:
        render_data_sources_tab()


if __name__ == "__main__":
    main()