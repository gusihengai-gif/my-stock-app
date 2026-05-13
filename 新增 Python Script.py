import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
import time
from datetime import datetime, timedelta
import pytz

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

@st.cache_data(ttl=30)
def get_analysis_data(ticker_input):
    try:
        symbol = ticker_input.strip()
        if symbol.isdigit(): 
            symbol_tw = f"{symbol}.TW"
            symbol_two = f"{symbol}.TWO"
        else:
            symbol_tw = symbol
            symbol_two = symbol

        # 優先嘗試上市 (.TW)
        ticker_obj = yf.Ticker(symbol_tw)
        df = ticker_obj.history(period="2y", interval="1d", auto_adjust=True)
        
        # 若沒數據，嘗試上櫃 (.TWO)
        if df.empty:
            ticker_obj = yf.Ticker(symbol_two)
            df = ticker_obj.history(period="2y", interval="1d", auto_adjust=True)
            if df.empty: return None, ticker_input
        
        # 修正 MultiIndex 問題
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        # --- 極限即時補點邏輯：確保 5/13, 5/14 有數據 ---
        tz_tw = pytz.timezone('Asia/Taipei')
        now_tw = datetime.now(tz_tw)
        
        # 獲取最新成交價 (使用 basic_info 作為首選)
        try:
            current_price = ticker_obj.basic_info['last_price']
            if current_price is None or current_price == 0:
                current_price = ticker_obj.fast_info.get('last_price')
            if current_price is None or current_price == 0:
                current_price = df['Close'].iloc[-1]
        except:
            current_price = df['Close'].iloc[-1]

        # 檢查最後一筆資料的日期
        last_date = df.index[-1].astimezone(tz_tw).date()
        
        # 如果最後一筆資料不是今天，且現在是開盤日（或是收盤後的即時價更新）
        if last_date < now_tw.date():
            # 建立一個新的數據點
            new_timestamp = pd.Timestamp(now_tw.replace(hour=0, minute=0, second=0, microsecond=0))
            new_row = pd.DataFrame({
                'Open': [current_price], 'High': [current_price], 
                'Low': [current_price], 'Close': [current_price], 'Volume': [0]
            }, index=[new_timestamp])
            # 確保時區一致後合併
            new_row.index = new_row.index.tz_localize(df.index.tz)
            df = pd.concat([df, new_row])
        # -------------------------------------------

        close = df['Close']
        df['MA5'] = close.rolling(5).mean()
        df['MA10'] = close.rolling(10).mean()
        df['BIAS10'] = ((close - df['MA10']) / df['MA10']) * 100
        df['RSI5'] = calculate_rsi(close, 5)
        df['RSI10'] = calculate_rsi(close, 10)
        
        df['Buy_Trigger'] = (df['RSI5'] > df['RSI10']) & (df['RSI5'].shift(1) <= df['RSI10'].shift(1)) & (df['RSI5'] > 50) & (df['BIAS10'] < 5)
        df['Sell_Trigger'] = (df['MA5'] < df['MA10']) & (df['RSI5'] < df['RSI10']) & (df['RSI5'] < 50) & (df['BIAS10'] > 10)
        
        return df, ticker_obj.ticker
    except Exception as e:
        st.error(f"分析出錯: {e}")
        return None, ticker_input

# --- UI 介面 ---
st.markdown(f"""<div class="stock-header"><h1 style='margin:0; color:white; font-size:2.2rem;'>🚀 台股終極策略監控</h1></div>""", unsafe_allow_html=True)

if 'view_days' not in st.session_state:
    st.session_state.view_days = 60

c_search, c_refresh = st.columns([4, 1])
with c_search:
    user_input = st.text_input("🔍 代號", value="2330", key="search_input", label_visibility="collapsed")
with c_refresh:
    if st.button("🔄 刷新"):
        st.cache_data.clear()
        st.rerun()

cols = st.columns(5)
day_options = [10, 20, 60, 120, 240]
for i, d in enumerate(day_options):
    if cols[i].button(f"{d}天"):
        st.session_state.view_days = d

data, final_ticker = get_analysis_data(user_input)

if data is not None:
    num_days = st.session_state.view_days
    display_df = data.tail(num_days)
    latest = display_df.iloc[-1]
    
    # 圖表
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=display_df.index, y=display_df['Close'],
        mode='lines', name='價格', line=dict(width=3, color='#38bdf8'),
        fill='tozeroy', fillcolor='rgba(56, 189, 248, 0.05)',
        hovertemplate="日期: %{x|%Y-%m-%d}<br>價格: %{y:.2f}<extra></extra>"
    ))
    
    # 標記買賣點
    buys = display_df[display_df['Buy_Trigger']]
    sells = display_df[display_df['Sell_Trigger']]
    fig.add_trace(go.Scatter(x=buys.index, y=buys['Close'], mode='markers', marker=dict(symbol='triangle-up', size=12, color='#ff4b4b'), name='買入'))
    fig.add_trace(go.Scatter(x=sells.index, y=sells['Close'], mode='markers', marker=dict(symbol='triangle-down', size=12, color='#00f900'), name='賣出'))

    y_min, y_max = display_df['Close'].min() * 0.98, display_df['Close'].max() * 1.02
    fig.update_layout(
        height=450, template="plotly_dark", paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
        margin=dict(l=0, r=0, t=10, b=0),
        xaxis=dict(showgrid=False), yaxis=dict(side='right', gridcolor='#1e293b', range=[y_min, y_max], autorange=False),
        showlegend=False, hovermode="x unified"
    )
    
    st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})

    c1, c2, c3 = st.columns(3)
    c1.metric("當前價格", f"{latest['Close']:.2f}")
    c2.metric("RSI (5D)", f"{latest['RSI5']:.1f}")
    c3.metric("10日乖離", f"{latest['BIAS10']:.2f}%")
    
    if latest['Buy_Trigger']: status, sc = "🔴 買入訊號觸發", "#ff4b4b"
    elif latest['Sell_Trigger']: status, sc = "🟢 賣出訊號觸發", "#00f900"
    else: status, sc = "趨勢觀察中", "#94a3b8"
    
    st.markdown(f"""<div class="status-box" style="border: 2px solid {sc}; color: {sc}; background: {sc}15;">{status}</div>""", unsafe_allow_html=True)
    
    # 顯示精確的時間戳，方便確認是否有更新
    st.caption(f"標的: {final_ticker} | 最後更新點日期: {latest.name.strftime('%Y-%m-%d')}")

    # --- 自動刷新邏輯 ---
    # 為了讓使用者在沒開盤時也能看，移除小時限制，改為通用 30 秒刷新
    time.sleep(30)
    st.rerun()
else:
    st.warning(f"目前無法獲取 '{user_input}' 的數據，請檢查代號是否正確。")
