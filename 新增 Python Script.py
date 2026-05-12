import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
import time
from datetime import datetime

# 頁面設定
st.set_page_config(page_title="台股精確策略監控", layout="wide")

# CSS 樣式：專業亮藍色調
st.markdown("""
    <style>
    .main { background-color: #0b0e14; }
    div[data-testid="stMetricValue"] { font-size: 1.8rem; color: #38bdf8; font-weight: bold; }
    .stMetric { background-color: #161b22; border-radius: 12px; border: 1px solid #30363d; padding: 15px; }
    .stock-header { background: #161b22; padding: 15px 20px; border-radius: 12px; border-left: 5px solid #38bdf8; margin-bottom: 20px; }
    .stButton>button { width: 100%; border-radius: 20px; background-color: #1e293b; color: white; border: 1px solid #38bdf8; }
    .stButton>button:hover { background-color: #38bdf8; color: black; }
    </style>
    """, unsafe_allow_html=True)

def calculate_rsi(series, period):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss.replace(0, 0.001)
    return 100 - (100 / (1 + rs))

def get_analysis_data(ticker_input):
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
        
        # 指標計算
        df['MA5'] = close.rolling(5).mean()
        df['MA10'] = close.rolling(10).mean()
        df['BIAS10'] = ((close - df['MA10']) / df['MA10']) * 100
        df['RSI5'] = calculate_rsi(close, 5)
        df['RSI10'] = calculate_rsi(close, 10)
        
        # --- 買入訊號 (紅) ---
        # 條件：RSI5 > RSI10 且 RSI5 > 50 且 BIAS10 < 5%
        df['Buy_Trigger'] = (df['RSI5'] > df['RSI10']) & \
                            (df['RSI5'].shift(1) <= df['RSI10'].shift(1)) & \
                            (df['RSI5'] > 50) & \
                            (df['BIAS10'] < 5)
        
        # --- 賣出訊號 (綠) ---
        # 修改為「同時滿足」所有條件 (AND)
        cond1 = (df['MA5'] < df['MA10'])
        cond2 = (df['RSI5'] < df['RSI10'])
        cond3 = (df['RSI5'] < 50)
        cond4 = (df['BIAS10'] > 10)
        
        # 只有當上述四個條件在同一天全部成立時，才觸發賣出訊號
        df['Sell_Trigger'] = cond1 & cond2 & cond3 & cond4
        
        return df, symbol
    except:
        return None, ticker_input

# --- UI ---
user_input = st.text_input("🔍 搜尋代號", value="2330")

if 'view_days' not in st.session_state:
    st.session_state.view_days = 60

cols = st.columns(5)
days_map = [("10D", 10), ("20D", 20), ("60D", 60), ("120D", 120), ("240D", 240)]
for i, (label, val) in enumerate(days_map):
    if cols[i].button(label): st.session_state.view_days = val

data, final_ticker = get_analysis_data(user_input)

if data is not None:
    st.markdown(f"""<div class="stock-header"><h1 style='margin:0; color:white;'>代號：{final_ticker.split('.')[0]}</h1></div>""", unsafe_allow_html=True)

    display_df = data.tail(st.session_state.view_days)
    latest = display_df.iloc[-1]
    
    # 動態計算 Y 軸範圍
    y_min = display_df['Close'].min() * 0.98
    y_max = display_df['Close'].max() * 1.02
    
    # --- 主圖表 ---
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=display_df.index, y=display_df['Close'], mode='lines', 
                             line=dict(width=3, color='#38bdf8'), name='價格'))
    
    buys = display_df[display_df['Buy_Trigger']]
    sells = display_df[display_df['Sell_Trigger']]
    
    fig.add_trace(go.Scatter(x=buys.index, y=buys['Close'], mode='markers', name='買',
                             marker=dict(symbol='triangle-up', size=16, color='#ff4b4b')))
    fig.add_trace(go.Scatter(x=sells.index, y=sells['Close'], mode='markers', name='賣',
                             marker=dict(symbol='triangle-down', size=16, color='#00f900')))

    fig.update_layout(
        height=450, 
        template="plotly_dark", 
        margin=dict(l=10, r=10, t=10, b=10),
        yaxis=dict(range=[y_min, y_max], side='right', tickformat='.1f', gridcolor='#1e293b'),
        xaxis=dict(showgrid=False),
        showlegend=False
    )
    st.plotly_chart(fig, use_container_width=True)

    # --- RSI 子圖 ---
    fig_rsi = go.Figure()
    fig_rsi.add_trace(go.Scatter(x=display_df.index, y=display_df['RSI5'], line=dict(color='#ff4b4b', width=2)))
    fig_rsi.add_trace(go.Scatter(x=display_df.index, y=display_df['RSI10'], line=dict(color='#94a3b8', width=2, dash='dot')))
    fig_rsi.update_layout(height=180, template="plotly_dark", margin=dict(l=10, r=10, t=0, b=0), yaxis=dict(side='right'))
    st.plotly_chart(fig_rsi, use_container_width=True)

    # 指標卡
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("價格", f"{latest['Close']:.2f}")
    c2.metric("RSI(5)", f"{latest['RSI5']:.1f}")
    c3.metric("10日乖離", f"{latest['BIAS10']:.2f}%")
    
    if latest['Buy_Trigger']: status, sc = "🔴 買入訊號", "#ff4b4b"
    elif latest['Sell_Trigger']: status, sc = "🟢 嚴格賣出訊號觸發", "#00f900"
    else: status, sc = "⚪ 趨勢觀察", "#94a3b8"
    
    st.markdown(f"<div style='text-align:center; border:1px solid {sc}; padding:10px; border-radius:10px; color:{sc};'><h2>{status}</h2></div>", unsafe_allow_html=True)

    # 盤中定時刷新
    if datetime.now().weekday() < 5 and 9 <= datetime.now().hour < 14:
        time.sleep(30)
        st.rerun()