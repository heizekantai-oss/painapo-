import pandas as pd
import yfinance as yf
import src.utils as utils
import os

# --- 設定読み込み ---
SECRETS = utils.load_secrets()
SLACK_WEBHOOK_URL = SECRETS.get("slack_webhook_url", "")
DISCORD_WEBHOOK_URL = SECRETS.get("discord_webhook_url", "") # Discordを追加

PORTFOLIO_FILE = "portfolio.csv"

def main():
    print("--- 株価アラートジョブ開始 ---")
    
    # 1. Webhook URLの確認
    if not SLACK_WEBHOOK_URL and not DISCORD_WEBHOOK_URL:
        print("エラー: secrets.toml に通知用URL (Slack または Discord) が設定されていません")
        return

    # 2. ファイルの読み込み
    # スクリプトの場所を基準にファイルパスを解決
    base_dir = os.path.dirname(os.path.abspath(__file__))
    file_path = os.path.join(base_dir, PORTFOLIO_FILE)

    if not os.path.exists(file_path):
        print(f"エラー: {PORTFOLIO_FILE} が見つかりません。アプリでポートフォリオを作成してください。")
        return

    df = pd.read_csv(file_path)
    if df.empty:
        print("ポートフォリオが空です")
        return

    # 3. 株価チェック
    alert_log = []
    
    for index, row in df.iterrows():
        t_code = row["銘柄コード"]
        t_name = row["銘柄名"] if "銘柄名" in row and row["銘柄名"] else t_code
        t_target = float(row["通知価格"]) if row["通知価格"] else 0
        
        if t_code and t_target > 0:
            try:
                # 現在値取得
                ticker = yf.Ticker(t_code)
                hist = ticker.history(period="1d")
                if not hist.empty:
                    cur_price = hist['Close'].iloc[-1]
                    print(f"チェック中: {t_name} ({t_code}) -> {cur_price:,.0f} (目標: {t_target:,.0f})")
                    
                    # 目標超え判定
                    if cur_price >= t_target:
                        # メッセージは見やすさ重視で共通フォーマットにします
                        alert_log.append(f"【到達】 {t_name} ({t_code})\n   現在値: {cur_price:,.0f} (目標: {t_target:,.0f})")
            except Exception as e:
                print(f"エラー ({t_code}): {e}")

    # 4. 通知送信
    if alert_log:
        msg_body = "\n------------------\n".join(alert_log)
        
        # Slackに送信
        if SLACK_WEBHOOK_URL:
            slack_msg = "*【朝の自動チェック】*\n" + msg_body
            res_slack = utils.send_slack_notification(SLACK_WEBHOOK_URL, slack_msg)
            print(f"Slack通知: {res_slack}")
            
        # Discordに送信
        if DISCORD_WEBHOOK_URL:
            discord_msg = "**【朝の自動チェック】**\n" + msg_body
            res_discord = utils.send_discord_notification(DISCORD_WEBHOOK_URL, discord_msg)
            print(f"Discord通知: {res_discord}")
            
    else:
        print("目標到達銘柄はありませんでした")

    print("--- 完了 ---")

if __name__ == "__main__":
    main()