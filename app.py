"""
NSE Combined Premium Spike Dashboard | Mini Bloomberg Terminal
Tracks ATM (CE + PE) combined premium for NSE indices & stocks
Flags >=5% spikes from session baseline with live charts
Credentials: .env file with DHAN_CLIENT_ID & DHAN_ACCESS_TOKEN
"""
import os
import time
from datetime import datetime, timedelta
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pytz
import streamlit as st
from dotenv import load_dotenv
import numpy as np

# Load environment variables from .env file
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

# =================================================================
# PAGE CONFIG & BLOOMBERG THEME
# =================================================================
st.set_page_config(
    page_title="NSE Premium Spike Terminal",
    page_icon="◆",
    layout="wide",
    initial_sidebar_state="expanded",
)

def inject_bloomberg_css():
    st.markdown("""
    <style>
    :root {
        --bg-main: #0a0e17; --bg-panel: #111827; --bg-card: #1e293b;
        --border: #2d3748; --text-primary: #e2e8f0; --text-secondary: #94a3b8;
        --accent-amber: #f59e0b; --accent-blue: #3b82f6;
        --success: #22c55e; --danger: #ef4444; --warning: #f97316;
    }
    .stApp { background-color: var(--bg-main); font-family: 'Segoe UI', system-ui, sans-serif; }
    section[data-testid="stSidebar"] { background-color: var(--bg-panel); border-right: 1px solid var(--border); }
    div[data-testid="stMetric"] {
        background: linear-gradient(135deg, var(--bg-card) 0%, var(--bg-panel) 100%);
        border: 1px solid var(--border); border-radius: 6px; padding: 16px;
    }
    div[data-testid="stMetricLabel"] { color: var(--text-secondary); font-size: 11px; letter-spacing: 1.2px; text-transform: uppercase; font-weight: 600; }
    div[data-testid="stMetricValue"] { color: var(--text-primary); font-size: 24px; font-weight: 700; font-variant-numeric: tabular-nums; }
    h1, h2, h3 { color: var(--text-primary) !important; letter-spacing: 0.5px; font-weight: 600; }
    .brand-header { display: flex; justify-content: space-between; align-items: center; padding: 12px 0; border-bottom: 2px solid var(--accent-amber); margin-bottom: 20px; }
    .brand-title { color: var(--accent-amber); font-size: 22px; font-weight: 700; letter-spacing: 1px; }
    .brand-subtitle { color: var(--text-secondary); font-size: 11px; letter-spacing: 2px; text-transform: uppercase; }
    .clock-badge { background: var(--bg-card); border: 1px solid var(--border); padding: 6px 12px; border-radius: 4px; font-size: 12px; color: var(--text-secondary); font-variant-numeric: tabular-nums; }
    .badge-live { background: rgba(34, 197, 94, 0.15); color: var(--success); border: 1px solid rgba(34, 197, 94, 0.4); padding: 4px 12px; border-radius: 4px; font-size: 11px; font-weight: 700; letter-spacing: 0.8px; text-transform: uppercase; }
    .badge-sim { background: rgba(245, 158, 11, 0.15); color: var(--accent-amber); border: 1px solid rgba(245, 158, 11, 0.4); padding: 4px 12px; border-radius: 4px; font-size: 11px; font-weight: 700; letter-spacing: 0.8px; text-transform: uppercase; }
    .spike-alert { background: linear-gradient(90deg, rgba(239, 68, 68, 0.15), rgba(239, 68, 68, 0.05)); border: 1px solid var(--danger); border-left: 5px solid var(--danger); padding: 12px 16px; border-radius: 4px; margin: 12px 0; animation: pulse 2s infinite; }
    .spike-alert-normal { background: rgba(34, 197, 94, 0.08); border: 1px solid var(--success); border-left: 5px solid var(--success); padding: 12px 16px; border-radius: 4px; margin: 12px 0; }
    @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.85; } }
    .ticker-strip { background: #000; border: 1px solid var(--accent-amber); border-radius: 4px; padding: 10px 16px; margin: 16px 0; font-size: 12px; color: var(--text-primary); overflow-x: auto; white-space: nowrap; }
    .ticker-item { display: inline-block; margin-right: 24px; padding: 4px 8px; }
    .ticker-up { color: var(--success); font-weight: 600; }
    .ticker-down { color: var(--danger); font-weight: 600; }
    .ticker-spike { color: var(--warning); font-weight: 700; }
    .stDataFrame { background-color: var(--bg-panel); border: 1px solid var(--border); border-radius: 6px; }
    th { background-color: var(--bg-card) !important; color: var(--text-secondary) !important; font-size: 11px !important; text-transform: uppercase; letter-spacing: 0.8px; font-weight: 600; }
    td { color: var(--text-primary); font-size: 12px; }
    .alert-item { background: rgba(245, 158, 11, 0.08); border-left: 3px solid var(--accent-amber); padding: 10px; margin: 8px 0; border-radius: 4px; font-size: 12px; }
    .alert-time { color: var(--text-secondary); font-size: 10px; }
    .alert-message { color: var(--text-primary); font-weight: 600; margin: 4px 0; }
    .stats-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin: 12px 0; }
    .stat-box { background: var(--bg-card); border: 1px solid var(--border); border-radius: 4px; padding: 10px; text-align: center; }
    .stat-label { color: var(--text-secondary); font-size: 10px; text-transform: uppercase; letter-spacing: 0.8px; }
    .stat-value { color: var(--text-primary); font-size: 16px; font-weight: 700; margin-top: 4px; }
    .info-box { background: rgba(59, 130, 246, 0.1); border: 1px solid rgba(59, 130, 246, 0.3); border-radius: 6px; padding: 14px; font-size: 11.5px; color: var(--text-secondary); line-height: 1.6; }
    .info-box strong { color: var(--text-primary); }
    </style>
    """, unsafe_allow_html=True)

inject_bloomberg_css()

# =================================================================
# INSTRUMENT REGISTRY
# =================================================================
INDEX_REGISTRY = {
    "NIFTY":      {"security_id": 13,  "segment": "IDX_I", "lot_size": 25},
    "BANKNIFTY":  {"security_id": 25,  "segment": "IDX_I", "lot_size": 15},
    "FINNIFTY":   {"security_id": 27,  "segment": "IDX_I", "lot_size": 25},
    "MIDCPNIFTY": {"security_id": 31,  "segment": "IDX_I", "lot_size": 25},
}
STOCK_SYMBOLS = ["RELIANCE", "HDFCBANK", "ICICIBANK", "INFY", "TCS", "SBIN", "KOTAKBANK", "AXISBANK"]
COMMODITY_SYMBOLS = ["GOLD", "SILVER", "CRUDEOIL", "NATURALGAS", "COPPER"]
ALL_SYMBOLS = list(INDEX_REGISTRY.keys()) + STOCK_SYMBOLS + COMMODITY_SYMBOLS
MIN_REFRESH_SECONDS = 10

# =================================================================
# DHAN CLIENT INITIALIZATION
# =================================================================
@st.cache_resource(show_spinner=False)
def get_dhan_client():
    """Return a dhanhq client, or None if credentials/SDK are missing."""
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

@st.cache_data(ttl=6*60*60, show_spinner=False)
def load_security_master():
    """Load Dhan instrument master (cached 6 hours). No args to avoid hashing errors."""
    client = get_dhan_client()
    if client is None:
        return pd.DataFrame()
    try:
        raw = client.fetch_security_list("compact")
        return raw if isinstance(raw, pd.DataFrame) else pd.DataFrame(raw)
    except Exception as e:
        st.session_state.setdefault("errors", []).append(f"Security master: {e}")
        return pd.DataFrame()

def resolve_security(symbol: str):
    """Resolve security ID for symbol (handles dynamic contracts)"""
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
        return None, None
    
    upper_name = master[name_col].astype(str).str.upper()
    
    if symbol in STOCK_SYMBOLS:
        hits = master[upper_name == symbol]
        seg = "NSE_EQ"
    else:
        hits = master[upper_name.str.startswith(symbol) & upper_name.str.contains("FUT")]
        seg = "MCX_COMM"
    
    if hits.empty:
        return None, None
    
    return int(hits.iloc[0][id_col]), seg

# =================================================================
# DATA FETCHING
# =================================================================
def fetch_atm_premium(symbol: str):
    """Fetch ATM combined premium (CE + PE) for a symbol"""
    client = get_dhan_client()
    if client is None:
        return None
    
    sec_id, seg = resolve_security(symbol)
    if sec_id is None:
        st.session_state.setdefault("errors", []).append(f"{symbol}: could not resolve security id")
        return None
    
    try:
        exp_resp = client.expiry_list(under_security_id=sec_id, under_exchange_segment=seg)
        expiries = exp_resp.get("data", []) if isinstance(exp_resp, dict) else []
        if not expiries:
            return None
        
        nearest_expiry = expiries[0]
        oc_resp = client.option_chain(under_security_id=sec_id, under_exchange_segment=seg, expiry=nearest_expiry)
        
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
            "symbol": symbol, "spot": float(spot), "strike": float(atm_key),
            "expiry": nearest_expiry, "ce": ce_ltp, "pe": pe_ltp,
            "combined": ce_ltp + pe_ltp, "ts": datetime.now(IST),
        }
    except Exception as e:
        st.session_state.setdefault("errors", []).append(f"{symbol}: {e}")
        return None

# =================================================================
# SESSION STATE MANAGEMENT
# =================================================================
if "history" not in st.session_state:
    st.session_state.history = {s: [] for s in ALL_SYMBOLS}
if "baseline" not in st.session_state:
    st.session_state.baseline = {}
if "alerts" not in st.session_state:
    st.session_state.alerts = []
if "errors" not in st.session_state:
    st.session_state.errors = []

def run_data_cycle(symbols, threshold):
    """Fetch data for all selected symbols"""
    now = datetime.now(IST)
    
    for i, sym in enumerate(symbols):
        rec = fetch_atm_premium(sym)
        if rec:
            st.session_state.history[sym].append(rec)
            st.session_state.history[sym] = st.session_state.history[sym][-500:]
            
            if sym not in st.session_state.baseline:
                st.session_state.baseline[sym] = rec["combined"]
            
            base = st.session_state.baseline[sym]
            pct_change = ((rec["combined"] - base) / base * 100) if base else 0
            
            if abs(pct_change) >= threshold:
                recent_alert = any(a["symbol"] == sym and (now - a["time"]).total_seconds() < 30 for a in st.session_state.alerts)
                if not recent_alert:
                    st.session_state.alerts.insert(0, {
                        "time": now, "symbol": sym, "pct_change": pct_change,
                        "combined": rec["combined"], "spot": rec["spot"],
                    })
                    if len(st.session_state.alerts) > 50:
                        st.session_state.alerts.pop()
        
        if i < len(symbols) - 1:
            time.sleep(3.2)  # Rate limiting

# =================================================================
# SIDEBAR CONTROLS
# =================================================================
with st.sidebar:
    st.markdown('<div class="brand-title">◆ PREMIUM TERMINAL</div>', unsafe_allow_html=True)
    st.markdown('<div class="brand-subtitle">NSE + MCX · ATM Spike Watch</div>', unsafe_allow_html=True)
    st.markdown("---")
    
    dhan_client = get_dhan_client()  # FIXED: Matches function name
    
    if dhan_client is None:
        st.markdown('<div class="badge-sim">⚠ SIMULATION MODE</div>', unsafe_allow_html=True)
        st.info("Add DHAN_CLIENT_ID and DHAN_ACCESS_TOKEN to your `.env` file or Streamlit Secrets.")
    else:
        st.markdown('<div class="badge-live">● LIVE MODE</div>', unsafe_allow_html=True)
        st.success("✓ Dhan API connected")
    
    st.markdown("---")
    
    selected_symbols = st.multiselect("Instruments", ALL_SYMBOLS, default=["NIFTY", "BANKNIFTY", "FINNIFTY"])
    threshold = st.number_input("Spike Threshold (%)", min_value=1.0, max_value=20.0, value=5.0, step=0.5)
    
    min_interval = max(MIN_REFRESH_SECONDS, 4 * max(len(selected_symbols), 1))
    refresh_interval = st.slider("Refresh Interval (sec)", min_value=min_interval, max_value=120, value=min_interval)
    
    auto_refresh = st.toggle("Auto-refresh", value=False)
    fetch_button = st.button("▶ Fetch Now", type="primary", use_container_width=True)
    
    if st.button("🔄 Reset Session", use_container_width=True):
        st.session_state.history = {s: [] for s in ALL_SYMBOLS}
        st.session_state.baseline = {}
        st.session_state.alerts = []
        st.session_state.errors = []
        st.rerun()
    
    with st.expander("⚙️ Debug Log"):
        if st.session_state.errors:
            for err in st.session_state.errors[-20:]:
                st.caption(err)
        else:
            st.caption("No errors logged")

if auto_refresh and AUTOREFRESH_AVAILABLE:
    st_autorefresh(interval=refresh_interval * 1000, key="auto_refresh")
elif auto_refresh and not AUTOREFRESH_AVAILABLE:
    st.sidebar.warning("Install `streamlit-autorefresh` to enable auto-refresh")

if dhan_client and selected_symbols and (auto_refresh or fetch_button):
    with st.spinner("Fetching option chain data..."):
        run_data_cycle(selected_symbols, threshold)  # FIXED: Removed client arg

# =================================================================
# MAIN DASHBOARD
# =================================================================
now_ist = datetime.now(IST)
st.markdown(f"""
<div class="brand-header">
    <div>
        <div class="brand-title">◆ NSE COMBINED PREMIUM TERMINAL</div>
        <div class="brand-subtitle">ATM Straddle Value · Spike Detection · Live Charts</div>
    </div>
    <div class="clock-badge">{now_ist.strftime('%H:%M:%S IST · %d %b %Y')}</div>
</div>
""", unsafe_allow_html=True)

if not selected_symbols:
    st.info("👈 Select instruments in the sidebar to begin monitoring")
    st.stop()

ticker_html = '<div class="ticker-strip">'
for sym in selected_symbols:
    hist = st.session_state.history.get(sym, [])
    if not hist:
        ticker_html += f'<span class="ticker-item">{sym}: No data</span>'
        continue
    last = hist[-1]
    base = st.session_state.baseline.get(sym, last["combined"])
    pct = ((last["combined"] - base) / base * 100) if base else 0
    direction = "↑" if pct >= 0 else "↓"
    cls = "ticker-up" if pct >= 0 else "ticker-down"
    spike_flag = ' <span class="ticker-spike"> SPIKE</span>' if abs(pct) >= threshold else ""
    ticker_html += f'<span class="ticker-item"><strong>{sym}</strong> {last["spot"]:.2f} | <span class="{cls}">Prem {last["combined"]:.2f} ({direction} {abs(pct):.1f}%)</span>{spike_flag}</span>'
ticker_html += '</div>'
st.markdown(ticker_html, unsafe_allow_html=True)

tabs = st.tabs(selected_symbols)
for tab, sym in zip(tabs, selected_symbols):
    with tab:
        hist = st.session_state.history.get(sym, [])
        if not hist:
            st.markdown('<div style="background: rgba(148,163,184,0.08); border: 1px solid #2d3748; border-radius: 6px; padding: 20px; text-align: center; color: #94a3b8;"><strong>No data yet</strong><br>Click "Fetch Now" or enable auto-refresh</div>', unsafe_allow_html=True)
            continue
        
        df = pd.DataFrame(hist)
        base = st.session_state.baseline.get(sym, df["combined"].iloc[0])
        df["pct_chg"] = (df["combined"] - base) / base * 100
        last = df.iloc[-1]
        current_pct = last["pct_chg"]
        is_spike = abs(current_pct) >= threshold
        
        if is_spike:
            direction = "📈 SPIKE UP" if current_pct > 0 else "📉 SPIKE DOWN"
            st.markdown(f'<div class="spike-alert"><strong>{direction}</strong> — {sym} combined premium is <strong style="font-size: 16px;">{current_pct:+.2f}%</strong> vs session baseline ({base:.2f})</div>', unsafe_allow_html=True)
        else:
            st.markdown(f'<div class="spike-alert-normal"><strong>✓ Normal</strong> — {sym} combined premium at <strong>{current_pct:+.2f}%</strong> vs baseline (threshold: ±{threshold}%)</div>', unsafe_allow_html=True)
        
        m1, m2, m3, m4, m5, m6 = st.columns(6)
        with m1: st.metric("Spot Price", f"{last['spot']:,.2f}")
        with m2: st.metric("ATM Strike", f"{last['strike']:,.0f}")
        with m3: st.metric("Combined Premium", f"₹{last['combined']:.2f}", f"{current_pct:+.2f}%")
        with m4: st.metric("CE Premium", f"₹{last['ce']:.2f}")
        with m5: st.metric("PE Premium", f"₹{last['pe']:.2f}")
        with m6: st.metric("Data Points", len(df))
        
        fig = make_subplots(specs=[[{"secondary_y": True}]])
        fig.add_trace(go.Scatter(x=df["ts"], y=df["combined"], name="Combined Premium (CE+PE)", line=dict(color="#f59e0b", width=2.5), fill="tozeroy", fillcolor="rgba(245, 158, 11, 0.15)"), secondary_y=False)
        
        spot_scaled = df["spot"] * (df["combined"].iloc[-1] / df["spot"].iloc[-1])
        fig.add_trace(go.Scatter(x=df["ts"], y=spot_scaled, name="Spot Price (scaled)", line=dict(color="#3b82f6", width=2)), secondary_y=True)
        
        fig.add_hline(y=base * (1 + threshold / 100), line_dash="dash", line_color="#ef4444", annotation_text=f"+{threshold}%", annotation_position="top right", secondary_y=False)
        fig.add_hline(y=base * (1 - threshold / 100), line_dash="dash", line_color="#22c55e", annotation_text=f"-{threshold}%", annotation_position="bottom right", secondary_y=False)
        
        fig.update_layout(template="plotly_dark", paper_bgcolor="#111827", plot_bgcolor="#111827", font=dict(family="ui-monospace, Consolas, monospace", color="#e2e8f0", size=11), height=400, margin=dict(l=10, r=10, t=40, b=10), legend=dict(orientation="h", y=1.15, x=0), showlegend=True)
        fig.update_yaxes(title_text="Combined Premium (₹)", gridcolor="#2d3748", secondary_y=False)
        fig.update_yaxes(title_text="Spot Price (scaled)", gridcolor="#2d3748", secondary_y=True)
        fig.update_xaxes(gridcolor="#2d3748", tickformat="%H:%M")
        st.plotly_chart(fig, use_container_width=True)
        
        st.markdown("### 📊 Session Statistics")
        prems = df["combined"].values
        st.markdown(f"""
        <div class="stats-grid">
            <div class="stat-box"><div class="stat-label">Max Premium</div><div class="stat-value">₹{np.max(prems):.2f}</div></div>
            <div class="stat-box"><div class="stat-label">Min Premium</div><div class="stat-value">₹{np.min(prems):.2f}</div></div>
            <div class="stat-box"><div class="stat-label">Avg Premium</div><div class="stat-value">₹{np.mean(prems):.2f}</div></div>
            <div class="stat-box"><div class="stat-label">Volatility Events</div><div class="stat-value">{len([a for a in st.session_state.alerts if a['symbol'] == sym])}</div></div>
        </div>
        """, unsafe_allow_html=True)
        
        with st.expander("📋 Tick Log", expanded=False):
            show_df = df[["ts", "spot", "strike", "ce", "pe", "combined", "pct_chg"]].copy()
            show_df.columns = ["Time", "Spot", "ATM Strike", "CE", "PE", "Combined", "% vs Base"]
            show_df["Time"] = show_df["Time"].dt.strftime("%H:%M:%S")
            show_df["% vs Base"] = show_df["% vs Base"].apply(lambda x: f"{x:+.2f}%")
            st.dataframe(show_df.iloc[::-1].reset_index(drop=True), use_container_width=True, height=300)

with st.sidebar:
    st.markdown("---")
    st.markdown("### ⚡ Spike Alerts")
    if not st.session_state.alerts:
        st.markdown(f'<div style="background: rgba(148,163,184,0.08); border: 1px solid #2d3748; border-radius: 6px; padding: 16px; text-align: center; color: #94a3b8; font-size: 12px;">No spikes detected yet<br>Monitoring for ≥{threshold}% moves</div>', unsafe_allow_html=True)
    else:
        for alert in st.session_state.alerts[:20]:
            direction = "📈" if alert["pct_change"] > 0 else "📉"
            color_class = "up" if alert["pct_change"] > 0 else "down"
            st.markdown(f'''
            <div class="alert-item">
                <div class="alert-time">{alert["time"].strftime("%H:%M:%S IST")}</div>
                <div class="alert-message">{direction} <strong>{alert["symbol"]}</strong> <span class="{color_class}">{alert["pct_change"]:+.1f}%</span></div>
                <div style="color: #94a3b8; font-size: 11px;">Prem: ₹{alert["combined"]:.2f} | Spot: {alert["spot"]:.2f}</div>
            </div>
            ''', unsafe_allow_html=True)

with st.expander("ℹ️ How to Read This Dashboard"):
    st.markdown('''
    <div class="info-box">
    <strong>Combined Premium</strong> = ATM Call LTP + ATM Put LTP (straddle value)<br><br>
    <strong>≥5% spike without big spot move</strong> often signals: Institutional positioning, Rising IV expectation, Breakout or event risk.<br><br>
    <strong>Rising premium + flat spot</strong> → Volatility expansion (favorable for option buyers)<br>
    <strong>Falling premium + flat spot</strong> → Theta crush / IV crush (favorable for sellers)<br><br>
    <strong>Data Source:</strong> Dhan API option-chain endpoint (rate limited to 1 request/3s per underlying)<br>
    <strong>Disclaimer:</strong> Educational/demo purposes only. Not investment advice.
    </div>
    ''', unsafe_allow_html=True)

st.markdown("---")
st.caption("◆ NSE/MCX Premium Terminal · Built with Streamlit + DhanHQ API · Data refresh rate: 1 request per 3s per underlying · Not investment advice")
