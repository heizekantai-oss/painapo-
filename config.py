# --- アプリケーション設定ファイル ---

# アプリケーション基本情報
APP_TITLE = "AI株価予測"

# AI設定
TRAINING_DAYS = 180       # AIが学習する過去の日数
FUTURE_DAYS = 30          # AIが予測する未来の日数
RANDOM_SEED = 42          # 再現性のための乱数シード

# 投資シミュレーター設定
VAR_CONFIDENCE_LEVEL = 0.95   # VaRの信頼区間
VAR_Z_SCORE = 1.645           # 95%信頼区間のZスコア
TARGET_SEARCH_DAYS = 14       # 最高値予測を探す範囲（直近何日か）

# データ取得設定
CURRENCY_PAIR = "JPY=X"       # 為替レート取得用シンボル
DEFAULT_TICKER = "7203.T"     # デフォルト銘柄（トヨタ）
MACRO_TICKERS = ["^TNX", "^GSPC"]  # マクロ指標（米国債10年、S&P500）

# チャート設定
CHART_HEIGHT = 800
MACRO_CHART_HEIGHT = 300