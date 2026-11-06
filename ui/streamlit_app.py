from datetime import datetime, timedelta, timezone
import os
from uuid import uuid4
from dotenv import load_dotenv
import requests
import streamlit as st
from ui.admin_dashboard import render_admin_dashboard
from ui.password_setup import render_password_setup

load_dotenv()
API_URL = os.getenv("API_URL", "http://127.0.0.1:8001/ask")
AUTH_URL = API_URL.rsplit("/", 1)[0] + "/auth"
HISTORY_URL = API_URL.rsplit("/", 1)[0] + "/conversations"
st.set_page_config(page_title="IT Support Copilot", page_icon="IT", layout="wide" if st.session_state.get("auth_session", {}).get("user", {}).get("role") == "admin" else "centered")


def clear_session(notice=None):
    for name in ("auth_session", "thread_id", "messages", "history_loaded", "conversations", "history_next_offset", "show_login_password", "login_role", "chat_search", "show_archived", "history_filter", "conversation_title", "conversation_archived", "chat_notice", "workspace"):
        st.session_state.pop(name, None)
    for name in list(st.session_state):
        if name.startswith("admin_"):
            st.session_state.pop(name, None)
    if notice:
        st.session_state.login_notice = notice


def refresh_login():
    current = st.session_state.auth_session
    response = requests.post(AUTH_URL + "/refresh", json={"refresh_token": current["refresh_token"]}, timeout=20)
    if response.status_code == 401:
        clear_session("Your session ended. Please sign in again.")
        st.rerun()
    response.raise_for_status()
    st.session_state.auth_session = response.json()


def show_sources(sources):
    if sources:
        with st.expander("View Sources"):
            for source in sources:
                if source.get("url"):
                    st.markdown(f"- [{source.get('title', 'Source')}]({source['url']})")
                elif source.get("document"):
                    st.write(f"- {source['document']} (Section: {source.get('section', 'N/A')})")


def history_get(url, params=None):
    response = requests.get(url, params=params, headers={"Authorization": "Bearer " + st.session_state.auth_session["access_token"]}, timeout=20)
    if response.status_code == 401:
        refresh_login()
        response = requests.get(url, params=params, headers={"Authorization": "Bearer " + st.session_state.auth_session["access_token"]}, timeout=20)
        if response.status_code == 401:
            clear_session("Please sign in again.")
            st.rerun()
    response.raise_for_status()
    return response.json()


def api_request(method, path, *, params=None, body=None):
    url = API_URL.rsplit("/", 1)[0] + path
    def send():
        headers = {"Authorization": "Bearer " + st.session_state.auth_session["access_token"]}
        if method == "GET":
            return requests.get(url, params=params, headers=headers, timeout=20)
        return requests.request(method, url, json=body, params=params, headers=headers, timeout=30)
    response = send()
    if response.status_code == 401:
        refresh_login()
        response = send()
        if response.status_code == 401:
            clear_session("Please sign in again.")
            st.rerun()
    response.raise_for_status()
    return response.json() if response.status_code != 204 else None


def load_conversation(thread_id):
    saved = history_get(HISTORY_URL + "/" + thread_id)
    st.session_state.thread_id = saved["thread_id"]
    st.session_state.messages = saved["messages"]
    st.session_state.conversation_title = saved.get("title", "Conversation")
    st.session_state.conversation_archived = saved.get("archived", False)


def load_history_index(offset=0):
    page = history_get(HISTORY_URL, params={"offset": offset, "limit": 20, "query": st.session_state.get("chat_search", ""), "archived": st.session_state.get("show_archived", False)})
    if offset == 0:
        st.session_state.conversations = page["items"]
    else:
        seen = {item["thread_id"] for item in st.session_state.conversations}
        st.session_state.conversations.extend(item for item in page["items"] if item["thread_id"] not in seen)
    st.session_state.history_next_offset = page.get("next_offset")
    for item in page["items"]:
        if item["thread_id"] == st.session_state.get("thread_id"):
            st.session_state.conversation_title = item["title"]
            st.session_state.conversation_archived = item.get("archived", False)


st.title("IT Support Copilot")
st.caption("Your workplace IT assistant")
if "auth_session" not in st.session_state:
    render_password_setup(AUTH_URL)
    if notice := st.session_state.pop("login_notice", None):
        st.info(notice)
    st.subheader("Sign in")
    login_choice = st.radio("Choose your login", ["Employee login", "Admin login"], horizontal=True, key="login_role")
    selected_role = "admin" if login_choice == "Admin login" else "employee"
    st.caption("Manage tickets, employees, and devices." if selected_role == "admin" else "Chat with IT support and manage your own tickets.")
    show_password = st.checkbox("Show password", key="show_login_password")
    email = st.text_input("Work email", key="login_email")
    password = st.text_input("Password", value=st.session_state.get("login_password", ""), type="default" if show_password else "password", key="login_password")
    submitted = st.button("Sign in")
    if submitted:
        try:
            response = requests.post(AUTH_URL + "/login", json={"email": email, "password": password, "role": selected_role}, timeout=20)
            if response.status_code in {401, 422}:
                st.error("Unable to sign in. Check your email and password, or contact IT.")
            elif response.status_code == 403:
                st.error("This account cannot use the selected login. Choose the login that matches your company role, or contact IT.")
            else:
                response.raise_for_status()
                st.session_state.auth_session = response.json()
                st.session_state.thread_id = str(uuid4())
                st.session_state.messages = []
                st.session_state.workspace = "Admin dashboard" if selected_role == "admin" else "Chat"
                st.rerun()
        except requests.RequestException:
            st.error("The sign-in service is unavailable. Please try again.")
    st.caption("First time here? Ask IT for a password setup link, then choose your password in this app.")
    st.stop()

for login_field in ("login_email", "login_password", "show_login_password"):
    st.session_state.pop(login_field, None)

try:
    session = st.session_state.auth_session
    if datetime.fromisoformat(session["session_expires_at"]) <= datetime.now(timezone.utc):
        clear_session("Your session ended. Please sign in again.")
        st.rerun()
    if datetime.fromisoformat(session["expires_at"]) <= datetime.now(timezone.utc) + timedelta(seconds=30):
        refresh_login()
except requests.RequestException:
    st.error("Unable to reconnect to the sign-in service. Please try again.")
    if st.button("Try again"):
        st.rerun()
    st.stop()

session = st.session_state.auth_session
st.sidebar.write(f"Signed in as **{session['user']['full_name']}**")
st.sidebar.caption(session["user"]["email"])
if st.sidebar.button("Sign out"):
    notice = "You have signed out."
    try:
        requests.post(AUTH_URL + "/logout", json={"refresh_token": session["refresh_token"]}, timeout=20).raise_for_status()
    except requests.RequestException:
        notice = "Signed out on this device. The server could not confirm session revocation."
    clear_session(notice)
    st.rerun()

if session["user"].get("role") == "admin":
    workspace = st.sidebar.radio("Workspace", ["Chat", "Admin dashboard"], key="workspace")
    if workspace == "Admin dashboard":
        render_admin_dashboard(api_request)
        st.stop()

if st.sidebar.button("New chat"):
    st.session_state.thread_id = str(uuid4())
    st.session_state.messages = []
    st.session_state.conversation_title = "New chat"
    st.session_state.conversation_archived = False
    st.session_state.chat_search = ""
    st.session_state.show_archived = False
    st.session_state.history_loaded = True
    st.rerun()

st.sidebar.subheader("Previous chats")
search = st.sidebar.text_input("Search chats", key="chat_search", max_chars=200, placeholder="Conversation name")
archived = st.sidebar.checkbox("Show archived chats", key="show_archived")
try:
    first_load = not st.session_state.get("history_loaded")
    if first_load or st.session_state.get("history_filter") != (search, archived):
        load_history_index()
        if first_load and not search and not archived and st.session_state.conversations:
            load_conversation(st.session_state.conversations[0]["thread_id"])
        st.session_state.history_loaded = True
        st.session_state.history_filter = (search, archived)
except requests.RequestException:
    st.sidebar.warning("Saved conversations could not be loaded. Please try again.")
    if st.sidebar.button("Retry history"):
        st.rerun()
if st.session_state.get("history_loaded") and not st.session_state.get("conversations"):
    st.sidebar.caption("No conversations match this view.")
for item in st.session_state.get("conversations", []):
    label = item["title"] or "Conversation"
    if item["thread_id"] == st.session_state.get("thread_id"):
        label = "Current: " + label
    if st.sidebar.button(label, key="conversation_" + item["thread_id"]):
        try:
            load_conversation(item["thread_id"])
            st.rerun()
        except requests.RequestException:
            st.sidebar.error("This conversation could not be opened. Please try again.")
if st.session_state.get("history_next_offset") is not None:
    if st.sidebar.button("Load older chats"):
        try:
            load_history_index(st.session_state.history_next_offset)
            st.rerun()
        except requests.RequestException:
            st.sidebar.error("Older conversations could not be loaded. Please try again.")

if "messages" not in st.session_state:
    st.session_state.messages = []
if "thread_id" not in st.session_state:
    st.session_state.thread_id = str(uuid4())
if notice := st.session_state.pop("chat_notice", None):
    st.success(notice)
if st.session_state.messages:
    st.subheader(st.session_state.get("conversation_title", "Conversation"))
    with st.expander("Manage conversation"):
        with st.form("rename_" + st.session_state.thread_id):
            title = st.text_input("Conversation name", value=st.session_state.get("conversation_title", "Conversation"), max_chars=80)
            rename = st.form_submit_button("Rename chat")
        if rename:
            try:
                saved = api_request("PATCH", "/conversations/" + st.session_state.thread_id, body={"title": title})
                st.session_state.conversation_title = saved["title"]
                load_history_index()
                st.session_state.chat_notice = "Conversation renamed."
                st.rerun()
            except requests.RequestException as error:
                st.error("The conversation could not be renamed. Enter a name and try again.")
        is_archived = st.session_state.get("conversation_archived", False)
        if st.button("Restore chat" if is_archived else "Archive chat"):
            try:
                saved = api_request("PATCH", "/conversations/" + st.session_state.thread_id, body={"archived": not is_archived})
                st.session_state.conversation_archived = saved["archived"]
                load_history_index()
                st.session_state.chat_notice = "Conversation restored." if is_archived else "Conversation archived. Find it using Show archived chats."
                st.rerun()
            except requests.RequestException:
                st.error("The conversation could not be updated. Please try again.")
    if st.session_state.get("conversation_archived"):
        st.info("This conversation is archived. Restore it to continue chatting.")
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])
        show_sources(message.get("sources", []))

if question := st.chat_input("Ask your IT support question...", disabled=st.session_state.get("conversation_archived", False)):
    st.session_state.messages.append({"role": "user", "content": question})
    with st.chat_message("user"):
        st.markdown(question)
    with st.chat_message("assistant"):
        with st.spinner("Working on your request..."):
            try:
                def send_question():
                    return requests.post(API_URL, json={"question": question, "thread_id": st.session_state.thread_id}, headers={"Authorization": "Bearer " + st.session_state.auth_session["access_token"]}, timeout=120)
                response = send_question()
                if response.status_code == 401:
                    refresh_login()
                    response = send_question()
                    if response.status_code == 401:
                        clear_session("Please sign in again.")
                        st.rerun()
                response.raise_for_status()
                result = response.json()
                answer = result["answer"]
                sources = result.get("sources", [])
                status = result.get("status", "unknown")
            except requests.RequestException:
                answer = "The service could not confirm a result. Check your tickets before repeating a request that creates or closes one."
                sources, status = [], "error"
        st.markdown(answer)
        show_sources(sources)
        st.session_state.messages.append({"role": "assistant", "content": answer, "sources": sources, "status": status})
        try:
            load_history_index()
        except requests.RequestException:
            st.sidebar.warning("The conversation list could not refresh. Your completed chat is saved by the backend.")
        else:
            st.rerun()
