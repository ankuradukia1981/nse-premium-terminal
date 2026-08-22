"""
NSE / MCX ATM Combined Premium Terminal
Bloomberg-style dashboard that tracks ATM (CE + PE) combined premium
for NSE indices and MCX commodities, flags >=X% spikes from session
baseline, and charts spot vs combined premium live via the Dhan API.
"""
import os
import time
from datetime import datetime
import pandas as pd
import plotly.graph_objects as go
import pytz
import streamlit as st
from dotenv import load_dotenv

# Load environment variables from .env file (for local execution)
load_dotenv()

try:
    from streamlit_autorefresh import st_autorefresh
    AUTOREFRESH_AVAILABLE = True
except ImportError:
    AUTOREFRESH_AVAILABLE = False

try:
    from dhanhq import DhanContext, dhanhq
    DHAN_AVAILABLE = True
except ImportError:
    DHAN_AVAILABLE = False

IST = pytz.timezone("Asia/Kolkata")

st.set_page_config(
    page_title="NSE / MCX Premium Terminal",
    page_icon="◆",
    layout="wide",
    initial_sidebar_state="expanded",
)

# =================================================================
# THEME  (Bloomberg-terminal dark palette)
# =================================================================
def inject_css():
    st.markdown(
        """
        <style>
        :root{
            --bg-void:#0A0E14; --bg-panel:#10161F; --bg-panel-alt:#161D29;
            --line:#232B38; --text:#E8EDF4; --dim:#6B7A8F;
            --amber:#FFB020; --up:#00D67C; --down:#FF4757; --alert:#FF6B35;
        }
        html, body, [class*="css"] { font-family: ui-monospace, 'SF Mono', Consolas, monospace; }
        .stApp { background-color: var(--bg-void); }
        section[data-testid="stSidebar"] { background-color: var(--bg-panel); border-right:1px solid var(--line); }
        div[data-testid="stMetric"] {
            background-color: var(--bg-panel-alt);
            border: 1px solid var(--line);
            padding: 12px 16px; border-radius: 4px;
        }
        div[data-testid="stMetricLabel"] { color: var(--dim); font-size: 11px; letter-spacing:1px; text-transform:uppercase; }
        h1, h2, h3 { color: var(--text) !important; letter-spacing: .5px; }
        .brand-bar {
            display:flex; justify-content:space-between; align-items:center;
            padding:6px 2px 14px 2px; border-bottom:1px solid var(--line); margin-bottom:14px;
        }
        .brand-mark { color: var(--amber); font-weight:700; font-size:20px; letter-spacing:1px; }
        .brand-sub { color: var(--dim); font-size:11px; letter-spacing:2px; text-transform:uppercase; }
        .spike-banner {
            background: linear-gradient(90deg, rgba(255,107,53,.20), rgba(255,107,53,.03));
            border:1px solid var(--alert); border-left:4px solid var(--alert);
            padding:10px 16px; border-radius:3px; margin-bottom:14px; color:var(--text); font-size:13px;
        }
        .quiet-banner {
            background: rgba(107,122,143,.08); border:1px solid var(--line);
            padding:10px 16px; border-radius:3px; margin-bottom:14px; color:var(--dim); font-size:12.5px;
        }
        .ticker-strip {
            background:#000; border:1px solid var(--amber); border-radius:3px;
            padding:8px 14px; margin-bottom:16px; font-size:12px; color:var(--text);
            white-space: nowrap; overflow-x:auto;
        }
        .ticker-strip span.up{color:var(--up);} .ticker-strip span.down{color:var(--down);}
        .ticker-strip span.flag{color:var(--alert); font-weight:700;}
        </style>
        """,
        unsafe_allow_html=True,
    )

inject_css()

# =================================================================
# INSTRUMENT REGISTRY
# =================================================================
INDEX_REGISTRY = {
    "NIFTY":     {"security_id": 13,  "segment": "IDX_I"},
    "BANKNIFTY": {"security_id": 25,  "segment": "IDX_I"},
    "FINNIFTY":  {"security_id": 27,  "segment": "IDX_I"},
}

COMMODITY_SYMBOLS = ["GOLD", "SILVER", "CRUDEOIL", "NATURALGAS"]
DYNAMIC_SYMBOLS = ["SENSEX"] + COMMODITY_SYMBOLS
ALL_SYMBOLS = list(INDEX_REGISTRY.keys()) + DYNAMIC_SYMBOLS

MIN_REFRESH_SECONDS = 10

# =================================================================
# DHAN CLIENT
# =================================================================
@st.cache_resource(show_spinner=False)
def get_dhan():
    # Checks Streamlit Cloud Secrets first, then falls back to local .env file
    client_id = st.secrets.get("DHAN_CLIENT_ID") or os.getenv("DHAN_CLIENT_ID")
    access_token = st.secrets.get("DHAN_ACCESS_TOKEN") or os.getenv("DHAN_ACCESS_TOKEN")
    
    if not DHAN_AVAILABLE or not client_id or not access_token:
        return None
        
    try:
        ctx = DhanContext(str(client_id), str(access_token))
        return dhanhq(ctx)
    except Exception as e:
        st.error(f"Failed to init Dhan client: {e}")
        return None

@st.cache_data(ttl=6 * 60 * 60, show_spinner=False)
def load_security_master():
    dhan = get_dhan()
    if dhan is None:
        return pd.DataFrame()
    try:
        raw = dhan.fetch_security_list("compact")
        df = raw if isinstance(raw, pd.DataFrame) else pd.DataFrame(raw)
        return df
    except Exception as e:
        st.session_state.setdefault("errors", []).append(f"security master: {e}")
        return pd.DataFrame()

def resolve_security(symbol: str):
    if symbol in INDEX_REGISTRY:
        r = INDEX_REGISTRY[symbol]
        return r["security_id"], r["segment"]
        
    master = load_security_master()
    if master.empty:
        return None, None
        
    cols = {c.lower(): c for c in master.columns}
    name_col = cols.get("sem_trading_symbol") or cols.get("symbol_name") or cols.get("trading_symbol")
    id_col = cols.get("sem_smst_security_id") or cols.get("security_id")
    
    if not (name_col and id_col):
        st.session_state.setdefault("errors", []).append(
            "Could not find expected symbol/id columns in security master."
        )
        return None, None
        
    upper_name = master[name_col].astype(str).str.upper()
    if symbol == "SENSEX":
        hits = master[upper_name == "SENSEX"]
        seg = "IDX_I"
    else:
        hits = master[upper_name.str.startswith(symbol) & upper_name.str.contains("FUT")]
        seg = "MCX_COMM"
        
    if hits.empty:
        return None, None
    return int(hits.iloc[0][id_col]), seg

# =================================================================
# DATA FETCH
# =================================================================
def fetch_atm_premium(symbol: str):
    dhan = get_dhan()
    if dhan is None:
        return None
        
    sec_id, seg = resolve_security(symbol)
    if sec_id is None:
        st.session_state.setdefault("errors", []).append(f"{symbol}: could not resolve security id")
        return None
        
    try:
        exp_resp = dhan.expiry_list(under_security_id=sec_id, under_exchange_segment=seg)
        expiries = exp_resp.get("data", []) if isinstance(exp_resp, dict) else []
        if not expiries:
            return None
            
        nearest_expiry = expiries[0]
        oc_resp = dhan.option_chain(
            under_security_id=sec_id, under_exchange_segment=seg, expiry=nearest_expiry
        )
        data = oc_resp.get("data", {}) if isinstance(oc_resp, dict) else {}
        spot = data.get("last_price")
        chain = data.get("oc", {})
        
        if spot is None or not chain:
            return None
            
        atm_key = min(chain.keys(), key=lambda k: abs(float(k) - float(spot)))
        leg = chain[atm_key]
        ce_ltp = float(leg.get("ce", {}).get("last_price") or 0)
        pe_ltp = float(leg.get("pe", {}).get("last_price") or 0)
        
        return {
            "symbol": symbol,
            "spot": float(spot),
            "strike": float(atm_key),
            "expiry": nearest_expiry,
            "ce": ce_ltp,
            "pe": pe_ltp,
            "combined": ce_ltp + pe_ltp,
            "ts": datetime.now(IST),
        }
    except Exception as e:
        st.session_state.setdefault("errors", []).append(f"{symbol}: {e}")
        return None

# =================================================================
# SESSION STATE
# =================================================================
if "history" not in st.session_state:
    st.session_state.history = {s: [] for s in ALL_SYMBOLS}
if "baseline" not in st.session_state:
    st.session_state.baseline = {}
if "errors" not in st.session_state:
    st.session_state.errors = []

def run_cycle(symbols):
    for i, sym in enumerate(symbols):
        rec = fetch_atm_premium(sym)
        if rec:
            st.session_state.history[sym].append(rec)
            st.session_state.history[sym] = st.session_state.history[sym][-500:]
            st.session_state.baseline.setdefault(sym, rec["combined"])
        if i < len(symbols) - 1:
            time.sleep(3.2)  # Respect Dhan rate limit

# =================================================================
# SIDEBAR
# =================================================================
with st.sidebar:
    st.markdown('<div class="brand-mark">◆ PREMIUM TERMINAL</div>', unsafe_allow_html=True)
    st.markdown('<div class="brand-sub">NSE + MCX · ATM Spike Watch</div>', unsafe_allow_html=True)
    st.markdown("---")
    
    dhan_client = get_dhan()
    if dhan_client is None:
        st.error("Dhan not connected — add DHAN_CLIENT_ID / DHAN_ACCESS_TOKEN to secrets or .env file.")
    else:
        st.success("Dhan client connected")
        
    selected = st.multiselect("Instruments", ALL_SYMBOLS, default=["NIFTY", "BANKNIFTY"])
    threshold = st.number_input("Spike threshold (%)", min_value=0.5, value=5.0, step=0.5)
    
    min_interval = max(MIN_REFRESH_SECONDS, 3 * max(len(selected), 1))
    interval = st.slider("Refresh interval (sec)", min_value=min_interval, max_value=120, value=min_interval)
    
    auto = st.toggle("Auto-refresh", value=False)
    manual_fetch = st.button("▶ Fetch Now", use_container_width=True)
    
    if st.button("Reset Session", use_container_width=True):
        st.session_state.history = {s: [] for s in ALL_SYMBOLS}
        st.session_state.baseline = {}
        st.session_state.errors = []
        st.rerun()
        
    with st.expander("Errors / debug log"):
        if st.session_state.errors:
            for e in st.session_state.errors[-15:]:
                st.caption(e)
        else:
            st.caption("No errors logged.")

if auto and AUTOREFRESH_AVAILABLE:
    st_autorefresh(interval=interval * 1000, key="auto_refresh_tick")
elif auto and not AUTOREFRESH_AVAILABLE:
    st.sidebar.warning("Install `streamlit-autorefresh` to enable auto-refresh.")

if dhan_client and selected and (auto or manual_fetch):
    with st.spinner("Fetching option chain..."):
        run_cycle(selected)

# =================================================================
# HEADER
# =================================================================
now_ist = datetime.now(IST)
st.markdown(
    f"""
    <div class="brand-bar">
        <div><span class="brand-mark">◆ NSE / MCX PREMIUM TERMINAL</span></div>
        <div style="color:var(--dim); font-size:13px;">{now_ist.strftime('%H:%M:%S IST · %d %b %Y')}</div>
    </div>
    """,
    unsafe_allow_html=True,
)

if not selected:
    st.info("Pick one or more instruments in the sidebar to begin.")
    st.stop()

# Ticker strip
ticker_bits = []
for sym in selected:
    hist = st.session_state.history.get(sym, [])
    if not hist:
        ticker_bits.append(f"<span>{sym} — no data yet</span>")
        continue
    last = hist[-1]
    base = st.session_state.baseline.get(sym, last["combined"])
    pct = ((last["combined"] - base) / base * 100) if base else 0
    cls = "up" if pct >= 0 else "down"
    flag = ' <span class="flag">⚠ SPIKE</span>' if pct >= threshold else ""
    ticker_bits.append(
        f"<span>{sym} {last['spot']:.2f}</span> "
        f"<span class='{cls}'>PREM {last['combined']:.2f} ({pct:+.2f}%)</span>{flag}"
    )
st.markdown('<div class="ticker-strip">' + "  |  ".join(ticker_bits) + "</div>", unsafe_allow_html=True)

# =================================================================
# PER-SYMBOL TABS
# =================================================================
tabs = st.tabs(selected)
for tab, sym in zip(tabs, selected):
    with tab:
        hist = st.session_state.history.get(sym, [])
        if not hist:
            st.markdown(
                '<div class="quiet-banner">No ticks yet for this symbol — click '
                '"Fetch Now" or enable auto-refresh in the sidebar.</div>',
                unsafe_allow_html=True,
            )
            continue

        df = pd.DataFrame(hist)
        base = st.session_state.baseline.get(sym, df["combined"].iloc[0])
        df["pct_chg"] = (df["combined"] - base) / base * 100
        last = df.iloc[-1]
        is_spike = last["pct_chg"] >= threshold
        
        if is_spike:
            st.markdown(
                f'<div class="spike-banner"> SPIKE — {sym} combined premium is '
                f'<b>{last["pct_chg"]:+.2f}%</b> vs session baseline ({base:.2f})</div>',
                unsafe_allow_html=True,
            )
            
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Spot", f"{last['spot']:.2f}")
        c2.metric("ATM Strike", f"{last['strike']:.0f}", help=f"Expiry: {last['expiry']}")
        c3.metric("Combined Premium (CE+PE)", f"{last['combined']:.2f}", f"{last['pct_chg']:+.2f}% vs base")
        c4.metric("Ticks logged", len(df))
        
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=df["ts"], y=df["combined"], name="Combined Premium",
            line=dict(color="#FFB020", width=2), yaxis="y1",
        ))
        fig.add_trace(go.Scatter(
            x=df["ts"], y=df["spot"], name="Spot",
            line=dict(color="#4C8DFF", width=2), yaxis="y2",
        ))
        fig.add_trace(go.Scatter(
            x=df["ts"], y=[base * (1 + threshold / 100)] * len(df), name=f"+{threshold:.1f}% threshold",
            line=dict(color="#FF6B35", width=1.5, dash="dash"), yaxis="y1",
        ))
        fig.update_layout(
            template="plotly_dark",
            paper_bgcolor="#161D29", plot_bgcolor="#161D29",
            font=dict(family="ui-monospace, Consolas, monospace", color="#E8EDF4", size=11),
            height=380, margin=dict(l=10, r=10, t=30, b=10),
            legend=dict(orientation="h", y=1.12, x=0),
            yaxis=dict(title="Combined Premium", gridcolor="#232B38"),
            yaxis2=dict(title="Spot", overlaying="y", side="right", showgrid=False),
            xaxis=dict(gridcolor="#232B38"),
        )
        st.plotly_chart(fig, use_container_width=True)
        
        with st.expander("Tick log", expanded=False):
            show_df = df[["ts", "spot", "strike", "ce", "pe", "combined", "pct_chg"]].copy()
            show_df.columns = ["Time", "Spot", "ATM Strike", "CE", "PE", "Comb. Premium", "% vs Base"]
            show_df["Time"] = show_df["Time"].dt.strftime("%H:%M:%S")
            st.dataframe(show_df.iloc[::-1], use_container_width=True, height=260)

st.caption("Data via Dhan API option-chain endpoint (rate limited to 1 request / 3s per underlying). Not investment advice.")
