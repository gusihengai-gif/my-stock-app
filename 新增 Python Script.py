import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
import time
from datetime import datetime
import pytz

# 頁面設定
st.set_page_config(page_title="台股監控修復版", layout="wide", initial_sidebar_state="collapsed")

# CSS 樣式
st.markdown("""
    <style>
    .main { background-color: #0b0e14; color: #e2e8f0; }
    div[data-testid="stMetricValue"] { font-size: 1.8rem; color: #38bdf8; font-weight: 800; }
    .stMetric { background-color: #161b22; border-radius: 12px; border: 1px solid #30363d; padding: 15px; }
    .stock-header { background: linear-gradient(90deg, #161b22 0%, #1e293b 100%); padding: 15px; border-radius: 12px; border-left: 6px solid #38bdf8; margin-bottom: 20px; }
    .stButton>button { width: 100%; border-radius: 10px; background-color: #1e293b; color: #38bdf8; border: 1px solid #38bdf8; }
    .status-box { text-align: center; padding: 15px; border-radius: 12px; margin-top: 15px; font-weight: bold; font-size: 1.2rem; }
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
        # 清理輸入
        sid = ticker_input.strip().upper()
        if sid.isdigit():
            # 優先嘗試上市，不行再上櫃
            df = yf.download(f"{sid}.TW", period="2y", interval="1d", progress=False)
            final_sid = f"{sid}.TW"
            if df.empty or len(df) < 10:
                df = yf.download(f"{sid}.TWO", period="2y", interval="1d", progress=False)
                final_sid = f"{sid}.TWO"
        else:
            df = yf.download(sid, period="2y", interval="1d", progress=False)
            final_sid = sid

        if df.empty: return None, sid

        # 處理 MultiIndex 列名問題
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        # 核心：補足最新價格 (解決 5/13, 5/14 沒更新問題)
        ticker_obj = yf.Ticker(final_sid)
        live_price = None
        
        # 獲取最即時的成交價
        try:
            live_price = ticker_obj.basic_info.get('last_price')
            if live_price is None or live_price == 0:
                live_price = ticker_obj.fast_info.get('last_price')
        except:
            pass

        # 檢查最後一筆資料日期 (轉換為不帶時區的 date 進行比較)
        last_date = df.index[-1].date()
        today_date = datetime.now(pytz.timezone('Asia/Taipei')).date()

        # 如果最後一筆是舊的且有即時價，手動補入
        if live_price and last_date < today_date:
            new_row = pd.DataFrame({
                'Open': [live_price], 'High': [live_price], 
                'Low': [live_price], 'Close': [live_price], 'Volume': [0]
            }, index=[pd.Timestamp(today_date)])
            df = pd.concat([df, new_row])

        # 計算指標
        close = df['Close']
        df['MA5'] = close.rolling(5).mean()
        df['MA10'] = close.rolling(10).mean()
        df['BIAS10'] = ((close - df['MA10']) / df['MA10']) * 100
        df['RSI5'] = calculate_rsi(close, 5)
        df['RSI10'] = calculate_rsi(close, 10)
        
        # 訊號判定
        df['Buy_Trigger'] = (df['RSI5'] > df['RSI10']) & (df['RSI5'].shift(1) <= df['RSI10'].shift(1)) & (df['RSI5'] > 50) & (df['BIAS10'] < 5)
        df['Sell_Trigger'] = (df['MA5'] < df['MA10']) & (df['RSI5'] < df['RSI10']) & (df['RSI5'] < 50) & (df['BIAS10'] > 10)
        
        return df, final_sid
    except Exception as e:
        st.error(f"數據抓取失敗: {str(e)}")
        return None, ticker_input

# --- 介面開始 ---
if 'view_days' not in st.session_state:
    st.session_state.view_days = 60

st.markdown("""<div class="stock-header"><h2 style='margin:0; color:white;'>💹 台股監控 (修復版)</h2></div>""", unsafe_allow_html=True)

c_input, c_btn = st.columns([4, 1])
with c_input:
    stock_code = st.text_input("輸入代碼 (如 2330)", value="2330", label_visibility="collapsed")
with c_btn:
    if st.button("🔄 強制刷新"):
        st.cache_data.clear()
        st.rerun()

# 天數切換
d_cols = st.columns(5)
for i, d in enumerate([10, 20, 60, 120, 240]):
    if d_cols[i].button(f"{d}D"):
        st.session_state.view_days = d

data, real_sid = get_stock_data(stock_code)

if data is not None:
    # 這裡修正了 session_state 的錯誤調用
    view_count = st.session_state.view_days
    display_df = data.tail(view_count)
    latest = display_df.iloc[-1]
    
    # 圖表繪製
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=display_df.index, y=display_df['Close'],
        line=dict(color='#38bdf8', width=2),
        fill='tozeroy', fillcolor='rgba(56, 189, 248, 0.05)',
        name="收盤價"
    ))
    
    # 訊號點
    buys = display_df[display_df['Buy_Trigger']]
    sells = display_df[display_df['Sell_Trigger']]
    fig.add_trace(go.Scatter(x=buys.index, y=buys['Close'], mode='markers', marker=dict(symbol='triangle-up', size=12, color='#ff4b4b'), name='買'))
    fig.add_trace(go.Scatter(x=sells.index, y=sells['Close'], mode='markers', marker=dict(symbol='triangle-down', size=12, color='#00f900'), name='賣'))

    fig.update_layout(
        height=400, template="plotly_dark", margin=dict(l=0, r=0, t=10, b=0),
        paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
        yaxis=dict(side='right', gridcolor='#30363d'), xaxis=dict(showgrid=False)
    )
    st.plotly_chart(fig, use_container_width=True)

    # 數據指標
    m1, m2, m3 = st.columns(3)
    m1.metric("當前成交", f"{latest['Close']:.2f}")
    m2.metric("RSI (5D)", f"{latest['RSI5']:.1f}")
    m3.metric("10日乖離", f"{latest['BIAS10']:.2f}%")

    # 狀態顯示
    if latest['Buy_Trigger']: 
        st.markdown(f'<div class="status-box" style="border:1px solid #ff4b4b; color:#ff4b4b;">🔴 策略觸發：建議買入</div>', unsafe_allow_html=True)
    elif latest['Sell_Trigger']:
        st.markdown(f'<div class="status-box" style="border:1px solid #00f900; color:#00f900;">🟢 策略觸發：建議賣出</div>', unsafe_allow_html=True)
    else:
        st.markdown(f'<div class="status-box" style="border:1px solid #94a3b8; color:#94a3b8;">⚪ 持續觀察中</div>', unsafe_allow_html=True)

    st.caption(f"標的: {real_sid} | 最後數據日期: {latest.name.date()}")
    
    # 自動每 60 秒重新載入
    time.sleep(60)
    st.rerun()
else:
    st.error("找不到該代碼的數據，請確認後重試。")
