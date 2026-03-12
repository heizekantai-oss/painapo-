import os
import json
import gspread
import yfinance as yf
import src.utils as utils

# --- 設定 ---
SLACK_WEBHOOK_URL = os.environ.get("SLACK_WEBHOOK_URL")
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")
# ▼▼ STEP2でメモしたあなたのスプレッドシートIDをここに貼る ▼▼
SPREADSHEET_ID = "1mdzl7Ihjx2usKQd_uAz83te167B5N-XiGYqm2_c5oUU"

def main():
    print("--- 🌐 スプレッドシート連携アラート開始 ---")

    # 1. Google Sheetsに合鍵を使ってログイン
    gcp_cred_json = os.environ.get("GCP_CREDENTIALS")
    if not gcp_cred_json:
        print("🚨 エラー: GitHubの金庫に GCP_CREDENTIALS がありません！")
        return

    try:
        # JSONの合鍵を読み込んでスプレッドシートを開く
        creds_dict = json.loads(gcp_cred_json)
        gc = gspread.service_account_from_dict(creds_dict)
        workbook = gc.open_by_key(SPREADSHEET_ID)
        worksheet = workbook.sheet1  # 1番左のシートを指定
        
        # シートの中身を全部取得する
        records = worksheet.get_all_records()
    except Exception as e:
        print(f"⚠️ スプレッドシート読み込みエラー: {e}")
        return

    if not records:
        print("シートに銘柄が登録されていません。")
        return

    # 2. 取得したデータをもとに株価をチェック
    for row in records:
        t_code = row.get("銘柄コード")
        t_name = row.get("銘柄名") or t_code
        t_target = row.get("通知価格")
        dest = str(row.get("通知先", "SLACK")).upper()

        if not t_code or not t_target:
            continue

        try:
            t_target = float(t_target)
            ticker = yf.Ticker(str(t_code))
            hist = ticker.history(period="1d")
            
            if not hist.empty:
                cur_price = hist['Close'].iloc[-1]
                print(f"チェック中: {t_name} ({t_code}) -> 現在値: {cur_price:,.1f} (目標: {t_target:,.1f})")

                # 目標到達で通知！
                if cur_price >= t_target:
                    message = f"🌟【目標到達！】\nあなたが登録した銘柄が目標価格を超えました。\n\n銘柄: {t_name} ({t_code})\n現在値: {cur_price:,.1f}\n目標値: {t_target:,.1f}"
                    
                    if dest == "SLACK" and SLACK_WEBHOOK_URL:
                        utils.send_slack_notification(SLACK_WEBHOOK_URL, message)
                        print(f"  -> ✅ Slackに通知しました")
                    elif dest == "DISCORD" and DISCORD_WEBHOOK_URL:
                        utils.send_discord_notification(DISCORD_WEBHOOK_URL, message)
                        print(f"  -> ✅ Discordに通知しました")
        
        except Exception as e:
            print(f"⚠️ エラー ({t_code}): {e}")

    print("--- 全チェック完了 ---")

if __name__ == "__main__":
    main()