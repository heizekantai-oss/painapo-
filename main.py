import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import numpy as np
import os

# --- 既存ファイルの読み込み ---
import src.data_loader as data_loader
import src.models as models
import src.llm as llm
import src.utils as utils
# -----------------------------

# --- 1. ページ設定 ---
st.set_page_config(layout="wide", page_title="AI株価予測")

# --- CSS設定 ---
st.markdown("""
    <style>
        .stApp { background-color: #0E1117; color: #FAFAFA; }
        .ai-console {
            background-color: #0D1117; color: #C9D1D9; font-family: 'Consolas', monospace;
            font-size: 14px; padding: 20px; border-left: 4px solid #238636;
            margin-top: 5px; border-radius: 4px;
        }
    </style>
""", unsafe_allow_html=True)

# --- 2. 設定 & キャッシュ ---
# utilsを使って読み込むように統一
SECRETS = utils.load_secrets()
GEMINI_API_KEY = SECRETS.get("gemini_api_key")
DEFAULT_WEBHOOK_URL = "" # Webhookは手動入力

@st.cache_data(ttl=3600, show_spinner=False)
def get_cached_ai_comment(ticker, name, df, pred, ai_score, fund_data):
    return llm.generate_gemini_comment(GEMINI_API_KEY, ticker, name, df, pred, ai_score, fund_data)

@st.cache_data(ttl=3600*24)
def get_company_name_cached(ticker):
    return utils.get_ticker_info(ticker)

@st.cache_data(ttl=3600)
def get_fundamentals_cached_v3(ticker):
    return utils.get_fundamentals(ticker)

@st.cache_data(ttl=3600*12)
def get_macro_data_cached(period):
    return data_loader.get_macro_trend(period)

# --- CSV保存用の関数 ---
# --- スプレッドシート保存用の関数 (CSVから変更) ---
import gspread
from google.oauth2.service_account import Credentials
import json

def get_gspread_client():
    # StreamlitのSecretsからGoogleの合鍵を読み込む
    gcp_json_str = st.secrets["GCP_CREDENTIALS"]
    creds_dict = json.loads(gcp_json_str)
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]
    creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
    return gspread.authorize(creds)

def load_portfolio():
    try:
        client = get_gspread_client()
        # SPREADSHEET_IDを使ってシートを開く
        sheet = client.open_by_key(st.secrets["SPREADSHEET_ID"]).sheet1
        records = sheet.get_all_records()
        if records:
            return pd.DataFrame(records)
        else:
            return pd.DataFrame(columns=["銘柄コード", "銘柄名", "保有株数", "取得単価", "通知価格", "通知先"])
    except Exception as e:
        st.error(f"スプレッドシートの読み込みエラー: {e}")
        return pd.DataFrame(columns=["銘柄コード", "銘柄名", "保有株数", "取得単価", "通知価格", "通知先"])

def save_portfolio(df):
    try:
        client = get_gspread_client()
        sheet = client.open_by_key(st.secrets["SPREADSHEET_ID"]).sheet1
        sheet.clear() # 一旦シートを空にする
        # データをスプレッドシートに書き込む
        df_filled = df.fillna("")
        sheet.update(values=[df_filled.columns.values.tolist()] + df_filled.values.tolist(), range_name="A1")
    except Exception as e:
        st.error(f"スプレッドシートの保存エラー: {e}")

# === ポートフォリオ入力用のポップアップ画面 ===
@st.dialog("ポートフォリオ管理")
def portfolio_dialog():
    st.write("銘柄を検索して追加するか、下の表を直接編集してください。")
    
    current_df = load_portfolio()
    
    # 互換性維持（足りない列を自動追加）
    if "銘柄名" not in current_df.columns: current_df["銘柄名"] = ""
    if "通知価格" not in current_df.columns: current_df["通知価格"] = 0
    if "通知先" not in current_df.columns: current_df["通知先"] = "SLACK"

    # --- 1. 検索＆追加エリア ---
    st.markdown("##### 新規追加")
    
    search_options = {}
    for cat, stocks in utils.COMPANY_DICT.items():
        for name, code in stocks.items():
            label = f"{name} ({code})"
            search_options[label] = {"code": code, "name": name}
    
    c1, c2 = st.columns([2, 1])
    with c1:
        selected_label = st.selectbox("銘柄を検索 (名称またはコード)", options=list(search_options.keys()), index=None, placeholder="入力して検索...")
    
    c_add1, c_add2, c_add3, c_add4, c_add5 = st.columns(5)
    qty_input = c_add1.number_input("株数", min_value=100, step=100, value=100, key="add_qty")
    cost_input = c_add2.number_input("取得単価", min_value=0.0, step=10.0, value=0.0, key="add_cost")
    alert_input = c_add3.number_input("通知価格", min_value=0.0, step=10.0, value=0.0, key="add_alert")
    dest_input = c_add4.selectbox("通知先", options=["SLACK", "DISCORD"], key="add_dest")
    
    if c_add5.button("リストに追加", type="primary"):
        if selected_label:
            target_data = search_options[selected_label]
            new_row = pd.DataFrame([{
                "銘柄コード": target_data["code"], "銘柄名": target_data["name"],
                "保有株数": qty_input, "取得単価": cost_input, 
                "通知価格": alert_input, "通知先": dest_input
            }])
            current_df = new_row if current_df.empty else pd.concat([current_df, new_row], ignore_index=True)
            save_portfolio(current_df)
            st.session_state["my_portfolio"] = current_df
            st.rerun()
        else:
            st.warning("銘柄を選択してください")

    st.markdown("---")

    # --- 2. 編集エリア ---
    st.markdown("##### 保有リスト編集")
    st.caption("変更内容は「保存して閉じる」を押すとスプレッドシートに書き込まれます。")

    edited_df = st.data_editor(
        current_df, num_rows="dynamic", use_container_width=True,
        column_config={
            "銘柄コード": st.column_config.TextColumn(width="small", required=True),
            "銘柄名": st.column_config.TextColumn(width="medium"),
            "保有株数": st.column_config.NumberColumn(min_value=0, step=100, format="%.0f"),
            "取得単価": st.column_config.NumberColumn(min_value=0, format="%.0f"),
            "通知価格": st.column_config.NumberColumn(min_value=0, format="%.0f"),
            "通知先": st.column_config.SelectboxColumn(options=["SLACK", "DISCORD"], width="small")
        },
        key="dialog_editor"
    )
    
    if st.button("保存して閉じる", type="primary"):
        save_portfolio(edited_df)
        st.session_state["my_portfolio"] = edited_df
        st.rerun()
# ============================================
# === ポートフォリオ入力用のポップアップ画面 ===
@st.dialog("ポートフォリオ管理")
def portfolio_dialog():
    st.write("銘柄を検索して追加するか、下の表を直接編集してください。")
    
    # ファイルから読み込み
    current_df = load_portfolio()
    
    # 互換性維持
    if "銘柄名" not in current_df.columns:
        current_df["銘柄名"] = ""
    if "通知価格" not in current_df.columns:
        current_df["通知価格"] = 0

    # --- 1. 検索＆追加エリア ---
    st.markdown("##### 新規追加")
    
    search_options = {}
    for cat, stocks in utils.COMPANY_DICT.items():
        for name, code in stocks.items():
            label = f"{name} ({code})"
            search_options[label] = {"code": code, "name": name}
    
    c1, c2 = st.columns([2, 1])
    with c1:
        selected_label = st.selectbox(
            "銘柄を検索 (名称またはコード)", 
            options=list(search_options.keys()),
            index=None,
            placeholder="入力して検索..."
        )
    
    c_add1, c_add2, c_add3, c_add4 = st.columns(4)
    qty_input = c_add1.number_input("株数", min_value=100, step=100, value=100, key="add_qty")
    cost_input = c_add2.number_input("取得単価", min_value=0.0, step=10.0, value=0.0, key="add_cost")
    alert_input = c_add3.number_input("通知価格", min_value=0.0, step=10.0, value=0.0, help="この価格を超えたら通知", key="add_alert")
    
    if c_add4.button("リストに追加", type="primary"):
        if selected_label:
            target_data = search_options[selected_label]
            new_row = pd.DataFrame([{
                "銘柄コード": target_data["code"],
                "銘柄名": target_data["name"],
                "保有株数": qty_input,
                "取得単価": cost_input,
                "通知価格": alert_input
            }])
            if current_df.empty:
                current_df = new_row
            else:
                current_df = pd.concat([current_df, new_row], ignore_index=True)
            
            save_portfolio(current_df) # ファイル保存
            st.session_state["my_portfolio"] = current_df
            st.rerun()
        else:
            st.warning("銘柄を選択してください")

    st.markdown("---")

    # --- 2. 編集エリア ---
    st.markdown("##### 保有リスト編集")
    st.caption("変更内容は「保存して閉じる」を押すとファイルに書き込まれます。")

    edited_df = st.data_editor(
        current_df,
        num_rows="dynamic",
        use_container_width=True,
        column_config={
            "銘柄コード": st.column_config.TextColumn(width="small", required=True),
            "銘柄名": st.column_config.TextColumn(width="medium", disabled=False),
            "保有株数": st.column_config.NumberColumn(min_value=0, step=100, format="%.0f"),
            "取得単価": st.column_config.NumberColumn(min_value=0, format="%.0f"),
            "通知価格": st.column_config.NumberColumn(min_value=0, format="%.0f", help="0で無効")
        },
        key="dialog_editor"
    )
    
    if st.button("保存して閉じる", type="primary"):
        save_portfolio(edited_df) # ファイル保存
        st.session_state["my_portfolio"] = edited_df
        st.rerun()
# ============================================

# --- 3. サイドバー (上部) ---
with st.sidebar:
    st.markdown("## AI株価予測")
    
    # === ポートフォリオ ===
    st.markdown("### Myポートフォリオ")
    
    # 起動時にファイルから読み込む
    if "my_portfolio" not in st.session_state:
        st.session_state["my_portfolio"] = load_portfolio()
    
    if st.button("ポートフォリオ編集", use_container_width=True):
        portfolio_dialog()

    pf_df = st.session_state["my_portfolio"]
    
    if not pf_df.empty:
        total_pl = 0
        current_total = 0
        
        for index, row in pf_df.iterrows():
            try:
                p_ticker = row["銘柄コード"]
                p_name = row["銘柄名"] if "銘柄名" in row and row["銘柄名"] else p_ticker
                p_qty = float(row["保有株数"]) if row["保有株数"] else 0
                p_cost = float(row["取得単価"]) if row["取得単価"] else 0
                
                if p_ticker and p_qty > 0:
                    import yfinance as yf
                    hist = yf.Ticker(p_ticker).history(period="1d")
                    if not hist.empty:
                        cur_price = hist['Close'].iloc[-1]
                        val = cur_price * p_qty
                        cost = p_cost * p_qty
                        current_total += val
                        total_pl += (val - cost)
            except:
                pass
        
        if current_total > 0:
            pl_color = "green" if total_pl >= 0 else "red"
            st.markdown(f"""
            <div style="background-color: #161b22; padding: 10px; border-radius: 5px; margin-top: 5px; margin-bottom: 10px;">
                <small>評価額合計</small> <b>{current_total:,.0f}</b><br>
                <small>含み損益</small> <b style="color:{pl_color}">{total_pl:+,.0f}</b>
            </div>
            """, unsafe_allow_html=True)

    st.markdown("---")

    # === 銘柄選択 ===
    input_mode = st.radio("入力モード", ["リストから選択", "コード直接入力"], horizontal=True)
    
    if input_mode == "リストから選択":
        company_dict = utils.COMPANY_DICT
        cat = st.selectbox("業種選択", list(company_dict.keys()))
        name_selected = st.selectbox("銘柄選択", list(company_dict[cat].keys()))
        ticker = company_dict[cat][name_selected]
        company_name = name_selected
    else:
        st.markdown("<small>例: 7203.T / NVDA</small>", unsafe_allow_html=True)
        ticker_input = st.text_input("銘柄コード", value="7203.T").upper()
        ticker = ticker_input.strip()
        company_name = get_company_name_cached(ticker) if ticker else "未入力"

    period = st.select_slider("期間", options=["3mo", "6mo", "1y", "2y"], value="6mo")


# --- 4. データ取得 ---
if ticker:
    df = data_loader.fetch_stock_data(ticker, period=period)
    if df is not None and not df.empty:
        result = models.run_ai_prediction(df)
    else:
        result = None
        
    fund_data = get_fundamentals_cached_v3(ticker)
    macro_df = get_macro_data_cached("2y")
else:
    result = None

is_foreign = ((".T" not in ticker) and (ticker.isalpha() or "-" in ticker))
currency = "$" if is_foreign else "¥"
fmt = ",.2f" if is_foreign else ",.0f"

# --- 5. メイン画面 ---
if result:
    df_train = result["df_train"]
    dates = pd.Series(result["future_dates"]).reset_index(drop=True)
    
    f_close = result["f_close"]
    f_high = result["f_high"]
    f_low = result["f_low"]
    f_open = result["f_open"]
    ai_score = result["score"]
    
    var95_pct = result.get("var95", 0.02) 

    # テクニカル指標
    df_train['SMA5'] = df_train['Close'].rolling(window=5).mean()
    df_train['SMA25'] = df_train['Close'].rolling(window=25).mean()
    
    delta = df_train['Close'].diff()
    gain = (delta.where(delta > 0, 0)).fillna(0)
    loss = (-delta.where(delta < 0, 0)).fillna(0)
    rs = gain.rolling(14).mean() / loss.rolling(14).mean()
    df_train['RSI'] = 100 - (100 / (1 + rs))

    exp12 = df_train['Close'].ewm(span=12, adjust=False).mean()
    exp26 = df_train['Close'].ewm(span=26, adjust=False).mean()
    df_train['MACD'] = exp12 - exp26
    df_train['Signal'] = df_train['MACD'].ewm(span=9, adjust=False).mean()
    df_train['Hist'] = df_train['MACD'] - df_train['Signal']

    last_price = df_train['Close'].iloc[-1]
    prev_price = df_train['Close'].iloc[-2]
    diff = last_price - prev_price
    diff_percent = (diff / prev_price) * 100
    
    # --- ターゲット計算 ---
    limit_days = 14
    search_range = min(limit_days, len(f_high))
    
    target_price = np.max(f_high[:search_range])
    target_idx = np.argmax(f_high[:search_range])
    target_date = dates[target_idx].strftime('%m/%d')
    
    upside_amount = target_price - last_price
    upside_percent = (upside_amount / last_price) * 100
    
    next_price = f_close[0]
    next_date_str = dates[0].strftime('%m/%d')
    next_diff = next_price - last_price

    if is_foreign:
        upside_str = f"{upside_amount:+,.2f} (+{upside_percent:.2f}%)"
    else:
        upside_str = f"{upside_amount:+,.0f} (+{upside_percent:.2f}%)"
    
    # === HEADER ===
    st.markdown(f"### {company_name} <span style='color:gray;'>({ticker})</span>", unsafe_allow_html=True)
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("現在値", f"{currency}{last_price:{fmt}}", f"{diff:+.2f} ({diff_percent:+.2f}%)")
    m2.metric(f"AI予想 ({next_date_str})", f"{currency}{next_price:{fmt}}", f"{next_diff:+.2f}")
    m3.metric("AI信頼度", f"{ai_score:.1f}%")
    m4.metric(f"最高値予測 ({target_date})", f"{currency}{target_price:{fmt}}", upside_str)

    st.markdown("---")

    # === FUNDAMENTALS ===
    f1, f2, f3, f4 = st.columns(4)
    f1.metric("PER (割安性)", fund_data['PER'])
    f2.metric("PBR (資産倍率)", fund_data['PBR'])
    f3.metric("配当利回り", fund_data['配当利回り'])
    f4.metric("時価総額", fund_data['時価総額'])

    st.markdown("---")
    
    # === CHART SECTION ===
    st.markdown("#### チャート & マクロ環境")

    fig = make_subplots(rows=3, cols=1, shared_xaxes=True, vertical_spacing=0.03, row_heights=[0.6, 0.2, 0.2], subplot_titles=("価格予測", "RSI", "MACD"))
    
    fig.add_trace(go.Candlestick(x=df_train.index, open=df_train['Open'], high=df_train['High'], low=df_train['Low'], close=df_train['Close'], name="実績", increasing_line_color='#00C853', decreasing_line_color='#FF3D00'), row=1, col=1)
    fig.add_trace(go.Candlestick(x=dates, open=f_open, high=f_high, low=f_low, close=f_close, name="AI予測", increasing_line_color='#00E5FF', decreasing_line_color='#FF4081'), row=1, col=1)
    
    if 'AI_Trend' in df_train.columns:
        fig.add_trace(go.Scatter(x=df_train.index, y=df_train['AI_Trend'], mode='lines', name='AIトレンド線', line=dict(color='yellow', width=1, dash='dot')), row=1, col=1)
        
    fig.add_trace(go.Scatter(x=df_train.index, y=df_train['SMA5'], mode='lines', name='5日線', line=dict(color='#FFA726', width=1), visible='legendonly'), row=1, col=1)
    fig.add_trace(go.Scatter(x=df_train.index, y=df_train['SMA25'], mode='lines', name='25日線', line=dict(color='#29B6F6', width=1), visible='legendonly'), row=1, col=1)
    
    fig.add_trace(go.Scatter(x=df_train.index, y=df_train['RSI'], mode='lines', name='RSI', line=dict(color='#D1C4E9', width=1.5), showlegend=False), row=2, col=1)
    fig.add_hline(y=70, line_dash="dot", line_color="red", row=2, col=1, opacity=0.5)
    fig.add_hline(y=30, line_dash="dot", line_color="cyan", row=2, col=1, opacity=0.5)
    
    fig.add_trace(go.Bar(x=df_train.index, y=df_train['Hist'], name='MACD', marker_color='gray', opacity=0.3, showlegend=False), row=3, col=1)
    fig.add_trace(go.Scatter(x=df_train.index, y=df_train['MACD'], mode='lines', name='MACD', line=dict(color='#00E676', width=1.5), showlegend=False), row=3, col=1)
    fig.add_trace(go.Scatter(x=df_train.index, y=df_train['Signal'], mode='lines', name='Signal', line=dict(color='#FF5252', width=1.5), showlegend=False), row=3, col=1)

    fig.update_layout(template="plotly_dark", height=800, xaxis_rangeslider_visible=False, hovermode='x unified', legend=dict(orientation="v", yanchor="top", y=0.99, xanchor="left", x=0.01, bgcolor="rgba(0,0,0,0.5)"), margin=dict(l=10, r=10, t=30, b=10))
    st.plotly_chart(fig, use_container_width=True)

    if macro_df is not None and not macro_df.empty:
        fig_macro = make_subplots(specs=[[{"secondary_y": True}]])
        fig_macro.add_trace(go.Scatter(x=macro_df.index, y=macro_df['^GSPC'], name="S&P 500", line=dict(color='#2196F3')), secondary_y=False)
        fig_macro.add_trace(go.Scatter(x=macro_df.index, y=macro_df['^TNX'], name="米国10年債利回り", line=dict(color='#FF5722', dash='dot')), secondary_y=True)
        fig_macro.update_layout(template="plotly_dark", height=300, hovermode='x unified', legend=dict(orientation="h", y=1.1), margin=dict(l=10, r=10, t=10, b=10))
        fig_macro.update_yaxes(title_text="S&P 500", secondary_y=False, showgrid=False)
        fig_macro.update_yaxes(title_text="利回り (%)", secondary_y=True, showgrid=True)
        st.plotly_chart(fig_macro, use_container_width=True)
    else:
        st.warning("マクロデータの取得に失敗しました。")

    st.markdown("---")

    # === TOOLS SECTION ===
    st.markdown("#### データ詳細 & 投資シミュレーター")
    
    col_table, col_sim = st.columns([1, 1.3])
    
    with col_table:
        st.markdown("##### 直近 & 予測データ")
        past = df_train.tail(4).copy()
        df_past = pd.DataFrame({"日付": [d.strftime('%m/%d') for d in past.index], "始値": past['Open'], "高値": past['High'], "安値": past['Low'], "終値": past['Close'], "Type": ["実績"]*4})
        df_future = pd.DataFrame({
            "日付": [d.strftime('%m/%d') for d in dates[:5]], 
            "始値": f_open[:5], "高値": f_high[:5], "安値": f_low[:5], "終値": f_close[:5], 
            "Type": ["予測"]*5
        })
        merged = pd.concat([df_past, df_future], ignore_index=True)
        
        st.dataframe(
            merged.style.format({"始値":"{:,.2f}","高値":"{:,.2f}","安値":"{:,.2f}","終値":"{:,.2f}"})
            .applymap(lambda v: 'color: #00E5FF; font-weight: bold;' if v == '予測' else '', subset=['Type']), 
            use_container_width=True, 
            hide_index=True
        )

    with col_sim:
        st.markdown("##### 期待値・リスク計算")
        default_units = 10 if is_foreign else 100
        default_invest = int(last_price * default_units)
        
        c_input, _ = st.columns([1, 0.1])
        with c_input:
            invest_amount = st.number_input(f"投資金額 ({currency})", min_value=0, value=default_invest, step=10000)
            shares_est = invest_amount / last_price
            st.caption(f"1株価格: {currency}{last_price:{fmt}} | 取得可能株数: 約 {shares_est:.1f} 株")

        potential_profit = (target_price - last_price) * shares_est
        expected_value = potential_profit * (ai_score / 100)
        var_loss = invest_amount * var95_pct
        
        st.markdown("---")
        
        r1, r2, r3 = st.columns(3)
        r1.metric("最大利益", f"+{currency}{potential_profit:,.0f}", f"目標値")
        r2.metric("期待値", f"+{currency}{expected_value:,.0f}", f"自信度{ai_score:.0f}%")
        r3.metric("VaR(95%)", f"-{currency}{var_loss:,.0f}")
        
        st.progress(int(ai_score))
        st.info(f"VaR分析: 統計的に95%の確率で、1日の損失はこの金額({var95_pct*100:.2f}%)以内に収まると予測されます。")

    st.markdown("---")

    # === AI REPORT ===
    st.markdown("#### AIレポート")

    if "last_ticker" not in st.session_state:
        st.session_state["last_ticker"] = None
    if "cached_comment" not in st.session_state:
        st.session_state["cached_comment"] = ""

    if st.session_state["last_ticker"] != ticker:
        st.session_state["cached_comment"] = ""
        st.session_state["last_ticker"] = ticker
    
    with st.status("市場データを分析中...", expanded=True) as status:
        if st.session_state["cached_comment"]:
            comment = st.session_state["cached_comment"]
            status.write("保存されたレポートを表示します")
        else:
            comment = get_cached_ai_comment(ticker, company_name, df_train, f_close, ai_score, fund_data)
            st.session_state["cached_comment"] = comment
        
        status.update(label="分析完了", state="complete")
        st.markdown(f'<div class="ai-console">{comment.replace(chr(10), "<br>")}</div>', unsafe_allow_html=True)

    # === サイドバー下部：通知機能 ===
    with st.sidebar:
        st.markdown("---")
        # 1. Discord
        st.markdown("### 通知設定 (Discord)")
        st.caption("Webhook URLを入力")
        user_discord_url = st.text_input("Webhook URL (Discord)", value="", type="password", key="sidebar_discord_webhook")
        
        if not pf_df.empty:
             if st.button("ポートフォリオのアラートをチェック (Discord)", type="secondary", use_container_width=True):
                if not user_discord_url:
                    st.error("URLを入力してください")
                else:
                    alert_log = []
                    with st.status("価格をチェック中...", expanded=True) as status:
                        import yfinance as yf
                        for index, row in pf_df.iterrows():
                            t_code = row["銘柄コード"]
                            t_name = row["銘柄名"] if "銘柄名" in row and row["銘柄名"] else t_code
                            t_target = float(row["通知価格"]) if row["通知価格"] else 0
                            if t_code:
                                try:
                                    cur = yf.Ticker(t_code).history(period="1d")['Close'].iloc[-1]
                                    st.write(f"{t_name}: {cur:,.0f}")
                                    if t_target > 0 and cur >= t_target:
                                        alert_log.append(f"**{t_name}** ({t_code}) が目標到達！\n現在値: {cur:,.0f} (目標: {t_target:,.0f})")
                                except:
                                    pass
                        
                        if alert_log:
                            msg_body = "**【目標株価到達アラート】**\n" + "\n".join(alert_log)
                            res = utils.send_discord_notification(user_discord_url, msg_body)
                            status.update(label="通知を送信しました！", state="complete")
                            st.success("通知しました")
                        else:
                            status.update(label="目標到達銘柄なし", state="complete")
                            st.info("目標を超えている銘柄はありません")

        if st.button("分析結果を送信 (Discord)", use_container_width=True):
            if not user_discord_url:
                st.error("URLを入力してください")
            else:
                with st.spinner("送信中..."):
                    msg = f"**【AI株価分析】 {company_name} ({ticker})**\n"
                    msg += f"現在値: {currency}{last_price:{fmt}} / AI信頼度: {ai_score:.1f}%\n"
                    msg += "--------------------------------\n"
                    msg += comment[:1500] + "..." 
                    
                    res = utils.send_discord_notification(user_discord_url, msg)
                    if "成功" in res:
                        st.success("通知を送信しました")
                    else:
                        st.error(res)

        st.markdown("---")

        # 2. Slack
        st.markdown("### 通知設定 (Slack)")
        st.caption("Webhook URLを入力")
        user_slack_url = st.text_input("Webhook URL (Slack)", value="", type="password", key="sidebar_slack_webhook")

        if not pf_df.empty:
             if st.button("ポートフォリオのアラートをチェック (Slack)", type="secondary", use_container_width=True):
                if not user_slack_url:
                    st.error("URLを入力してください")
                else:
                    alert_log = []
                    with st.status("価格をチェック中...", expanded=True) as status:
                        import yfinance as yf
                        for index, row in pf_df.iterrows():
                            t_code = row["銘柄コード"]
                            t_name = row["銘柄名"] if "銘柄名" in row and row["銘柄名"] else t_code
                            t_target = float(row["通知価格"]) if row["通知価格"] else 0
                            if t_code:
                                try:
                                    cur = yf.Ticker(t_code).history(period="1d")['Close'].iloc[-1]
                                    st.write(f"{t_name}: {cur:,.0f}")
                                    if t_target > 0 and cur >= t_target:
                                        alert_log.append(f"*{t_name}* ({t_code}) が目標到達！\n現在値: {cur:,.0f} (目標: {t_target:,.0f})")
                                except:
                                    pass
                        
                        if alert_log:
                            msg_body = "*【目標株価到達アラート】*\n" + "\n".join(alert_log)
                            res = utils.send_slack_notification(user_slack_url, msg_body)
                            status.update(label="通知を送信しました！", state="complete")
                            st.success("通知しました")
                        else:
                            status.update(label="目標到達銘柄なし", state="complete")
                            st.info("目標を超えている銘柄はありません")

        if st.button("分析結果を送信 (Slack)", use_container_width=True):
            if not user_slack_url:
                st.error("URLを入力してください")
            else:
                with st.spinner("送信中..."):
                    msg = f"*【AI株価分析】 {company_name} ({ticker})*\n"
                    msg += f"現在値: {currency}{last_price:{fmt}} / AI信頼度: {ai_score:.1f}%\n"
                    msg += "--------------------------------\n"
                    msg += comment[:1500] + "..." 
                    
                    res = utils.send_slack_notification(user_slack_url, msg)
                    if "成功" in res:
                        st.success("通知を送信しました")
                    else:
                        st.error(res)

else:
    st.error("データ取得エラー: 銘柄コードを確認してください")