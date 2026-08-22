"""
NSE ATM Live Desk — Streamlit + DhanHQ
Live ATM Combined Premium (CE + PE) for NSE indices via Dhan API.
"""

import os
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Config — security IDs (verify / update from Dhan instrument master if needed)
# ---------------------------------------------------------------------------
UNDERLYINGS = {
    "NIFTY": {"scrip": 13, "seg": "IDX_I", "step": 50, "name": "NIFTY 50"},
    "BANKNIFTY": {"scrip": 25, "seg": "IDX_I", "step": 100, "name": "BANK NIFTY"},
    "FINNIFTY": {"scrip": 27, "seg": "IDX_I", "step": 50, "name": "FIN NIFTY"},
    "MIDCPNIFTY": {"scrip": 442, "seg": "IDX_I", "step": 25, "name": "MIDCAP NIFTY"},
}

# ---------------------------------------------------------------------------
# Dhan client
# ---------------------------------------------------------------------------
def get_dhan():
    """Return dhanhq client or None if credentials missing."""
    client_id = st.secrets.get("1110555196") or os.getenv("1110555196")
    access_token = st.secrets.get("eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzUxMiJ9.eyJ1c2VyUmVnaW9uIjoiUjEiLCJpc3MiOiJkaGFuIiwicGFydG5lcklkIjoiIiwiZXhwIjoxNzg3NDU3MDY0LCJpYXQiOjE3ODczNzA2NjQsInRva2VuQ29uc3VtZXJUeXBlIjoiU0VMRiIsIndlYmhvb2tVcmwiOiIiLCJkaGFuQ2xpZW50SWQiOiIxMTEwNTU1MTk2In0.7MtXNCXUM8Vx3_CMEzPIIekJGeqPHq7NdGK7K6hFNyZoLZZnT3CuRn-LPO4fKxcBplzPrfM8J4V4gHI98QOwFQ") or os.getenv("DHAN_ACCESS_TOKEN")
    if not client_id or not access_token or "your_" in str(access_token):
        return None
    try:
        from dhanhq import dhanhq
        return dhanhq(client_id, access_token)
    except Exception as e:
        st.error(f"Failed to init Dhan client: {e}")
        return None


def fetch_expiry_list(dhan, scrip: int, seg: str) -> List[str]:
    try:
        resp = dhan.expiry_list(under_security_id=scrip, under_exchange_segment=seg)
        data = resp.get("data") if isinstance(resp, dict) else resp
        if isinstance(data, list):
            return [str(x) for x in data]
        return []
    except Exception as e:
        st.warning(f"Expiry list error: {e}")
        return []


def fetch_option_chain(dhan, scrip: int, seg: str, expiry: str) -> Dict[str, Any]:
    try:
        resp = dhan.option_chain(
            under_security_id=scrip,
            under_exchange_segment=seg,
            expiry=expiry,
        )
        return resp if isinstance(resp, dict) else {"data": resp}
    except Exception as e:
        st.error(f"Option chain error: {e}")
        return {}


def extract_atm(chain: Dict[str, Any], step: float = 50) -> Optional[Dict[str, Any]]:
    """Parse Dhan option-chain response → ATM summary."""
    data = chain.get("data") or chain
    rows = []
    if isinstance(data, list):
        rows = data
    elif isinstance(data, dict):
        rows = data.get("oc") or data.get("options") or data.get("data") or []
        if isinstance(rows, dict):
            rows = [{"strike": k, **v} for k, v in rows.items()]

    if not rows:
        return None

    # Spot
    spot = 0.0
    for r in rows:
        for key in ("underlying_value", "spot", "underlyingValue", "last_price"):
            if key in r and r[key]:
                try:
                    spot = float(r[key])
                    break
                except Exception:
                    pass
        if spot:
            break
    if not spot:
        strikes = []
        for r in rows:
            s = r.get("strike_price") or r.get("strike") or r.get("Strike")
            if s:
                try:
                    strikes.append(float(s))
                except Exception:
                    pass
        if strikes:
            spot = sorted(strikes)[len(strikes) // 2]

    best = None
    best_dist = 1e18
    for r in rows:
        strike = r.get("strike_price") or r.get("strike") or r.get("Strike")
        if strike is None:
            continue
        try:
            strike = float(strike)
        except Exception:
            continue
        dist = abs(strike - spot)
        if dist < best_dist:
            best_dist = dist
            best = r
            best["__strike"] = strike

    if not best:
        return None

    strike = best["__strike"]
    ce = best.get("ce") or best.get("CE") or best.get("call") or {}
    pe = best.get("pe") or best.get("PE") or best.get("put") or {}

    def ltp(leg):
        for k in ("last_price", "ltp", "LTP", "close"):
            if leg.get(k) is not None:
                try:
                    return float(leg[k])
                except Exception:
                    pass
        return 0.0

    def oi(leg):
        for k in ("oi", "open_interest", "OI"):
            if leg.get(k) is not None:
                return leg[k]
        return None

    def iv(leg):
        for k in ("implied_volatility", "iv", "IV"):
            if leg.get(k) is not None:
                try:
                    return float(leg[k])
                except Exception:
                    pass
        return None

    ce_ltp, pe_ltp = ltp(ce), ltp(pe)
    combined = ce_ltp + pe_ltp
    ivs = [x for x in (iv(ce), iv(pe)) if x is not None]
    avg_iv = sum(ivs) / len(ivs) if ivs else None

    return {
        "spot": round(spot, 2),
        "atm_strike": strike,
        "ce_ltp": round(ce_ltp, 2),
        "pe_ltp": round(pe_ltp, 2),
        "combined_premium": round(combined, 2),
        "ce_oi": oi(ce),
        "pe_oi": oi(pe),
        "iv": round(avg_iv, 2) if avg_iv else None,
    }


# ---------------------------------------------------------------------------
# Streamlit UI
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="NSE ATM Live · Dhan",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("NSE ATM Live Desk")
st.caption("Live ATM Combined Premium (CE + PE) via **DhanHQ** API")

with st.sidebar:
    st.header("Settings")
    symbol = st.selectbox("Underlying", list(UNDERLYINGS.keys()), index=0)
    refresh_sec = st.slider("Auto-refresh (seconds)", 5, 60, 10)
    auto = st.checkbox("Auto refresh", value=True)
    st.divider()
    st.markdown("**Credentials**")
    st.caption("Set `DHAN_CLIENT_ID` + `DHAN_ACCESS_TOKEN` in `.env` or Streamlit Secrets.")
    if st.button("Clear session history"):
        st.session_state.history = []
        st.rerun()

meta = UNDERLYINGS[symbol]
dhan = get_dhan()

col_a, col_b, col_c = st.columns(3)
with col_a:
    if dhan:
        st.success("Dhan client · connected")
    else:
        st.error("Dhan credentials missing — using demo numbers")
with col_b:
    st.info(f"Symbol · {meta['name']}")
with col_c:
    st.write(datetime.now().strftime("%Y-%m-%d %H:%M:%S IST"))


@st.cache_data(ttl=refresh_sec, show_spinner="Fetching option chain…")
def load_atm(sym: str, _ts: int) -> Dict[str, Any]:
    if not dhan:
        import random
        base = {"NIFTY": 24850, "BANKNIFTY": 51200, "FINNIFTY": 23800, "MIDCPNIFTY": 13200}[sym]
        step = UNDERLYINGS[sym]["step"]
        spot = base * (1 + random.uniform(-0.002, 0.002))
        strike = round(spot / step) * step
        prem = 180 + random.uniform(-30, 40)
        return {
            "spot": round(spot, 2),
            "atm_strike": strike,
            "ce_ltp": round(prem * 0.48, 2),
            "pe_ltp": round(prem * 0.52, 2),
            "combined_premium": round(prem, 2),
            "ce_oi": None,
            "pe_oi": None,
            "iv": round(14 + random.uniform(0, 6), 1),
            "expiry": "demo",
            "source": "demo",
        }

    scrip, seg, step = meta["scrip"], meta["seg"], meta["step"]
    expiries = fetch_expiry_list(dhan, scrip, seg)
    if not expiries:
        raise RuntimeError("No expiries returned. Check scrip ID / segment / token.")
    expiry = expiries[0]
    chain = fetch_option_chain(dhan, scrip, seg, expiry)
    atm = extract_atm(chain, step)
    if not atm:
        raise RuntimeError("Could not parse ATM from chain response.")
    atm["expiry"] = expiry
    atm["source"] = "dhan"
    return atm


if "last_refresh" not in st.session_state:
    st.session_state.last_refresh = 0
if "history" not in st.session_state:
    st.session_state.history = []

now_ts = int(time.time() // refresh_sec)
try:
    data = load_atm(symbol, now_ts)
except Exception as e:
    st.error(f"Fetch failed: {e}")
    st.stop()

m1, m2, m3, m4, m5, m6 = st.columns(6)
m1.metric("Spot", f"{data['spot']:,.2f}")
m2.metric("ATM Strike", f"{data['atm_strike']}")
m3.metric("CE LTP", f"₹{data['ce_ltp']:,.2f}")
m4.metric("PE LTP", f"₹{data['pe_ltp']:,.2f}")
m5.metric("Combined Prem", f"₹{data['combined_premium']:,.2f}")
m6.metric("IV ≈", f"{data['iv']}%" if data.get("iv") else "—")

st.caption(f"Expiry: {data.get('expiry')} · Source: {data.get('source')}")

st.session_state.history.append(
    {
        "time": datetime.now().strftime("%H:%M:%S"),
        "prem": data["combined_premium"],
        "spot": data["spot"],
    }
)
st.session_state.history = st.session_state.history[-80:]

hist = pd.DataFrame(st.session_state.history)
fig = go.Figure()
fig.add_trace(
    go.Scatter(
        x=hist["time"],
        y=hist["prem"],
        mode="lines",
        name="Combined Premium",
        line=dict(color="#f59e0b", width=2),
        fill="tozeroy",
        fillcolor="rgba(245,158,11,0.12)",
    )
)
fig.update_layout(
    title=f"{symbol} — ATM Combined Premium (session)",
    height=340,
    margin=dict(l=40, r=20, t=50, b=40),
    paper_bgcolor="#0b1120",
    plot_bgcolor="#0b1120",
    font=dict(color="#e5e7eb"),
    xaxis=dict(gridcolor="#1f2937"),
    yaxis=dict(gridcolor="#1f2937", title="₹"),
)
st.plotly_chart(fig, use_container_width=True)

with st.expander("Session history"):
    st.dataframe(hist.iloc[::-1], use_container_width=True)

if auto:
    time.sleep(refresh_sec)
    st.rerun()
