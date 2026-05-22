import os
import requests
import pandas as pd
import ta
import time

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
    params = {
        "symbol": symbol,
        "interval": interval,
        "limit": 300
    }
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
        df["high"] if "high" in df.columns else df["close"],
        df["low"] if "low" in df.columns else df["close"],
        df["close"]
    ).average_true_range()
    return df

def get_market_trend(df):
    last = df.iloc[-1]
    if last["close"] > last["ema200"]:
        return "BULL"
    return "BEAR"

def get_support_resistance(df):
    recent = df.tail(50)
    resistance = recent["close"].max()
    support = recent["close"].min()
    return support, resistance

def check_volume(df):
    last = df.iloc[-1]
    return last["volume"] > last["vol_ma"] * 1.5

def get_signal(df):
    last = df.iloc[-1]
    rsi = last["rsi"]
    macd = last["macd"]
    ema20 = last["ema20"]
    ema50 = last["ema50"]
    price = last["close"]
    bb_low = last["bb_low"]
    bb_high = last["bb_high"]
    trend = get_market_trend(df)
    high_volume = check_volume(df)
    support, resistance = get_support_resistance(df)

    buy_conditions = [
        rsi < 35,
        macd > 0,
        ema20 > ema50,
        trend == "BULL",
        price <= bb_low * 1.02,
        high_volume,
    ]
    sell_conditions = [
        rsi > 65,
        macd < 0,
        ema20 < ema50,
        trend == "BEAR",
        price >= bb_high * 0.98,
        high_volume,
    ]

    buy_score = sum(buy_conditions)
    sell_score = sum(sell_conditions)

    if buy_score >= 5:
        return "BUY", buy_score, support, resistance
    elif sell_score >= 5:
        return "SELL", sell_score, support, resistance
    return None, 0, support, resistance

def check_1h(symbol):
    df = get_data(symbol, interval="1h")
    if df is None:
        return None, None
    df = analyze(df)
    last = df.iloc[-1]
    buy_1h = last["rsi"] < 40 and last["macd"] > 0
    sell_1h = last["rsi"] > 60 and last["macd"] < 0
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

def build_message(coin, signal, last, score, support, resistance):
    price = last["close"]
    atr = last["atr"]
    strength = "⭐⭐⭐⭐⭐" if score == 6 else "⭐⭐⭐⭐"

    if signal == "BUY":
        tp1 = price + (atr * 1.5)
        tp2 = price + (atr * 3.0)
        tp3 = price + (atr * 5.0)
        sl  = price - (atr * 1.5)
        zone = f"   Low  : {format_price(price * 0.998)}\n   High : {format_price(price * 1.002)}"
        zone_label = "📥 <b>Buy Zone</b>"
        emoji = "🟢"
        action = "BUY"
    else:
        tp1 = price - (atr * 1.5)
        tp2 = price - (atr * 3.0)
        tp3 = price - (atr * 5.0)
        sl  = price + (atr * 1.5)
        zone = f"   Low  : {format_price(price * 0.998)}\n   High : {format_price(price * 1.002)}"
        zone_label = "📤 <b>Sell Zone</b>"
        emoji = "🔴"
        action = "SELL"

    msg = (
        f"{emoji} <b>{action} SIGNAL — {coin}</b>\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"💪 Strength : {strength} ({score}/6)\n"
        f"💰 Price : {format_price(price)}\n"
        f"\n"
        f"{zone_label}\n"
        f"{zone}\n"
        f"\n"
        f"🎯 <b>Take Profit</b>\n"
        f"   TP1 : {format_price(tp1)}\n"
        f"   TP2 : {format_price(tp2)}\n"
        f"   TP3 : {format_price(tp3)}\n"
        f"\n"
        f"🛑 <b>Stop Loss</b> : {format_price(sl)}\n"
        f"\n"
        f"📊 RSI : {last['rsi']:.1f} | MACD : {last['macd']:.6f}\n"
        f"📈 Support : {format_price(support)}\n"
        f"📉 Resistance : {format_price(resistance)}\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"⚠️ নিজে বিশ্লেষণ করে trade করুন"
    )
    return msg

def send_telegram(msg):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    requests.post(url, data={"chat_id": CHAT_ID, "text": msg, "parse_mode": "HTML"})

# Start
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
        signal, score, support, resistance = get_signal(df)

        if signal:
            buy_1h, sell_1h = check_1h(coin)
            if signal == "BUY" and not buy_1h:
                print(f"Skip {coin}: 1H not confirmed")
                continue
            if signal == "SELL" and not sell_1h:
                print(f"Skip {coin}: 1H not confirmed")
                continue

            last = df.iloc[-1]
            msg = build_message(coin, signal, last, score, support, resistance)
            send_telegram(msg)
            print(f"✅ Signal: {coin} - {signal} ({score}/6)")
            signals_found += 1
            time.sleep(1)
        else:
            print(f"No signal: {coin} | RSI: {df.iloc[-1]['rsi']:.1f}")

        time.sleep(0.3)
    except Exception as e:
        print(f"Error {coin}: {e}")

print(f"Done! Signals: {signals_found}")
