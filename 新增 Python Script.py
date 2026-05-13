import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
import time
from datetime import datetime
import pytz

# 頁面基本設定
st.set_page_config(page_title="台股即時監控系統", layout="wide")

# 解決 session_state 初始化問題
if 'view_days' not in st.session_state:
    st.session_state.view_days = 60

# 自定義 CSS
st.markdown("""
    <style>
    .stMetric { background-color: #161b22; border-radius: 10px; padding: 10px; border: 1px solid #30363d; }
    .status-box { padding: 15px; border-radius: 10px; margin: 10px 0; font-weight: bold; text-align: center; }
    </style>
    """, unsafe_allow_html=True)

def calculate_rsi(series, period):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss.replace(0, 0.001)
    return 100 - (100 / (1 + rs))

@st.cache_data(ttl=60)
def fetch_data(symbol):
    try:
        sid = symbol.strip().upper()
        # 判斷是否需要加上台股後綴
        formatted_sid = f"{sid}.TW" if sid.isdigit() and len(sid) <= 4 else sid
        
        df = yf.download(formatted_sid, period="2y", interval="1d", progress=False)
        
        # 若 .TW 沒數據，嘗試 .TWO (上櫃)
        if df.empty and sid.isdigit():
            formatted_sid = f"{sid}.TWO"
            df = yf.download(formatted_sid, period="2y", interval="1d", progress=False)
            
        if df.empty:
            return None, formatted_sid

        # 處理 MultiIndex 欄位名問題
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        # 數據清理：移除時區資訊
        if df.index.tz is not None:
            df.index = df.index.tz_localize(None)

        # 計算技術指標
        df['MA5'] = df['Close'].rolling(5).mean()
        df['MA10'] = df['Close'].rolling(10).mean()
        df['RSI5'] = calculate_rsi(df['Close'], 5)
        df['RSI10'] = calculate_rsi(df['Close'], 10)
        
        # 計算 10 日乖離率 (BIAS)
        df['BIAS10'] = ((df['Close'] - df['MA10']) / df['MA10']) * 100
        
        # --- 買進訊號策略更新 ---
        # 1. MA5 > MA10
        # 2. RSI5 > RSI10 且 RSI5 > 50
        # 3. BIAS10 < 5%
        cond1 = df['MA5'] > df['MA10']
        cond2 = (df['RSI5'] > df['RSI10']) & (df['RSI5'] > 50)
        cond3 = df['BIAS10'] < 5
        
        df['Buy_Signal'] = cond1 & cond2 & cond3
        
        # 賣出訊號 (維持原樣或可根據需要調整)
        df['Sell_Signal'] = (df['Close'] < df['MA10']) & (df['RSI5'] < 45)
        
        return df, formatted_sid
    except Exception as e:
        st.error(f"分析出錯: {str(e)}")
        return None, symbol

# --- 主介面 ---
st.title("📈 台股即時監測")

col_ctrl1, col_ctrl2 = st.columns([3, 1])
with col_ctrl1:
    target_stock = st.text_input("輸入股票代碼 (例如: 2330)", value="2330")
with col_ctrl2:
    if st.button("刷新數據"):
        st.cache_data.clear()
        st.rerun()

# 天數切換按鈕
d_cols = st.columns(5)
day_options = [10, 20, 60, 120, 240]
for i, d in enumerate(day_options):
    if d_cols[i].button(f"{d}天"):
        st.session_state.view_days = d

data, final_sid = fetch_data(target_stock)

if data is not None:
    view_days = st.session_state.view_days if 'view_days' in st.session_state else 60
    display_df = data.tail(view_days)
    latest = display_df.iloc[-1]
    
    # 動態 Y 軸範圍計算
    current_min = display_df['Close'].min()
    current_max = display_df['Close'].max()
    y_range_min = current_min * 0.97
    y_range_max = current_max * 1.03

    # 繪製圖表
    fig = go.Figure()

    # 股價線
    fig.add_trace(go.Scatter(
        x=display_df.index, y=display_df['Close'],
        name="收盤價", line=dict(color='#38bdf8', width=2),
        fill='tozeroy', fillcolor='rgba(56, 189, 248, 0.05)'
    ))

    # 買入訊號標記
    buys = display_df[display_df['Buy_Signal']]
    fig.add_trace(go.Scatter(
        x=buys.index, y=buys['Close'],
        mode='markers', name='買入訊號',
        marker=dict(symbol='triangle-up', size=12, color='#ef4444')
    ))

    fig.update_layout(
        template="plotly_dark",
        height=500,
        margin=dict(l=10, r=10, t=30, b=10),
        xaxis=dict(
            showgrid=False, 
            rangeslider=dict(visible=False),
            fixedrange=True
        ),
        yaxis=dict(
            side='right',
            gridcolor='#334155',
            range=[y_range_min, y_range_max],
            fixedrange=True
        ),
        hovermode="x unified",
        dragmode=False
    )

    st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})

    # 狀態資訊卡
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("當前價格", f"{latest['Close']:.2f}")
    c2.metric("RSI(5)", f"{latest['RSI5']:.1f}")
    c3.metric("10日乖離", f"{latest['BIAS10']:.2f}%")
    c4.metric("5日均線", f"{latest['MA5']:.2f}")

    # 訊號提示
    if latest['Buy_Signal']:
        st.markdown('<div class="status-box" style="background:#450a0a; color:#f87171; border:1px solid #ef4444;">🔥 偵測到精確買入訊號：均線+RSI+乖離率多重符合</div>', unsafe_allow_html=True)
    elif latest['Sell_Signal']:
        st.markdown('<div class="status-box" style="background:#064e3b; color:#4ade80; border:1px solid #22c55e;">⚠️ 注意：價格跌破均線且 RSI 偏弱</div>', unsafe_allow_html=True)
    else:
        st.markdown('<div class="status-box" style="background:#1e293b; color:#94a3b8; border:1px solid #334155;">🔎 目前趨勢穩定，無明顯交易訊號</div>', unsafe_allow_html=True)

    st.caption(f"最後更新時間: {latest.name.strftime('%Y-%m-%d')} | 標的代號: {final_sid}")
else:
    st.warning(f"找不到 '{target_stock}' 的數據，請檢查代碼是否正確。")
