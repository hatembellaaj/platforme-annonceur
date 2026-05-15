from __future__ import annotations

import os
from urllib.parse import urlsplit, unquote

import streamlit as st


def _get_setting(name: str, default: str = "") -> str:
    try:
        value = st.secrets.get(name, default)
    except Exception:
        value = os.getenv(name, default)
    return str(value or "").strip()


def _get_supabase_password() -> str:
    direct_password = _get_setting("SUPABASE_DB_PASSWORD")
    if direct_password:
        return direct_password
    db_url = _get_setting("SUPABASE_DB_URL")
    if not db_url:
        return ""
    parsed = urlsplit(db_url)
    if parsed.password:
        return unquote(parsed.password)
    return ""


def get_supabase_conninfo() -> str:
    db_url = _get_setting("SUPABASE_DB_URL")
    if db_url:
        parsed = urlsplit(db_url)
        user = parsed.username or _get_setting("SUPABASE_DB_USER", "postgres")
        password = parsed.password or _get_supabase_password()
        host = parsed.hostname or _get_setting("SUPABASE_DB_HOST")
        port = parsed.port or int(_get_setting("SUPABASE_DB_PORT", "5432") or 5432)
        dbname = parsed.path.lstrip("/") or _get_setting("SUPABASE_DB_NAME", "postgres")
    else:
        supabase_url = _get_setting("SUPABASE_URL")
        host = _get_setting("SUPABASE_DB_HOST")
        if not host and supabase_url:
            hostname = urlsplit(supabase_url).hostname or ""
            project_ref = hostname.split(".")[0] if hostname else ""
            host = f"db.{project_ref}.supabase.co" if project_ref else ""
        port = int(_get_setting("SUPABASE_DB_PORT", "5432") or 5432)
        dbname = _get_setting("SUPABASE_DB_NAME", "postgres")
        user = _get_setting("SUPABASE_DB_USER", "postgres")
        password = _get_supabase_password()
    if not host or not password:
        raise RuntimeError("Supabase database configuration incomplete.")
    sslmode = _get_setting("SUPABASE_DB_SSLMODE", "require") or "require"
    return f"host={host} port={port} dbname={dbname} user={user} password={password} sslmode={sslmode}"
