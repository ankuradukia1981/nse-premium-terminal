import streamlit as st
import pandas as pd
import numpy as np
import time
from datetime import datetime, timedelta
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import os
from dotenv import load_dotenv
import warnings
warnings.filterwarnings('ignore')

# Load environment variables
load_dotenv()

# Page config
st.set_page_config(
    page_title="NSE/MCX Premium Terminal",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for terminal theme
st.markdown("""
<style>
    /* Terminal dark theme */
    .stApp {
        background-color: #0a0e27;
        color: #00ff9d;
    }
    
    /* Header styling */
    .main-header {
        background: linear-gradient(90deg, #0a0e27 0%, #1a1f3a 100%);
        padding: 1rem;
        border-bottom: 2px solid #00ff9d;
        margin-bottom: 1rem;
        font-family: 'Courier New', monospace;
    }
    
    .main-header h1 {
        color: #00ff9d;
        font-size: 1.8rem;
        margin: 0;
        text-shadow: 0 0 10px #00ff9d;
    }
    
    .badge {
        display: inline-block;
        background: #00ff9d;
        color: #0a0e27;
        padding: 0.2rem 0.6rem;
        border-radius: 3px;
        font-size: 0.75rem;
        font-weight: bold;
        margin-left: 0.5rem;
    }
    
    /* Stats cards */
    .stat-card {
        background: #1a1f3a;
        border: 1px solid #00ff9d;
        border-radius: 5px;
        padding: 1rem;
        text-align: center;
        font-family: 'Courier New', monospace;
    }
    
    .stat-value {
        font-size: 1.5rem;
        color: #00ff9d;
        font-weight: bold;
    }
    
    .stat-label {
        font-size: 0.8rem;
        color: #888;
        margin-top: 0.3rem;
    }
    
    /* Table styling */
    .dataframe {
        background: #0a0e27 !important;
        color: #00ff9d !important;
        font-family: 'Courier New', monospace !important;
        border: 1px solid #00ff9d !important;
    }
    
    .dataframe th {
        background: #1a1f3a !important;
        color: #00ff9d !important;
        border: 1px solid #00ff9d !important;
        padding: 0.5rem !important;
    }
    
    .dataframe td {
        background: #0a0e27 !important;
        color: #00ff9d !important;
        border: 1px solid #333 !important;
        padding: 0.5rem !important;
    }
    
    /* Spike row highlight */
    .spike-row {
        border-left: 4px solid #00ffff !important;
        background: rgba(0, 255, 255, 0.05) !important;
    }
    
    /* Buttons */
    .stButton > button {
        background: #1a1f3a;
        color: #00ff9d;
        border: 1px solid #00ff9d;
        font-family: 'Courier New', monospace;
        transition: all 0.3s;
    }
    
    .stButton > button:hover {
        background: #00ff9d;
        color: #0a0e27;
        box-shadow: 0 0 10px #00ff9d;
    }
    
    /* Selectbox and inputs */
    .stSelectbox, .stNumberInput, .stCheckbox {
        font-family: 'Courier New', monospace !important;
    }
    
    /* Chart container */
    .chart-container {
        background: #1a1f3a;
        border: 1px solid #00ff9d;
        border-radius: 5px;
        padding: 1rem;
        margin-top: 1rem;
    }
    
    /* Empty state */
    .empty-state {
        text-align: center;
        padding: 3rem;
        color: #888;
        font-family: 'Courier New', monospace;
    }
    
    /* Status indicators */
    .status-active {
        color: #00ff9d;
    }
    
    .status-warning {
        color: #ffaa00;
    }
    
    .status-critical {
        color: #ff0055;
    }
</style>
""", unsafe_allow_html=True)

# Initialize session state
if 'data' not in st.session_state:
    st.session_state.data = pd.DataFrame()
if 'spike_count' not in st.session_state:
    st.session_state.spike_count = 0
if 'show_chart' not in st.session_state:
    st.session_state.show_chart = False
if 'selected_symbol' not in st.session_state:
    st.session_state.selected_symbol = None
if 'last_update' not in st.session_state:
    st.session_state.last_update = datetime.now()

# Header
st.markdown("""
<div class="main-header">
    <h1>⚡ NSE/MCX PREMIUM TERMINAL <span class="badge">v3.1</span></h1>
    <div style="font-size: 0.9rem; color: #888; margin-top: 0.5rem;">
        ATM Combined Premium Spike Monitor | 
        <span id="clock">--:--:-- IST</span>
    </div>
</div>
""", unsafe_allow_html=True)

# Sidebar controls
with st.sidebar:
    st.markdown("### ⚙️ Controls")
    
    timeframe = st.selectbox(
        "Timeframe",
        ["1 min", "5 min", "15 min", "30 min"],
        index=1
    )
    
    spike_threshold = st.number_input(
        "Spike Threshold (%)",
        min_value=1.0,
        max_value=20.0,
        value=5.0,
        step=0.5
    )
    
    show_only_spikes = st.checkbox("Show only ≥ threshold", value=False)
    
    col1, col2 = st.columns(2)
    with col1:
        pause_btn = st.button("⏸ Pause", use_container_width=True)
    with col2:
        reset_btn = st.button("↻ Reset", use_container_width=True)
    
    st.markdown("---")
    st.markdown("### 📊 Session Stats")
    
    # Stats will be updated below
    stats_container = st.container()

# Main content area
main_col1, main_col2 = st.columns([3, 1])

with main_col1:
    st.markdown("### 📡 F & O Watchlist — Combined Premium Monitor")
    
    # Simulated data for demo (replace with DhanHQ API calls)
    symbols = [
        "NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY",
        "RELIANCE", "TCS", "HDFCBANK", "INFY"
    ]
    
    # Generate or update data
    if st.session_state.data.empty or not pause_btn:
        data_list = []
        for symbol in symbols:
            # Simulate market data
            spot = np.random.uniform(1000, 25000) if "NIFTY" in symbol else np.random.uniform(1000, 5000)
            atm_strike = round(spot / 50) * 50 if "NIFTY" in symbol else round(spot / 10) * 10
            
            # Calculate premiums (simulated)
            ce_premium = np.random.uniform(50, 500)
            pe_premium = np.random.uniform(50, 500)
            combined_premium = ce_premium + pe_premium
            
            # Calculate % change (simulated)
            pct_change = np.random.uniform(-10, 15)
            
            # IV simulation
            atm_iv = np.random.uniform(10, 35)
            
            # Status based on spike
            if abs(pct_change) >= spike_threshold:
                status = "⚡ SPIKE"
                status_class = "status-critical"
            elif abs(pct_change) >= spike_threshold * 0.7:
                status = "⚠ WATCH"
                status_class = "status-warning"
            else:
                status = "✓ ACTIVE"
                status_class = "status-active"
            
            # Expiry (next Thursday)
            today = datetime.now()
            days_until_thursday = (3 - today.weekday()) % 7
            if days_until_thursday == 0:
                days_until_thursday = 7
            expiry = today + timedelta(days=days_until_thursday)
            
            data_list.append({
                "Symbol": symbol,
                "Expiry": expiry.strftime("%d %b"),
                "Spot": f"{spot:.2f}",
                "ATM": atm_strike,
                "Comb.Prem": f"{combined_premium:.2f}",
                "% Chg": f"{pct_change:+.2f}%",
                "CE": f"{ce_premium:.2f}",
                "PE": f"{pe_premium:.2f}",
                "ATM IV": f"{atm_iv:.1f}%",
                "Status": status,
                "Chart": "📈"
            })
        
        st.session_state.data = pd.DataFrame(data_list)
        st.session_state.last_update = datetime.now()
        
        # Count spikes
        spike_count = sum(1 for status in st.session_state.data["Status"] if "SPIKE" in status)
        st.session_state.spike_count = spike_count

# Display data
df = st.session_state.data.copy()

# Apply filter
if show_only_spikes:
    df = df[df["Status"].str.contains("SPIKE|WATCH", na=False)]

if df.empty:
    st.markdown("""
    <div class="empty-state">
        <h3>⚡ Spike Alerts</h3>
        <p>0 today</p>
        <p style="color: #666;">Waiting for spikes...</p>
    </div>
    """, unsafe_allow_html=True)
else:
    # Display table with custom formatting
    st.dataframe(
        df,
        use_container_width=True,
        hide_index=True,
        height=400
    )
    
    # Add view chart buttons
    st.markdown("##### Quick Actions")
    cols = st.columns(len(df))
    for idx, (col, row) in enumerate(zip(cols, df.itertuples())):
        with col:
            if st.button(f"📈 {row.Symbol}", key=f"chart_{idx}"):
                st.session_state.show_chart = True
                st.session_state.selected_symbol = row.Symbol
                st.rerun()

with main_col2:
    st.markdown("### ⚡ Spike Alerts")
    
    # Spike alerts panel
    st.markdown(f"""
    <div class="stat-card">
        <div class="stat-value">{st.session_state.spike_count}</div>
        <div class="stat-label">today</div>
    </div>
    """, unsafe_allow_html=True)
    
    if st.session_state.spike_count == 0:
        st.markdown("""
        <div style="text-align: center; color: #888; padding: 1rem; font-family: 'Courier New', monospace;">
            Waiting for spikes...
        </div>
        """, unsafe_allow_html=True)
    else:
        spike_symbols = df[df["Status"].str.contains("SPIKE", na=False)]["Symbol"].tolist()
        for symbol in spike_symbols[:5]:
            st.markdown(f"⚡ **{symbol}**")
    
    st.markdown("---")
    st.markdown("### 📈 Session Stats")
    
    # Calculate stats
    if not df.empty:
        premiums = df["Comb.Prem"].str.replace(',', '').astype(float)
        max_prem = premiums.max()
        min_prem = premiums.min()
        avg_prem = premiums.mean()
        vol_events = st.session_state.spike_count
    else:
        max_prem = min_prem = avg_prem = 0
        vol_events = 0
    
    st.markdown(f"""
    <div style="font-family: 'Courier New', monospace; font-size: 0.9rem;">
        <div style="margin: 0.5rem 0;">
            <span style="color: #888;">Max Prem:</span> 
            <span style="color: #00ff9d; float: right;">{max_prem:.2f}</span>
        </div>
        <div style="margin: 0.5rem 0;">
            <span style="color: #888;">Min Prem:</span> 
            <span style="color: #00ff9d; float: right;">{min_prem:.2f}</span>
        </div>
        <div style="margin: 0.5rem 0;">
            <span style="color: #888;">Avg Prem:</span> 
            <span style="color: #00ff9d; float: right;">{avg_prem:.2f}</span>
        </div>
        <div style="margin: 0.5rem 0;">
            <span style="color: #888;">Vol Events:</span> 
            <span style="color: #00ff9d; float: right;">{vol_events}</span>
        </div>
    </div>
    """, unsafe_allow_html=True)

# Chart view (full page)
if st.session_state.show_chart and st.session_state.selected_symbol:
    st.markdown("---")
    st.markdown(f"### 📊 {st.session_state.selected_symbol} — Spot vs Combined Premium & Volume")
    
    # Back button
    if st.button("← Back to Dashboard (Esc)"):
        st.session_state.show_chart = False
        st.session_state.selected_symbol = None
        st.rerun()
    
    # Generate chart data
    time_points = 50
    timestamps = [datetime.now() - timedelta(minutes=time_points-i) for i in range(time_points)]
    
    # Simulate price data
    base_price = float(df[df["Symbol"] == st.session_state.selected_symbol]["Spot"].values[0].replace(',', ''))
    spot_prices = [base_price + np.random.uniform(-50, 50) for _ in range(time_points)]
    
    # Simulate combined premium
    base_premium = float(df[df["Symbol"] == st.session_state.selected_symbol]["Comb.Prem"].values[0].replace(',', ''))
    combined_premiums = [base_premium + np.random.uniform(-100, 100) for _ in range(time_points)]
    
    # Simulate volume
    volumes = [np.random.randint(1000, 10000) for _ in range(time_points)]
    
    # Create subplots
    fig = make_subplots(
        rows=3, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.03,
        subplot_titles=("Spot Price", "Combined Premium", "Volume"),
        row_heights=[0.4, 0.4, 0.2]
    )
    
    # Add traces
    fig.add_trace(
        go.Scatter(x=timestamps, y=spot_prices, name="Spot", line=dict(color="#00ff9d", width=2)),
        row=1, col=1
    )
    
    fig.add_trace(
        go.Scatter(x=timestamps, y=combined_premiums, name="Combined Premium", line=dict(color="#00ffff", width=2)),
        row=2, col=1
    )
    
    fig.add_trace(
        go.Bar(x=timestamps, y=volumes, name="Volume", marker_color="#ffaa00"),
        row=3, col=1
    )
    
    # Update layout
    fig.update_layout(
        height=800,
        plot_bgcolor="#0a0e27",
        paper_bgcolor="#1a1f3a",
        font=dict(color="#00ff9d", family="Courier New"),
        showlegend=True,
        legend=dict(bgcolor="rgba(0,0,0,0)"),
        xaxis=dict(gridcolor="#333"),
        yaxis=dict(gridcolor="#333"),
        xaxis2=dict(gridcolor="#333"),
        yaxis2=dict(gridcolor="#333"),
        xaxis3=dict(gridcolor="#333"),
        yaxis3=dict(gridcolor="#333")
    )
    
    st.plotly_chart(fig, use_container_width=True)

# Footer
st.markdown("---")
st.markdown("""
<div style="text-align: center; color: #666; font-family: 'Courier New', monospace; font-size: 0.8rem; padding: 1rem;">
    Combined Prem = ATM Call LTP + ATM Put LTP · ≥5% spike w/o big spot move = IV expansion<br>
    Data simulated for demo | NSE/MCX Premium Terminal v3.1 · Spike Monitor
</div>
""", unsafe_allow_html=True)

# Auto-refresh every 5 seconds
if not pause_btn:
    time.sleep(5)
    st.rerun()