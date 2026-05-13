import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
import time
from datetime import datetime

# 頁面設定：使用寬版模式
st.set_page_config(page_title="台股終極策略監控", layout="wide", initial_sidebar_state="collapsed")

# CSS 樣式：極簡深色風格
st.markdown("""
    <style>
    .main { background-color: #0b0e14; color: #e2e8f0; }
    div[data-testid="stMetricValue"] { font-size: 1.8rem; color: #38bdf8; font-weight: 800; }
    .stMetric { background-color: #161b22; border-radius: 15px; border: 1px solid #30363d; padding: 15px; }
    .stock-header { background: #161b22; padding: 20px; border-radius: 15px; border-left: 6px solid #38bdf8; margin-bottom: 20px; }
    .stButton>button { width: 100%; border-radius: 12px; background-color: #1e293b; color: #38bdf8; border: 1px solid #38bdf8; font-weight: bold; }
    .status-box { text-align: center; padding: 20px; border-radius: 15px; margin-top: 20px; font-weight: bold; font-size: 1.5rem; }
    /* 隱藏 Streamlit 內建的 Plotly 放大按鈕 */
    button[title="View fullscreen"] { display: none; }
    </style>
    """, unsafe_allow_html=True)

def calculate_rsi(series, period):
    """計算 RSI 指標"""
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss.replace(0, 0.001)
    return 100 - (100 / (1 + rs))

@st.cache_data(ttl=60)
def fetch_data(ticker_input):
    """抓取資料與計算核心指標"""
    try:
        symbol = ticker_input.strip().upper()
        if symbol.isdigit(): symbol = f"{symbol}.TW"
        
        df = yf.download(symbol, period="2y", auto_adjust=True, progress=False)
        if df.empty and ".TW" in symbol:
            symbol = symbol.replace(".TW", ".TWO")
            df = yf.download(symbol, period="2y", auto_adjust=True, progress=False)
        
        if df.empty: return None, symbol

        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        
        # 修正時區
        if df.index.tz is not None:
            df.index = df.index.tz_convert(None)
            
        close = df['Close'].squeeze()
        
        # 技術指標計算
        df['MA20'] = close.rolling(20).mean()
        df['MA60'] = close.rolling(60).mean()
        df['MA10'] = close.rolling(10).mean()
        df['BIAS10'] = ((close - df['MA10']) / df['MA10']) * 100
        df['RSI5'] = calculate_rsi(close, 5)
        df['RSI10'] = calculate_rsi(close, 10)
        
        # 買入訊號
        df['Buy_Signal'] = (df['MA20'] > df['MA60']) & \
                          (df['RSI5'] > df['RSI10']) & \
                          (df['RSI5'] > 50) & \
                          (df['BIAS10'] <= 5)
        
        # 賣出訊號
        df['Sell_Signal'] = (close < df['MA10']) & (df['RSI5'] < 45)
        
        return df, symbol
    except Exception as e:
        st.error(f"分析出錯: {e}")
        return None, ticker_input

# --- UI 介面 ---
st.markdown("""<div class="stock-header"><h1 style='margin:0; color:white;'>🚀 台股即時監控</h1></div>""", unsafe_allow_html=True)

col_input, col_refresh = st.columns([4, 1])
with col_input:
    user_input = st.text_input("🔍 代號", value="2330")
with col_refresh:
    if st.button("刷新"):
        st.cache_data.clear()
        st.rerun()

if 'view_days' not in st.session_state:
    st.session_state.view_days = 60

cols_days = st.columns(5)
days_map = [("10D", 10), ("20D", 20), ("60D", 60), ("120D", 120), ("240D", 240)]
for i, (label, val) in enumerate(days_map):
    if cols_days[i].button(label):
        st.session_state.view_days = val

data, final_sid = fetch_data(user_input)

if data is not None:
    display_df = data.tail(st.session_state.view_days)
    latest = display_df.iloc[-1]
    
    # --- 主圖表 ---
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=display_df.index, y=display_df['Close'],
        mode='lines', name='價格',
        line=dict(width=3, color='#38bdf8'),
        fill='tozeroy', fillcolor='rgba(56, 189, 248, 0.05)'
    ))
    
    # 買賣點標記
    buys = display_df[display_df['Buy_Signal']]
    sells = display_df[display_df['Sell_Signal']]
    
    fig.add_trace(go.Scatter(x=buys.index, y=buys['Close'], mode='markers', name='買入',
                             marker=dict(symbol='triangle-up', size=15, color='#ff4b4b')))
    fig.add_trace(go.Scatter(x=sells.index, y=sells['Close'], mode='markers', name='賣出',
                             marker=dict(symbol='triangle-down', size=15, color='#00f900')))

    fig.update_layout(
        height=500, template="plotly_dark",
        paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
        margin=dict(l=10, r=10, t=10, b=10),
        xaxis=dict(showgrid=False, fixedrange=True), # 禁用 X 軸縮放
        yaxis=dict(side='right', gridcolor='#1e293b', fixedrange=True), # 禁用 Y 軸縮放
        hovermode="x unified", showlegend=False,
        dragmode=False # 徹底禁用鼠標框選縮放
    )
    
    # 使用 config 參數隱藏右上角工具列 (Modebar)
    st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})

    # 指標卡
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("價格", f"{latest['Close']:.2f}")
    c2.metric("RSI(5)", f"{latest['RSI5']:.1f}")
    c3.metric("10日乖離", f"{latest['BIAS10']:.2f}%")
    c4.metric("MA20", f"{latest['MA20']:.1f}")
    
    if latest['Buy_Signal']:
        status, sc = "🔴 買入訊號觸發", "#ff4b4b"
    elif latest['Sell_Signal']:
        status, sc = "🟢 賣出訊號觸發", "#00f900"
    else:
        status, sc = "⚪ 趨勢觀察中", "#94a3b8"
    
    st.markdown(f"""<div class="status-box" style="border: 2px solid {sc}; color: {sc}; background: {sc}15;">{status}</div>""", unsafe_allow_html=True)
    st.caption(f"最後更新: {latest.name.strftime('%Y-%m-%d')} | {final_sid}")

    # 盤中刷新
    now = datetime.now()
    if now.weekday() < 5 and 9 <= now.hour < 14:
        time.sleep(30)
        st.rerun()
else:
    st.warning("查無數據，請確認代號。")
