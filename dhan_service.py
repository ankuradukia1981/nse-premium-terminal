"""
All Dhan-facing logic lives here: client init, scrip-master based security-id
resolution for MCX commodities, option-chain fetch + ATM combined-premium
extraction, and a realistic simulated feed used whenever live credentials
or a live connection are unavailable (so the dashboard always runs).
"""
import os
import math
import random
import time
from datetime import datetime, timedelta

import pandas as pd
import requests
import streamlit as st

from config import SCRIP_MASTER_URL, INDEX_INSTRUMENTS, COMMODITY_INSTRUMENTS


# --------------------------------------------------------------------------
# Client init
# --------------------------------------------------------------------------
def get_dhan():
    """Return a connected dhanhq client, or None if creds are missing/invalid.
    Never raises — callers should treat None as 'fall back to simulation'."""
    client_id = st.secrets.get("DHAN_CLIENT_ID", None) or os.getenv("DHAN_CLIENT_ID")
    access_token = st.secrets.get("DHAN_ACCESS_TOKEN", None) or os.getenv("DHAN_ACCESS_TOKEN")

    if not client_id or not access_token or "your_" in str(access_token).lower():
        return None

    try:
        from dhanhq import dhanhq
        try:
            # Newer SDK (>=2.x) uses DhanContext
            from dhanhq import DhanContext
            ctx = DhanContext(str(client_id), str(access_token))
            client = dhanhq(ctx)
        except ImportError:
            # Older SDK: direct constructor
            client = dhanhq(str(client_id), str(access_token))
        return client
    except Exception:
        return None


def dhan_is_connected(client) -> bool:
    if client is None:
        return False
    try:
        profile = client.get_profile()
        return isinstance(profile, dict) and profile.get("status") in ("success", "Success", None)
    except Exception:
        return False


# --------------------------------------------------------------------------
# Scrip master (used to resolve MCX commodity underlyings + verify index IDs)
# --------------------------------------------------------------------------
@st.cache_data(ttl=6 * 60 * 60, show_spinner=False)
def load_scrip_master() -> pd.DataFrame:
    """Download & cache Dhan's compact scrip master (refreshed every 6h)."""
    resp = requests.get(SCRIP_MASTER_URL, timeout=30)
    resp.raise_for_status()
    from io import StringIO
    df = pd.read_csv(StringIO(resp.text), low_memory=False)
    return df


def resolve_mcx_underlying(symbol: str):
    """
    Find the nearest-expiry MCX future for `symbol` (e.g. CRUDEOIL) to use as
    the option-chain underlying, straight from the scrip master. Returns
    (security_id, expiry_date_str, trading_symbol) or (None, None, None).
    """
    try:
        df = load_scrip_master()
    except Exception:
        return None, None, None

    try:
        mask = (
            (df["SEM_EXM_EXCH_ID"].astype(str).str.upper() == "MCX")
            & (df["SEM_INSTRUMENT_NAME"].astype(str).str.upper() == "FUTCOM")
            & (df["SEM_TRADING_SYMBOL"].astype(str).str.upper().str.contains(symbol.upper()))
        )
        sub = df[mask].copy()
        if sub.empty:
            return None, None, None
        if "SEM_EXPIRY_DATE" in sub.columns:
            sub["_exp"] = pd.to_datetime(sub["SEM_EXPIRY_DATE"], errors="coerce")
            sub = sub.sort_values("_exp")
        row = sub.iloc[0]
        return (
            int(row["SEM_SMST_SECURITY_ID"]),
            str(row.get("SEM_EXPIRY_DATE", "")),
            str(row.get("SEM_TRADING_SYMBOL", "")),
        )
    except Exception:
        return None, None, None


def search_scrip_master(query: str, limit: int = 25) -> pd.DataFrame:
    """Free-text search of the scrip master by trading symbol — used by the
    'Look up Security ID' helper in the sidebar so users can self-serve
    correct IDs instead of relying on hardcoded values that can go stale."""
    try:
        df = load_scrip_master()
    except Exception:
        return pd.DataFrame()
    cols = [c for c in [
        "SEM_TRADING_SYMBOL", "SEM_CUSTOM_SYMBOL", "SEM_SMST_SECURITY_ID",
        "SEM_EXM_EXCH_ID", "SEM_SEGMENT", "SEM_INSTRUMENT_NAME",
        "SEM_EXPIRY_DATE", "SEM_STRIKE_PRICE", "SEM_OPTION_TYPE", "SEM_LOT_UNITS",
    ] if c in df.columns]
    hit = df[df["SEM_TRADING_SYMBOL"].astype(str).str.upper().str.contains(query.upper(), na=False)]
    return hit[cols].head(limit)


# --------------------------------------------------------------------------
# Live option-chain fetch + ATM combined premium extraction
# --------------------------------------------------------------------------
def get_expiry_list(client, security_id, segment):
    try:
        resp = client.expiry_list(under_security_id=security_id, under_exchange_segment=segment)
        data = resp.get("data") if isinstance(resp, dict) else resp
        return data or []
    except Exception:
        return []


def fetch_atm_combined_premium(client, security_id, segment, strike_step, expiry=None):
    """
    Pulls the live option chain and returns a dict:
    {spot, atm_strike, ce_ltp, pe_ltp, combined_premium, atm_iv}
    or None if the call fails (caller should fall back to simulation).
    """
    try:
        if expiry is None:
            expiries = get_expiry_list(client, security_id, segment)
            if not expiries:
                return None
            expiry = expiries[0]

        resp = client.option_chain(
            under_security_id=security_id,
            under_exchange_segment=segment,
            expiry=expiry,
        )
        data = resp.get("data") if isinstance(resp, dict) else resp
        if not data:
            return None

        spot = float(data.get("last_price") or data.get("underlying_ltp") or 0)
        oc = data.get("oc") or data.get("option_chain") or {}
        if not spot or not oc:
            return None

        atm_strike = min(oc.keys(), key=lambda k: abs(float(k) - spot))
        leg = oc[atm_strike]
        ce = leg.get("ce", {}) or {}
        pe = leg.get("pe", {}) or {}
        ce_ltp = float(ce.get("last_price", 0) or 0)
        pe_ltp = float(pe.get("last_price", 0) or 0)
        ce_iv = float(ce.get("implied_volatility", 0) or 0)
        pe_iv = float(pe.get("implied_volatility", 0) or 0)

        return {
            "spot": spot,
            "atm_strike": float(atm_strike),
            "ce_ltp": ce_ltp,
            "pe_ltp": pe_ltp,
            "combined_premium": ce_ltp + pe_ltp,
            "atm_iv": round((ce_iv + pe_iv) / 2, 2) if (ce_iv or pe_iv) else None,
            "expiry": expiry,
        }
    except Exception:
        return None


# --------------------------------------------------------------------------
# Simulation engine (fallback when no live creds / call fails)
# Ported & generalised from the earlier standalone HTML dashboard so the
# behaviour (mean-reverting premium + occasional vol bursts) stays consistent.
# --------------------------------------------------------------------------
_SIM_BASE = {
    "NIFTY":      {"spot": 24850, "prem": 185, "step": 50},
    "BANKNIFTY":  {"spot": 51200, "prem": 420, "step": 100},
    "FINNIFTY":   {"spot": 23800, "prem": 160, "step": 50},
    "SENSEX":     {"spot": 81200, "prem": 610, "step": 100},
    "CRUDEOIL":   {"spot": 5850,  "prem": 95,  "step": 50},
    "NATURALGAS": {"spot": 258,   "prem": 9.5, "step": 5},
    "GOLD":       {"spot": 74200, "prem": 640, "step": 100},
    "SILVER":     {"spot": 91500, "prem": 980, "step": 250},
}


def _randn():
    return random.gauss(0, 1)


def init_sim_state(symbol: str):
    base = _SIM_BASE.get(symbol, {"spot": 1000, "prem": 20, "step": 10})
    open_prem = base["prem"] * (0.95 + random.random() * 0.10)
    return {
        "spot": base["spot"] + _randn() * base["spot"] * 0.002,
        "prem": open_prem,
        "open_prem": open_prem,
        "step": base["step"],
        "base_prem": base["prem"],
    }


def step_sim(state: dict) -> dict:
    """Advance one simulated tick; mutates and returns a fresh reading dict."""
    base_prem = state["base_prem"]
    vol = state["spot"] * 0.0008
    spot = state["spot"] + _randn() * vol

    d_prem = (state["open_prem"] - state["prem"]) * 0.02 + _randn() * (base_prem * 0.012)
    if random.random() < 0.045:  # occasional positioning / vol-event spike
        d_prem += (1 if random.random() > 0.4 else -1) * base_prem * (0.04 + random.random() * 0.09)
    d_prem -= base_prem * 0.0008  # mild theta drift

    prem = max(base_prem * 0.4, state["prem"] + d_prem)
    split = 0.42 + random.random() * 0.16
    ce = prem * split
    pe = prem * (1 - split)

    state["spot"] = spot
    state["prem"] = prem

    atm_strike = round(spot / state["step"]) * state["step"]
    pct = ((prem - state["open_prem"]) / state["open_prem"]) * 100
    iv = 12 + abs(pct) * 0.35 + random.random() * 4

    return {
        "spot": round(spot, 2),
        "atm_strike": float(atm_strike),
        "ce_ltp": round(ce, 2),
        "pe_ltp": round(pe, 2),
        "combined_premium": round(prem, 2),
        "atm_iv": round(iv, 1),
        "expiry": "SIMULATED",
        "pct_vs_open": round(pct, 2),
    }
