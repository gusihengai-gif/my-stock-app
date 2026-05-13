import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
import time
from datetime import datetime, timedelta

# 頁面設定
st.set_page_config(page_title="台股終極策略監控", layout="wide", initial_sidebar_state="collapsed")

# CSS 樣式
st.markdown("""
    <style>
    .main { background-color: #0b0e14; color: #e2e8f0; }
    div[data-testid="stMetricValue"] { font-size: 2rem; color: #38bdf8; font-weight: 800; }
    .stMetric { background-color: #161b22; border-radius: 15px; border: 1px solid #30363d; padding: 20px; }
    .stock-header { background: linear-gradient(90deg, #161b22 0%, #1e293b 100%); padding: 20px; border-radius: 15px; border-left: 6px solid #38bdf8; margin-bottom: 25px; }
    .stButton>button { width: 100%; border-radius: 12px; background-color: #1e293b; color: #38bdf8; border: 1px solid #38bdf8; font-weight: bold; }
    .status-box { text-align: center; padding: 20px; border-radius: 15px; margin-top: 20px; font-weight: bold; font-size: 1.5rem; }
    </style>
    """, unsafe_allow_html=True)

def calculate_rsi(series, period):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss.replace(0, 0.001)
    return 100 - (100 / (1 + rs))

@st.cache_data(ttl=60)
def get_analysis_data(ticker_input):
    try:
        symbol = ticker_input.strip()
        if symbol.isdigit(): symbol = f"{symbol}.TW"
        
        # 1. 抓取歷史數據
        ticker_obj = yf.Ticker(symbol)
        df = ticker_obj.history(period="2y", interval="1d", auto_adjust=True)
        
        if df.empty:
            return None, symbol

        # 處理 MultiIndex 欄位問題
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        # 2. 強制即時補點 (解決卡在 5/12 的問題)
        # 獲取今日最新價格與日期
        fast_info = ticker_obj.fast_info
        last_price = fast_info.get('last_price', None)
        # 轉為台灣日期
        today_ts = pd.Timestamp(datetime.now().date(), tz=df.index.tz)
        
        # 如果最後一筆數據不是今天，且目前有即時價格，則補上一行
        if df.index[-1].date() < today_ts.date() and last_price:
            new_row = pd.DataFrame({
                'Open': [last_price], 'High': [last_price], 
                'Low': [last_price], 'Close': [last_price], 
                'Volume': [0]
            }, index=[today_ts])
            df = pd.concat([df, new_row])
        
        # 計算指標
        close = df['Close']
        df['MA5'] = close.rolling(5).mean()
        df['MA10'] = close.rolling(10).mean()
        df['BIAS10'] = ((close - df['MA10']) / df['MA10']) * 100
        df['RSI5'] = calculate_rsi(close, 5)
        df['RSI10'] = calculate_rsi(close, 10)
        
        df['Buy_Trigger'] = (df['RSI5'] > df['RSI10']) & (df['RSI5'].shift(1) <= df['RSI10'].shift(1)) & (df['RSI5'] > 50) & (df['BIAS10'] < 5)
        df['Sell_Trigger'] = (df['MA5'] < df['MA10']) & (df['RSI5'] < df['RSI10']) & (df['RSI5'] < 50) & (df['BIAS10'] > 10)
        
        return df, symbol
    except Exception as e:
        st.error(f"數據抓取失敗: {e}")
        return None, ticker_input

# --- 主介面 ---
st.markdown(f"""<div class="stock-header"><h1 style='margin:0; color:white; font-size:2.2rem;'>🚀 台股終極策略監控</h1></div>""", unsafe_allow_html=True)

# 初始化 Session State 防止報錯
if 'view_days' not in st.session_state:
    st.session_state.view_days = 60

c_search, c_refresh = st.columns([4, 1])
with c_search:
    user_input = st.text_input("🔍 請輸入台股代號 (如: 2330)", value="2330", label_visibility="collapsed")
with c_refresh:
    if st.button("🔄 刷新"):
        st.cache_data.clear()
        st.rerun()

# 天數切換
cols = st.columns(5)
for i, d in enumerate([10, 20, 60, 120, 240]):
    if cols[i].button(f"{d}天"):
        st.session_state.view_days = d

data, final_ticker = get_analysis_data(user_input)

if data is not None:
    # 修正：直接使用 session_state 的值
    display_df = data.tail(st.session_state.view_days)
    latest = display_df.iloc[-1]
    
    # Plotly 圖表
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=display_df.index, y=display_df['Close'],
        mode='lines', name='價格', line=dict(width=3, color='#38bdf8'),
        fill='tozeroy', fillcolor='rgba(56, 189, 248, 0.05)',
        hovertemplate="日期: %{x|%Y-%m-%d}<br>價格: %{y:.2f}<extra></extra>"
    ))
    
    # 買賣標記
    buys = display_df[display_df['Buy_Trigger']]
    sells = display_df[display_df['Sell_Trigger']]
    fig.add_trace(go.Scatter(x=buys.index, y=buys['Close'], mode='markers', name='買', marker=dict(symbol='triangle-up', size=12, color='#ff4b4b')))
    fig.add_trace(go.Scatter(x=sells.index, y=sells['Close'], mode='markers', name='賣', marker=dict(symbol='triangle-down', size=12, color='#00f900')))

    fig.update_layout(
        height=450, template="plotly_dark", paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
        margin=dict(l=0, r=0, t=10, b=0),
        xaxis=dict(showgrid=False), yaxis=dict(side='right', gridcolor='#1e293b'),
        showlegend=False, hovermode="x unified"
    )
    
    st.plotly_chart(fig, use_container_width=True)

    # 數據指標卡
    c1, c2, c3 = st.columns(3)
    c1.metric("當前價格", f"{latest['Close']:.2f}")
    c2.metric("RSI (5D)", f"{latest['RSI5']:.1f}")
    c3.metric("10日乖離", f"{latest['BIAS10']:.2f}%")
    
    # 訊號狀態
    if latest['Buy_Trigger']: status, sc = "🔴 買入訊號觸發", "#ff4b4b"
    elif latest['Sell_Trigger']: status, sc = "🟢 賣出訊號觸發", "#00f900"
    else: status, sc = "趨勢觀察中", "#94a3b8"
    
    st.markdown(f"""<div class="status-box" style="border: 2px solid {sc}; color: {sc}; background: {sc}15;">{status}</div>""", unsafe_allow_html=True)
    st.caption(f"數據最後更新日期: {latest.name.strftime('%Y-%m-%d')}")

else:
    st.warning("找不到數據，請確認代號是否正確。")
