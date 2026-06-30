import streamlit as st


def rerun_app():
    try:
        st.rerun()
    except AttributeError:
        st.experimental_rerun()