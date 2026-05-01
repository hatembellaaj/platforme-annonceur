from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pandas as pd
import requests
import streamlit as st

APP_DIR = Path(__file__).resolve().parent
RULES_FILE = APP_DIR / "AI_ASSISTANT_RULES.md"
DEFAULT_GEMINI_MODEL = "gemini-2.5-flash"
GEMINI_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


def get_gemini_api_key() -> str:
    try:
        value = st.secrets.get("GAM_GEMINI_API_KEY", "") or st.secrets.get("GEMINI_API_KEY", "")
    except Exception:
        value = ""
    value = str(value or "").strip()
    if value:
        return value
    value = os.getenv("GAM_GEMINI_API_KEY", "") or os.getenv("GEMINI_API_KEY", "")
    return str(value or "").strip()


def assistant_ready() -> bool:
    return bool(get_gemini_api_key())


def _read_rules() -> str:
    try:
        return RULES_FILE.read_text(encoding="utf-8")
    except OSError:
        return ""


def _json_safe(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if isinstance(value, (pd.Series, pd.Index)):
        return [_json_safe(item) for item in value.tolist()]
    if isinstance(value, pd.DataFrame):
        return [_json_safe(item) for item in value.to_dict(orient="records")]
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    return str(value)


def _compact_records(frame: pd.DataFrame, columns: list[str], limit: int) -> list[dict[str, Any]]:
    if frame.empty:
        return []
    available = [column for column in columns if column in frame.columns]
    sample = frame[available].head(limit).copy()
    return _json_safe(sample)


def build_assistant_context(
    grain: str,
    start_date_iso: str,
    end_date_iso: str,
    advertiser_df: pd.DataFrame,
    advertiser_table_df: pd.DataFrame,
    order_table_df: pd.DataFrame,
    campaign_table_df: pd.DataFrame,
    creative_df: pd.DataFrame,
    daily_df: pd.DataFrame,
) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "grain": grain,
        "start_date": start_date_iso,
        "end_date": end_date_iso,
        "active_advertisers": int(advertiser_df["advertiser_id"].nunique()) if not advertiser_df.empty else 0,
        "advertisers_in_scope": int(advertiser_table_df["advertiser_id"].nunique()) if not advertiser_table_df.empty and "advertiser_id" in advertiser_table_df.columns else 0,
        "orders_in_scope": int(order_table_df["order_id"].nunique()) if not order_table_df.empty and "order_id" in order_table_df.columns else 0,
        "campaigns_in_scope": int(campaign_table_df["campaign_id"].nunique()) if not campaign_table_df.empty and "campaign_id" in campaign_table_df.columns else 0,
        "daily_rows_in_scope": int(len(daily_df)),
        "total_impressions_interval": int(pd.to_numeric(daily_df.get("impressions", 0), errors="coerce").fillna(0).sum()) if not daily_df.empty else 0,
        "total_clicks_interval": int(pd.to_numeric(daily_df.get("clicks", 0), errors="coerce").fillna(0).sum()) if not daily_df.empty else 0,
    }

    advertiser_columns = [
        "advertiser_id",
        "advertiser_name",
        "active_campaign_count",
        "objective_effective_value",
        "impressions",
        "official_start_date",
        "official_end_date",
        "alert_label",
    ]
    order_columns = [
        "order_id",
        "order_name",
        "advertiser_name",
        "active_campaign_count",
        "objective_effective_value",
        "impressions",
        "Q",
        "R",
        "S",
        "alert_label",
        "official_start_date",
        "official_end_date",
    ]
    campaign_columns = [
        "campaign_id",
        "campaign_name",
        "order_name",
        "source_status",
        "objective_effective_value",
        "impressions",
        "Q",
        "R",
        "S",
        "progress_pct_ui",
        "alert_label",
        "start_date",
        "end_date",
    ]
    creative_columns = [
        "campaign_id",
        "creative_id",
        "creative_name",
        "creative_start_date",
        "creative_end_date",
    ]
    daily_columns = [
        "date",
        "advertiser_name",
        "order_name",
        "campaign_name",
        "source_status",
        "impressions",
        "clicks",
        "ctr",
    ]

    return {
        "summary": summary,
        "available_entities": {
            "advertiser_names": sorted([str(item) for item in advertiser_df.get("advertiser_name", pd.Series(dtype="object")).dropna().astype(str).unique().tolist()])[:200],
            "order_names": sorted([str(item) for item in order_table_df.get("order_name", pd.Series(dtype="object")).dropna().astype(str).unique().tolist()])[:300],
            "campaign_names": sorted([str(item) for item in campaign_table_df.get("campaign_name", pd.Series(dtype="object")).dropna().astype(str).unique().tolist()])[:400],
        },
        "advertisers": _compact_records(advertiser_table_df, advertiser_columns, 150),
        "orders": _compact_records(order_table_df, order_columns, 120),
        "campaigns": _compact_records(campaign_table_df, campaign_columns, 200),
        "creatives": _compact_records(creative_df, creative_columns, 250),
        "daily_rows": _compact_records(daily_df.sort_values("date", ascending=False), daily_columns, 300) if not daily_df.empty else [],
    }


def _assistant_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "answer_markdown": {"type": "string"},
            "confidence": {"type": "string"},
            "warnings": {"type": "array", "items": {"type": "string"}},
            "used_data": {"type": "array", "items": {"type": "string"}},
            "tables": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "columns": {"type": "array", "items": {"type": "string"}},
                        "rows": {
                            "type": "array",
                            "items": {
                                "type": "array",
                                "items": {"type": ["string", "number", "integer", "boolean", "null"]},
                            },
                        },
                    },
                    "required": ["title", "columns", "rows"],
                },
            },
            "charts": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "chart_type": {"type": "string"},
                        "x_label": {"type": "string"},
                        "y_label": {"type": "string"},
                        "series_label": {"type": ["string", "null"]},
                        "points": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "x": {"type": ["string", "number", "integer"]},
                                    "y": {"type": ["number", "integer"]},
                                    "series": {"type": ["string", "null"]},
                                },
                                "required": ["x", "y", "series"],
                            },
                        },
                    },
                    "required": ["title", "chart_type", "x_label", "y_label", "series_label", "points"],
                },
            },
        },
        "required": ["answer_markdown", "confidence", "warnings", "used_data", "tables", "charts"],
        "propertyOrdering": ["answer_markdown", "confidence", "warnings", "used_data", "tables", "charts"],
    }


def _build_contents(question: str, context: dict[str, Any], history: list[dict[str, str]]) -> list[dict[str, Any]]:
    rules = _read_rules()
    context_text = json.dumps(_json_safe(context), ensure_ascii=False, indent=2)
    prompt = (
        "Tu es l'assistant IA de Platform Annonceur.\n\n"
        "Regles:\n"
        f"{rules}\n\n"
        "Contexte JSON disponible:\n"
        f"{context_text}\n\n"
        "Reponds uniquement a partir de ce contexte. "
        "Si une information manque, dis-le clairement. "
        "Tu peux proposer des tableaux et graphiques utiles si cela aide la reponse."
    )
    contents: list[dict[str, Any]] = [{"role": "user", "parts": [{"text": prompt}]}]
    for turn in history[-6:]:
        user_text = str(turn.get("user", "") or "").strip()
        model_text = str(turn.get("model", "") or "").strip()
        if user_text:
            contents.append({"role": "user", "parts": [{"text": user_text}]})
        if model_text:
            contents.append({"role": "model", "parts": [{"text": model_text}]})
    contents.append({"role": "user", "parts": [{"text": question}]})
    return contents


def ask_gemini_assistant(question: str, context: dict[str, Any], history: list[dict[str, str]], model: str = DEFAULT_GEMINI_MODEL) -> dict[str, Any]:
    api_key = get_gemini_api_key()
    if not api_key:
        raise RuntimeError("Missing Gemini API key.")

    payload = {
        "contents": _build_contents(question, context, history),
        "generationConfig": {
            "temperature": 0.2,
            "responseMimeType": "application/json",
            "responseJsonSchema": _assistant_schema(),
        },
    }
    response = requests.post(
        GEMINI_ENDPOINT.format(model=model),
        headers={"Content-Type": "application/json", "x-goog-api-key": api_key},
        json=payload,
        timeout=180,
    )
    response.raise_for_status()
    data = response.json()
    text = ""
    for candidate in data.get("candidates", []):
        content = candidate.get("content", {})
        for part in content.get("parts", []):
            if "text" in part:
                text += str(part["text"])
    if not text.strip():
        raise RuntimeError("Gemini returned an empty response.")
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Gemini JSON parse error: {exc}") from exc
    parsed.setdefault("warnings", [])
    parsed.setdefault("used_data", [])
    parsed.setdefault("tables", [])
    parsed.setdefault("charts", [])
    return parsed
