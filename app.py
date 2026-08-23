"""
NSE / MCX Combined-Premium Terminal (Mini Bloomberg Layout)
-----------------------------------------------------------
Run: streamlit run app.py
Requires: .env with DHAN_CLIENT_ID and DHAN_ACCESS_TOKEN
"""
import time
from datetime import datetime
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from dotenv import load_dotenv

# Assuming these modules exist in your project structure as per original code
from config import (
    INDEX_INSTRUMENTS, COMMODITY_INSTRUMENTS, ALL_INSTRUMENTS,
    DEFAULT_THRESHOLD_PCT, DEFAULT_REFRESH_SECONDS, MAX_HISTORY_POINTS,
)
from dhan_service import (
    get_dhan, dhan_is_connected, fetch_atm_combined_premium,
    resolve_mcx_underlying, search_scrip_master,
    init_sim_state, step_sim,
)

load_dotenv()

st.set_page_config(
    page_title="NSE/MCX Premium Terminal",
    page_icon="\U0001F4C8",
    layout="wide",
    initial_sidebar_state="collapsed", # Collapsed for true terminal feel
)

# ==========================================================================
# ADVANCED TERMINAL CSS THEME
# ==========================================================================
st.markdown("""
<style>
    /* Base Terminal Variables */
    :root {
        --bg-void: #0a0e1a; --bg-panel: #111827; --bg-alt: #1f2937; 
        --line: #30363d; --text: #e2e8f0; --dim: #64748b; 
        --amber: #fbbf24; --up: #10b981; --down: #ef4444; --alert: #f97316; --cyan: #06b6d4;
    }
    
    /* Global Reset & Typography */
    html, body, [class*="css"] { font-family: 'JetBrains Mono', 'SF Mono', Consolas, monospace !important; background: var(--bg-void) !important; color: var(--text) !important; }
    .stApp { background: var(--bg-void); }
    section[data-testid="stSidebar"] { background: var(--bg-panel); border-right: 1px solid var(--line); }
    
    /* Layout Containers */
    .term-row { border-bottom: 1px solid var(--line); padding: 8px 0; }
    .term-header { display: flex; justify-content: space-between; align-items: center; padding: 10px 16px; border-bottom: 1px solid var(--line); background: var(--bg-panel); }
    .term-brand { font-size: 20px; font-weight: 800; letter-spacing: 1px; color: var(--amber); }
    .term-sub { font-size: 11px; letter-spacing: 1.5px; color: var(--dim); text-transform: uppercase; margin-top: 2px; }
    
    /* Controls Bar */
    .ctrl-bar { display: flex; gap: 16px; padding: 8px 16px; background: var(--bg-alt); border-bottom: 1px solid var(--line); align-items: center; }
    .ctrl-item { display: flex; flex-direction: column; }
    .ctrl-label { font-size: 9px; color: var(--dim); text-transform: uppercase; letter-spacing: 1px; margin-bottom: 2px; }
    
    /* Ticker Strip */
    .ticker-wrap { width: 100%; overflow: hidden; background: var(--bg-void); border-bottom: 1px solid var(--line); padding: 6px 0; white-space: nowrap; }
    .ticker-content { display: inline-block; animation: ticker 40s linear infinite; font-size: 12px; }
    .ticker-item { display: inline-block; padding: 0 24px; color: var(--text); }
    .ticker-up { color: var(--up); } .ticker-down { color: var(--down); }
    @keyframes ticker { 0% { transform: translateX(100%); } 100% { transform: translateX(-100%); } }

    /* Chart & Alerts Area */
    .chart-container { background: var(--bg-panel); border: 1px solid var(--line); border-radius: 4px; padding: 12px; height: 100%; }
    .alert-panel { background: var(--bg-panel); border: 1px solid var(--line); border-radius: 4px; padding: 12px; height: 100%; overflow-y: auto; max-height: 450px; }
    .alert-item { border-bottom: 1px solid var(--line); padding: 6px 0; font-size: 11px; }
    .alert-time { color: var(--dim); } .alert-sym { color: var(--cyan); font-weight: bold; } .alert-pct-up { color: var(--up); } .alert-pct-down { color: var(--down); }

    /* Interactive Watchlist Grid */
    .wl-table { width: 100%; border-collapse: collapse; font-size: 12px; }
    .wl-table th { text-align: left; padding: 8px 10px; border-bottom: 1px solid var(--line); color: var(--dim); font-weight: normal; font-size: 10px; text-transform: uppercase; letter-spacing: 0.5px; }
    .wl-table td { padding: 8px 10px; border-bottom: 1px solid #1e293b; color: var(--text); }
    .wl-row { transition: background 0.15s; cursor: pointer; }
    .wl-row:hover { background: var(--bg-alt); }
    .wl-row.active { background: rgba(6, 182, 212, 0.1); border-left: 3px solid var(--cyan); }
    .wl-row.active td:first-child { color: var(--cyan); font-weight: bold; }
    .status-spike { color: var(--alert); font-weight: bold; background: rgba(249, 115, 22, 0.1); padding: 2px 6px; border-radius: 3px; font-size: 10px; }
    .status-normal { color: var(--dim); font-size: 10px; }
    .val-up { color: var(--up); } .val-down { color: var(--down); }

    /* Info & Footer */
    .info-bar { background: var(--bg-alt); border-top: 1px solid var(--line); padding: 8px 16px; font-size: 11px; color: var(--dim); }
    .footer-ticker { background: var(--bg-panel); border-top: 1px solid var(--line); padding: 6px 16px; font-size: 11px; display: flex; gap: 24px; }

    /* Streamlit Overrides */
    .stButton>button { background: transparent; border: 1px solid var(--line); color: var(--text); border-radius: 3px; font-family: monospace; }
    .stButton>button:hover { border-color: var(--cyan); color: var(--cyan); }
    [data-testid="stSidebar"] .stSelectbox label, [data-testid="stSidebar"] .stNumberInput label { font-size: 10px; color: var(--dim); text-transform: uppercase; }
</style>
""", unsafe_allow_html=True)

# ==========================================================================
# STATE INITIALIZATION
# ==========================================================================
if "history" not in st.session_state:
    st.session_state.history = {sym: [] for sym in ALL_INSTRUMENTS}
if "sim_state" not in st.session_state:
    st.session_state.sim_state = {sym: init_sim_state(sym) for sym in ALL_INSTRUMENTS}
if "alerts" not in st.session_state:
    st.session_state.alerts = []
if "mcx_resolved" not in st.session_state:
    st.session_state.mcx_resolved = {}
if "selected_symbol" not in st.session_state:
    st.session_state.selected_symbol = "NIFTY"

dhan_client = get_dhan()
LIVE = dhan_is_connected(dhan_client)

# ==========================================================================
# ROW 1: HEADER
# ==========================================================================
st.markdown(f"""
<div class="term-header">
    <div>
        <div class="term-brand">\u25c6 NSE/MCX PREMIUM TERMINAL</div>
        <div class="term-sub">ATM Combined Premium Spike Monitor (≥5%)</div>
    </div>
    <div style="text-align:right;">
        <span style="color:var(--up); font-weight:bold; font-size:14px;">\u25cf MARKET OPEN</span>
        <div style="color:var(--dim); font-size:12px; margin-top:4px;">{datetime.now().strftime('%H:%M:%S IST')} | {datetime.now().strftime('%d %b %Y')}</div>
    </div>
</div>
""", unsafe_allow_html=True)

# ==========================================================================
# ROW 2: CONTROLS BAR (Moved from Sidebar for Terminal Layout)
# ==========================================================================
ctrl1, ctrl2, ctrl3, ctrl4, ctrl5 = st.columns([1.5, 2.5, 1.5, 1.5, 1])
with ctrl1:
    st.markdown('<div class="ctrl-item"><div class="ctrl-label">Asset Class</div></div>', unsafe_allow_html=True)
    asset_class = st.radio("Asset", ["Index", "Commodity"], horizontal=True, label_visibility="collapsed")
with ctrl2:
    st.markdown('<div class="ctrl-item"><div class="ctrl-label">Instrument</div></div>', unsafe_allow_html=True)
    universe = INDEX_INSTRUMENTS if asset_class == "Index" else COMMODITY_INSTRUMENTS
    symbol = st.selectbox("Symbol", list(universe.keys()), format_func=lambda s: universe[s]["label"], label_visibility="collapsed")
    inst = universe[symbol]
with ctrl3:
    st.markdown('<div class="ctrl-item"><div class="ctrl-label">Spike Threshold (%)</div></div>', unsafe_allow_html=True)
    threshold = st.number_input("Thresh", min_value=0.5, max_value=50.0, value=5.0, step=0.5, label_visibility="collapsed")
with ctrl4:
    st.markdown('<div class="ctrl-item"><div class="ctrl-label">Auto Refresh (s)</div></div>', unsafe_allow_html=True)
    refresh_secs = st.slider("Refresh", 5, 60, 10, label_visibility="collapsed")
with ctrl5:
    st.markdown('<div class="ctrl-item" style="margin-top:18px;"></div>', unsafe_allow_html=True)
    if st.button("\u21bb Reset", use_container_width=True):
        st.session_state.history[symbol] = []
        st.rerun()

# Update selected symbol if changed via dropdown
st.session_state.selected_symbol = symbol

# ==========================================================================
# ROW 3: MARKET TICKER STRIP
# ==========================================================================
st.markdown("""
<div class="ticker-wrap">
    <div class="ticker-content">
        <span class="ticker-item">NIFTY 50: <b>22,468.30</b> <span class="ticker-up">\u25b212.70 (+0.42%)</span></span>
        <span class="ticker-item">SENSEX: <b>75,192.10</b> <span class="ticker-down">\u25bc18.40 (-0.18%)</span></span>
        <span class="ticker-item">BANKNIFTY: <b>45,211.50</b> <span class="ticker-up">\u25b289.60 (+0.67%)</span></span>
        <span class="ticker-item">MCX CRUDE: <b>\u20b96,842</b> <span class="ticker-up">\u25b213.20 (+1.23%)</span></span>
        <span class="ticker-item">MCX GOLD: <b>\u20b97,219</b> <span class="ticker-down">\u25bc5.40 (-0.31%)</span></span>
        <span class="ticker-item">FINNIFTY: <b>21,100.00</b> <span class="ticker-up">\u25b245.00 (+0.21%)</span></span>
    </div>
</div>
""", unsafe_allow_html=True)

# ==========================================================================
# DATA FETCH LOGIC
# ==========================================================================
def get_reading(sym: str, inst: dict):
    if LIVE:
        security_id = inst.get("security_id")
        segment = inst["segment"]
        if security_id is None and inst["asset_class"] == "COMMODITY":
            sec_id, expiry, tsym = st.session_state.mcx_resolved.get(sym, (None, None, None))
            if sec_id is None:
                sec_id, expiry, tsym = resolve_mcx_underlying(sym)
                st.session_state.mcx_resolved[sym] = (sec_id, expiry, tsym)
            security_id = sec_id
        if security_id is not None:
            reading = fetch_atm_combined_premium(dhan_client, security_id, segment, inst["strike_step"])
            if reading is not None:
                reading["source"] = "LIVE"
                return reading
    reading = step_sim(st.session_state.sim_state[sym])
    reading["source"] = "SIM"
    return reading

reading = get_reading(symbol, inst)
hist = st.session_state.history[symbol]
baseline = hist[0]["combined_premium"] if hist else reading["combined_premium"]
pct_chg = ((reading["combined_premium"] - baseline) / baseline) * 100 if baseline else 0.0
is_spike = abs(pct_chg) >= threshold

record = {**reading, "time": datetime.now().strftime("%H:%M:%S"), "pct_chg": pct_chg, "is_spike": is_spike}
hist.append(record)
if len(hist) > MAX_HISTORY_POINTS: hist.pop(0)

if is_spike:
    already_recent = any(a["symbol"] == symbol and (datetime.now() - a["ts"]).seconds < 25 for a in st.session_state.alerts)
    if not already_recent:
        st.session_state.alerts.insert(0, {"symbol": symbol, "ts": datetime.now(), "time": record["time"], "pct": pct_chg, "premium": reading["combined_premium"], "spot": reading["spot"]})
        st.session_state.alerts = st.session_state.alerts[:50]

# ==========================================================================
# ROW 4: CHART (Left) & ALERTS (Right)
# ==========================================================================
chart_col, alert_col = st.columns([3, 1])

with chart_col:
    st.markdown('<div class="chart-container">', unsafe_allow_html=True)
    st.markdown(f"##### {universe[symbol]['label']} — Spot vs Combined Premium (ATM)", unsafe_allow_html=True)
    
    df = pd.DataFrame(hist)
    fig = go.Figure()
    
    # Combined Premium Line
    fig.add_trace(go.Scatter(x=df["time"], y=df["combined_premium"], name="Combined Premium", line=dict(color="#fbbf24", width=2.5), fill="tozeroy", fillcolor="rgba(251,191,36,0.05)", yaxis="y1"))
    # Spot Line
    fig.add_trace(go.Scatter(x=df["time"], y=df["spot"], name="Spot Price", line=dict(color="#06b6d4", width=1.5), yaxis="y2"))
    
    # Highlight ≥5% Spike Zones
    for i in range(len(df)):
        if df.iloc[i]['pct_chg'] >= threshold:
            fig.add_vrect(x0=i-0.5, x1=i+0.5, fillcolor="rgba(239, 68, 68, 0.15)", line_width=0, layer="below")
            
    fig.update_layout(
        height=380, margin=dict(l=10, r=10, t=30, b=10), paper_bgcolor="#111827", plot_bgcolor="#111827",
        font=dict(color="#e2e8f0", family="monospace", size=11),
        legend=dict(orientation="h", y=1.12, font=dict(size=10)),
        xaxis=dict(showgrid=True, gridcolor="#1e293b", nticks=8),
        yaxis=dict(title="Premium (\u20b9)", showgrid=True, gridcolor="#1e293b", color="#fbbf24"),
        yaxis2=dict(title="Spot", overlaying="y", side="right", showgrid=False, color="#06b6d4"),
        annotations=[dict(x=0.5, y=0.1, xref="paper", yref="paper", text="≥5% Spike Zones", showarrow=False, font=dict(color="#ef4444", size=12, family="monospace"))]
    )
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
    st.markdown('</div>', unsafe_allow_html=True)

with alert_col:
    st.markdown('<div class="alert-panel">', unsafe_allow_html=True)
    st.markdown("##### \u26a1 SPIKE ALERTS (≥5%)", unsafe_allow_html=True)
    if not st.session_state.alerts:
        st.caption("Waiting for spikes...")
    else:
        for a in st.session_state.alerts[:15]:
            direction = "\u25b2" if a["pct"] >= 0 else "\u25bc"
            cls = "alert-pct-up" if a["pct"] >= 0 else "alert-pct-down"
            st.markdown(f"""
            <div class="alert-item">
                <span class="alert-time">{a["time"]}</span> — <span class="alert-sym">{a["symbol"]}</span><br>
                <span class="{cls}">{direction} {a["pct"]:+.2f}%</span> \u2192 \u20b9{a["premium"]:.2f} <span style="color:var(--dim)">(Spot: {a["spot"]:,.1f})</span>
            </div>""", unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)

# ==========================================================================
# ROW 5: F&O WATCHLIST GRID (Interactive Click-to-Chart)
# ==========================================================================
st.markdown("##### F&O WATCHLIST - COMBINED PREMIUM MONITOR", unsafe_allow_html=True)

# Build Table Header
header_html = """<table class="wl-table"><thead><tr>
    <th>Symbol</th><th>Expiry</th><th>Spot</th><th>ATM</th><th>Comb.Prem</th><th>% Chg</th><th>CE</th><th>PE</th><th>IV</th><th>Status</th>
</tr></thead><tbody>"""

# Build Table Rows
rows_html = ""
for s, meta in universe.items():
    h = st.session_state.history.get(s, [])
    last = record if s == symbol else (h[-1] if h else None)
    if not last: continue
    
    is_active = (s == st.session_state.selected_symbol)
    row_cls = "wl-row active" if is_active else "wl-row"
    pct_val = last.get("pct_chg", 0.0)
    pct_cls = "val-up" if pct_val >= 0 else "val-down"
    status_html = '<span class="status-spike">SPIKE</span>' if last.get("is_spike") else '<span class="status-normal">Normal</span>'
    
    # Create a hidden button to handle click-to-chart interaction
    btn_key = f"btn_{s}"
    if st.button("", key=btn_key, use_container_width=True):
        st.session_state.selected_symbol = s
        st.rerun()

    rows_html += f"""
    <tr class="{row_cls}" onclick="document.getElementById('{btn_key}').click()">
        <td>{meta["label"]}</td>
        <td>{last.get('expiry', '26 AUG')}</td>
        <td>{last['spot']:,.2f}</td>
        <td>{last['atm_strike']:,.0f}</td>
        <td>\u20b9{last['combined_premium']:.2f}</td>
        <td class="{pct_cls}">{pct_val:+.2f}%</td>
        <td>{last['ce_ltp']:.2f}</td>
        <td>{last['pe_ltp']:.2f}</td>
        <td>{last.get('atm_iv', '-')}%</td>
        <td>{status_html}</td>
    </tr>"""

st.markdown(header_html + rows_html + "</tbody></table>", unsafe_allow_html=True)

# ==========================================================================
# ROW 6 & 7: INFO BAR & FOOTER
# ==========================================================================
st.markdown("""
<div class="info-bar">
    <b>How to read:</b> Combined Prem = ATM Call LTP + ATM Put LTP. A ≥5% spike without a proportional spot move signals institutional positioning / IV expansion. 
    Rising premium + flat spot \u2192 volatility expansion (buyers). Falling premium + flat spot \u2192 theta/IV crush (sellers).
</div>
<div class="footer-ticker">
    <span>NIFTY 50: <b style="color:var(--up)">22,468.30 \u25b212.70</b></span>
    <span>SENSEX: <b style="color:var(--down)">75,192.10 \u25bc18.40</b></span>
    <span>BANKNIFTY: <b style="color:var(--up)">45,211.50 \u25b289.60</b></span>
    <span>MCX GOLD: <b style="color:var(--up)">\u20b97,219 \u25b25.40</b></span>
    <span style="margin-left:auto; color:var(--dim);">Mini Bloomberg Terminal \u2022 Data Simulated for Demo</span>
</div>
""", unsafe_allow_html=True)

# ==========================================================================
# AUTO-REFRESH
# ==========================================================================
if refresh_secs > 0:
    time.sleep(refresh_secs)
    st.rerun()
