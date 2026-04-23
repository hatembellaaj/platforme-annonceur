from __future__ import annotations

import io
import os
import re
import tempfile
import time
from datetime import date, datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

import pandas as pd
import requests
import streamlit as st
from googleads import ad_manager as ad_manager_sdk


APP_DIR = Path(__file__).resolve().parent
DEFAULT_API_VERSION = "v202508"


def _get_secret(name: str, default: str = "") -> str:
    try:
        value = st.secrets.get(name, default)
    except Exception:
        value = os.getenv(name, default)
    return str(value or "").strip()


def _normalize_dt(value: Any) -> str:
    if value is None:
        return ""
    try:
        if hasattr(value, "date") and hasattr(value, "hour"):
            d = value.date
            return f"{int(d.year):04d}-{int(d.month):02d}-{int(d.day):02d}"
        parsed = pd.to_datetime(value, errors="coerce")
        if pd.isna(parsed):
            return ""
        return parsed.date().isoformat()
    except Exception:
        return ""


def _safe_int(value: Any) -> int | None:
    try:
        if value is None:
            return None
        return int(value)
    except Exception:
        return None


def _get_stats_value(stats: Any, attr: str) -> float:
    if stats is None:
        return 0.0
    try:
        value = getattr(stats, attr, 0)
        return float(value or 0)
    except Exception:
        return 0.0


def _goal_dict(goal: Any) -> dict[str, Any]:
    if goal is None:
        return {"goal_type": "", "unit_type": "", "units": 0}
    return {
        "goal_type": str(getattr(goal, "goalType", "") or ""),
        "unit_type": str(getattr(goal, "unitType", "") or ""),
        "units": _safe_int(getattr(goal, "units", 0)) or 0,
    }


def _fetch_all_by_statement(service, method_name: str, query: str, page_size: int = 500) -> list[Any]:
    offset = 0
    rows: list[Any] = []
    while True:
        statement = {"query": f"{query} LIMIT {page_size} OFFSET {offset}"}
        response = getattr(service, method_name)(statement)
        batch = getattr(response, "results", None) or response.get("results", []) or []
        if not batch:
            break
        rows.extend(batch)
        if len(batch) < page_size:
            break
        offset += page_size
    return rows


def _normalize_report_frame(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return frame
    renamed = {}
    for col in frame.columns:
        clean = str(col or "")
        clean = clean.replace("Dimension.", "").replace("Column.", "")
        clean = clean.replace("DimensionAttribute.", "")
        renamed[col] = clean.lower()
    return frame.rename(columns=renamed)


def _parse_date_input(value: str) -> dict[str, int]:
    parsed = pd.to_datetime(value).date()
    return {"year": parsed.year, "month": parsed.month, "day": parsed.day}


def _build_report_statement(campaign_ids: list[int], order_ids: list[int]) -> dict[str, str] | None:
    if campaign_ids:
        ids = ", ".join(str(int(item)) for item in campaign_ids)
        return {"query": f"WHERE LINE_ITEM_ID IN ({ids})"}
    if order_ids:
        ids = ", ".join(str(int(item)) for item in order_ids)
        return {"query": f"WHERE ORDER_ID IN ({ids})"}
    return None


@lru_cache(maxsize=1)
def get_gam_client():
    key_json = _get_secret("GAM_SERVICE_ACCOUNT_JSON")
    key_file = APP_DIR / "gam-service-account.json"
    if key_json:
        key_file.write_text(key_json, encoding="utf-8")
    if not key_file.exists():
        raise FileNotFoundError("Missing GAM service account JSON.")

    network_code = _get_secret("GAM_NETWORK_CODE", "9167326")
    api_version = _get_secret("GAM_API_VERSION", DEFAULT_API_VERSION)
    yaml_text = (
        "ad_manager:\n"
        "  application_name: Platform-Annonceur\n"
        f"  network_code: '{network_code}'\n"
        f"  path_to_private_key_file: \"{str(key_file).replace(chr(92), '/')}\"\n"
    )
    runtime_yaml_file = Path(tempfile.gettempdir()) / "platform-annonceur-googleads.yaml"
    runtime_yaml_file.write_text(yaml_text, encoding="utf-8")
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = str(key_file)
    client = ad_manager_sdk.AdManagerClient.LoadFromStorage(str(runtime_yaml_file))
    client._platform_annonceur_api_version = api_version
    return client


def _api_version() -> str:
    client = get_gam_client()
    return str(getattr(client, "_platform_annonceur_api_version", DEFAULT_API_VERSION))


@st.cache_data(ttl=1800, show_spinner="Chargement du contexte GAM...")
def get_company_order_campaign_bundle() -> dict[str, pd.DataFrame]:
    client = get_gam_client()
    api_version = _api_version()
    company_svc = client.GetService("CompanyService", version=api_version)
    order_svc = client.GetService("OrderService", version=api_version)
    line_item_svc = client.GetService("LineItemService", version=api_version)

    companies = _fetch_all_by_statement(company_svc, "getCompaniesByStatement", "WHERE type = 'ADVERTISER' ORDER BY id")
    orders = _fetch_all_by_statement(order_svc, "getOrdersByStatement", "ORDER BY id")
    line_items = _fetch_all_by_statement(line_item_svc, "getLineItemsByStatement", "ORDER BY id")

    company_name_map = {
        int(item.id): str(getattr(item, "name", "") or "")
        for item in companies
        if getattr(item, "id", None) is not None
    }
    order_advertiser_map: dict[int, int] = {}
    order_name_map: dict[int, str] = {}
    order_rows = []
    for item in orders:
        if getattr(item, "id", None) is None:
            continue
        order_id = int(item.id)
        advertiser_id = int(getattr(item, "advertiserId", 0) or 0) if getattr(item, "advertiserId", None) else None
        order_advertiser_map[order_id] = advertiser_id or 0
        order_name_map[order_id] = str(getattr(item, "name", "") or "")
        order_rows.append(
            {
                "order_id": order_id,
                "order_name": str(getattr(item, "name", "") or ""),
                "status": str(getattr(item, "status", "") or ""),
                "advertiser_id": advertiser_id,
                "advertiser_name": company_name_map.get(advertiser_id or -1, "") if advertiser_id else "",
                "start_date": _normalize_dt(getattr(item, "startDateTime", None)),
                "end_date": _normalize_dt(getattr(item, "endDateTime", None)),
                "is_archived": bool(getattr(item, "isArchived", False)),
            }
        )

    companies_df = pd.DataFrame(
        [
            {
                "advertiser_id": int(getattr(item, "id", 0) or 0),
                "advertiser_name": str(getattr(item, "name", "") or ""),
                "company_type": str(getattr(item, "type", "") or ""),
            }
            for item in companies
        ]
    )
    orders_df = pd.DataFrame(order_rows)

    campaign_rows = []
    for item in line_items:
        goal = _goal_dict(getattr(item, "primaryGoal", None))
        order_id = int(getattr(item, "orderId", 0) or 0) if getattr(item, "orderId", None) else None
        advertiser_id = order_advertiser_map.get(order_id or 0) if order_id else None
        campaign_rows.append(
            {
                "campaign_id": int(getattr(item, "id", 0) or 0),
                "campaign_name": str(getattr(item, "name", "") or ""),
                "status": str(getattr(item, "status", "") or ""),
                "order_id": order_id,
                "order_name": order_name_map.get(order_id or 0, "") if order_id else "",
                "advertiser_id": advertiser_id,
                "advertiser_name": company_name_map.get(advertiser_id or -1, "") if advertiser_id else "",
                "start_date": _normalize_dt(getattr(item, "startDateTime", None)),
                "end_date": _normalize_dt(getattr(item, "endDateTime", None)),
                "impressions_delivered": _get_stats_value(getattr(item, "stats", None), "impressionsDelivered"),
                "clicks_delivered": _get_stats_value(getattr(item, "stats", None), "clicksDelivered"),
                "primary_goal_units": goal["units"],
                "contracted_units_bought": _safe_int(getattr(item, "contractedUnitsBought", None)) or 0,
                "units_bought": _safe_int(getattr(item, "unitsBought", None)) or 0,
                "is_archived": bool(getattr(item, "isArchived", False)),
            }
        )
    campaigns_df = pd.DataFrame(campaign_rows)
    return {"companies_df": companies_df, "orders_df": orders_df, "campaigns_df": campaigns_df}


def run_direct_report(
    dimensions: list[str],
    columns: list[str],
    start_date: str,
    end_date: str,
    advertiser_name: str = "",
    campaign_name: str = "",
    limit_rows: int = 200000,
) -> dict[str, Any]:
    bundle = get_company_order_campaign_bundle()
    scoped_df = bundle["campaigns_df"].copy()
    if advertiser_name.strip():
        scoped_df = scoped_df[scoped_df["advertiser_name"].astype(str).str.upper() == advertiser_name.strip().upper()].copy()
    if campaign_name.strip():
        scoped_df = scoped_df[scoped_df["campaign_name"].astype(str).str.upper() == campaign_name.strip().upper()].copy()

    client = get_gam_client()
    api_version = _api_version()
    report_service = client.GetService("ReportService", version=api_version)
    statement = _build_report_statement(
        campaign_ids=[int(x) for x in scoped_df["campaign_id"].dropna().tolist()],
        order_ids=[int(x) for x in scoped_df["order_id"].dropna().tolist()],
    )
    report_query = {
        "dimensions": dimensions,
        "dimensionAttributes": [],
        "columns": columns,
        "dateRangeType": "CUSTOM_DATE",
        "startDate": _parse_date_input(start_date),
        "endDate": _parse_date_input(end_date),
        "adUnitView": "HIERARCHICAL",
    }
    if statement:
        report_query["statement"] = statement
    report_job_result = report_service.runReportJob({"reportQuery": report_query})
    report_job_id = int(report_job_result["id"])

    max_wait_seconds = 180
    elapsed = 0
    status = "IN_PROGRESS"
    while elapsed < max_wait_seconds:
        status = report_service.getReportJobStatus(report_job_id)
        if status == "COMPLETED":
            break
        if status in ("FAILED", "CANCELLED"):
            raise RuntimeError(f"Report job {report_job_id} ended with status {status}")
        time.sleep(5)
        elapsed += 5
    if status != "COMPLETED":
        raise TimeoutError(f"Report job {report_job_id} did not complete within {max_wait_seconds} seconds")

    download_url = report_service.getReportDownloadUrlWithOptions(
        report_job_id,
        {
            "exportFormat": "CSV_DUMP",
            "includeReportProperties": False,
            "includeTotalsRow": False,
            "useGzipCompression": False,
        },
    )
    response = requests.get(download_url, timeout=180)
    response.raise_for_status()
    frame = _normalize_report_frame(pd.read_csv(io.StringIO(response.text)))
    if limit_rows and len(frame) > int(limit_rows):
        frame = frame.head(int(limit_rows)).copy()
    return {"report_job_id": report_job_id, "status": status, "rows": frame.to_dict(orient="records")}
