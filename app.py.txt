import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go

# --- PAGE CONFIG ---
st.set_page_config(page_title="Quant Swing Terminal", layout="wide", page_icon="📈")

# --- TITLE ---
st.markdown("<h1 style='text-align: center; color: #1E90FF;'>📈 Top 1% Quant Swing Terminal</h1>", unsafe_allow_html=True)
st.markdown("<p style='text-align: center; color: gray;'>Institutional-Grade Confluence Screener | Upload your weekly data to begin.</p>", unsafe_allow_html=True)

# --- SIDEBAR: DATA UPLOAD & 1% FILTERS ---
st.sidebar.header("📂 Data Input")
uploaded_file = st.sidebar.file_uploader("Upload Improved Excel File", type=['xlsx'])

if uploaded_file is not None:
    df = pd.read_excel(uploaded_file)
    
    # Clean data just in case
    df = df.replace(['ERROR:#N/A', 'ERROR: #N/A', '#N/A', 'N/A', 'inf', '-inf'], np.nan)
    
    st.sidebar.markdown("---")
    st.sidebar.header("🎯 1% Trader Filters")
    
    # 1. Liquidity Filter
    min_mcap = st.sidebar.slider("Min Market Cap (₹ Cr) [Institutional Liquidity]", 0, 100000, 2000, step=500)
    
    # 2. Fundamental Filter (Operating Leverage)
    require_leverage = st.sidebar.checkbox("Require Operating Leverage (NP Growth > Rev Growth)", value=True)
    min_margin = st.sidebar.slider("Min Net Margin (%)", 0, 50, 5)
    
    # 3. Technical Pullback Filter
    min_1m_ret = st.sidebar.slider("Min 1-Month Return (%) [Uptrend]", 0, 100, 15)
    max_1w_ret = st.sidebar.slider("Max 1-Week Return (%) [Resting/Pullback]", -10, 10, 3)
    max_1d_ret = st.sidebar.slider("Max 1-Day Return (%) [Buy the Dip]", -10, 10, 0)
    
    # 4. Data Quality
    hide_missing = st.sidebar.checkbox("Hide Stocks with Missing Data", value=True)

    # --- APPLY FILTERS ---
    filtered_df = df.copy()
    
    if hide_missing:
        filtered_df = filtered_df[filtered_df['Data_Quality'] == '✅ Clean']
        
    filtered_df = filtered_df[filtered_df['MarCap_Cr'] >= min_mcap]
    
    if require_leverage:
        filtered_df = filtered_df[filtered_df['YoY_NP_Growth_Pct'] > filtered_df['YoY_Rev_Growth_Pct']]
        filtered_df = filtered_df[filtered_df['NetMargin_Jun26_Pct'] >= min_margin]
        
    filtered_df = filtered_df[
        (filtered_df['Ret_1M'] >= min_1m_ret) & 
        (filtered_df['Ret_1W'] <= max_1w_ret) & 
        (filtered_df['Ret_1D'] <= max_1d_ret)
    ]
    
    # Sort by strongest fundamental catalyst
    filtered_df = filtered_df.sort_values(by='YoY_NP_Growth_Pct', ascending=False)

    # --- MAIN DASHBOARD LAYOUT ---
    
    # Metric Cards
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("🎯 Setups Found", len(filtered_df))
    col2.metric("💰 Avg Market Cap (₹ Cr)", f"{filtered_df['MarCap_Cr'].mean():,.0f}" if not filtered_df.empty else "0")
    col3.metric("🚀 Avg YoY NP Growth", f"{filtered_df['YoY_NP_Growth_Pct'].mean():.1f}%" if not filtered_df.empty else "0%")
    col4.metric("📊 Avg 1M Return", f"{filtered_df['Ret_1M'].mean():.1f}%" if not filtered_df.empty else "0%")
    
    st.markdown("---")
    
    # Charts Row
    col_left, col_right = st.columns(2)
    
    with col_left:
        st.subheader("🎯 The 'Sweet Spot' (Momentum vs. Fundamentals)")
        if not filtered_df.empty:
            fig_scatter = px.scatter(
                filtered_df, 
                x='Ret_1M', 
                y='YoY_NP_Growth_Pct', 
                size='MarCap_Cr', 
                color='Industry',
                hover_name='Symbol',
                title="1M Return vs. YoY Profit Growth (Bubble = Market Cap)",
                template="plotly_dark"
            )
            fig_scatter.update_layout(height=400)
            st.plotly_chart(fig_scatter, use_container_width=True)
            
    with col_right:
        st.subheader("🌡️ Sector Relative Strength (Heatmap)")
        if not filtered_df.empty:
            sector_perf = filtered_df.groupby('Industry')['Ret_1M'].mean().sort_values(ascending=False).reset_index()
            fig_bar = px.bar(
                sector_perf, 
                x='Ret_1M', 
                y='Industry', 
                orientation='h',
                title="Average 1-Month Return by Sector (Trade the Leaders)",
                color='Ret_1M',
                color_continuous_scale='Blues',
                template="plotly_dark"
            )
            fig_bar.update_layout(height=400, yaxis={'categoryorder':'total ascending'})
            st.plotly_chart(fig_bar, use_container_width=True)

    # Interactive Data Table
    st.markdown("---")
    st.subheader("📋 Final Watchlist (Institutional Confluence Setups)")
    
    display_cols = ['Symbol', 'Industry', 'MarCap_Cr', 'CMP_Rs', 'YoY_Rev_Growth_Pct', 
                    'YoY_NP_Growth_Pct', 'NetMargin_Jun26_Pct', 'Ret_1M', 'Ret_1W', 'Ret_1D']
    
    st.dataframe(
        filtered_df[display_cols].style.format({
            'MarCap_Cr': '₹{:,.0f} Cr',
            'CMP_Rs': '₹{:,.2f}',
            'YoY_Rev_Growth_Pct': '{:.1f}%',
            'YoY_NP_Growth_Pct': '{:.1f}%',
            'NetMargin_Jun26_Pct': '{:.1f}%',
            'Ret_1M': '{:.2f}%',
            'Ret_1W': '{:.2f}%',
            'Ret_1D': '{:.2f}%'
        }).background_gradient(cmap='Greens', subset=['YoY_NP_Growth_Pct']),
        use_container_width=True,
        height=600
    )

else:
    st.info("👈 Please upload your `aug_dataai_IMPROVED.xlsx` file in the sidebar to generate the terminal.")