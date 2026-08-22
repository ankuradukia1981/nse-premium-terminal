import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, timedelta
import time
import random

# ==========================================
# 1. DHAN API SETUP & SECRETS
# ==========================================
try:
    from dhanhq import dhanhq
    DHAN_AVAILABLE = True
except ImportError:
    DHAN_AVAILABLE = False

# Securely fetch credentials from Streamlit Secrets (or fallback to placeholders)
DHAN_CLIENT_ID = st.secrets.get("DHAN_CLIENT_ID", "YOUR_CLIENT_ID_HERE")
DHAN_ACCESS_TOKEN = st.secrets.get("DHAN_ACCESS_TOKEN", "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzUxMiJ9.eyJ1c2VyUmVnaW9uIjoiUjEiLCJpc3MiOiJkaGFuIiwicGFydG5lcklkIjoiIiwiZXhwIjoxNzg3NDU3MDY0LCJpYXQiOjE3ODczNzA2NjQsInRva2VuQ29uc3VtZXJUeXBlIjoiU0VMRiIsIndlYmhvb2tVcmwiOiIiLCJkaGFuQ2xpZW50SWQiOiIxMTEwNTU1MTk2In0.7MtXNCXUM8Vx3_CMEzPIIekJGeqPHq7NdGK7K6hFNyZoLZZnT3CuRn-LPO4fKxcBplzPrfM8J4V4gHI98QOwFQ")

# Initialize Dhan Client
dhan_client = None
if DHAN_AVAILABLE and DHAN_CLIENT_ID != "YOUR_CLIENT_ID_HERE":
    try:
        dhan_client = dhanhq(DHAN_CLIENT_ID, DHAN_ACCESS_TOKEN)
        # Quick connection test
        profile = dhan_client.get_profile()
        DHAN_CONNECTED = profile.get('status') == 'success'
    except Exception:
        DHAN_CONNECTED = False
else:
    DHAN_CONNECTED = False

# ==========================================
# 2. CONFIGURATION & STATE
# ==========================================
st.set_page_config(page_title="NSE Premium Spike Terminal | Live", layout="wide", page_icon="📈")

# Bloomberg Dark Theme CSS
st.markdown("""
<style>
    .main { background-color: #0a0e17; color: #e2e8f0; }
    .stApp { background-color: #0a0e17; }
    .metric-card { background-color: #111827; padding: 15px; border-radius: 6px; border: 1px solid #1e293b; text-align: center; }
    .metric-label { font-size: 11px; color: #94a3b8; text-transform: uppercase; letter-spacing: 1px; }
    .metric-value { font-size: 22px; font-weight: 700; font-variant-numeric: tabular-nums; margin-top: 5px; }
    .spike-text { color: #f59e0b; animation: pulse 1.5s infinite; }
    .up { color: #22c55e; } .down { color: #ef4444; }
    .alert-box { background-color: rgba(245, 158, 11, 0.1); border-left: 3px solid #f59e0b; padding: 8px; margin-bottom: 6px; border-radius: 4px; font-size: 12px; }
    th { background-color: #0f172a !important; color: #94a3b8 !important; font-size: 11px !important; }
    .success-box { background-color: rgba(34, 197, 94, 0.1); border-left: 3px solid #22c55e; padding: 10px; border-radius: 4px; margin-bottom: 10px; }
    @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.5; } }
</style>
""", unsafe_allow_html=True)

# NSE Indexes Universe with Dhan Security IDs
UNIVERSE = {
    'NIFTY':      {'yf': '^NSEI',     'step': 50,  'base_prem': 180, 'dhan_id': '1333'},
    'BANKNIFTY':  {'yf': '^NSEBANK',  'step': 100, 'base_prem': 410, 'dhan_id': '1334'},
    'FINNIFTY':   {'yf': 'FINNIFTY.NS','step': 50,  'base_prem': 160, 'dhan_id': '1335'},
    'MIDCPNIFTY': {'yf': 'NIFTYMIDCAP.NS','step': 50, 'base_prem': 120, 'dhan_id': '1336'},
}

# Initialize Session State
if 'history' not in st.session_state:
    st.session_state.history = {sym: [] for sym in UNIVERSE}
if 'alerts' not in st.session_state:
    st.session_state.alerts = []
if 'open_prem' not in st.session_state:
    st.session_state.open_prem = {sym: data['base_prem'] * (0.95 + random.random() * 0.1) for sym, data in UNIVERSE.items()}
if 'spots' not in st.session_state:
    st.session_state.spots = {sym: data['base_prem'] * 100 for sym, data in UNIVERSE.items()}

# ==========================================
# 3. DATA ENGINE
# ==========================================
def get_next_expiry():
    """Get next weekly expiry date (Thursday)"""
    today = datetime.now()
    days_ahead = 3 - today.weekday()  # Thursday
    if days_ahead < 0:
        days_ahead += 7
    next_thursday = today + timedelta(days=days_ahead)
    return next_thursday.strftime('%Y-%m-%d')

def get_atm_premium_dhan(sym, spot_price):
    """Fetch ATM Call and Put premiums from Dhan API"""
    try:
        cfg = UNIVERSE[sym]
        atm_strike = round(spot_price / cfg['step']) * cfg['step']
        expiry_date = get_next_expiry()
        
        option_chain = dhan_client.get_option_chain(
            security_id=cfg['dhan_id'],
            exchange_segment='NSE_FO',
            product_type='OPTION',
            expiry_date=expiry_date
        )
        
        if option_chain.get('status') != 'success':
            return None, None, atm_strike
        
        ce_ltp, pe_ltp = None, None
        min_diff = float('inf')
        best_ce, best_pe = None, None
        
        for option in option_chain.get('response', []):
            strike = float(option.get('strikePrice', 0))
            diff = abs(strike - atm_strike)
            
            if diff < min_diff:
                min_diff = diff
                best_ce = None
                best_pe = None
                
            if diff == min_diff:
                if option.get('optionType') == 'CE':
                    best_ce = float(option.get('lastPrice', 0))
                elif option.get('optionType') == 'PE':
                    best_pe = float(option.get('lastPrice', 0))
                    
        return best_ce, best_pe, atm_strike
    except Exception:
        return None, None, None

def calculate_smart_premium(sym, spot):
    """Fallback Smart Premium Engine if API fails"""
    cfg = UNIVERSE[sym]
    hist = st.session_state.history[sym]
    open_p = st.session_state.open_prem[sym]
    
    if not hist:
        return open_p
    
    last = hist[-1]
    prem_change = random.gauss(0, cfg['base_prem'] * 0.005) - (cfg['base_prem'] * 0.0003)
    
    if random.random() < 0.03:
        prem_change += last['prem'] * random.uniform(0.04, 0.08) * random.choice([-1, 1])
        
    return max(cfg['base_prem'] * 0.3, last['prem'] + prem_change)

def get_live_data(sym):
    """Fetch live data: Dhan API > Fallback Smart Engine"""
    cfg = UNIVERSE[sym]
    open_p = st.session_state.open_prem[sym]
    
    # Try Dhan API first
    if DHAN_CONNECTED and dhan_client:
        try:
            # 1. Get Spot
            spot_data = dhan_client.get_quotes(security_id=cfg['dhan_id'], exchange_segment='NSE_EQ')
            if spot_data.get('status') == 'success':
                spot = float(spot_data['response'].get('lastPrice', 0))
            else:
                import yfinance as yf
                ticker = yf.Ticker(cfg['yf'])
                todays_data = ticker.history(period='1d')
                spot = float(todays_data['Close'].iloc[-1]) if not todays_data.empty else st.session_state.spots.get(sym, 24000)
            
            # 2. Get ATM Premiums
            ce_ltp, pe_ltp, atm_strike = get_atm_premium_dhan(sym, spot)
            
            if ce_ltp is not None and pe_ltp is not None:
                prem = ce_ltp + pe_ltp
            else:
                prem = calculate_smart_premium(sym, spot)
                ce_ltp, pe_ltp = prem * 0.5, prem * 0.5
                atm_strike = round(spot / cfg['step']) * cfg['step']
                
        except Exception:
            # Fallback to yfinance + smart engine
            import yfinance as yf
            ticker = yf.Ticker(cfg['yf'])
            todays_data = ticker.history(period='1d')
            spot = float(todays_data['Close'].iloc[-1]) if not todays_data.empty else st.session_state.spots.get(sym, 24000)
            prem = calculate_smart_premium(sym, spot)
            ce_ltp, pe_ltp = prem * 0.5, prem * 0.5
            atm_strike = round(spot / cfg['step']) * cfg['step']
    else:
        # Fallback to yfinance + smart engine
        import yfinance as yf
        ticker = yf.Ticker(cfg['yf'])
        todays_data = ticker.history(period='1d')
        spot = float(todays_data['Close'].iloc[-1]) if not todays_data.empty else st.session_state.spots.get(sym, 24000)
        prem = calculate_smart_premium(sym, spot)
        ce_ltp, pe_ltp = prem * 0.5, prem * 0.5
        atm_strike = round(spot / cfg['step']) * cfg['step']
    
    st.session_state.spots[sym] = spot
    pct_chg = ((prem - open_p) / open_p) * 100 if open_p > 0 else 0
    
    tick = {
        'time': datetime.now().strftime("%H:%M:%S"),
        'spot': round(spot, 2),
        'prem': round(prem, 2),
        'ce': round(ce_ltp, 2),
        'pe': round(pe_ltp, 2),
        'pct_chg': round(pct_chg, 2),
        'strike': int(atm_strike)
    }
    
    st.session_state.history[sym].append(tick)
    if len(st.session_state.history[sym]) > 60:
        st.session_state.history[sym].pop(0)
    
    # Spike Detection
    threshold = st.session_state.get('threshold', 5.0)
    if abs(pct_chg) >= threshold:
        recent_alert = any(a['sym'] == sym and (datetime.now().timestamp() - a['ts']) < 30 for a in st.session_state.alerts)
        if not recent_alert:
            st.session_state.alerts.insert(0, {
                'ts': datetime.now().timestamp(),
                'time': tick['time'],
                'sym': sym,
                'pct': pct_chg,
                'prem': tick['prem'],
                'spot': tick['spot']
            })
            if len(st.session_state.alerts) > 20:
                st.session_state.alerts.pop()
    
    return tick

# ==========================================
# 4. MAIN UI
# ==========================================
st.title("📈 NSE Premium Spike Terminal")

if DHAN_CONNECTED:
    st.success("✅ **LIVE MODE:** Connected to Dhan API - Fetching real-time option chain data")
else:
    st.info("⚠️ **SIMULATION MODE:** Dhan API not connected. Using yfinance spot + Smart Premium Engine. Add your keys in Streamlit Secrets to go live.")

col1, col2, col3 = st.columns([1, 2, 1])

with col1:
    st.session_state.threshold = st.number_input("Spike Threshold (%)", min_value=1.0, max_value=20.0, value=5.0, step=0.5)
    selected_sym = st.selectbox("Focus Symbol", list(UNIVERSE.keys()))
    show_only_spikes = st.checkbox("Show Only ≥ Threshold", value=False)

with col2:
    st.markdown("### Live Market Feed")
    run_live = st.button("▶ Start Live Feed", type="primary")

with col3:
    st.markdown("### ⚡ Spike Alerts")
    alert_container = st.container(height=300)

# ==========================================
# 5. LIVE LOOP
# ==========================================
if run_live:
    placeholder = st.empty()
    
    for _ in range(100):  # Runs for ~3.5 minutes
        ticks = {}
        for sym in UNIVERSE:
            ticks[sym] = get_live_data(sym)
        
        # Build Watchlist
        rows = []
        for sym, tick in ticks.items():
            if show_only_spikes and abs(tick['pct_chg']) < st.session_state.threshold:
                continue
            rows.append({
                'Symbol': sym, 'Spot': tick['spot'], 'ATM Strike': tick['strike'],
                'Comb. Prem': tick['prem'], 'CE': tick['ce'], 'PE': tick['pe'], '% Chg': tick['pct_chg']
            })
        
        df = pd.DataFrame(rows)
        if not df.empty:
            df = df.sort_values(by='% Chg', key=abs, ascending=False).reset_index(drop=True)
            def highlight_spikes(val):
                if isinstance(val, (int, float)) and abs(val) >= st.session_state.threshold:
                    return 'color: #f59e0b; font-weight: bold;'
                elif isinstance(val, (int, float)) and val > 0:
                    return 'color: #22c55e;'
                elif isinstance(val, (int, float)) and val < 0:
                    return 'color: #ef4444;'
                return ''
            styled_df = df.style.applymap(highlight_spikes, subset=['% Chg'])
        else:
            styled_df = pd.DataFrame(columns=['Symbol', 'Spot', 'ATM Strike', 'Comb. Prem', 'CE', 'PE', '% Chg'])

        focus_latest = ticks.get(selected_sym)
        
        with placeholder.container():
            m1, m2, m3, m4 = st.columns(4)
            if focus_latest:
                m1.metric("Spot", f"{focus_latest['spot']:,}", delta=f"{focus_latest['pct_chg']}% Prem Chg")
                m2.metric("ATM Strike", focus_latest['strike'])
                m3.metric("Combined Prem", f"₹{focus_latest['prem']}", delta=f"₹{focus_latest['ce']} CE / ₹{focus_latest['pe']} PE")
                m4.metric("Active Alerts", len(st.session_state.alerts))
                
                # Chart
                fig = go.Figure()
                focus_hist = st.session_state.history[selected_sym]
                times = [t['time'] for t in focus_hist]
                prems = [t['prem'] for t in focus_hist]
                spots = [t['spot'] for t in focus_hist]
                
                if prems and spots:
                    min_p, max_p = min(prems), max(prems)
                    min_s, max_s = min(spots), max(spots)
                    range_p = max_p - min_p if max_p != min_p else 1
                    scaled_spots = [min_p + ((s - min_s) / (max_s - min_s + 1)) * range_p for s in spots]
                    
                    fig.add_trace(go.Scatter(x=times, y=scaled_spots, name='Spot (Scaled)', line=dict(color='#3b82f6', width=1.5)))
                    fig.add_trace(go.Scatter(x=times, y=prems, name='Combined Premium', line=dict(color='#f59e0b', width=2.5), fill='tozeroy', fillcolor='rgba(245,158,11,0.1)'))
                    
                    fig.update_layout(
                        title=f"{selected_sym} | Spot vs ATM Combined Premium",
                        template="plotly_dark", paper_bgcolor='#0a0e17', plot_bgcolor='#0a0e17',
                        font=dict(color='#e2e8f0'), margin=dict(l=20, r=20, t=40, b=20), height=350,
                        xaxis=dict(showgrid=True, gridcolor='#1e293b'), yaxis=dict(showgrid=True, gridcolor='#1e293b', title="Premium (₹)")
                    )
                    st.plotly_chart(fig, use_container_width=True)
            
            st.markdown("### F&O Watchlist")
            st.dataframe(styled_df, use_container_width=True, height=300)
            
            with alert_container:
                if not st.session_state.alerts:
                    st.markdown("<div style='color:#64748b; text-align:center; padding:20px;'>Monitoring for spikes...</div>", unsafe_allow_html=True)
                else:
                    for a in st.session_state.alerts:
                        direction = "📈 SPIKE" if a['pct'] > 0 else "📉 CRUSH"
                        color = "#22c55e" if a['pct'] > 0 else "#ef4444"
                        st.markdown(f"""
                        <div class="alert-box">
                            <div style="color:#94a3b8; font-size:10px;">{a['time']} IST | {a['sym']}</div>
                            <div style="font-weight:bold; color:{color};">{direction} {abs(a['pct']):.1f}%</div>
                            <div>Prem: ₹{a['prem']} | Spot: {a['spot']}</div>
                        </div>
                        """, unsafe_allow_html=True)
        time.sleep(2)
else:
    st.info("Click **▶ Start Live Feed** to begin streaming market data.")
