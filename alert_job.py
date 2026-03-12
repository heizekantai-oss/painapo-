import pandas as pd
import yfinance as yf
import src.utils as utils
import os

# --- 1. GitHubの金庫（Secrets）からURLを読み込む ---
# ユーザーが画面から入力したURLが、この変数（環境変数）に渡される仕組みです
SLACK_WEBHOOK_URL = os.environ.get("SLACK_WEBHOOK_URL")
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")

PORTFOLIO_FILE = "portfolio.csv"

def main():
    print("--- 画面登録銘柄の自動チェック開始 ---")
    
    # 2. ポートフォリオファイルの読み込み
    base_dir = os.path.dirname(os.path.abspath(__file__))
    file_path = os.path.join(base_dir, PORTFOLIO_FILE)

    if not os.path.exists(file_path):
        print(f"通知対象なし: {PORTFOLIO_FILE} がまだ作成されていません。")
        return

    try:
        df = pd.read_csv(file_path)
    except Exception as e:
        print(f"ファイル読み込みエラー: {e}")
        return

    if df.empty:
        print("ポートフォリオに銘柄が登録されていません。")
        return

    # 3. 1行ずつ（ユーザーが登録した銘柄ごとに）チェック
    for index, row in df.iterrows():
        # CSVの列名は、お手元の「マイポートフォリオ」機能の保存形式に合わせています
        t_code = row.get("銘柄コード")
        t_name = row.get("銘柄名") or t_code
        t_target = row.get("通知価格")

        if not t_code or pd.isna(t_target):
            continue

        try:
            t_target = float(t_target)
            ticker = yf.Ticker(str(t_code))
            hist = ticker.history(period="1d")
            
            if not hist.empty:
                cur_price = hist['Close'].iloc[-1]
                print(f"チェック中: {t_name} ({t_code}) -> 現在値: {cur_price:,.1f}")

                # 目標超え判定
                if cur_price >= t_target:
                    message = f"🌟【目標到達！】\nあなたが登録した銘柄が目標価格を超えました。\n\n銘柄: {t_name} ({t_code})\n現在値: {cur_price:,.1f}\n目標値: {t_target:,.1f}"
                    
                    # 💡 登録されているURLすべてに送る（ユーザーが指定した宛先に届く）
                    if SLACK_WEBHOOK_URL:
                        utils.send_slack_notification(SLACK_WEBHOOK_URL, message)
                        print(f"  -> ✅ Slackに通知しました")
                    
                    if DISCORD_WEBHOOK_URL:
                        utils.send_discord_notification(DISCORD_WEBHOOK_URL, message)
                        print(f"  -> ✅ Discordに通知しました")
        
        except Exception as e:
            print(f"⚠️ エラー ({t_code}): {e}")

    print("--- 全チェック完了 ---")

if __name__ == "__main__":
    main()