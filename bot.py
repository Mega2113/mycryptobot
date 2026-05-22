import os
import requests
import pandas as pd
import ta
import time
import numpy as np

TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
CHAT_ID = os.environ["CHAT_ID"]

def get_all_pairs():
    url = "https://data-api.binance.vision/api/v3/exchangeInfo"
    r = requests.get(url, timeout=10)
    symbols = r.json()["symbols"]
    usdt_pairs = [
        s["symbol"] for s in symbols
        if s["symbol"].endswith("USDT") and s["status"] == "TRADING"
    ]
    return usdt_pairs

def get_data(symbol, interval="4h"):
    url = "https://data-api.binance.vision/api/v3/klines"
    params = {"symbol": symbol, "interval": interval, "limit": 300}
    r = requests.get(url, params=params, timeout=10)
    data = r.json()
    if not data or len(data) < 60:
        return None
    df = pd.DataFrame(data, columns=[
        "time","open","high","low","close","volume",
        "close_time","quote_vol","trades","taker_buy_base",
        "taker_buy_quote","ignore"
    ])
    df = df[["time","open","high","low","close","volume"]].astype(float)
    return df

def calculate_fibonacci(df):
    recent = df.tail(100)
    high = recent["high"].max() if "high" in recent.columns else recent["close"].max()
    low = recent["low"].min() if "low" in recent.columns else recent["close"].min()
    diff = high - low
    levels = {
        "0.0":   high,
        "0.236": high - diff * 0.236,
        "0.382": high - diff * 0.382,
        "0.5":   high - diff * 0.5,
        "0.618": high - diff * 0.618,
        "0.786": high - diff * 0.786,
        "1.0":   low
    }
    return levels, high, low

def get_fib_zone(price, levels):
    if price <= levels["0.5"]:
        if price <= levels["0.618"]:
            return "STRONG_BUY", "0.618 (Golden Ratio)"
        return "BUY", "0.5"
    else:
        if price >= levels["0.236"]:
            return "STRONG_SELL", "0.236"
        return "SELL", "0.5"

def analyze(df):
    df["rsi"] = ta.momentum.RSIIndicator(df["close"]).rsi()
    macd = ta.trend.MACD(df["close"])
    df["macd"] = macd.macd_diff()
    df["ema20"] = ta.trend.EMAIndicator(df["close"], 20).ema_indicator()
    df["ema50"] = ta.trend.EMAIndicator(df["close"], 50).ema_indicator()
    df["ema200"] = ta.trend.EMAIndicator(df["close"], 200).ema_indicator()
    bb = ta.volatility.BollingerBands(df["close"])
    df["bb_high"] = bb.bollinger_hband()
    df["bb_low"] = bb.bollinger_lband()
    df["vol_ma"] = df["volume"].rolling(20).mean()
    df["atr"] = ta.volatility.AverageTrueRange(
        df["close"], df["close"], df["close"]
    ).average_true_range()
    # Stochastic RSI
    stoch_rsi = ta.momentum.StochRSIIndicator(df["close"])
    df["stoch_k"] = stoch_rsi.stochrsi_k()
    df["stoch_d"] = stoch_rsi.stochrsi_d()
    return df

def get_market_trend(df):
    last = df.iloc[-1]
    if last["close"] > last["ema200"]:
        return "BULL"
    return "BEAR"

def check_volume(df):
    last = df.iloc[-1]
    return last["volume"] > last["vol_ma"] * 1.5

def get_signal(df):
    last = df.iloc[-1]
    price = last["close"]
    rsi = last["rsi"]
    macd = last["macd"]
    ema20 = last["ema20"]
    ema50 = last["ema50"]
    bb_low = last["bb_low"]
    bb_high = last["bb_high"]
    stoch_k = last["stoch_k"]
    stoch_d = last["stoch_d"]
    trend = get_market_trend(df)
    high_volume = check_volume(df)

    # Fibonacci
    fib_levels, fib_high, fib_low = calculate_fibonacci(df)
    fib_zone, fib_label = get_fib_zone(price, fib_levels)

    # Support/Resistance
    recent = df.tail(50)
    support = recent["close"].min()
    resistance = recent["close"].max()

    # BUY conditions
    buy_conditions = [
        rsi < 35,                          # RSI oversold
        macd > 0,                          # MACD positive
        ema20 > ema50,                     # Uptrend
        trend == "BULL",                   # Bull market
        price <= bb_low * 1.02,            # Near BB low
        high_volume,                       # High volume
        stoch_k < 0.2 and stoch_d < 0.2,  # Stoch RSI oversold
        fib_zone in ["BUY", "STRONG_BUY"], # Fib buy zone
    ]

    # SELL conditions
    sell_conditions = [
        rsi > 65,                            # RSI overbought
        macd < 0,                            # MACD negative
        ema20 < ema50,                       # Downtrend
        trend == "BEAR",                     # Bear market
        price >= bb_high * 0.98,             # Near BB high
        high_volume,                         # High volume
        stoch_k > 0.8 and stoch_d > 0.8,    # Stoch RSI overbought
        fib_zone in ["SELL", "STRONG_SELL"], # Fib sell zone
    ]

    buy_score = sum(buy_conditions)
    sell_score = sum(sell_conditions)

    if buy_score >= 6:
        return "BUY", buy_score, support, resistance, fib_levels, fib_label
    elif sell_score >= 6:
        return "SELL", sell_score, support, resistance, fib_levels, fib_label

    return None, 0, support, resistance, fib_levels, fib_label

def check_1h(symbol):
    df = get_data(symbol, interval="1h")
    if df is None:
        return None, None
    df = analyze(df)
    last = df.iloc[-1]
    buy_1h = last["rsi"] < 40 and last["macd"] > 0 and last["stoch_k"] < 0.3
    sell_1h = last["rsi"] > 60 and last["macd"] < 0 and last["stoch_k"] > 0.7
    return buy_1h, sell_1h

def format_price(price):
    if price < 0.0001:
        return f"${price:.8f}"
    elif price < 1:
        return f"${price:.6f}"
    elif price < 100:
        return f"${price:.4f}"
    else:
        return f"${price:.2f}"

def build_message(coin, signal, last, score, support, resistance, fib_levels, fib_label):
    price = last["close"]
    atr = last["atr"]
    stoch = last["stoch_k"]
    strength = "⭐⭐⭐⭐⭐" if score == 8 else "⭐⭐⭐⭐" if score >= 6 else "⭐⭐⭐"

    if signal == "BUY":
        tp1 = price + (atr * 1.5)
        tp2 = price + (atr * 3.0)
        tp3 = price + (atr * 5.0)
        sl  = price - (atr * 1.5)
        zone_label = "📥 <b>Buy Zone</b>"
        emoji = "🟢"

        msg = (
            f"🟢 <b>BUY SIGNAL — {coin}</b>\n"
            f"━━━━━━━━━━━━━━━━\n"
            f"💪 Strength : {strength} ({score}/8)\n"
            f"💰 Price : {format_price(price)}\n"
            f"\n"
            f"{zone_label}\n"
            f"   Low  : {format_price(price * 0.998)}\n"
            f"   High : {format_price(price * 1.002)}\n"
            f"\n"
            f"🎯 <b>Take Profit</b>\n"
            f"   TP1 : {format_price(tp1)}\n"
            f"   TP2 : {format_price(tp2)}\n"
            f"   TP3 : {format_price(tp3)}\n"
            f"\n"
            f"🛑 <b>Stop Loss</b> : {format_price(sl)}\n"
            f"\n"
            f"📊 RSI : {last['rsi']:.1f}\n"
            f"📊 Stoch RSI : {stoch:.2f} (oversold)\n"
            f"📐 Fib Level : {fib_label}\n"
            f"📈 Support : {format_price(support)}\n"
            f"📉 Resistance : {format_price(resistance)}\n"
            f"━━━━━━━━━━━━━━━━\n"
            f"⚠️ নিজে বিশ্লেষণ করে trade করুন"
        )
    else:
        tp1 = price - (atr * 1.5)
        tp2 = price - (atr * 3.0)
        tp3 = price - (atr * 5.0)
        sl  = price + (atr * 1.5)

        msg = (
            f"🔴 <b>SELL SIGNAL — {coin}</b>\n"
            f"━━━━━━━━━━━━━━━━\n"
            f"💪 Strength : {strength} ({score}/8)\n"
            f"💰 Price : {format_price(price)}\n"
            f"\n"
            f"📤 <b>Sell Zone</b>\n"
            f"   Low  : {format_price(price * 0.998)}\n"
            f"   High : {format_price(price * 1.002)}\n"
            f"\n"
            f"🎯 <b>Take Profit</b>\n"
            f"   TP1 : {format_price(tp1)}\n"
            f"   TP2 : {format_price(tp2)}\n"
            f"   TP3 : {format_price(tp3)}\n"
            f"\n"
            f"🛑 <b>Stop Loss</b> : {format_price(sl)}\n"
            f"\n"
            f"📊 RSI : {last['rsi']:.1f}\n"
            f"📊 Stoch RSI : {stoch:.2f} (overbought)\n"
            f"📐 Fib Level : {fib_label}\n"
            f"📈 Support : {format_price(support)}\n"
            f"📉 Resistance : {format_price(resistance)}\n"
            f"━━━━━━━━━━━━━━━━\n"
            f"⚠️ নিজে বিশ্লেষণ করে trade করুন"
        )

    return msg

def send_telegram(msg):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    requests.post(url, data={"chat_id": CHAT_ID, "text": msg, "parse_mode": "HTML"})

print("Fetching all USDT pairs from Binance Vision...")
all_pairs = get_all_pairs()
print(f"Total pairs: {len(all_pairs)}")

signals_found = 0

for coin in all_pairs:
    try:
        df = get_data(coin, interval="4h")
        if df is None:
            continue
        df = analyze(df)
        signal, score, support, resistance, fib_levels, fib_label = get_signal(df)

        if signal:
            buy_1h, sell_1h = check_1h(coin)
            if signal == "BUY" and not buy_1h:
                print(f"Skip {coin}: 1H not confirmed")
                continue
            if signal == "SELL" and not sell_1h:
                print(f"Skip {coin}: 1H not confirmed")
                continue

            last = df.iloc[-1]
            msg = build_message(coin, signal, last, score, support, resistance, fib_levels, fib_label)
            send_telegram(msg)
            print(f"Signal: {coin} - {signal} ({score}/8)")
            signals_found += 1
            time.sleep(1)
        else:
            print(f"No signal: {coin} | RSI: {df.iloc[-1]['rsi']:.1f}")

        time.sleep(0.3)
    except Exception as e:
        print(f"Error {coin}: {e}")

print(f"Done! Signals: {signals_found}")
