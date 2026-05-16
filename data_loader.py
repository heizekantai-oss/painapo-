import yfinance as yf
import streamlit as st
import pandas as pd
import config  # <--- 設定ファイルを読み込み

# --- 為替レート取得 ---
@st.cache_data(ttl=3600) 
def get_usd_jpy_rate():
    try:
        # configから通貨ペアを取得
        ticker_data = yf.Ticker(config.CURRENCY_PAIR)
        history = ticker_data.history(period="1d")
        if not history.empty:
            return history['Close'].iloc[-1]
        return 155.0 
    except:
        return 155.0

# --- 株価データ取得 ---
def fetch_stock_data(ticker, period="2y"):
    df = yf.download(ticker, period=period, progress=False)
    
    if isinstance(df.columns, pd.MultiIndex):
        try:
            df = df.xs(ticker, axis=1, level=1)
        except:
            try:
                df.columns = df.columns.get_level_values(0)
            except:
                pass
        
    if df.empty:
        return None
    
    return df

# --- マクロ経済データ取得 ---
def get_macro_trend(period="2y"):
    try:
        # configからマクロ指標リストを取得
        tickers = config.MACRO_TICKERS
        data = yf.download(tickers, period=period, progress=False, group_by='ticker')
        
        df_macro = pd.DataFrame()
        
        # 指標名をconfigから動的に取得するのは少し複雑になるため、
        # ここでは固定のキー名 '^TNX', '^GSPC' を維持しつつ、リストはconfig由来とします
        if isinstance(data.columns, pd.MultiIndex):
            try:
                df_macro['^TNX'] = data['^TNX']['Close']
                df_macro['^GSPC'] = data['^GSPC']['Close']
            except:
                try:
                    df_macro['^TNX'] = data[('^TNX', 'Close')]
                    df_macro['^GSPC'] = data[('^GSPC', 'Close')]
                except:
                    data_flat = data.copy()
                    data_flat.columns = ['_'.join(col).strip() for col in data_flat.columns.values]
                    tnx_col = [c for c in data_flat.columns if '^TNX' in c and 'Close' in c][0]
                    gspc_col = [c for c in data_flat.columns if '^GSPC' in c and 'Close' in c][0]
                    df_macro['^TNX'] = data_flat[tnx_col]
                    df_macro['^GSPC'] = data_flat[gspc_col]

        else:
            df_macro['^TNX'] = data['Close']['^TNX']
            df_macro['^GSPC'] = data['Close']['^GSPC']
            
        return df_macro.ffill().dropna()
    except Exception as e:
        print(f"Macro Data Error: {e}")
        return None