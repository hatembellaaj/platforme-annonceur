from __future__ import annotations

import sys
from datetime import timedelta
from pathlib import Path

import pandas as pd
import streamlit as st

APP_DIR = Path(__file__).resolve().parent
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from ai_assistant import ask_gemini_assistant, assistant_ready, build_assistant_context  # noqa: E402
from platform_data import (  # noqa: E402
    build_admin_table,
    build_admin_summary,
    build_advertiser_records,
    build_advertiser_summary_row,
    build_campaign_records,
    build_campaign_table,
    build_order_records,
    build_daily_frame,
    fetch_gam_creative_assignments,
    fetch_gam_campaign_snapshot,
    fetch_gam_order_snapshot,
    fetch_gam_daily_report,
    load_order_overrides,
    load_campaign_overrides,
    get_override_storage_mode,
    save_order_overrides,
    save_campaign_overrides,
    safe_float,
)

st.set_page_config(
    page_title="Platform Annonceur",
    page_icon="PA",
    layout="wide",
)


def inject_styles() -> None:
    st.markdown(
        """
        <style>
        :root {
          --ink: #14213d;
          --muted: #6b7280;
          --paper: #f6f4ef;
          --panel: rgba(255,255,255,.92);
          --line: rgba(20,33,61,.10);
          --gold: #d4a017;
          --mint: #1f8a70;
          --red: #c44536;
          --sand: #f0e6d2;
        }
        .stApp {
          background:
            radial-gradient(circle at top right, rgba(212,160,23,.18), transparent 28%),
            radial-gradient(circle at left center, rgba(31,138,112,.13), transparent 24%),
            linear-gradient(180deg, #f8f5ee 0%, #f2efe8 100%);
        }
        .block-container { padding-top: 1.5rem; padding-bottom: 2rem; }
        .hero {
          background: linear-gradient(135deg, rgba(20,33,61,.98), rgba(31,138,112,.92));
          color: white;
          padding: 1.3rem 1.4rem;
          border-radius: 24px;
          border: 1px solid rgba(255,255,255,.12);
          box-shadow: 0 18px 40px rgba(20,33,61,.18);
          margin-bottom: 1rem;
        }
        .hero h1 { margin: 0 0 .25rem 0; font-size: 2rem; }
        .hero p { margin: 0; color: rgba(255,255,255,.82); }
        .panel-card {
          background: var(--panel);
          border: 1px solid var(--line);
          border-radius: 18px;
          padding: 1rem 1rem .95rem 1rem;
          box-shadow: 0 10px 28px rgba(20,33,61,.06);
          margin: .75rem 0;
        }
        .section-title { font-size: 1.05rem; font-weight: 700; color: var(--ink); margin: .25rem 0 .75rem 0; }
        div[data-testid="stDataEditor"] table { min-width: 100%; }
        </style>
        """,
        unsafe_allow_html=True,
    )


def fmt_number(value: float | int | None) -> str:
    if value in (None, ""):
        return "-"
    return f"{float(value):,.0f}".replace(",", " ")


def fmt_pct(value: float | int | None) -> str:
    if value in (None, ""):
        return "-"
    return f"{float(value):.1f}%"


def render_formula_box() -> None:
    with st.expander("Formules utilisees dans les tableaux", expanded=False):
        st.markdown(
            """
            - `CTR = clics / impressions * 100`
            - `P = SOMME(des colonnes periode visibles)`
            - `Q = P / nombre de periodes visibles`
            - `R = Q - C`
            - `S = R / Q`
            - La barre de progression est separee des alertes
            - Les alertes suivent maintenant le pacing dans le temps:
              `objectif attendu a date = objectif total * jours ecoules / duree totale`
            """
        )


def to_status_override_label(value: object) -> str:
    if value is True:
        return "Active"
    if value is False:
        return "Inactive"
    return "Auto"


def from_status_override_label(value: object) -> bool | None:
    if value == "Active":
        return True
    if value == "Inactive":
        return False
    return None


def normalize_date_cell(value: object) -> str | None:
    if value is None or value == "" or pd.isna(value):
        return None
    try:
        return pd.to_datetime(value, errors="coerce").date().isoformat()
    except Exception:
        return None


def is_blank_cell(value: object) -> bool:
    if value is None:
        return True
    if isinstance(value, str) and value.strip() == "":
        return True
    try:
        return bool(pd.isna(value))
    except Exception:
        return False


def ensure_state() -> None:
    if "order_overrides" not in st.session_state:
        st.session_state["order_overrides"] = load_order_overrides()
    if "campaign_overrides" not in st.session_state:
        st.session_state["campaign_overrides"] = load_campaign_overrides()


def refresh_effective_models() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    campaign_source_frame = fetch_gam_campaign_snapshot()
    order_source_frame = fetch_gam_order_snapshot()
    campaign_df = build_campaign_records(campaign_source_frame, st.session_state["campaign_overrides"])
    order_df = build_order_records(order_source_frame, campaign_df, st.session_state["order_overrides"])
    advertiser_df = build_advertiser_records(order_df)
    return campaign_source_frame, campaign_df, order_df, advertiser_df


def update_order_overrides(edited_df: pd.DataFrame, base_df: pd.DataFrame) -> bool:
    changed = False
    overrides = dict(st.session_state["order_overrides"])
    indexed = base_df.set_index("order_id")
    for row in edited_df.to_dict("records"):
        order_id = str(row["order_id"])
        base_row = indexed.loc[order_id]
        source_value = safe_float(base_row["objective_source_value"])
        override_value = row.get("objective_override_value")
        normalized_override = None if is_blank_cell(override_value) else safe_float(override_value)
        current = overrides.get(order_id, {})
        if normalized_override in (None, 0.0) and source_value == 0:
            normalized_override = None
        if normalized_override is None:
            if order_id in overrides:
                overrides.pop(order_id, None)
                changed = True
        else:
            if current.get("objective_override_value") != normalized_override:
                overrides[order_id] = {"objective_override_value": normalized_override}
                changed = True
    if changed:
        st.session_state["order_overrides"] = overrides
        save_order_overrides(overrides)
    return changed


def update_campaign_overrides(edited_df: pd.DataFrame) -> bool:
    changed = False
    overrides = dict(st.session_state["campaign_overrides"])
    for row in edited_df.to_dict("records"):
        campaign_id = str(row["campaign_id"])
        payload = {
            "objective_override_value": None if is_blank_cell(row.get("objective_override_value")) else safe_float(row.get("objective_override_value")),
            "is_active_override": from_status_override_label(row.get("status_override")),
            "start_date_override": normalize_date_cell(row.get("start_date_override")),
            "end_date_override": normalize_date_cell(row.get("end_date_override")),
        }
        has_value = any(value not in (None, "") for value in payload.values())
        current = overrides.get(campaign_id)
        if not has_value:
            if campaign_id in overrides:
                overrides.pop(campaign_id, None)
                changed = True
            continue
        if current != payload:
            overrides[campaign_id] = payload
            changed = True
    if changed:
        st.session_state["campaign_overrides"] = overrides
        save_campaign_overrides(overrides)
    return changed


def render_admin_page(order_df: pd.DataFrame) -> None:
    st.markdown('<div class="section-title">Page Admin</div>', unsafe_allow_html=True)
    start_floor = pd.Timestamp.now().date() - timedelta(days=120)
    max_day = pd.Timestamp.now().date()
    c1, c2 = st.columns([1.35, 1])
    with c1:
        interval = st.date_input(
            "Intervalle",
            value=(max(start_floor, max_day - timedelta(days=90)), max_day),
            min_value=start_floor,
            max_value=max_day,
        )
    with c2:
        grain = st.radio(
            "Colonnes d'impressions",
            options=["day", "week", "month"],
            index=2,
            horizontal=True,
            format_func=lambda value: {"day": "Jour", "week": "Semaine", "month": "Mois"}[value],
        )

    start_date, end_date = interval if isinstance(interval, tuple) else (start_floor, max_day)
    filtered_daily = build_daily_frame(fetch_gam_daily_report(start_date.isoformat(), end_date.isoformat()))
    summary = build_admin_summary(filtered_daily, order_df)

    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("Annonceurs actifs", fmt_number(summary["active_advertisers"]))
    m2.metric("Campagnes actives", fmt_number(summary["active_campaigns"]))
    m3.metric("Objectif effectif", fmt_number(summary["effective_objective_total"]))
    m4.metric("Impressions", fmt_number(summary["total_impressions"]))
    m5.metric("Progression", fmt_pct(summary["global_progress_ui"]))

    render_formula_box()

    st.markdown('<div class="section-title">Tableau ordres</div>', unsafe_allow_html=True)
    admin_table_df, period_labels, grain_labels = build_admin_table(filtered_daily, order_df, grain)
    advertiser_editor = admin_table_df[
        [
            "order_id",
            "order_name",
            "advertiser_id",
            "advertiser_name",
            "active_campaign_count",
            "active_status_label",
            "objective_source_value",
            "objective_override_value",
            "objective_effective_value",
            "obj_period",
            *period_labels,
            "P",
            "Q",
            "R",
            "S",
            "progress_pct_ui",
            "alert_label",
            "official_start_date",
            "official_end_date",
            "duration_days",
        ]
    ].rename(
        columns={
            "order_name": "Ordre",
            "advertiser_name": "Annonceur",
            "active_campaign_count": "Campagnes actives",
            "active_status_label": "Statut",
            "objective_source_value": "Obj. API",
            "objective_override_value": "Obj. corrige",
            "objective_effective_value": "Obj. effectif",
            "obj_period": grain_labels["objective"],
            "P": grain_labels["sum"],
            "Q": "Moyenne",
            "R": grain_labels["gap"],
            "S": "ecart/moyenne",
            "progress_pct_ui": "Progression",
            "alert_label": "Alerte",
            "official_start_date": "Debut",
            "official_end_date": "Fin",
            "duration_days": "Duree",
        }
    )
    for column_name in ["Debut", "Fin"]:
        advertiser_editor[column_name] = advertiser_editor[column_name].fillna("").replace("", "-")
    advertiser_edited = st.data_editor(
        advertiser_editor,
        width="stretch",
        hide_index=True,
        key="platform_admin_advertisers",
        column_config={
            "order_id": None,
            "advertiser_id": None,
            "Obj. API": st.column_config.NumberColumn(disabled=True, format="%.0f"),
            "Obj. corrige": st.column_config.NumberColumn(format="%.0f"),
            "Obj. effectif": st.column_config.NumberColumn(disabled=True, format="%.0f"),
            grain_labels["objective"]: st.column_config.NumberColumn(disabled=True, format="%.0f"),
            "Campagnes actives": st.column_config.NumberColumn(disabled=True, format="%d"),
            "Moyenne": st.column_config.NumberColumn(disabled=True, format="%.0f"),
            grain_labels["gap"]: st.column_config.NumberColumn(disabled=True, format="%.0f"),
            "ecart/moyenne": st.column_config.NumberColumn(disabled=True, format="%.1f%%"),
            "Progression": st.column_config.ProgressColumn(min_value=0, max_value=100, format="%.1f%%"),
        },
    )
    advertiser_save_df = advertiser_edited.rename(
        columns={
            "Ordre": "order_name",
            "Annonceur": "advertiser_name",
            "Campagnes actives": "active_campaign_count",
            "Statut": "active_status_label",
            "Debut": "official_start_date",
            "Fin": "official_end_date",
            "Duree": "duration_days",
            "Obj. API": "objective_source_value",
            "Obj. corrige": "objective_override_value",
            "Obj. effectif": "objective_effective_value",
            "Progression": "progress_pct_ui",
            "Alerte": "alert_label",
        }
    )
    if update_order_overrides(advertiser_save_df, order_df):
        st.rerun()


def render_advertiser_page(advertiser_df: pd.DataFrame, campaign_df: pd.DataFrame) -> None:
    st.markdown('<div class="section-title">Page Annonceur</div>', unsafe_allow_html=True)
    active_advertisers = advertiser_df[advertiser_df["is_active"]].copy()
    advertiser_options = active_advertisers["advertiser_name"].tolist()
    if not advertiser_options:
        st.info("Aucun annonceur actif disponible.")
        return
    selected_name = st.selectbox("Annonceur", advertiser_options)
    advertiser_row = active_advertisers[active_advertisers["advertiser_name"] == selected_name].iloc[0]
    advertiser_id = str(advertiser_row["advertiser_id"])
    advertiser_campaigns = campaign_df[campaign_df["advertiser_id"].astype(str) == advertiser_id].copy()
    start_floor = pd.Timestamp.now().date() - timedelta(days=120)
    max_day = pd.Timestamp.now().date()

    c1, c2 = st.columns([1.3, 1])
    with c1:
        grain = st.radio(
            "Colonnes d'impressions",
            options=["day", "week", "month"],
            index=2,
            horizontal=True,
            key="advertiser_grain",
            format_func=lambda value: {"day": "Jour", "week": "Semaine", "month": "Mois"}[value],
        )
    with c2:
        interval = st.date_input(
            "Intervalle",
            value=(max(start_floor, max_day - timedelta(days=90)), max_day),
            min_value=start_floor,
            max_value=max_day,
            key="advertiser_interval",
        )
    start_date, end_date = interval if isinstance(interval, tuple) else (start_floor, max_day)
    advertiser_daily = build_daily_frame(fetch_gam_daily_report(start_date.isoformat(), end_date.isoformat(), advertiser_name=selected_name))
    filtered_daily = advertiser_daily[advertiser_daily["advertiser_id"].astype(str) == advertiser_id].copy()
    advertiser_summary = build_advertiser_summary_row(filtered_daily, advertiser_row)

    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("Statut", "Actif" if advertiser_row["active_status_label"] == "Active" else "Inactif")
    m2.metric("Campagnes actives", fmt_number(advertiser_row["active_campaign_count"]))
    m3.metric("Objectif effectif", fmt_number(advertiser_row["objective_effective_value"]))
    m4.metric("Impressions", fmt_number(advertiser_summary["total_impressions"]))
    m5.metric("Progression", fmt_pct(advertiser_summary["progress_ui"]))

    st.caption(
        f'Intervalle officiel : {advertiser_row["official_start_date"] or "-"} -> {advertiser_row["official_end_date"] or "-"}'
        f' | Duree : {int(advertiser_row["duration_days"])} jours'
    )

    st.markdown('<div class="section-title">Tableau campagnes</div>', unsafe_allow_html=True)
    campaign_table_df, period_labels, grain_labels = build_campaign_table(filtered_daily, advertiser_campaigns, advertiser_id, grain)
    advertiser_campaign_editor = campaign_table_df[
        [
            "campaign_id",
            "campaign_name",
            "source_status",
            "active_status_label",
            "is_active_override",
            "objective_source_value",
            "objective_override_value",
            "objective_effective_value",
            "obj_period",
            *period_labels,
            "P",
            "Q",
            "R",
            "S",
            "progress_pct_ui",
            "alert_label",
            "start_date_source",
            "start_date_override",
            "start_date",
            "end_date_source",
            "end_date_override",
            "end_date",
            "duration_days",
        ]
    ].copy()
    advertiser_campaign_editor["is_active_override"] = advertiser_campaign_editor["is_active_override"].apply(to_status_override_label)
    advertiser_campaign_editor["start_date_override"] = pd.to_datetime(advertiser_campaign_editor["start_date_override"], errors="coerce").dt.date
    advertiser_campaign_editor["end_date_override"] = pd.to_datetime(advertiser_campaign_editor["end_date_override"], errors="coerce").dt.date
    advertiser_campaign_editor = advertiser_campaign_editor.rename(
        columns={
            "campaign_name": "Campagne",
            "source_status": "Statut API",
            "active_status_label": "Statut",
            "is_active_override": "Statut corrige",
            "objective_source_value": "Obj. API",
            "objective_override_value": "Obj. corrige",
            "objective_effective_value": "Obj. effectif",
            "obj_period": grain_labels["objective"],
            "P": grain_labels["sum"],
            "Q": "Moyenne",
            "R": grain_labels["gap"],
            "S": "ecart/moyenne",
            "progress_pct_ui": "Progression",
            "alert_label": "Alerte",
            "start_date_source": "Debut API",
            "start_date_override": "Debut corrige",
            "start_date": "Debut",
            "end_date_source": "Fin API",
            "end_date_override": "Fin corrige",
            "end_date": "Fin",
            "duration_days": "Duree",
        }
    )
    for column_name in ["Debut", "Fin", "Debut API", "Fin API"]:
        advertiser_campaign_editor[column_name] = advertiser_campaign_editor[column_name].fillna("").replace("", "-")
    advertiser_campaign_edited = st.data_editor(
        advertiser_campaign_editor,
        width="stretch",
        hide_index=True,
        key="platform_advertiser_campaigns",
        column_config={
            "campaign_id": None,
            "Statut corrige": st.column_config.SelectboxColumn(options=["Auto", "Active", "Inactive"]),
            "Debut corrige": st.column_config.DateColumn(format="YYYY-MM-DD"),
            "Fin corrige": st.column_config.DateColumn(format="YYYY-MM-DD"),
            "Obj. API": st.column_config.NumberColumn(disabled=True, format="%.0f"),
            "Obj. corrige": st.column_config.NumberColumn(format="%.0f"),
            "Obj. effectif": st.column_config.NumberColumn(disabled=True, format="%.0f"),
            grain_labels["objective"]: st.column_config.NumberColumn(disabled=True, format="%.0f"),
            "Moyenne": st.column_config.NumberColumn(disabled=True, format="%.0f"),
            grain_labels["gap"]: st.column_config.NumberColumn(disabled=True, format="%.0f"),
            "ecart/moyenne": st.column_config.NumberColumn(disabled=True, format="%.1f%%"),
            "Progression": st.column_config.ProgressColumn(min_value=0, max_value=100, format="%.1f%%"),
        },
    )
    advertiser_campaign_save_df = advertiser_campaign_edited.rename(
        columns={
            "Campagne": "campaign_name",
            "Statut": "active_status_label",
            "Statut corrige": "status_override",
            "Debut API": "start_date_source",
            "Debut corrige": "start_date_override",
            "Debut": "start_date",
            "Fin API": "end_date_source",
            "Fin corrige": "end_date_override",
            "Fin": "end_date",
            "Duree": "duration_days",
            "Obj. API": "objective_source_value",
            "Obj. corrige": "objective_override_value",
            "Obj. effectif": "objective_effective_value",
            "Progression": "progress_pct_ui",
            "Alerte": "alert_label",
        }
    )
    if update_campaign_overrides(advertiser_campaign_save_df):
        st.rerun()

    st.markdown('<div class="section-title">Creations par campagne</div>', unsafe_allow_html=True)
    creative_df = fetch_gam_creative_assignments(tuple(advertiser_campaigns["campaign_id"].astype(str).tolist()))
    campaign_lookup = campaign_table_df.set_index("campaign_id").to_dict("index") if not campaign_table_df.empty else {}
    for campaign_row in campaign_table_df[["campaign_id", "campaign_name", "start_date", "end_date"]].to_dict("records"):
        campaign_id = str(campaign_row["campaign_id"])
        creatives_slice = creative_df[creative_df["campaign_id"].astype(str) == campaign_id].copy() if not creative_df.empty else pd.DataFrame()
        expander_label = f'{campaign_row["campaign_name"]} ({len(creatives_slice)})'
        with st.expander(expander_label, expanded=False):
            if creatives_slice.empty:
                st.caption("Aucune creation liee a cette campagne.")
                continue
            base_start = campaign_row.get("start_date") or campaign_lookup.get(campaign_id, {}).get("start_date")
            base_end = campaign_row.get("end_date") or campaign_lookup.get(campaign_id, {}).get("end_date")
            creatives_display = creatives_slice[["creative_name", "creative_start_date", "creative_end_date"]].copy()
            creatives_display["creative_start_date"] = creatives_display["creative_start_date"].fillna("").replace("", base_start or "-")
            creatives_display["creative_end_date"] = creatives_display["creative_end_date"].fillna("").replace("", base_end or "-")
            creatives_display = creatives_display.rename(
                columns={
                    "creative_name": "Creation",
                    "creative_start_date": "Debut",
                    "creative_end_date": "Fin",
                }
            )
            st.dataframe(creatives_display, width="stretch", hide_index=True)


def render_ai_tables_and_charts(payload: dict[str, object]) -> None:
    for warning in payload.get("warnings", []) or []:
        st.warning(str(warning))
    tables = payload.get("tables", []) or []
    for table in tables:
        title = str(table.get("title", "") or "").strip()
        columns = [str(item) for item in table.get("columns", []) or []]
        rows = table.get("rows", []) or []
        if title:
            st.markdown(f"**{title}**")
        if columns:
            try:
                frame = pd.DataFrame(rows, columns=columns)
            except Exception:
                continue
            st.dataframe(frame, width="stretch", hide_index=True)
    charts = payload.get("charts", []) or []
    for chart in charts:
        title = str(chart.get("title", "") or "").strip()
        chart_type = str(chart.get("chart_type", "") or "").strip().lower()
        points = chart.get("points", []) or []
        if not points:
            continue
        frame = pd.DataFrame(points)
        if frame.empty or "x" not in frame.columns or "y" not in frame.columns:
            continue
        if title:
            st.markdown(f"**{title}**")
        if "series" in frame.columns and frame["series"].notna().any():
            pivot = frame.pivot_table(index="x", columns="series", values="y", aggfunc="sum").sort_index()
            if chart_type == "bar":
                st.bar_chart(pivot)
            else:
                st.line_chart(pivot)
        else:
            single = frame[["x", "y"]].copy().sort_values("x")
            single = single.set_index("x")
            if chart_type == "bar":
                st.bar_chart(single)
            else:
                st.line_chart(single)


def render_ai_assistant_page(advertiser_df: pd.DataFrame, order_df: pd.DataFrame, campaign_df: pd.DataFrame) -> None:
    st.markdown('<div class="section-title">Assistant IA</div>', unsafe_allow_html=True)
    if not assistant_ready():
        st.warning("Cle Gemini absente. Ajoute `GAM_GEMINI_API_KEY` ou `GEMINI_API_KEY` dans les secrets Streamlit.")
        return

    start_floor = pd.Timestamp.now().date() - timedelta(days=120)
    max_day = pd.Timestamp.now().date()
    top1, top2, top3 = st.columns([1.1, 1.1, 1.2])
    with top1:
        scope = st.radio("Scope", options=["Global", "Annonceur"], horizontal=True, key="ai_scope")
    with top2:
        grain = st.radio(
            "Grain",
            options=["day", "week", "month"],
            index=2,
            horizontal=True,
            key="ai_grain",
            format_func=lambda value: {"day": "Jour", "week": "Semaine", "month": "Mois"}[value],
        )
    with top3:
        interval = st.date_input(
            "Intervalle",
            value=(max(start_floor, max_day - timedelta(days=90)), max_day),
            min_value=start_floor,
            max_value=max_day,
            key="ai_interval",
        )
    start_date, end_date = interval if isinstance(interval, tuple) else (start_floor, max_day)
    selected_name = ""
    if scope == "Annonceur":
        advertiser_options = advertiser_df[advertiser_df["is_active"]]["advertiser_name"].tolist()
        if not advertiser_options:
            st.info("Aucun annonceur actif disponible.")
            return
        selected_name = st.selectbox("Annonceur cible", advertiser_options, key="ai_advertiser")

    daily = build_daily_frame(fetch_gam_daily_report(start_date.isoformat(), end_date.isoformat(), advertiser_name=selected_name))
    if scope == "Annonceur" and selected_name:
        scoped_advertiser_df = advertiser_df[advertiser_df["advertiser_name"] == selected_name].copy()
        if scoped_advertiser_df.empty:
            st.info("Annonceur introuvable dans le scope actif.")
            return
        advertiser_row = scoped_advertiser_df.iloc[0]
        advertiser_id = str(advertiser_row["advertiser_id"])
        scoped_daily = daily[daily["advertiser_id"].astype(str) == advertiser_id].copy()
        scoped_campaigns = campaign_df[campaign_df["advertiser_id"].astype(str) == advertiser_id].copy()
        campaign_table_df, _, _ = build_campaign_table(scoped_daily, scoped_campaigns, advertiser_id, grain)
        order_table_df = order_df[order_df["advertiser_id"].astype(str) == advertiser_id].copy()
        creative_df = fetch_gam_creative_assignments(tuple(scoped_campaigns["campaign_id"].astype(str).tolist()))
        context = build_assistant_context(
            page_scope=scope,
            selected_advertiser=selected_name,
            grain=grain,
            start_date_iso=start_date.isoformat(),
            end_date_iso=end_date.isoformat(),
            advertiser_df=scoped_advertiser_df,
            order_table_df=order_table_df,
            campaign_table_df=campaign_table_df,
            creative_df=creative_df,
            daily_df=scoped_daily,
        )
    else:
        scoped_orders = order_df[order_df["is_active"]].copy()
        order_table_df, _, _ = build_admin_table(daily, scoped_orders, grain)
        campaign_table_df = campaign_df[campaign_df["is_active"]].copy()
        creative_df = pd.DataFrame(columns=["campaign_id", "creative_id", "creative_name", "creative_start_date", "creative_end_date"])
        context = build_assistant_context(
            page_scope=scope,
            selected_advertiser="",
            grain=grain,
            start_date_iso=start_date.isoformat(),
            end_date_iso=end_date.isoformat(),
            advertiser_df=advertiser_df[advertiser_df["is_active"]].copy(),
            order_table_df=order_table_df,
            campaign_table_df=campaign_table_df,
            creative_df=creative_df,
            daily_df=daily,
        )

    if "ai_chat_history" not in st.session_state:
        st.session_state["ai_chat_history"] = []

    action_col1, action_col2 = st.columns([1, 1])
    with action_col1:
        if st.button("Effacer la conversation", key="ai_clear_chat"):
            st.session_state["ai_chat_history"] = []
            st.rerun()
    with action_col2:
        st.caption("L'assistant repond uniquement avec les donnees chargees dans cette page.")

    for message in st.session_state["ai_chat_history"]:
        with st.chat_message("user"):
            st.markdown(str(message.get("user", "")))
        with st.chat_message("assistant"):
            st.markdown(str(message.get("answer_markdown", "")))
            render_ai_tables_and_charts(message)

    prompt = st.chat_input("Pose une question sur les campagnes, les objectifs, les alertes, ou demande un tableau / graphique.")
    if prompt:
        with st.chat_message("user"):
            st.markdown(prompt)
        with st.chat_message("assistant"):
            with st.spinner("Analyse IA en cours..."):
                try:
                    history = [{"user": item.get("user", ""), "model": item.get("answer_markdown", "")} for item in st.session_state["ai_chat_history"]]
                    payload = ask_gemini_assistant(prompt, context, history)
                except Exception as exc:
                    st.error(f"Assistant IA indisponible : {exc}")
                    return
            st.markdown(str(payload.get("answer_markdown", "")))
            render_ai_tables_and_charts(payload)
        st.session_state["ai_chat_history"].append({"user": prompt, **payload})
        st.rerun()


def main() -> None:
    inject_styles()
    ensure_state()

    st.markdown(
        """
        <div class="hero">
          <h1>Platform Annonceur</h1>
          <p>Pages Admin et Annonceur avec objectifs corriges, statuts actifs et calculs Excel.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    try:
        _, campaign_df, order_df, advertiser_df = refresh_effective_models()
    except Exception as exc:
        st.error(f"Chargement GAM impossible : {exc}")
        return

    if advertiser_df.empty or campaign_df.empty:
        st.warning("Aucune donnee GAM n'a ete retournee pour la plateforme.")
        return

    active_advertisers = advertiser_df[advertiser_df["is_active"]].copy()
    active_orders = order_df[order_df["is_active"]].copy()

    page = st.sidebar.radio("Surface", options=["Admin", "Annonceur", "Assistant IA"])
    st.sidebar.caption(f"Annonceurs actifs : {len(active_advertisers)}")
    st.sidebar.caption(f"Campagnes : {len(campaign_df)}")
    storage_mode = get_override_storage_mode()
    st.sidebar.caption(f"Stockage corrections : {'Supabase' if storage_mode == 'supabase' else 'Local'}")
    if storage_mode != "supabase":
        st.sidebar.warning("Supabase n'est pas configure. Le stockage local peut ne pas persister sur Streamlit Cloud.")

    if page == "Admin":
        render_admin_page(active_orders)
    elif page == "Annonceur":
        render_advertiser_page(active_advertisers, campaign_df)
    else:
        render_ai_assistant_page(active_advertisers, active_orders, campaign_df)


if __name__ == "__main__":
    main()
