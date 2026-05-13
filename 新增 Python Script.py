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

# 縮短快取時間以獲取較新數據
@st.cache_data(ttl=60)
def get_analysis_data(ticker_input):
    try:
        symbol = ticker_input.strip()
        if symbol.isdigit(): symbol = f"{symbol}.TW"
        
        # 核心優化：優先抓取最新 1 天的即時數據
        # 這樣能解決 yfinance 對台股收盤數據更新較慢的問題
        df = yf.download(symbol, period="2y", interval="1d", auto_adjust=True, progress=False)
        
        # 如果是交易時段，嘗試補強最後一筆價格
        ticker_obj = yf.Ticker(symbol)
        fast_info = ticker_obj.fast_info
        
        if not df.empty:
            # 確保欄位名稱正確
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            
            # 檢查最後一筆日期，如果不是今天且目前是交易時間，則補上即時價
            last_date = df.index[-1].date()
            today = datetime.now().date()
            if last_date < today and 'last_price' in fast_info:
                # 建立一條新的數據行來代表今天
                new_row = df.iloc[-1:].copy()
                new_row.index = [pd.Timestamp(today)]
                new_row['Close'] = fast_info['last_price']
                df = pd.concat([df, new_row])
        
        if df.empty and ".TW" in symbol:
            symbol = symbol.replace(".TW", ".TWO")
            df = yf.download(symbol, period="2y", auto_adjust=True, progress=False)
        
        if df.empty: return None, symbol

        close = df['Close'].squeeze()
        df['MA5'] = close.rolling(5).mean()
        df['MA10'] = close.rolling(10).mean()
        df['BIAS10'] = ((close - df['MA10']) / df['MA10']) * 100
        df['RSI5'] = calculate_rsi(close, 5)
        df['RSI10'] = calculate_rsi(close, 10)
        
        df['Buy_Trigger'] = (df['RSI5'] > df['RSI10']) & (df['RSI5'].shift(1) <= df['RSI10'].shift(1)) & (df['RSI5'] > 50) & (df['BIAS10'] < 5)
        df['Sell_Trigger'] = (df['MA5'] < df['MA10']) & (df['RSI5'] < df['RSI10']) & (df['RSI5'] < 50) & (df['BIAS10'] > 10)
        
        return df, symbol
    except Exception as e:
        return None, ticker_input

# --- 介面 ---
st.markdown(f"""<div class="stock-header"><h1 style='margin:0; color:white; font-size:2.2rem;'>🚀 台股終極策略監控</h1></div>""", unsafe_allow_html=True)

# 搜尋與手動刷新
c_search, c_refresh = st.columns([4, 1])
with c_search:
    user_input = st.text_input("🔍 代號", value="2330", label_visibility="collapsed")
with c_refresh:
    if st.button("🔄 刷新"):
        st.cache_data.clear()
        st.rerun()

# 修正：初始化 session_state
if 'view_days' not in st.session_state:
    st.session_state.view_days = 60

# 天數切換按鈕
cols = st.columns(5)
days_list = [10, 20, 60, 120, 240]
for i, d in enumerate(days_list):
    if cols[i].button(f"{d}天"):
        st.session_state.view_days = d

data, final_ticker = get_analysis_data(user_input)

if data is not None:
    current_days = st.session_state.view_days
    display_df = data.tail(current_days)
    latest = display_df.iloc[-1]
    
    # 圖表
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=display_df.index, y=display_df['Close'],
        mode='lines', name='價格', line=dict(width=3, color='#38bdf8'),
        fill='tozeroy', fillcolor='rgba(56, 189, 248, 0.05)',
        customdata=display_df[['RSI5', 'BIAS10']],
        hovertemplate="價格: %{y:.2f}<br>RSI: %{customdata[0]:.1f}<extra></extra>"
    ))
    
    # 買賣點
    buys = display_df[display_df['Buy_Trigger']]
    sells = display_df[display_df['Sell_Trigger']]
    fig.add_trace(go.Scatter(x=buys.index, y=buys['Close'], mode='markers', name='買', marker=dict(symbol='triangle-up', size=12, color='#ff4b4b')))
    fig.add_trace(go.Scatter(x=sells.index, y=sells['Close'], mode='markers', name='賣', marker=dict(symbol='triangle-down', size=12, color='#00f900')))

    # y 軸價格範圍自動優化
    y_min, y_max = display_df['Close'].min() * 0.97, display_df['Close'].max() * 1.03

    fig.update_layout(
        height=450, template="plotly_dark", paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
        margin=dict(l=0, r=0, t=10, b=0),
        xaxis=dict(showgrid=False, showline=True, linecolor='#30363d'),
        yaxis=dict(side='right', gridcolor='#1e293b', range=[y_min, y_max], autorange=False),
        showlegend=False, hovermode="x unified"
    )
    
    st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})

    # 卡片
    c1, c2, c3 = st.columns(3)
    c1.metric("當前價格", f"{latest['Close']:.2f}")
    c2.metric("RSI (5D)", f"{latest['RSI5']:.1f}")
    c3.metric("10日乖離", f"{latest['BIAS10']:.2f}%")
    
    if latest['Buy_Trigger']: status, sc = "🔴 買入訊號觸發", "#ff4b4b"
    elif latest['Sell_Trigger']: status, sc = "🟢 賣出訊號觸發", "#00f900"
    else: status, sc = "趨勢觀察中", "#94a3b8"
    
    st.markdown(f"""<div class="status-box" style="border: 2px solid {sc}; color: {sc}; background: {sc}15;">{status}</div>""", unsafe_allow_html=True)

    # 盤中自動刷新邏輯 (台股交易時間 09:00 - 13:30)
    now = datetime.now()
    if now.weekday() < 5 and (9 <= now.hour < 14):
        # 顯示最後更新時間
        st.caption(f"盤中自動監控中... 最後更新: {now.strftime('%H:%M:%S')}")
        time.sleep(30) # 每 30 秒刷一次
        st.rerun()
else:
    st.warning("請輸入正確代號。")
