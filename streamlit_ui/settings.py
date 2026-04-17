import subprocess
import sys

import streamlit as st
from config_service import config_service


def _pick_directory() -> str | None:
    script = (
        "import tkinter as tk; from tkinter import filedialog; "
        "root = tk.Tk(); root.withdraw(); root.wm_attributes('-topmost', 1); "
        "path = filedialog.askdirectory(title='Select Base Directory'); "
        "root.destroy(); print(path, end='')"
    )
    result = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True)
    return result.stdout.strip() or None


def _render_path_entry(entry) -> None:
    picker_key = f"_picked_{entry.key}"
    current = st.session_state.get(picker_key, entry.value or "")

    col_input, col_btn = st.columns([4, 1])
    with col_input:
        new_val = st.text_input(entry.label, value=current, help=entry.description)
    with col_btn:
        st.write("")  # spacer for vertical alignment
        if st.button("Browse…", key=f"browse_{entry.key}"):
            picked = _pick_directory()
            if picked:
                st.session_state[picker_key] = picked
                st.rerun()

    if st.button(f"Save {entry.label}", key=f"save_{entry.key}", type="primary"):
        if new_val:
            config_service.set(entry.key, new_val)
            st.session_state.pop(picker_key, None)
            st.success(f"{entry.label} saved!")


@st.dialog("🔐 Unlock Settings")
def render_password_dialog():
    if not config_service.has_master_password():
        st.warning("No master password set. Create one to encrypt your secrets.")
        with st.form("dialog_setup_master_password"):
            password = st.text_input("Master Password", type="password")
            confirm = st.text_input("Confirm Password", type="password")
            submitted = st.form_submit_button("Set Master Password", type="primary")
        if submitted:
            if not password:
                st.error("Password cannot be empty.")
            elif len(password) < 8:
                st.error("Password must be at least 8 characters.")
            elif password != confirm:
                st.error("Passwords don't match.")
            else:
                config_service.set_master_password(password)
                st.rerun()
    else:
        st.info("Enter your master password to unlock encrypted settings.")
        with st.form("dialog_unlock_master_password"):
            password = st.text_input("Master Password", type="password")
            submitted = st.form_submit_button("Unlock", type="primary")
        if submitted:
            if config_service.unlock(password):
                st.rerun()
            else:
                st.error("Incorrect password.")


def render_settings_page():
    st.title("Settings")

    if not config_service.has_master_password():
        _render_setup_master_password()
        return

    if config_service.is_locked():
        _render_unlock()
        return

    _render_config_forms()


def _render_setup_master_password():
    st.warning("No master password set. Create one to encrypt your secrets.")

    with st.form("setup_master_password"):
        password = st.text_input("Master Password", type="password")
        confirm = st.text_input("Confirm Password", type="password")
        submitted = st.form_submit_button("Set Master Password", type="primary")

    if submitted:
        if not password:
            st.error("Password cannot be empty.")
        elif len(password) < 8:
            st.error("Password must be at least 8 characters.")
        elif password != confirm:
            st.error("Passwords don't match.")
        else:
            config_service.set_master_password(password)
            st.success("Master password set!")
            st.rerun()


def _render_unlock():
    st.info("Enter your master password to unlock encrypted settings.")

    with st.form("unlock_master_password"):
        password = st.text_input("Master Password", type="password")
        submitted = st.form_submit_button("Unlock", type="primary")

    if submitted:
        if config_service.unlock(password):
            st.success("Unlocked!")
            st.rerun()
        else:
            st.error("Incorrect password.")


def _render_config_forms():
    col1, col2 = st.columns([3, 1])
    with col2:
        if st.button("Import from .env", use_container_width=True):
            count = config_service.seed_from_env()
            if count > 0:
                st.success(f"Imported {count} value(s) from environment.")
                st.rerun()
            else:
                st.info("No environment values found to import.")

    groups = config_service.get_all_by_group()

    for group_name, entries in groups.items():
        path_entries = [e for e in entries if e.value_type == "path"]
        other_entries = [e for e in entries if e.value_type != "path"]

        configured = sum(1 for e in entries if e.value)
        total = len(entries)
        status = f"({configured}/{total})"

        with st.expander(f"{group_name} {status}", expanded=True):
            for entry in path_entries:
                _render_path_entry(entry)

            if other_entries:
                with st.form(f"settings_form_{group_name}"):
                    values = {}
                    for entry in other_entries:
                        if entry.value_type == "json_content":
                            current_json_content = ""
                            if entry.value:
                                try:
                                    with open(entry.value, "r") as f:
                                        current_json_content = f.read()
                                except Exception:
                                    pass

                            values[entry.key] = st.text_area(
                                entry.label,
                                value=current_json_content,
                                height=200,
                                help=entry.description,
                            )
                        else:
                            input_type = "password" if entry.is_secret else "default"
                            values[entry.key] = st.text_input(
                                entry.label,
                                value=entry.value or "",
                                type=input_type,
                                help=entry.description,
                            )

                    if st.form_submit_button(f"Save {group_name}", type="primary"):
                        saved = 0
                        for key, val in values.items():
                            if val:
                                entry_type = next(
                                    (e.value_type for e in other_entries if e.key == key),
                                    "string",
                                )

                                if entry_type == "json_content":
                                    file_path = "service_account_key.json"
                                    try:
                                        with open(file_path, "w") as f:
                                            f.write(val)
                                        config_service.set(key, file_path)
                                        saved += 1
                                    except Exception as e:
                                        st.error(f"Failed to save {key}: {e}")
                                else:
                                    config_service.set(key, val)
                                    saved += 1
                        if saved:
                            st.success(f"{group_name} settings saved!")
                            st.rerun()
