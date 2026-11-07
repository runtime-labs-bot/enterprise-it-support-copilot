"""Explicit confirmations inside admin chat; secrets never enter chat messages."""
import os
from urllib.parse import urlencode
import requests
import streamlit as st
from ui.admin_dashboard import error_message


def render_admin_actions(api, thread_id):
    try:
        data = api("GET", "/admin/chat/actions", params={"thread_id": thread_id})
    except requests.RequestException as error:
        st.warning("Admin action reviews could not be loaded. " + error_message(error))
        return
    for action in data.get("items", []):
        with st.container(border=True):
            st.subheader("Review admin action")
            plan = action["plan"]
            st.write(f"**{plan['operation'].replace('_', ' ').title()}**" + (f" · ID {plan['record_id']}" if plan.get("record_id") else ""))
            if action.get("before"):
                with st.expander("Current record"):
                    st.json(action["before"])
            st.write("Requested changes")
            st.json(plan["changes"])
            if plan.get("override"):
                st.warning("This overrides the normal ticket workflow. The reason will be recorded in ticket history.")
            if plan["operation"] == "setup_login":
                st.warning("This creates a login with the displayed role and issues a private activation link.")
            st.caption("Expires: " + action["expires_at"])
            if action["status"] != "pending":
                st.warning("This action is already executing or has an uncertain outcome. Check the record before requesting another change.")
                continue
            confirm, cancel = st.columns(2)
            if confirm.button("Confirm action", key="admin_confirm_" + action["id"], type="primary"):
                try:
                    result = api("POST", f"/admin/chat/actions/{action['id']}/confirm", body={"thread_id": thread_id})
                except requests.RequestException as error:
                    st.error(error_message(error) + " Check the current record before retrying.")
                else:
                    if result.get("private_setup_token"):
                        base = os.getenv("COPILOT_PUBLIC_URL", "http://localhost:8501").rstrip("/")
                        st.session_state.admin_private_setup_link = {"thread_id": thread_id, "url": base + "/?" + urlencode({"setup": result["private_setup_token"]})}
                    st.session_state.admin_chat_notice = result.get("history_warning") or "Admin action completed. The result is saved in this conversation."
                    # Restore the public transcript after server-side confirmation.
                    st.session_state.history_loaded = False
                    st.session_state.admin_refresh_thread = thread_id
                    st.rerun()
            if cancel.button("Cancel action", key="admin_cancel_" + action["id"]):
                try:
                    api("POST", f"/admin/chat/actions/{action['id']}/cancel", body={"thread_id": thread_id})
                    st.rerun()
                except requests.RequestException as error:
                    st.error(error_message(error))
    if notice := st.session_state.pop("admin_chat_notice", None):
        st.success(notice)
    private = st.session_state.get("admin_private_setup_link")
    if private and private["thread_id"] == thread_id:
        st.warning("Private password setup link: share only with the intended employee. This link is not saved in chat.")
        st.code(private["url"], language=None)
        if st.button("Hide private setup link", key="admin_hide_private_link"):
            st.session_state.pop("admin_private_setup_link", None)
            st.rerun()
