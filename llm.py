import google.generativeai as genai
import re
import src.utils as utils # <--- 作成したutilsを使ってニュースを取得

def generate_gemini_comment(api_key, ticker_symbol, company_name, df_train, pred_close, ai_score, fundamentals):
    if not api_key: return "APIキー設定エラー"

    last_price = df_train['Close'].iloc[-1]
    start_price = df_train['Close'].iloc[0]
    trend = "上昇" if last_price > start_price else "下落"
    target_price = pred_close[-1]
    
    confidence = "高い" if ai_score >= 80 else "中程度" if ai_score >= 50 else "低い"
    
    # utilsにある関数を使ってニュースを取得
    recent_news = utils.get_latest_news(ticker_symbol)

    # 配当表示用
    div_display = fundamentals['配当利回り']
    if div_display == "-":
        div_display = "データ取得不可"

    prompt = f"""
    あなたはプロの投資家です。以下のデータを統合し、投資判断レポートを作成してください。

    【分析対象】{company_name} ({ticker_symbol})
    
    【財務指標】
    - PER: {fundamentals['PER']} / PBR: {fundamentals['PBR']}
    - 配当利回り: {div_display} / 時価総額: {fundamentals['時価総額']}

    【テクニカル】
    - 現在値: {last_price:,.0f} / トレンド: {trend}
    - AI予想価格: {target_price:,.0f}
    - AI信頼度: {ai_score:.1f}% ({confidence})
    
    【ニュース】
    {recent_news}

    【指示】
    1. ニュースや経済情勢が追い風か向かい風か。
    2. テクニカル（AI予測）とファンダメンタルズ（割安性・配当）の両面から評価。
    3. プロとしての結論（買い・様子見・売りなど）。
    
    ※Markdownの見出しやボールド記号は使わず、平文で書いてください。
    """

    try:
        genai.configure(api_key=api_key)
        # ユーザー指定の最新モデルを使用
        model = genai.GenerativeModel("gemini-2.5-flash") 
        response = model.generate_content(prompt)
        text = re.sub(r'[*#`]', '', response.text) # 記号削除
        return text.strip()
    except Exception as e:
        return f"エラー: {str(e)}"