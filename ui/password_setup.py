"""First-time account activation, separate from chat and model context."""
import requests
import streamlit as st


def render_password_setup(auth_url):
    if "setup" in st.query_params:
        st.session_state.setup_token = st.query_params["setup"]
        # Remove the credential from the address bar immediately.
        del st.query_params["setup"]
    if not st.session_state.get("setup_token"):
        return
    st.subheader("Set your password")
    st.caption("Choose a password with 12 to 128 characters. Your company role is assigned by IT.")
    visible = st.checkbox("Show password", key="setup_visible")
    password = st.text_input("New password", type="default" if visible else "password", key="setup_password", value=st.session_state.get("setup_password", ""), max_chars=128)
    confirm = st.text_input("Confirm password", type="default" if visible else "password", key="setup_confirm", value=st.session_state.get("setup_confirm", ""), max_chars=128)
    if st.button("Set password"):
        if not 12 <= len(password) <= 128 or not password.strip():
            st.error("Use 12 to 128 characters, including a non-space character.")
        elif password != confirm:
            st.error("The passwords do not match.")
        else:
            try:
                response = requests.post(auth_url + "/setup-password", json={"token": st.session_state.setup_token, "password": password}, timeout=20)
                if response.status_code in {400, 404, 409}:
                    st.error("This setup link has expired, was already used, or the account already exists. Ask IT for help.")
                elif response.status_code == 422:
                    st.error("Check the password requirements and try again.")
                else:
                    response.raise_for_status()
                    user = response.json()
                    for key in ("setup_token", "setup_password", "setup_confirm", "setup_visible"):
                        st.session_state.pop(key, None)
                    st.session_state.login_email = user["email"]
                    st.session_state.login_role = "Admin login" if user["role"] == "admin" else "Employee login"
                    st.session_state.login_notice = "Password set. You can now sign in."
                    st.rerun()
            except requests.RequestException:
                st.error("Password setup is unavailable. Please try again.")
    if st.button("Back to sign in"):
        for key in ("setup_token", "setup_password", "setup_confirm", "setup_visible"):
            st.session_state.pop(key, None)
        st.rerun()
    st.stop()
