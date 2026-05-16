import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from datetime import timedelta
import config  # <--- 設定ファイルを読み込み

# --- AI予測・計算ロジック ---
def run_ai_prediction(df, training_days=config.TRAINING_DAYS, future_days=config.FUTURE_DAYS):
    # 2. 学習
    df_train = df.tail(training_days).copy()
    df_train['DayCount'] = np.arange(len(df_train))
    
    X = df_train[['DayCount']]
    y = df_train['Close']

    model = RandomForestRegressor(n_estimators=100, max_depth=5, random_state=config.RANDOM_SEED)
    
    # --- NaN（欠損値）が含まれる行をきれいに削除する ---
    valid_idx = ~np.isnan(y) & ~pd.DataFrame(X).isna().any(axis=1)
    X_clean, y_clean = X[valid_idx], y[valid_idx]
    
    model.fit(X_clean, y_clean)
    
    # 欠損値を除いた状態で予測すると行数がズレるため、予測時は元のXを使う
    df_train['AI_Trend'] = model.predict(X)
    score = model.score(X_clean, y_clean) * 100
    
    recent_trend = df_train['AI_Trend'].iloc[-1] - df_train['AI_Trend'].iloc[-5]
    trend_slope = recent_trend / 5

    # 3. ボラティリティ計算
    returns = np.log(1 + df_train['Close'].pct_change())
    daily_volatility = returns.std()
    
    # VaR計算 (configのZスコアを使用)
    var_95_percent = daily_volatility * config.VAR_Z_SCORE
    
    daily_range_pct = ((df_train['High'] - df_train['Low']) / df_train['Open']).mean()
    if np.isnan(daily_range_pct):
        daily_range_pct = 0.02 

    # 4. 未来のローソク足生成
    last_close = df_train['Close'].iloc[-1]
    last_date = df_train.index[-1]
    
    future_dates = []
    f_open = []
    f_high = []
    f_low = []
    f_close = []
    
    current_price = last_close
    np.random.seed(config.RANDOM_SEED) # シードもconfigから

    for i in range(1, future_days + 1):
        next_date = last_date + timedelta(days=i)
        future_dates.append(next_date)
        
        sim_open = current_price
        
        drift = trend_slope / last_close
        shock = np.random.normal(0, daily_volatility)
        sim_close = sim_open * (1 + drift + shock)
        
        body_high = max(sim_open, sim_close)
        body_low = min(sim_open, sim_close)
        
        upper_wick = sim_open * daily_range_pct * np.random.uniform(0.1, 0.8)
        lower_wick = sim_open * daily_range_pct * np.random.uniform(0.1, 0.8)
        
        sim_high = body_high + upper_wick
        sim_low = body_low - lower_wick
        
        f_open.append(sim_open)
        f_high.append(sim_high)
        f_low.append(sim_low)
        f_close.append(sim_close)
        
        current_price = sim_close

    return {
        "df_train": df_train,
        "future_dates": pd.Series(future_dates),
        "f_open": np.array(f_open),
        "f_high": np.array(f_high),
        "f_low": np.array(f_low),
        "f_close": np.array(f_close),
        "score": score,
        "var95": var_95_percent
    }