import yfinance as yf
import pandas as pd
from datetime import timedelta
import requests
import json
import toml
import os

# --- 銘柄リスト ---
COMPANY_DICT = {
    "国内株式（電気機器・輸送用機器）": {
        "日立製作所": "6501.T", "トヨタ自動車": "7203.T", 
        "ソニーグループ": "6758.T", "キーエンス": "6861.T"
    },
    "国内株式（情報・通信・サービス）": {
        "ソフトバンクグループ": "9984.T", "任天堂": "7974.T", 
        "日本電信電話 (NTT)": "9432.T", "楽天グループ": "4755.T"
    },
    "国内株式（銀行・卸売・商社）": {
        "三菱UFJフィナンシャルG": "8306.T", "三菱商事": "8058.T", "伊藤忠商事": "8001.T"
    },
    "外国株式・暗号資産": {
        "Apple Inc.": "AAPL", "Alphabet (Google)": "GOOGL", 
        "Microsoft Corp": "MSFT", "NVIDIA Corp": "NVDA",
        "ビットコイン (BTC)": "BTC-USD" 
    }
}

def get_ticker_info(ticker):
    try:
        t = yf.Ticker(ticker)
        info = t.info
        name = info.get('shortName') or info.get('longName') or ticker
        return name
    except:
        return ticker

def get_fundamentals(ticker):
    """財務指標を取得（3段階の配当取得ロジック）"""
    try:
        t = yf.Ticker(ticker)
        info = t.info
        
        # PER, PBR, 時価総額
        per = info.get('trailingPE', '-')
        pbr = info.get('priceToBook', '-')
        mkt_cap = info.get('marketCap', '-')
        
        # --- 配当利回り 3段階チャレンジ ---
        final_div = None

        # 1. まず通常の dividendYield をチェック
        div1 = info.get('dividendYield')
        if isinstance(div1, (int, float)) and 0 < div1 < 0.2: # 0%〜20%なら採用
            final_div = div1
        
        # 2. ダメなら trailingAnnualDividendYield (過去1年実績) をチェック
        if final_div is None:
            div2 = info.get('trailingAnnualDividendYield')
            if isinstance(div2, (int, float)) and 0 < div2 < 0.2:
                final_div = div2
        
        # 3. それでもダメなら 手動計算 (配当金 ÷ 株価)
        if final_div is None:
            try:
                rate = info.get('dividendRate')
                price = info.get('currentPrice') or info.get('regularMarketPrice') or info.get('previousClose')
                if rate and price and price > 0:
                    calc_div = rate / price
                    if 0 < calc_div < 0.2: # 計算結果が正常なら採用
                        final_div = calc_div
            except:
                pass

        # 結果のフォーマット
        if final_div is not None:
            div_str = f"{final_div*100:.2f}%"
        else:
            div_str = "-"
        # --------------------------------

        # 時価総額の単位調整
        if isinstance(mkt_cap, (int, float)):
            if mkt_cap > 1_000_000_000_000:
                cap_str = f"{mkt_cap/1_000_000_000_000:.1f}兆"
            elif mkt_cap > 100_000_000:
                cap_str = f"{mkt_cap/100_000_000:.0f}億"
            else:
                cap_str = f"{mkt_cap:,.0f}"
        else:
            cap_str = "-"
            
        per_str = f"{per:.2f}倍" if isinstance(per, (int, float)) else "-"
        pbr_str = f"{pbr:.2f}倍" if isinstance(pbr, (int, float)) else "-"

        return {
            "PER": per_str, "PBR": pbr_str,
            "配当利回り": div_str, "時価総額": cap_str
        }
    except:
        return {"PER": "-", "PBR": "-", "配当利回り": "-", "時価総額": "-"}

def get_latest_news(ticker):
    try:
        t = yf.Ticker(ticker)
        news_list = t.news
        if not news_list: return "ニュースなし"
        headlines = []
        for n in news_list[:5]:
            title = n.get('title', 'No Title')
            headlines.append(f"・{title}")
        return "\n".join(headlines)
    except:
        return "取得失敗"

def send_discord_notification(webhook_url, message):
    """Discordにメッセージを送信する"""
    if not webhook_url:
        return "Webhook URLが設定されていません"
    
    data = {"content": message}
    headers = {"Content-Type": "application/json"}
    
    try:
        response = requests.post(webhook_url, data=json.dumps(data), headers=headers)
        if response.status_code == 204:
            return "送信成功"
        else:
            return f"送信失敗: {response.status_code}"
    except Exception as e:
        return f"エラー: {str(e)}"

def send_slack_notification(webhook_url, message):
    """Slackにメッセージを送信する"""
    if not webhook_url:
        return "Webhook URLが設定されていません"
    
    # Slackは payload={"text": "..."} の形式
    data = {"text": message}
    headers = {"Content-Type": "application/json"}
    
    try:
        response = requests.post(webhook_url, data=json.dumps(data), headers=headers)
        # Slackは成功時 200 OK を返す
        if response.status_code == 200:
            return "送信成功"
        else:
            return f"送信失敗: {response.status_code} {response.text}"
    except Exception as e:
        return f"エラー: {str(e)}"

def load_secrets():
    """
    secrets.toml を読み込んで辞書として返す。
    Streamlit経由でも、直接実行でも動くようにする。
    """
    # 1. Streamlit経由の場合
    try:
        import streamlit as st
        # st.secretsが辞書としてアクセス可能か確認
        if hasattr(st, "secrets") and st.secrets:
            return st.secrets
    except:
        pass
    
    # 2. ファイルから直接読む場合 (バッチ処理用)
    try:
        # .streamlit/secrets.toml を探す
        path = os.path.join(os.path.dirname(__file__), "..", ".streamlit", "secrets.toml")
        path = os.path.normpath(path)
        if os.path.exists(path):
            return toml.load(path)
    except Exception as e:
        print(f"設定読み込みエラー: {e}")
    
    return {}