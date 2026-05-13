import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
import time
from datetime import datetime

# 頁面設定：使用寬版模式
st.set_page_config(page_title="台股終極策略監控", layout="wide", initial_sidebar_state="collapsed")

# CSS 樣式：深色專業風格
st.markdown("""
    <style>
    .main { background-color: #0b0e14; color: #e2e8f0; }
    div[data-testid="stMetricValue"] { font-size: 2rem; color: #38bdf8; font-weight: 800; }
    .stMetric { background-color: #161b22; border-radius: 15px; border: 1px solid #30363d; padding: 20px; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1); }
    .stock-header { background: linear-gradient(90deg, #161b22 0%, #1e293b 100%); padding: 20px; border-radius: 15px; border-left: 6px solid #38bdf8; margin-bottom: 25px; }
    .stButton>button { width: 100%; border-radius: 12px; background-color: #1e293b; color: #38bdf8; border: 1px solid #38bdf8; font-weight: bold; transition: 0.3s; }
    .stButton>button:hover { background-color: #38bdf8; color: #0b0e14; transform: translateY(-2px); }
    .status-box { text-align: center; padding: 20px; border-radius: 15px; margin-top: 20px; font-weight: bold; font-size: 1.5rem; }
    </style>
    """, unsafe_allow_html=True)

def calculate_rsi(series, period):
    """計算 RSI 指標"""
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss.replace(0, 0.001)
    return 100 - (100 / (1 + rs))

def get_analysis_data(ticker_input):
    """抓取資料與計算核心指標"""
    try:
        symbol = ticker_input.strip()
        if symbol.isdigit(): symbol = f"{symbol}.TW"
        
        df = yf.download(symbol, period="2y", auto_adjust=True, progress=False)
        if df.empty and ".TW" in symbol:
            symbol = symbol.replace(".TW", ".TWO")
            df = yf.download(symbol, period="2y", auto_adjust=True, progress=False)
        
        if df.empty: return None, symbol

        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        
        close = df['Close'].squeeze()
        
        # 技術指標計算
        df['MA5'] = close.rolling(5).mean()
        df['MA10'] = close.rolling(10).mean()
        df['BIAS10'] = ((close - df['MA10']) / df['MA10']) * 100
        df['RSI5'] = calculate_rsi(close, 5)
        df['RSI10'] = calculate_rsi(close, 10)
        
        # 買入訊號邏輯
        df['Buy_Trigger'] = (df['RSI5'] > df['RSI10']) & \
                            (df['RSI5'].shift(1) <= df['RSI10'].shift(1)) & \
                            (df['RSI5'] > 50) & \
                            (df['BIAS10'] < 5)
        
        # 賣出訊號邏輯
        df['Sell_Trigger'] = (df['MA5'] < df['MA10']) & (df['RSI5'] < df['RSI10']) & \
                            (df['RSI5'] < 50) & (df['BIAS10'] > 10)
        
        return df, symbol
    except Exception as e:
        st.error(f"分析出錯: {e}")
        return None, ticker_input

# --- UI 介面 ---
st.markdown(f"""<div class="stock-header"><h1 style='margin:0; color:white; font-size:2.2rem;'>🚀 台股終極端策略監控</h1><p style='color:#94a3b8; margin:5px 0 0 0;'>即時收盤價分析與策略偵測</p></div>""", unsafe_allow_html=True)

user_input = st.text_input("🔍 輸入台股代號 (例如: 2330, 2454, 0050)", value="2330")

# 預設顯示最近 60 天
view_days = 60

data, final_ticker = get_analysis_data(user_input)

if data is not None:
    display_df = data.tail(view_days)
    latest = display_df.iloc[-1]
    
    # --- 主圖表 ---
    fig = go.Figure()
    
    # 增加收盤價曲線
    fig.add_trace(go.Scatter(
        x=display_df.index,
        y=display_df['Close'],
        mode='lines',
        name='價格',
        line=dict(width=3, color='#38bdf8'),
        fill='tozeroy',
        fillcolor='rgba(56, 189, 248, 0.05)',
        customdata=display_df[['RSI5', 'BIAS10']],
        hovertemplate=(
            "<b>%{x|%Y-%m-%d}</b><br>" +
            "價格: %{y:.2f}<br>" +
            "RSI: %{customdata[0]:.1f}<br>" +
            "乖離: %{customdata[1]:.2f}%" +
            "<extra></extra>"
        )
    ))
    
    # 買賣標記
    buys = display_df[display_df['Buy_Trigger']]
    sells = display_df[display_df['Sell_Trigger']]
    
    fig.add_trace(go.Scatter(x=buys.index, y=buys['Close'], mode='markers', name='買入',
                             marker=dict(symbol='triangle-up', size=15, color='#ff4b4b')))
    fig.add_trace(go.Scatter(x=sells.index, y=sells['Close'], mode='markers', name='賣出',
                             marker=dict(symbol='triangle-down', size=15, color='#00f900')))

    fig.update_layout(
        height=500, 
        template="plotly_dark", 
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        margin=dict(l=10, r=10, t=10, b=10),
        xaxis=dict(
            showgrid=False,
            showspikes=True, 
            spikemode='across',
            spikesnap='cursor',
            showline=True, 
            linecolor='#30363d'
        ),
        yaxis=dict(
            side='right', 
            tickformat='.2f', 
            gridcolor='#1e293b', 
            showspikes=True, 
            spikemode='across',
            spikesnap='cursor',
            showline=True, 
            linecolor='#30363d',
            autorange=True,
            fixedrange=False
        ),
        showlegend=False,
        hovermode="x unified"
    )
    
    # 關鍵修正：config={'displayModeBar': False} 隱藏右上角工具列 (相機、放大鏡等)
    st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})

    # --- 指標數據卡 ---
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("價格", f"{latest['Close']:.2f}")
    c2.metric("RSI (5D)", f"{latest['RSI5']:.1f}")
    c3.metric("10日乖離率", f"{latest['BIAS10']:.2f}%")
    
    if latest['Buy_Trigger']: status, sc = "🔴 買入訊號觸發", "#ff4b4b"
    elif latest['Sell_Trigger']: status, sc = "🟢 賣出訊號觸發", "#00f900"
    else: status, sc = "趨勢觀察中", "#94a3b8"
    
    st.markdown(f"""<div class="status-box" style="border: 2px solid {sc}; color: {sc}; background: {sc}15;">{status}</div>""", unsafe_allow_html=True)

    # 盤中更新
    now = datetime.now()
    if now.weekday() < 5 and 9 <= now.hour < 14:
        st.info(f"自動重整中... 最後更新: {now.strftime('%H:%M:%S')}")
        time.sleep(30)
        st.rerun()
else:
    st.warning("請輸入正確代號。")
