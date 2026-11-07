"""Restore an HttpOnly browser session without exposing tokens to JavaScript."""
import os
from html import escape
from uuid import uuid4
import requests
import streamlit as st

COOKIE_NAME = "meridian_browser_session"


def enabled():
    return bool(os.getenv("COPILOT_BROWSER_AUTH_URL") and os.getenv("BROWSER_UI_AUTH_KEY"))


def session_request(auth_url, operation, handle, *, force_refresh=False):
    return requests.post(auth_url + "/browser/" + operation, json={"handle": handle, "force_refresh": force_refresh}, headers={"X-UI-Auth-Key": os.environ["BROWSER_UI_AUTH_KEY"]}, timeout=45)


def restore_browser_login(auth_url):
    if not enabled() or st.session_state.get("browser_restore_attempted"):
        return
    handle = st.context.cookies.get(COOKIE_NAME)
    if not handle:
        st.session_state.browser_restore_attempted = True
        return
    try:
        response = session_request(auth_url, "restore", handle)
        if response.status_code == 401:
            st.session_state.browser_restore_attempted = True
            st.session_state.login_notice = "Your session ended. Please sign in again."
            return
        response.raise_for_status()
        tokens = response.json()
    except requests.RequestException:
        st.error("Your saved login could not be restored. Please try again when the service is available.")
        if st.button("Retry saved login"):
            st.rerun()
        st.stop()
    st.session_state.auth_session = tokens
    st.session_state.browser_handle = handle
    st.session_state.browser_restore_attempted = True
    st.session_state.thread_id = str(uuid4())
    st.session_state.messages = []
    st.session_state.workspace = "Admin chat" if tokens["user"]["role"] == "admin" else "Chat"
    st.rerun()


def render_login():
    role = "admin" if st.session_state.get("login_role") == "Admin login" else "employee"
    url = os.environ["COPILOT_BROWSER_AUTH_URL"].rstrip("/") + "/login?role=" + role
    # Streamlit's iframe sandbox blocks top-level login redirects. Navigate in
    # the current tab to a normal browser form so HttpOnly cookies are reliable.
    st.markdown(f'<a href="{escape(url, quote=True)}" target="_self" style="display:inline-block;padding:12px 20px;border:1px solid #d5d8de;border-radius:8px;text-decoration:none;color:inherit">Continue to sign in</a>', unsafe_allow_html=True)
    st.caption("Choose Employee login or Admin login on the sign-in page. You will return here automatically.")
    st.caption("First time here? Ask IT for a password setup link, then choose your password in this app.")
