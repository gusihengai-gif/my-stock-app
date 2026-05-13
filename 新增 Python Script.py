import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
import time
from datetime import datetime
import pytz

# 頁面設定
st.set_page_config(page_title="台股即時監控專業版", layout="wide", initial_sidebar_state="collapsed")

# CSS 樣式：強化 Y 軸與 Tooltip 質感
st.markdown("""
    <style>
    .main { background-color: #0b1117; color: #e2e8f0; }
    div[data-testid="stMetricValue"] { font-size: 1.8rem; color: #38bdf8; font-weight: 800; }
    .stMetric { background-color: #161b22; border-radius: 12px; border: 1px solid #30363d; padding: 15px; }
    .stock-header { background: linear-gradient(90deg, #161b22 0%, #1e293b 100%); padding: 15px; border-radius: 12px; border-left: 6px solid #38bdf8; margin-bottom: 10px; }
    .stButton>button { width: 100%; border-radius: 8px; background-color: #1e293b; color: #38bdf8; border: 1px solid #30363d; }
    .status-box { text-align: center; padding: 12px; border-radius: 10px; margin-top: 10px; font-weight: bold; }
    </style>
    """, unsafe_allow_html=True)

def calculate_rsi(series, period):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss.replace(0, 0.001)
    return 100 - (100 / (1 + rs))

@st.cache_data(ttl=30)
def get_stock_data(ticker_input):
    try:
        sid = ticker_input.strip().upper()
        formatted_sid = f"{sid}.TW" if sid.isdigit() else sid
        
        # 1. 抓取歷史 K 線
        df = yf.download(formatted_sid, period="2y", interval="1d", progress=False)
        if df.empty and sid.isdigit():
            formatted_sid = f"{sid}.TWO"
            df = yf.download(formatted_sid, period="2y", interval="1d", progress=False)

        if df.empty: return None, sid

        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        # 2. 即時報價注入邏輯
        ticker_obj = yf.Ticker(formatted_sid)
        info = ticker_obj.fast_info
        live_price = info.get('last_price')
        
        tz_tw = pytz.timezone('Asia/Taipei')
        now_tw = datetime.now(tz_tw)
        last_date_in_df = df.index[-1].date()

        # 如果最新的 K 線不是今天，則把即時價當作今天的收盤價注入
        if live_price and last_date_in_df < now_tw.date():
            new_timestamp = pd.Timestamp(now_tw.date())
            new_row = pd.DataFrame({
                'Open': [info.get('open', live_price)], 
                'High': [info.get('day_high', live_price)], 
                'Low': [info.get('day_low', live_price)], 
                'Close': [live_price], 
                'Volume': [info.get('last_volume', 0)]
            }, index=[new_timestamp])
            df = pd.concat([df, new_row])

        # 3. 計算技術指標
        close = df['Close']
        df['MA5'] = close.rolling(5).mean()
        df['MA10'] = close.rolling(10).mean()
        df['RSI5'] = calculate_rsi(close, 5)
        df['RSI10'] = calculate_rsi(close, 10)
        df['BIAS10'] = ((close - df['MA10']) / df['MA10']) * 100
        
        # 訊號
        df['Buy_Signal'] = (df['RSI5'] > df['RSI10']) & (df['RSI5'].shift(1) <= df['RSI10'].shift(1))
        df['Sell_Signal'] = (df['MA5'] < df['MA10']) & (df['RSI5'] < 50)
        
        return df, formatted_sid
    except Exception:
        return None, ticker_input

# 初始化
if 'view_days' not in st.session_state:
    st.session_state.view_days = 60

# --- UI 介面 ---
st.markdown('<div class="stock-header"><h3 style="margin:0;">🚀 台股全時段監測系統</h3></div>', unsafe_allow_html=True)

c1, c2 = st.columns([4, 1])
with c1:
    stock_code = st.text_input("代碼", value="2330", label_visibility="collapsed")
with c2:
    if st.button("🔄 刷新"):
        st.cache_data.clear()
        st.rerun()

# 時間區間選取
d_cols = st.columns(5)
for i, d in enumerate([10, 20, 60, 120, 240]):
    if d_cols[i].button(f"{d}天"):
        st.session_state.view_days = d

data, real_sid = get_stock_data(stock_code)

if data is not None:
    display_df = data.tail(st.session_state.view_days)
    latest = display_df.iloc[-1]
    
    # 動態計算 Y 軸範圍：取顯示區間的最低與最高價，並給予 2% 的上下緩衝
    y_min = display_df['Close'].min() * 0.98
    y_max = display_df['Close'].max() * 1.02

    # --- Plotly 圖表 ---
    fig = go.Figure()

    # 1. 價格曲線
    fig.add_trace(go.Scatter(
        x=display_df.index, y=display_df['Close'],
        name="收盤價", line=dict(color='#38bdf8', width=3),
        hovertemplate="價格: %{y:.2f}<br>MA5: %{customdata[0]:.2f}<br>MA10: %{customdata[1]:.2f}",
        customdata=display_df[['MA5', 'MA10']]
    ))

    # 2. RSI 隱藏追蹤 (為了在 Tooltip 顯示)
    fig.add_trace(go.Scatter(
        x=display_df.index, y=display_df['RSI5'],
        name="RSI(5)", line=dict(color='rgba(0,0,0,0)'),
        hovertemplate="RSI(5): %{y:.1f}"
    ))

    # 3. 買賣訊號點
    buys = display_df[display_df['Buy_Signal']]
    sells = display_df[display_df['Sell_Signal']]
    fig.add_trace(go.Scatter(x=buys.index, y=buys['Close'], mode='markers', marker=dict(symbol='triangle-up', size=15, color='#ef4444'), name='買入'))
    fig.add_trace(go.Scatter(x=sells.index, y=sells['Close'], mode='markers', marker=dict(symbol='triangle-down', size=15, color='#22c55e'), name='賣出'))

    # 佈局設定
    fig.update_layout(
        height=480, template="plotly_dark",
        hovermode="x unified", 
        showlegend=False,
        margin=dict(l=10, r=10, t=10, b=10),
        paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
        xaxis=dict(showgrid=False, type='date'),
        yaxis=dict(
            side='right', 
            gridcolor='#1e293b', 
            fixedrange=False,
            range=[y_min, y_max],  # 強制 Y 軸根據當前數據區間調整
            tickformat='.1f'
        ),
        hoverlabel=dict(bgcolor="#1e293b", font_size=13)
    )

    # 顯示圖表
    st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})

    # 數據卡片
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("即時成交價", f"{latest['Close']:.2f}")
    m2.metric("RSI(5)", f"{latest['RSI5']:.1f}")
    m3.metric("10日乖離", f"{latest['BIAS10']:.1f}%")
    m4.metric("今日成交量", f"{int(latest['Volume']):,}")

    # 警報面板
    if latest['Buy_Signal']:
        st.markdown('<div class="status-box" style="background:#450a0a; color:#f87171; border:1px solid #ef4444;">🚨 買入訊號：RSI 黃金交叉</div>', unsafe_allow_html=True)
    elif latest['Sell_Signal']:
        st.markdown('<div class="status-box" style="background:#064e3b; color:#4ade80; border:1px solid #22c55e;">✅ 賣出訊號：趨勢轉弱</div>', unsafe_allow_html=True)
    else:
        st.markdown('<div class="status-box" style="background:#1e293b; color:#94a3b8; border:1px solid #334155;">📊 市場掃描中：無特別訊號</div>', unsafe_allow_html=True)

    st.caption(f"數據最後更新: {latest.name.strftime('%Y-%m-%d')} | 標的: {real_sid}")
    
    # 自動刷新
    time.sleep(30)
    st.rerun()
else:
    st.error("無法取得該股票數據。")
