"""Role-gated operational workspace backed by protected Meridian APIs."""
import requests
import os
from urllib.parse import urlencode
import streamlit as st

STATUSES = ["open", "in_progress", "resolved", "closed"]
PRIORITIES = ["low", "medium", "high", "urgent"]
TYPES = ["laptop", "desktop", "monitor", "printer", "phone", "tablet", "other"]
TRANSITIONS = {"open": ["in_progress"], "in_progress": ["resolved"], "resolved": ["in_progress", "closed"], "closed": []}


def error_message(error):
    try:
        detail = error.response.json().get("detail")
        if isinstance(detail, str):
            return detail
    except (AttributeError, ValueError):
        pass
    return "The request could not be completed. Please try again."


def save(api, method, path, body):
    try:
        api(method, path, body=body)
    except requests.RequestException as error:
        st.error(error_message(error))
    else:
        st.session_state.admin_notice = "Changes saved."
        st.rerun()


def pager(key, total, count, size=20):
    offset = st.session_state.get(key, 0)
    st.caption(f"{offset + 1 if count else 0}–{offset + count} of {total}")
    left, right = st.columns(2)
    if left.button("Previous page", key=key + "_prev", disabled=offset == 0):
        st.session_state[key] = max(0, offset-size)
        st.rerun()
    if right.button("Next page", key=key + "_next", disabled=offset+count >= total):
        st.session_state[key] = offset+size
        st.rerun()


def overview(api):
    data = api("GET", "/admin/summary")
    a, b, c = st.columns(3)
    a.metric("Employees", data["employees"]["total"])
    b.metric("Devices", data["devices"]["total"])
    c.metric("Active tickets", data["tickets"]["open"] + data["tickets"]["in_progress"])
    for column, status in zip(st.columns(4), STATUSES):
        column.metric(status.replace("_", " ").title(), data["tickets"][status])
    st.write(f"**{data['tickets']['high_priority_active']}** high or urgent priority tickets need attention.")
    st.write(f"**{data['employees']['active']}** active employees · **{data['devices']['unassigned']}** unassigned devices")


def tickets(api):
    with st.form("admin_ticket_filters"):
        search = st.text_input("Search tickets", key="admin_ticket_search")
        a, b = st.columns(2)
        status = a.selectbox("Status filter", ["All"] + STATUSES, key="admin_ticket_status_filter")
        priority = b.selectbox("Priority filter", ["All"] + PRIORITIES, key="admin_ticket_priority_filter")
        if st.form_submit_button("Apply ticket filters"):
            st.session_state.admin_ticket_offset = 0
    params = {"offset": st.session_state.get("admin_ticket_offset", 0), "limit": 20, "search": search}
    params.update({key: value for key, value in {"status": status, "priority": priority}.items() if value != "All"})
    data = api("GET", "/admin/tickets", params=params)
    rows = data["items"]
    if not rows:
        st.info("No tickets match these filters.")
    else:
        st.dataframe([{key: row[key] for key in ("id", "title", "employee_id", "device_id", "status", "priority", "updated_at")} for row in rows], hide_index=True, width="stretch")
    pager("admin_ticket_offset", data["total"], len(rows))
    if not rows:
        return
    by_id = {row["id"]: row for row in rows}
    selected = st.selectbox("Open a ticket", list(by_id), index=None, format_func=lambda value: f"#{value} · {by_id[value]['title']}", key="admin_ticket_selected")
    if selected is None:
        return
    row = by_id[selected]
    st.subheader(f"Ticket #{selected}")
    st.write(row["description"])
    override = st.checkbox("Override workflow", key=f"admin_ticket_override_{selected}", help="Overrides require a reason and are recorded in status history.")
    options = STATUSES if override else [row["status"]] + TRANSITIONS[row["status"]]
    with st.form(f"admin_ticket_edit_{selected}"):
        next_status = st.selectbox("Ticket status", options, index=options.index(row["status"]))
        next_priority = st.selectbox("Ticket priority", PRIORITIES, index=PRIORITIES.index(row["priority"]))
        reporter = st.number_input("Reporter employee ID", min_value=1, value=row["employee_id"], step=1)
        device = st.number_input("Device ID (0 for none)", min_value=0, value=row["device_id"] or 0, step=1)
        reason = st.text_area("Reason for status change", max_chars=2000)
        if st.form_submit_button("Save ticket"):
            values = {"status": next_status, "priority": next_priority, "employee_id": int(reporter), "device_id": int(device) or None}
            changes = {key: value for key, value in values.items() if value != row[key]}
            if not changes:
                st.info("There are no changes to save.")
            elif override and "status" in changes and not reason.strip():
                st.error("Enter a reason for the status override.")
            else:
                if reason.strip():
                    changes["reason"] = reason.strip()
                changes["override"] = override
                save(api, "PATCH", f"/admin/tickets/{selected}", changes)
    st.subheader("Status history")
    key = f"admin_history_offset_{selected}"
    offset = st.session_state.get(key, 0)
    events = api("GET", f"/admin/tickets/{selected}/history", params={"offset": offset, "limit": 20})
    if events:
        st.dataframe(events, hide_index=True, width="stretch")
    else:
        st.info("No status changes on this page.")
    left, right = st.columns(2)
    if left.button("Newer history", key=key+"_prev", disabled=offset == 0):
        st.session_state[key] = max(0, offset-20)
        st.rerun()
    if right.button("Older history", key=key+"_next", disabled=len(events) < 20):
        st.session_state[key] = offset+20
        st.rerun()


def employees(api):
    with st.expander("Add employee"):
        with st.form("admin_create_employee"):
            name = st.text_input("Full name")
            email = st.text_input("Work email")
            department = st.text_input("Department")
            job = st.text_input("Job title")
            if st.form_submit_button("Create employee"):
                save(api, "POST", "/admin/employees", {"full_name": name, "email": email, "department": department.strip() or None, "job_title": job.strip() or None})
    with st.form("admin_employee_filters"):
        search = st.text_input("Search employees by name or email", key="admin_employee_search")
        active = st.selectbox("Employee status", ["All", "Active", "Inactive"], key="admin_employee_active")
        if st.form_submit_button("Apply employee filters"):
            st.session_state.admin_employee_offset = 0
    params = {"offset": st.session_state.get("admin_employee_offset", 0), "limit": 20, "search": search}
    if active != "All":
        params["is_active"] = active == "Active"
    data = api("GET", "/admin/employees", params=params)
    rows = data["items"]
    st.dataframe(rows, hide_index=True, width="stretch") if rows else st.info("No employees match these filters.")
    pager("admin_employee_offset", data["total"], len(rows))
    if not rows:
        return
    by_id = {row["id"]: row for row in rows}
    selected = st.selectbox("Edit employee", list(by_id), index=None, format_func=lambda value: f"#{value} · {by_id[value]['full_name']}", key="admin_employee_selected")
    if selected is None:
        return
    row = by_id[selected]
    with st.expander("Set up login account"):
        st.caption("Generate a private, one-time link for this employee to choose their password. Valid for 24 hours. A new link invalidates earlier links. Existing login accounts are preserved.")
        role = st.selectbox("Login account role", ["employee", "admin"], key=f"admin_setup_role_{selected}")
        if st.button("Generate password setup link", key=f"admin_setup_link_{selected}", disabled=not row["is_active"]):
            invitation = api("POST", "/admin/setup-invitations", body={"employee_id": selected, "role": role})
            base = os.getenv("COPILOT_PUBLIC_URL", "http://localhost:8501").rstrip("/")
            link = base + "/?" + urlencode({"setup": invitation["token"]})
            st.warning("Share privately with the intended employee. Anyone with this link can activate this account.")
            st.code(link, language=None)
            st.caption(f"Expires: {invitation['expires_at']}")
    with st.form(f"admin_employee_edit_{selected}"):
        name = st.text_input("Full name", value=row["full_name"])
        email = st.text_input("Work email", value=row["email"])
        department = st.text_input("Department", value=row["department"] or "")
        job = st.text_input("Job title", value=row["job_title"] or "")
        active = st.checkbox("Active employee", value=row["is_active"])
        if st.form_submit_button("Save employee"):
            values = {"full_name": name, "email": email, "department": department.strip() or None, "job_title": job.strip() or None, "is_active": active}
            changes = {key: value for key, value in values.items() if value != row[key]}
            save(api, "PATCH", f"/admin/employees/{selected}", changes) if changes else st.info("There are no changes to save.")


def device_fields(row=None):
    row = row or {}
    values = {
        "asset_tag": st.text_input("Asset tag", value=row.get("asset_tag", "")),
        "device_type": st.selectbox("Device type", TYPES, index=TYPES.index(row.get("device_type", "laptop"))),
        "manufacturer": st.text_input("Manufacturer", value=row.get("manufacturer") or "").strip() or None,
        "model": st.text_input("Model", value=row.get("model") or "").strip() or None,
        "serial_number": st.text_input("Serial number", value=row.get("serial_number") or "").strip() or None,
        "assigned_employee_id": int(st.number_input("Assigned employee ID (0 for unassigned)", min_value=0, value=row.get("assigned_employee_id") or 0, step=1)) or None,
    }
    return values


def devices(api):
    with st.expander("Add device"):
        with st.form("admin_create_device"):
            values = device_fields()
            if st.form_submit_button("Create device"):
                save(api, "POST", "/admin/devices", values)
    with st.form("admin_device_filters"):
        search = st.text_input("Search asset tag or serial number", key="admin_device_search")
        if st.form_submit_button("Apply device filters"):
            st.session_state.admin_device_offset = 0
    data = api("GET", "/admin/devices", params={"offset": st.session_state.get("admin_device_offset", 0), "limit": 20, "search": search})
    rows = data["items"]
    st.dataframe(rows, hide_index=True, width="stretch") if rows else st.info("No devices match this search.")
    pager("admin_device_offset", data["total"], len(rows))
    if not rows:
        return
    by_id = {row["id"]: row for row in rows}
    selected = st.selectbox("Edit device", list(by_id), index=None, format_func=lambda value: f"#{value} · {by_id[value]['asset_tag']}", key="admin_device_selected")
    if selected is not None:
        row = by_id[selected]
        with st.form(f"admin_device_edit_{selected}"):
            values = device_fields(row)
            if st.form_submit_button("Save device"):
                changes = {key: value for key, value in values.items() if value != row[key]}
                save(api, "PATCH", f"/admin/devices/{selected}", changes) if changes else st.info("There are no changes to save.")


def render_admin_dashboard(api):
    st.header("Admin dashboard")
    if notice := st.session_state.pop("admin_notice", None):
        st.success(notice)
    section = st.radio("Section", ["Overview", "Tickets", "Employees", "Devices"], horizontal=True, key="admin_section")
    if st.button("Refresh dashboard"):
        st.rerun()
    try:
        {"Overview": overview, "Tickets": tickets, "Employees": employees, "Devices": devices}[section](api)
    except requests.RequestException as error:
        st.error(error_message(error))
