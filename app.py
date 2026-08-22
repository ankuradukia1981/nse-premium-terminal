import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, timedelta
import time
import random
import yfinance as yf
import os

# ==========================================
# 1. DHAN API & SECRETS CONFIGURATION
# ==========================================
try:
    from dhanhq import dhanhq
    DHAN_LIB_AVAILABLE = True
except ImportError:
    DHAN_LIB_AVAILABLE = False

# Securely load credentials from Streamlit Secrets
DHAN_CLIENT_ID = st.secrets.get("DHAN_CLIENT_ID", "")
DHAN_ACCESS_TOKEN = st.secrets.get("DHAN_ACCESS_TOKEN", "")

# ==========================================
# 2. PROFESSIONAL BLOOMBERG-STYLE CSS
# ==========================================
st.set_page_config(page_title="NSE Volatility Terminal", layout="wide", page_icon="")

st.markdown("""
<style>
    .main { background-color: #0a0e17; color: #e2e8f0; font-family: 'Segoe UI', system-ui, sans-serif; }
    .stApp { background-color: #0a0e17; }
    
    /* Metric Cards */
    .metric-card { 
        background-color: #111827; padding: 16px; border-radius: 6px; 
        border: 1px solid #1e293b; text-align: center; margin-bottom: 10px;
    }
    .metric-label { font-size: 10px; color: #94a3b8; text-transform: uppercase; letter-spacing: 1.5px; margin-bottom: 6px; }
    .metric-value { font-size: 24px; font-weight: 700; font-variant-numeric: tabular-nums; }
    
    /* Spike Animations & Colors */
    .spike-text { color: #f59e0b; animation: pulse 1.2s infinite; }
    .up { color: #22c55e; } .down { color: #ef4444; }
    
    /* Alert Boxes */
    .alert-box { 
        background-color: rgba(245, 158, 11, 0.08); border-left: 3px solid #f59e0b; 
        padding: 10px; margin-bottom: 8px; border-radius: 4px; font-size: 12px; 
    }
    .live-badge { 
        background: rgba(34,197,94,0.15); color: #22c55e; border: 1px solid rgba(34,197,94,0.3);
        padding: 4px 12px; border-radius: 4px; font-size: 11px; font-weight: bold; letter-spacing: 1px;
    }
    .sim-badge { 
        background: rgba(245,158,11,0.15); color: #f59e0b; border: 1px solid rgba(245,158,11,0.3);
        padding: 4px 12px; border-radius: 4px; font-size: 11px; font-weight: bold; letter-spacing: 1px;
    }
    
    /* Table Styling */
    th { background-color: #0f172a !important; color: #94a3b8 !important; font-size: 11px !important; text-transform: uppercase; }
    
    @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.4; } }
</style>
""", unsafe_allow_html=True)

# ==========================================
# 3. UNIVERSE DEFINITION (INDEXES & COMMODITIES)
# ==========================================
UNIVERSE = {
    'NIFTY':      {'yf': '^NSEI',     'step': 50,  'base_prem': 180, 'dhan_id': '1333'},
    'BANKNIFTY':  {'yf': '^NSEBANK',  'step': 100, 'base_prem': 410, 'dhan_id': '1334'},
    'FINNIFTY':   {'yf': 'FINNIFTY.NS','step': 50,  'base_prem': 160, 'dhan_id': '1335'},
    'MIDCPNIFTY': {'yf': 'NIFTYMIDCAP.NS','step': 50, 'base_prem': 120, 'dhan_id': '1336'},
    'GOLD':       {'yf': 'GC=F',      'step': 100, 'base_prem': 850, 'dhan_id': '1337'},
    'SILVER':     {'yf': 'SI=F',      'step': 500, 'base_prem': 1200, 'dhan_id': '1338'},
    'CRUDEOIL':   {'yf': 'CL=F',      'step': 10,  'base_prem': 95,  'dhan_id': '1339'},
}

# Initialize Session State
for key, default_val in [
    ('history', {sym: [] for sym in UNIVERSE}),
    ('alerts', []),
    ('open_prem', {sym: data['base_prem'] * (0.95 + random.random() * 0.1) for sym, data in UNIVERSE.items()}),
    ('spots', {sym: data['base_prem'] * 100 for sym, data in UNIVERSE.items()})
]:
    if key not in st.session_state:
        st.session_state[key] = default_val

# ==========================================
# 4. DATA ENGINE (DHAN LIVE + SMART FALLBACK)
# ==========================================
def get_next_expiry():
    today = datetime.now()
    days_ahead = 3 - today.weekday()
    if days_ahead < 0: days_ahead += 7
    return (today + timedelta(days=days_ahead)).strftime('%Y-%m-%d')

def fetch_atm_premiums_dhan(sym, spot):
    """Fetches exact ATM CE/PE LTPs via Dhan Option Chain"""
    try:
        cfg = UNIVERSE[sym]
        atm_strike = round(spot / cfg['step']) * cfg['step']
        
        oc = dhan_client.get_option_chain(
            security_id=cfg['dhan_id'], exchange_segment='NSE_FO', 
            product_type='OPTION', expiry_date=get_next_expiry()
        )
        if oc.get('status') != 'success': return None, None, atm_strike
        
        ce_ltp, pe_ltp = None, None
        min_diff = float('inf')
        
        for opt in oc.get('response', []):
            strike = float(opt.get('strikePrice', 0))
            diff = abs(strike - atm_strike)
            
            if diff <= min_diff:
                min_diff = diff
                if opt.get('optionType') == 'CE': ce_ltp = float(opt.get('lastPrice', 0))
                elif opt.get('optionType') == 'PE': pe_ltp = float(opt.get('lastPrice', 0))
                
        return ce_ltp, pe_ltp, atm_strike
    except: return None, None, None

def smart_premium_engine(sym, spot):
    """Realistic fallback engine simulating Theta decay + IV expansion"""
    cfg = UNIVERSE[sym]
    hist = st.session_state.history[sym]
    open_p = st.session_state.open_prem[sym]
    
    if not hist: return open_p
    
    last = hist[-1]
    change = random.gauss(0, cfg['base_prem'] * 0.005) - (cfg['base_prem'] * 0.0003)
    
    # Simulate occasional volatility events (3% probability per tick)
    if random.random() < 0.03:
        change += last['prem'] * random.uniform(0.04, 0.08) * random.choice([-1, 1])
        
    return max(cfg['base_prem'] * 0.3, last['prem'] + change)

def get_market_data(sym):
    """Primary data fetcher: Dhan Live > YFinance Fallback"""
    cfg = UNIVERSE[sym]
    open_p = st.session_state.open_prem[sym]
    
    # Attempt Dhan Live Data
    if IS_LIVE_MODE and dhan_client:
        try:
            sq = dhan_client.get_quotes(security_id=cfg['dhan_id'], exchange_segment='NSE_EQ')
            spot = float(sq['response']['lastPrice']) if sq.get('status')=='success' else st.session_state.spots[sym]
            
            ce, pe, strike = fetch_atm_premiums_dhan(sym, spot)
            if ce is not None and pe is not None:
                prem = ce + pe
            else:
                prem = smart_premium_engine(sym, spot)
                ce, pe, strike = prem*0.5, prem*0.5, round(spot/cfg['step'])*cfg['step']
        except:
            # Fallback to yfinance
            ticker = yf.Ticker(cfg['yf'])
            hist = ticker.history(period='1d')
            spot = float(hist['Close'].iloc[-1]) if not hist.empty else st.session_state.spots[sym]
            prem = smart_premium_engine(sym, spot)
            ce, pe, strike = prem*0.5, prem*0.5, round(spot/cfg['step'])*cfg['step']
    else:
        # Pure Simulation Mode
        ticker = yf.Ticker(cfg['yf'])
        hist = ticker.history(period='1d')
        spot = float(hist['Close'].iloc[-1]) if not hist.empty else st.session_state.spots[sym]
        prem = smart_premium_engine(sym, spot)
        ce, pe, strike = prem*0.5, prem*0.5, round(spot/cfg['step'])*cfg['step']

    st.session_state.spots[sym] = spot
    pct_chg = ((prem - open_p) / open_p) * 100 if open_p > 0 else 0
    
    tick = {
        'time': datetime.now().strftime("%H:%M:%S"), 'spot': round(spot, 2),
        'prem': round(prem, 2), 'ce': round(ce, 2), 'pe': round(pe, 2),
        'pct_chg': round(pct_chg, 2), 'strike': int(strike)
    }
    
    st.session_state.history[sym].append(tick)
    if len(st.session_state.history[sym]) > 60: st.session_state.history[sym].pop(0)
    
    # Spike Detection Logic
    threshold = st.session_state.get('threshold', 5.0)
    if abs(pct_chg) >= threshold:
        recent = any(a['sym']==sym and (datetime.now().timestamp()-a['ts'])<30 for a in st.session_state.alerts)
        if not recent:
            st.session_state.alerts.insert(0, {
                'ts': datetime.now().timestamp(), 'time': tick['time'], 'sym': sym,
                'pct': pct_chg, 'prem': tick['prem'], 'spot': tick['spot']
            })
            if len(st.session_state.alerts) > 20: st.session_state.alerts.pop()
            
    return tick

# ==========================================
# 5. MAIN UI RENDERING
# ==========================================
st.title("📈 NSE Volatility & Premium Terminal")

# Status Banner
if IS_LIVE_MODE:
    st.markdown('<div class="live-badge">✅ LIVE MODE: DhanHQ API Connected</div>', unsafe_allow_html=True)
else:
    st.markdown('<div class="sim-badge">⚠️ SIMULATION MODE: Add Dhan Credentials in Streamlit Secrets</div>', unsafe_allow_html=True)

col1, col2, col3 = st.columns([1, 2, 1])

with col1:
    st.session_state.threshold = st.number_input("Spike Threshold (%)", min_value=1.0, max_value=20.0, value=5.0, step=0.5)
    selected_sym = st.selectbox("Focus Symbol", list(UNIVERSE.keys()))
    filter_spikes = st.checkbox("Show Only ≥ Threshold", value=False)

with col2:
    st.markdown("### Intraday Market Feed")
    run_feed = st.button("▶ Start Live Feed", type="primary", use_container_width=True)

with col3:
    st.markdown("### ⚡ Volatility Alerts")
    alert_box = st.container(height=320)

# ==========================================
# 6. REAL-TIME FEED LOOP
# ==========================================
if run_feed:
    placeholder = st.empty()
    
    for _ in range(100):  # Runs for ~3.5 minutes to prevent cloud timeouts
        ticks = {sym: get_market_data(sym) for sym in UNIVERSE}
        
        # Build Watchlist DataFrame
        rows = []
        for sym, t in ticks.items():
            if filter_spikes and abs(t['pct_chg']) < st.session_state.threshold: continue
            rows.append({'Symbol': sym, 'Spot': t['spot'], 'ATM Strike': t['strike'], 
                         'Comb. Prem': t['prem'], 'CE': t['ce'], 'PE': t['pe'], '% Chg': t['pct_chg']})
        
        df = pd.DataFrame(rows)
        if not df.empty:
            df = df.sort_values(by='% Chg', key=abs, ascending=False).reset_index(drop=True)
            def highlight(val):
                if isinstance(val, (int,float)):
                    if abs(val) >= st.session_state.threshold: return 'color:#f59e0b;font-weight:bold;'
                    return 'color:#22c55e;' if val>0 else 'color:#ef4444;'
                return ''
            styled_df = df.style.applymap(highlight, subset=['% Chg'])
        else:
            styled_df = pd.DataFrame(columns=['Symbol','Spot','ATM Strike','Comb. Prem','CE','PE','% Chg'])

        focus = ticks.get(selected_sym)
        
        with placeholder.container():
            m1, m2, m3, m4 = st.columns(4)
            if focus:
                m1.metric("Spot Price", f"{focus['spot']:,}", delta=f"{focus['pct_chg']}% Prem Δ")
                m2.metric("ATM Strike", focus['strike'])
                m3.metric("Combined Premium", f"₹{focus['prem']}", delta=f"₹{focus['ce']} CE / ₹{focus['pe']} PE")
                m4.metric("Active Alerts", len(st.session_state.alerts))
                
                # Dual-Axis Chart
                fig = go.Figure()
                h = st.session_state.history[selected_sym]
                times = [x['time'] for x in h]
                prems = [x['prem'] for x in h]
                spots = [x['spot'] for x in h]
                
                if prems and spots:
                    min_p, max_p = min(prems), max(prems)
                    min_s, max_s = min(spots), max(spots)
                    rng = max_p - min_p if max_p!=min_p else 1
                    scaled = [min_p + ((s-min_s)/(max_s-min_s+1))*rng for s in spots]
                    
                    fig.add_trace(go.Scatter(x=times, y=scaled, name='Spot (Scaled)', line=dict(color='#3b82f6', width=1.5)))
                    fig.add_trace(go.Scatter(x=times, y=prems, name='ATM Straddle Value', line=dict(color='#f59e0b', width=2.5), fill='tozeroy', fillcolor='rgba(245,158,11,0.1)'))
                    
                    fig.update_layout(title=f"{selected_sym} | Spot vs Combined Premium", template="plotly_dark",
                                      paper_bgcolor='#0a0e17', plot_bgcolor='#0a0e17', font=dict(color='#e2e8f0'),
                                      margin=dict(l=20,r=20,t=40,b=20), height=350,
                                      xaxis=dict(showgrid=True, gridcolor='#1e293b'), yaxis=dict(title="Premium (₹)", gridcolor='#1e293b'))
                    st.plotly_chart(fig, use_container_width=True)
            
            st.markdown("### F&O Watchlist")
            st.dataframe(styled_df, use_container_width=True, height=300)
            
            with alert_box:
                if not st.session_state.alerts:
                    st.markdown("<div style='color:#64748b;text-align:center;padding:20px;'>Monitoring market for ≥5% premium spikes...</div>", unsafe_allow_html=True)
                else:
                    for a in st.session_state.alerts:
                        dir_txt = "📈 SPIKE" if a['pct']>0 else "📉 CRUSH"
                        clr = "#22c55e" if a['pct']>0 else "#ef4444"
                        st.markdown(f"""<div class="alert-box">
                            <div style="color:#94a3b8;font-size:10px;">{a['time']} IST | {a['sym']}</div>
                            <div style="font-weight:bold;color:{clr};">{dir_txt} {abs(a['pct']):.1f}%</div>
                            <div>Prem: ₹{a['prem']} | Spot: {a['spot']}</div></div>""", unsafe_allow_html=True)
        time.sleep(2)
else:
    st.info("Click **▶ Start Live Feed** to initialize the market data stream.")
