from __future__ import annotations

import json
import sys
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd
import psycopg
import streamlit as st

from gam_api import get_company_order_campaign_bundle, run_direct_report  # noqa: E402
from local_supabase import get_supabase_conninfo  # noqa: E402

APP_DIR = Path(__file__).resolve().parent
SETTINGS_FILE = APP_DIR / "platform_settings.json"
ORDER_OVERRIDES_FILE = APP_DIR / "order_overrides.json"
CAMPAIGN_OVERRIDES_FILE = APP_DIR / "campaign_overrides.json"
OVERRIDES_TABLE = "platform_annonceur_overrides"

ACTIVE_STATUSES = {"DELIVERING", "ACTIVE", "READY", "STARTED", "APPROVED"}
INACTIVE_STATUSES = {
    "COMPLETED",
    "PAUSED",
    "PAUSED_INVENTORY_RELEASED",
    "INACTIVE",
    "CANCELED",
    "DISAPPROVED",
    "DRAFT",
    "PENDING_APPROVAL",
    "ON_HOLD",
}
MONTH_LABELS_FR = {
    1: "janv.",
    2: "fevr.",
    3: "mars",
    4: "avr.",
    5: "mai",
    6: "juin",
    7: "juil.",
    8: "aout",
    9: "sept.",
    10: "oct.",
    11: "nov.",
    12: "dec.",
}


@dataclass
class CampaignRecord:
    advertiser_id: str
    advertiser_name: str
    campaign_id: str
    campaign_name: str
    order_id: str
    order_name: str
    impressions: int
    clicks: int
    ctr: float
    objective_source_value: float
    objective_override_value: float | None
    objective_effective_value: float
    source_status: str
    is_archived_source: bool
    is_active_source: bool
    is_active_override: bool | None
    is_active: bool
    active_status_label: str
    start_date_source: str | None
    start_date_override: str | None
    start_date: str | None
    end_date_source: str | None
    end_date_override: str | None
    end_date: str | None
    duration_days: int
    progress_pct_raw: float
    progress_pct_ui: float
    alert_label: str


@dataclass
class OrderRecord:
    order_id: str
    order_name: str
    advertiser_id: str
    advertiser_name: str
    impressions: int
    clicks: int
    ctr: float
    objective_source_value: float
    objective_override_value: float | None
    objective_effective_value: float
    active_campaign_count: int
    total_campaign_count: int
    is_active: bool
    active_status_label: str
    official_start_date: str | None
    official_end_date: str | None
    duration_days: int
    progress_pct_raw: float
    progress_pct_ui: float
    alert_label: str
    is_archived_source: bool


@dataclass
class AdvertiserRecord:
    advertiser_id: str
    advertiser_name: str
    impressions: int
    clicks: int
    ctr: float
    objective_source_value: float
    objective_override_value: float | None
    objective_effective_value: float
    active_campaign_count: int
    total_campaign_count: int
    is_active: bool
    active_status_label: str
    official_start_date: str | None
    official_end_date: str | None
    duration_days: int
    progress_pct_raw: float
    progress_pct_ui: float
    alert_label: str


def safe_float(value: Any) -> float:
    try:
        if value in ("", None):
            return 0.0
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def safe_int(value: Any) -> int:
    try:
        if value in ("", None):
            return 0
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def compute_ctr(impressions: Any, clicks: Any) -> float:
    impression_value = safe_float(impressions)
    click_value = safe_float(clicks)
    return round((click_value / impression_value) * 100, 3) if impression_value else 0.0


def parse_iso_date(value: Any) -> date | None:
    if value in (None, ""):
        return None
    try:
        parsed = pd.to_datetime(value, errors="coerce")
        if pd.isna(parsed):
            return None
        return parsed.date()
    except Exception:
        return None


def format_iso_date(value: Any) -> str | None:
    parsed = parse_iso_date(value)
    return parsed.isoformat() if parsed else None


def duration_days(start_value: Any, end_value: Any) -> int:
    start_date = parse_iso_date(start_value)
    end_date = parse_iso_date(end_value)
    if not start_date or not end_date:
        return 0
    return max((end_date - start_date).days + 1, 0)


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def save_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def get_override_storage_mode() -> str:
    try:
        get_supabase_conninfo()
        return "supabase"
    except Exception:
        return "local"


def ensure_override_storage_schema() -> None:
    if get_override_storage_mode() != "supabase":
        return
    with psycopg.connect(get_supabase_conninfo()) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                f"""
                create table if not exists {OVERRIDES_TABLE} (
                    scope text not null,
                    entity_id text not null,
                    payload jsonb not null default '{{}}'::jsonb,
                    updated_at timestamptz not null default now(),
                    primary key (scope, entity_id)
                )
                """
            )
        connection.commit()


def load_override_scope(scope: str, fallback_path: Path) -> dict[str, Any]:
    if get_override_storage_mode() != "supabase":
        return load_json(fallback_path)
    try:
        ensure_override_storage_schema()
        result: dict[str, Any] = {}
        with psycopg.connect(get_supabase_conninfo()) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"select entity_id, payload from {OVERRIDES_TABLE} where scope = %s order by entity_id",
                    (scope,),
                )
                for entity_id, payload in cursor.fetchall():
                    result[str(entity_id)] = dict(payload or {})
        return result
    except Exception:
        return load_json(fallback_path)


def save_override_scope(scope: str, payload: dict[str, Any], fallback_path: Path) -> None:
    if get_override_storage_mode() != "supabase":
        save_json(fallback_path, payload)
        return
    try:
        ensure_override_storage_schema()
        with psycopg.connect(get_supabase_conninfo()) as connection:
            with connection.cursor() as cursor:
                cursor.execute(f"delete from {OVERRIDES_TABLE} where scope = %s", (scope,))
                for entity_id, row_payload in payload.items():
                    cursor.execute(
                        f"""
                        insert into {OVERRIDES_TABLE}(scope, entity_id, payload, updated_at)
                        values (%s, %s, %s::jsonb, now())
                        on conflict (scope, entity_id) do update
                        set payload = excluded.payload, updated_at = excluded.updated_at
                        """,
                        (scope, str(entity_id), json.dumps(row_payload, ensure_ascii=False)),
                    )
            connection.commit()
    except Exception:
        save_json(fallback_path, payload)


def load_platform_settings(path: Path = SETTINGS_FILE) -> dict[str, Any]:
    return load_override_scope("settings", path)


def save_platform_settings(settings: dict[str, Any], path: Path = SETTINGS_FILE) -> None:
    save_override_scope("settings", settings, path)


def load_order_overrides(path: Path = ORDER_OVERRIDES_FILE) -> dict[str, dict[str, Any]]:
    raw = load_override_scope("order", path)
    result: dict[str, dict[str, Any]] = {}
    for order_id, values in raw.items():
        result[str(order_id)] = {
            "objective_override_value": safe_float(values.get("objective_override_value", 0))
            if values.get("objective_override_value") not in (None, "")
            else None,
        }
    return result


def save_order_overrides(overrides: dict[str, dict[str, Any]], path: Path = ORDER_OVERRIDES_FILE) -> None:
    payload = {}
    for order_id, values in overrides.items():
        payload[str(order_id)] = {
            "objective_override_value": values.get("objective_override_value"),
        }
    save_override_scope("order", payload, path)


def load_campaign_overrides(path: Path = CAMPAIGN_OVERRIDES_FILE) -> dict[str, dict[str, Any]]:
    raw = load_override_scope("campaign", path)
    result: dict[str, dict[str, Any]] = {}
    for campaign_id, values in raw.items():
        status_override = values.get("is_active_override")
        if status_override not in (True, False, None):
            status_override = None
        result[str(campaign_id)] = {
            "objective_override_value": safe_float(values.get("objective_override_value", 0))
            if values.get("objective_override_value") not in (None, "")
            else None,
            "is_active_override": status_override,
            "start_date_override": format_iso_date(values.get("start_date_override")),
            "end_date_override": format_iso_date(values.get("end_date_override")),
        }
    return result


def save_campaign_overrides(overrides: dict[str, dict[str, Any]], path: Path = CAMPAIGN_OVERRIDES_FILE) -> None:
    payload = {}
    for campaign_id, values in overrides.items():
        payload[str(campaign_id)] = {
            "objective_override_value": values.get("objective_override_value"),
            "is_active_override": values.get("is_active_override"),
            "start_date_override": format_iso_date(values.get("start_date_override")),
            "end_date_override": format_iso_date(values.get("end_date_override")),
        }
    save_override_scope("campaign", payload, path)


@st.cache_data(ttl=1800, show_spinner="Chargement des campagnes GAM...")
def fetch_gam_campaign_snapshot() -> pd.DataFrame:
    bundle = get_company_order_campaign_bundle()
    campaigns = bundle.get("campaigns_df", pd.DataFrame()).copy()
    if campaigns.empty:
        return pd.DataFrame(
            columns=[
                "advertiser_id",
                "advertiser_name",
                "campaign_id",
                "campaign_name",
                "order_id",
                "order_name",
                "status",
                "is_archived",
                "start_date",
                "end_date",
                "primary_goal_units",
                "contracted_units_bought",
                "units_bought",
                "impressions_delivered",
                "clicks_delivered",
            ]
        )
    campaigns["advertiser_id"] = campaigns["advertiser_id"].fillna(0).astype(int).astype(str)
    campaigns["campaign_id"] = campaigns["campaign_id"].fillna(0).astype(int).astype(str)
    campaigns["order_id"] = campaigns["order_id"].fillna(0).astype(int).astype(str)
    campaigns["advertiser_name"] = campaigns["advertiser_name"].fillna("").astype(str).str.strip()
    campaigns["campaign_name"] = campaigns["campaign_name"].fillna("").astype(str).str.strip()
    campaigns["order_name"] = campaigns["order_name"].fillna("").astype(str).str.strip()
    campaigns["status"] = campaigns["status"].fillna("").astype(str).str.strip().str.upper()
    campaigns["start_date"] = campaigns["start_date"].apply(format_iso_date)
    campaigns["end_date"] = campaigns["end_date"].apply(format_iso_date)
    campaigns["is_archived"] = campaigns["is_archived"].fillna(False).astype(bool)
    for column in [
        "primary_goal_units",
        "contracted_units_bought",
        "units_bought",
        "impressions_delivered",
        "clicks_delivered",
    ]:
        campaigns[column] = pd.to_numeric(campaigns.get(column, 0), errors="coerce").fillna(0)
    return campaigns


@st.cache_data(ttl=1800, show_spinner="Chargement des ordres GAM...")
def fetch_gam_order_snapshot() -> pd.DataFrame:
    bundle = get_company_order_campaign_bundle()
    orders = bundle.get("orders_df", pd.DataFrame()).copy()
    if orders.empty:
        return pd.DataFrame(
            columns=[
                "order_id",
                "order_name",
                "advertiser_id",
                "advertiser_name",
                "status",
                "start_date",
                "end_date",
                "is_archived",
            ]
        )
    orders["order_id"] = orders["order_id"].fillna(0).astype(int).astype(str)
    orders["advertiser_id"] = orders["advertiser_id"].fillna(0).astype(int).astype(str)
    orders["order_name"] = orders["order_name"].fillna("").astype(str).str.strip()
    orders["advertiser_name"] = orders["advertiser_name"].fillna("").astype(str).str.strip()
    orders["status"] = orders["status"].fillna("").astype(str).str.strip().str.upper()
    orders["start_date"] = orders["start_date"].apply(format_iso_date)
    orders["end_date"] = orders["end_date"].apply(format_iso_date)
    orders["is_archived"] = orders["is_archived"].fillna(False).astype(bool)
    return orders


@st.cache_data(ttl=1800, show_spinner="Chargement des impressions GAM...")
def fetch_gam_daily_report(start_date_iso: str, end_date_iso: str, advertiser_name: str = "") -> pd.DataFrame:
    report = run_direct_report(
        dimensions=["DATE", "ADVERTISER_ID", "ADVERTISER_NAME", "ORDER_ID", "ORDER_NAME", "LINE_ITEM_ID", "LINE_ITEM_NAME", "LINE_ITEM_STATUS"],
        columns=["AD_SERVER_IMPRESSIONS", "AD_SERVER_CLICKS", "AD_SERVER_CTR"],
        start_date=start_date_iso,
        end_date=end_date_iso,
        advertiser_name=advertiser_name,
    )
    rows = report.get("rows", []) if isinstance(report, dict) else []
    if not rows:
        return pd.DataFrame(
            columns=[
                "date",
                "advertiser_id",
                "advertiser_name",
                "order_id",
                "order_name",
                "campaign_id",
                "campaign_name",
                "source_status",
                "impressions",
                "clicks",
                "ctr",
            ]
        )
    frame = pd.DataFrame(rows)
    def text_series(column_name: str) -> pd.Series:
        if column_name in frame.columns:
            return frame[column_name].fillna("").astype(str).str.strip()
        return pd.Series([""] * len(frame), index=frame.index, dtype="object")
    frame["date"] = pd.to_datetime(frame.get("date"), errors="coerce")
    frame = frame.dropna(subset=["date"]).copy()
    frame["advertiser_id"] = text_series("advertiser_id")
    frame["advertiser_name"] = text_series("advertiser_name")
    frame["order_id"] = text_series("order_id")
    frame["order_name"] = text_series("order_name")
    frame["campaign_id"] = text_series("line_item_id")
    frame["campaign_name"] = text_series("line_item_name")
    frame["source_status"] = text_series("line_item_status").str.upper()
    frame["impressions"] = pd.to_numeric(frame.get("ad_server_impressions", 0), errors="coerce").fillna(0).astype(int)
    frame["clicks"] = pd.to_numeric(frame.get("ad_server_clicks", 0), errors="coerce").fillna(0).astype(int)
    frame["ctr"] = pd.to_numeric(frame.get("ad_server_ctr", 0), errors="coerce").fillna(0.0)
    return frame[
        [
            "date",
            "advertiser_id",
            "advertiser_name",
            "order_id",
            "order_name",
            "campaign_id",
            "campaign_name",
            "source_status",
            "impressions",
            "clicks",
            "ctr",
        ]
    ].copy()


def infer_is_active(source_status: str, start_value: Any, end_value: Any, is_archived: bool) -> bool:
    if is_archived:
        return False
    status = str(source_status or "").strip().upper()
    today = pd.Timestamp.now().date()
    start_day = parse_iso_date(start_value)
    end_day = parse_iso_date(end_value)
    if status in INACTIVE_STATUSES:
        return False
    if status and status not in ACTIVE_STATUSES:
        return False
    if start_day and start_day > today:
        return False
    if end_day and end_day < today:
        return False
    return True


def get_objective_source_value(row: pd.Series) -> float:
    for candidate in ["primary_goal_units", "contracted_units_bought", "units_bought"]:
        value = safe_float(row.get(candidate))
        if value > 0:
            return round(value, 2)
    return 0.0


def compute_progress_ui(impressions: Any, objective: Any) -> tuple[float, float]:
    objective_value = safe_float(objective)
    if objective_value <= 0:
        return 0.0, 0.0
    progress_raw = round((safe_float(impressions) / objective_value) * 100, 2)
    return progress_raw, min(progress_raw, 100.0)


def build_campaign_records(frame: pd.DataFrame, campaign_overrides: dict[str, dict[str, Any]]) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame([asdict(record) for record in []])

    records: list[CampaignRecord] = []
    for _, row in frame.iterrows():
        campaign_id = str(row.get("campaign_id", ""))
        override = campaign_overrides.get(campaign_id, {})
        objective_override = override.get("objective_override_value")
        source_start = format_iso_date(row.get("start_date"))
        source_end = format_iso_date(row.get("end_date"))
        start_override = format_iso_date(override.get("start_date_override"))
        end_override = format_iso_date(override.get("end_date_override"))
        status_override = override.get("is_active_override")
        objective_source = get_objective_source_value(row)
        objective_effective = objective_override if objective_override not in (None, "") else objective_source
        source_status = str(row.get("status", "") or "").upper()
        source_is_active = infer_is_active(source_status, source_start, source_end, bool(row.get("is_archived", False)))
        effective_is_active = status_override if status_override is not None else source_is_active
        effective_start = start_override or source_start
        effective_end = end_override or source_end
        impressions = safe_int(row.get("impressions_delivered"))
        clicks = safe_int(row.get("clicks_delivered"))
        progress_raw, progress_ui = compute_progress_ui(impressions, objective_effective)
        records.append(
            CampaignRecord(
                advertiser_id=str(row.get("advertiser_id", "")),
                advertiser_name=str(row.get("advertiser_name", "") or ""),
                campaign_id=campaign_id,
                campaign_name=str(row.get("campaign_name", "") or ""),
                order_id=str(row.get("order_id", "") or ""),
                order_name=str(row.get("order_name", "") or ""),
                impressions=impressions,
                clicks=clicks,
                ctr=compute_ctr(impressions, clicks),
                objective_source_value=objective_source,
                objective_override_value=round(safe_float(objective_override), 2) if objective_override not in (None, "") else None,
                objective_effective_value=round(objective_effective, 2),
                source_status=source_status,
                is_archived_source=bool(row.get("is_archived", False)),
                is_active_source=source_is_active,
                is_active_override=status_override,
                is_active=bool(effective_is_active),
                active_status_label="Active" if effective_is_active else "Inactive",
                start_date_source=source_start,
                start_date_override=start_override,
                start_date=effective_start,
                end_date_source=source_end,
                end_date_override=end_override,
                end_date=effective_end,
                duration_days=duration_days(effective_start, effective_end),
                progress_pct_raw=progress_raw,
                progress_pct_ui=progress_ui,
                alert_label="Active" if effective_is_active else "Inactive",
            )
        )
    return pd.DataFrame([asdict(record) for record in records]).sort_values(
        ["is_active", "impressions", "campaign_name"],
        ascending=[False, False, True],
    ).reset_index(drop=True)


def build_order_records(order_df: pd.DataFrame, campaign_df: pd.DataFrame, order_overrides: dict[str, dict[str, Any]]) -> pd.DataFrame:
    if order_df.empty:
        return pd.DataFrame([asdict(record) for record in []])

    records: list[OrderRecord] = []
    for _, row in order_df.iterrows():
        order_id = str(row.get("order_id", ""))
        order_slice = campaign_df[campaign_df["order_id"].astype(str) == order_id].copy()
        override = order_overrides.get(order_id, {})
        non_archived_slice = order_slice[~order_slice["is_archived_source"].astype(bool)].copy() if not order_slice.empty else order_slice
        objective_source_base = non_archived_slice if not non_archived_slice.empty else order_slice
        objective_source = round(safe_float(objective_source_base["objective_source_value"].sum()), 2) if not objective_source_base.empty else 0.0
        objective_override = override.get("objective_override_value")
        objective_effective = objective_override if objective_override not in (None, "") else objective_source
        active_slice = order_slice[order_slice["is_active"]].copy()
        active_campaign_count = safe_int(active_slice["campaign_id"].nunique()) if not active_slice.empty else 0
        total_campaign_count = safe_int(order_slice["campaign_id"].nunique()) if not order_slice.empty else 0
        impressions = safe_int(order_slice["impressions"].sum()) if not order_slice.empty else 0
        clicks = safe_int(order_slice["clicks"].sum()) if not order_slice.empty else 0
        official_start = min(filter(None, active_slice["start_date"].tolist()), default=None) if not active_slice.empty else format_iso_date(row.get("start_date"))
        official_end = max(filter(None, active_slice["end_date"].tolist()), default=None) if not active_slice.empty else format_iso_date(row.get("end_date"))
        progress_raw, progress_ui = compute_progress_ui(impressions, objective_effective)
        records.append(
            OrderRecord(
                order_id=order_id,
                order_name=str(row.get("order_name", "") or ""),
                advertiser_id=str(row.get("advertiser_id", "") or ""),
                advertiser_name=str(row.get("advertiser_name", "") or ""),
                impressions=impressions,
                clicks=clicks,
                ctr=compute_ctr(impressions, clicks),
                objective_source_value=objective_source,
                objective_override_value=round(safe_float(objective_override), 2) if objective_override not in (None, "") else None,
                objective_effective_value=round(objective_effective, 2),
                active_campaign_count=active_campaign_count,
                total_campaign_count=total_campaign_count,
                is_active=active_campaign_count > 0,
                active_status_label="Active" if active_campaign_count > 0 else "Inactive",
                official_start_date=official_start,
                official_end_date=official_end,
                duration_days=duration_days(official_start, official_end),
                progress_pct_raw=progress_raw,
                progress_pct_ui=progress_ui,
                alert_label="Active" if active_campaign_count > 0 else "Inactive",
                is_archived_source=bool(row.get("is_archived", False)),
            )
        )
    return pd.DataFrame([asdict(record) for record in records]).sort_values(
        ["is_active", "active_campaign_count", "impressions", "advertiser_name", "order_name"],
        ascending=[False, False, False, True, True],
    ).reset_index(drop=True)


def build_advertiser_records(order_df: pd.DataFrame) -> pd.DataFrame:
    if order_df.empty:
        return pd.DataFrame([asdict(record) for record in []])

    records: list[AdvertiserRecord] = []
    for (advertiser_id, advertiser_name), advertiser_slice in order_df.groupby(["advertiser_id", "advertiser_name"], as_index=False):
        active_slice = advertiser_slice[advertiser_slice["is_active"]].copy()
        official_start = min(filter(None, active_slice["official_start_date"].tolist()), default=None) if not active_slice.empty else None
        official_end = max(filter(None, active_slice["official_end_date"].tolist()), default=None) if not active_slice.empty else None
        total_impressions = safe_int(advertiser_slice["impressions"].sum())
        total_clicks = safe_int(advertiser_slice["clicks"].sum())
        objective_effective = round(safe_float(advertiser_slice["objective_effective_value"].sum()), 2)
        objective_source = round(safe_float(advertiser_slice["objective_source_value"].sum()), 2)
        progress_raw, progress_ui = compute_progress_ui(total_impressions, objective_effective)
        active_campaign_count = safe_int(active_slice["active_campaign_count"].sum()) if not active_slice.empty else 0
        records.append(
            AdvertiserRecord(
                advertiser_id=str(advertiser_id),
                advertiser_name=str(advertiser_name),
                impressions=total_impressions,
                clicks=total_clicks,
                ctr=compute_ctr(total_impressions, total_clicks),
                objective_source_value=objective_source,
                objective_override_value=None,
                objective_effective_value=round(objective_effective, 2),
                active_campaign_count=active_campaign_count,
                total_campaign_count=safe_int(advertiser_slice["order_id"].nunique()),
                is_active=active_campaign_count > 0,
                active_status_label="Active" if active_campaign_count > 0 else "Inactive",
                official_start_date=official_start,
                official_end_date=official_end,
                duration_days=duration_days(official_start, official_end),
                progress_pct_raw=progress_raw,
                progress_pct_ui=progress_ui,
                alert_label="Active" if active_campaign_count > 0 else "Inactive",
            )
        )
    return pd.DataFrame([asdict(record) for record in records]).sort_values(
        ["is_active", "active_campaign_count", "advertiser_name"],
        ascending=[False, False, True],
    ).reset_index(drop=True)


def build_daily_frame(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame(
            columns=[
                "advertiser_id",
                "advertiser_name",
                "order_id",
                "order_name",
                "campaign_id",
                "campaign_name",
                "date",
                "impressions",
                "clicks",
                "ctr",
                "source_status",
            ]
        )
    daily = (
        frame.groupby(
            [
                "advertiser_id",
                "advertiser_name",
                "order_id",
                "order_name",
                "campaign_id",
                "campaign_name",
                "date",
                "source_status",
            ],
            as_index=False,
        )[["impressions", "clicks"]]
        .sum()
    )
    daily["ctr"] = daily.apply(lambda item: compute_ctr(item["impressions"], item["clicks"]), axis=1)
    return daily


def apply_date_filter(daily_df: pd.DataFrame, start_date: date, end_date: date) -> pd.DataFrame:
    if daily_df.empty:
        return daily_df
    working = daily_df.copy()
    mask = (pd.to_datetime(working["date"]).dt.date >= start_date) & (pd.to_datetime(working["date"]).dt.date <= end_date)
    return working.loc[mask].copy()


def build_admin_summary(filtered_daily: pd.DataFrame, order_df: pd.DataFrame) -> dict[str, Any]:
    total_impressions = safe_int(filtered_daily["impressions"].sum()) if not filtered_daily.empty else 0
    total_clicks = safe_int(filtered_daily["clicks"].sum()) if not filtered_daily.empty else 0
    effective_objective_total = round(safe_float(order_df["objective_effective_value"].sum()), 2) if not order_df.empty else 0.0
    global_progress_raw, global_progress_ui = compute_progress_ui(total_impressions, effective_objective_total)
    return {
        "active_advertisers": safe_int(order_df.loc[order_df["is_active"], "advertiser_id"].nunique()) if not order_df.empty else 0,
        "active_campaigns": safe_int(order_df["active_campaign_count"].sum()) if not order_df.empty else 0,
        "total_impressions": total_impressions,
        "total_clicks": total_clicks,
        "total_ctr": compute_ctr(total_impressions, total_clicks),
        "effective_objective_total": effective_objective_total,
        "global_progress_raw": global_progress_raw,
        "global_progress_ui": global_progress_ui,
    }


def build_advertiser_summary_row(filtered_daily: pd.DataFrame, advertiser_row: pd.Series) -> dict[str, Any]:
    total_impressions = safe_int(filtered_daily["impressions"].sum()) if not filtered_daily.empty else 0
    total_clicks = safe_int(filtered_daily["clicks"].sum()) if not filtered_daily.empty else 0
    objective_effective = safe_float(advertiser_row.get("objective_effective_value"))
    progress_raw, progress_ui = compute_progress_ui(total_impressions, objective_effective)
    return {
        "total_impressions": total_impressions,
        "total_clicks": total_clicks,
        "total_ctr": compute_ctr(total_impressions, total_clicks),
        "progress_raw": progress_raw,
        "progress_ui": progress_ui,
    }


def format_month_label(period_value: pd.Period) -> str:
    return f"{MONTH_LABELS_FR.get(period_value.month, str(period_value.month))}-{str(period_value.year)[-2:]}"


def get_grain_labels(grain: str) -> dict[str, str]:
    if grain == "day":
        return {
            "objective": "Obj. jour",
            "sum": "somme/jours",
            "gap": "Ecart/jour",
            "radio": "Jour",
        }
    if grain == "week":
        return {
            "objective": "Obj. sem",
            "sum": "somme/semaines",
            "gap": "Ecart/sem",
            "radio": "Semaine",
        }
    return {
        "objective": "ob. Mens",
        "sum": "somme/mois",
        "gap": "Ecart/mois",
        "radio": "Mois",
    }


def _get_period_key(series: pd.Series, grain: str) -> pd.Series:
    if grain == "day":
        return pd.to_datetime(series).dt.to_period("D")
    if grain == "week":
        return pd.to_datetime(series).dt.to_period("W-MON")
    if grain == "month":
        return pd.to_datetime(series).dt.to_period("M")
    raise ValueError(f"Unsupported grain: {grain}")


def _format_period_label(period_value: pd.Period, grain: str) -> str:
    if grain == "day":
        return period_value.start_time.strftime("%Y-%m-%d")
    if grain == "week":
        start = period_value.start_time.strftime("%Y-%m-%d")
        end = period_value.end_time.strftime("%Y-%m-%d")
        return f"{start} -> {end}"
    return format_month_label(period_value)


def _count_total_periods(start_value: Any, end_value: Any, grain: str) -> int:
    start_day = parse_iso_date(start_value)
    end_day = parse_iso_date(end_value)
    if not start_day or not end_day or end_day < start_day:
        return 0
    date_range = pd.date_range(start_day, end_day, freq="D")
    return max(_get_period_key(pd.Series(date_range), grain).nunique(), 0)


def compute_table_alert(is_active: bool, moyenne: float, ecart_periode: float) -> str:
    if not is_active:
        return "Inactif"
    if moyenne <= 0:
        return "Aucune diffusion"
    if ecart_periode < 0:
        return "En retard"
    if ecart_periode > 0:
        return "En avance"
    return "Dans l'objectif"


def _prepare_period_columns(filtered_daily: pd.DataFrame, group_cols: list[str], grain: str) -> tuple[pd.DataFrame, list[str], int]:
    if filtered_daily.empty:
        return pd.DataFrame(columns=group_cols), [], 0
    working = filtered_daily.copy()
    working["period_key"] = _get_period_key(pd.to_datetime(working["date"]), grain)
    grouped = working.groupby(group_cols + ["period_key"], as_index=False)["impressions"].sum()
    periods = sorted(grouped["period_key"].unique())
    labels = [_format_period_label(period_value, grain) for period_value in periods]
    grouped["period_label"] = grouped["period_key"].apply(lambda item: _format_period_label(item, grain))
    pivot = grouped.pivot(index=group_cols, columns="period_label", values="impressions").reset_index()
    pivot = pivot.fillna(0)
    for label in labels:
        if label not in pivot.columns:
            pivot[label] = 0
    return pivot, labels, len(labels)


def _attach_period_metrics(
    table: pd.DataFrame,
    period_labels: list[str],
    visible_period_count: int,
    grain: str,
    start_col: str,
    end_col: str,
    objective_col: str,
    status_col: str,
) -> pd.DataFrame:
    labels = get_grain_labels(grain)
    for label in period_labels:
        table[label] = pd.to_numeric(table[label], errors="coerce").fillna(0).astype(int)
    table["period_target_count"] = table.apply(
        lambda item: _count_total_periods(item.get(start_col), item.get(end_col), grain),
        axis=1,
    )
    table["obj_period"] = table.apply(
        lambda item: (safe_float(item.get(objective_col)) / safe_float(item.get("period_target_count")))
        if safe_float(item.get("period_target_count")) > 0
        else 0.0,
        axis=1,
    )
    table["P"] = table[period_labels].sum(axis=1) if period_labels else 0
    table["Q"] = table["P"] / visible_period_count if visible_period_count > 0 else 0
    table["R"] = table["Q"] - table["obj_period"]
    table["S"] = table.apply(
        lambda item: (safe_float(item["R"]) / safe_float(item["Q"]) * 100) if safe_float(item["Q"]) > 0 else 0.0,
        axis=1,
    )
    table["progress_pct_ui"] = table.apply(
        lambda item: compute_progress_ui(item["P"], item.get(objective_col))[1],
        axis=1,
    )
    table["alert_label"] = table.apply(
        lambda item: compute_table_alert(str(item.get(status_col)) == "Active", safe_float(item["Q"]), safe_float(item["R"])),
        axis=1,
    )
    table["objective_label"] = labels["objective"]
    return table


def build_admin_table(filtered_daily: pd.DataFrame, order_df: pd.DataFrame, grain: str) -> tuple[pd.DataFrame, list[str], dict[str, str]]:
    base_columns = [
        "order_id",
        "order_name",
        "advertiser_id",
        "advertiser_name",
        "active_campaign_count",
        "active_status_label",
        "official_start_date",
        "official_end_date",
        "duration_days",
        "objective_source_value",
        "objective_override_value",
        "objective_effective_value",
    ]
    pivot, period_labels, visible_period_count = _prepare_period_columns(filtered_daily, ["order_id"], grain)
    table = order_df[base_columns].copy().merge(pivot, on="order_id", how="left")
    table = _attach_period_metrics(
        table,
        period_labels,
        visible_period_count,
        grain,
        start_col="official_start_date",
        end_col="official_end_date",
        objective_col="objective_effective_value",
        status_col="active_status_label",
    )
    table = table.sort_values(["active_campaign_count", "P", "advertiser_name", "order_name"], ascending=[False, False, True, True]).reset_index(drop=True)
    return table, period_labels, get_grain_labels(grain)


def build_campaign_table(filtered_daily: pd.DataFrame, campaign_df: pd.DataFrame, advertiser_id: str, grain: str) -> tuple[pd.DataFrame, list[str], dict[str, str]]:
    campaign_slice = campaign_df[campaign_df["advertiser_id"].astype(str) == str(advertiser_id)].copy()
    if campaign_slice.empty:
        return campaign_slice, [], get_grain_labels(grain)
    base_columns = [
        "campaign_id",
        "campaign_name",
        "source_status",
        "active_status_label",
        "is_active_override",
        "start_date_source",
        "start_date_override",
        "start_date",
        "end_date_source",
        "end_date_override",
        "end_date",
        "duration_days",
        "objective_source_value",
        "objective_override_value",
        "objective_effective_value",
    ]
    campaign_daily = filtered_daily[filtered_daily["advertiser_id"].astype(str) == str(advertiser_id)].copy()
    pivot, period_labels, visible_period_count = _prepare_period_columns(campaign_daily, ["campaign_id"], grain)
    table = campaign_slice[base_columns].merge(pivot, on="campaign_id", how="left")
    table = _attach_period_metrics(
        table,
        period_labels,
        visible_period_count,
        grain,
        start_col="start_date",
        end_col="end_date",
        objective_col="objective_effective_value",
        status_col="active_status_label",
    )
    table = table.sort_values(["P", "campaign_name"], ascending=[False, True]).reset_index(drop=True)
    return table, period_labels, get_grain_labels(grain)
