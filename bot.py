import os
import requests
import pandas as pd
import ta
import time

TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
CHAT_ID = os.environ["CHAT_ID"]

def get_all_usd_pairs():
    url = "https://api.kraken.com/0/public/AssetPairs"
    r = requests.get(url, timeout=10)
    pairs = r.json()["result"]
    usd_pairs = [
        pair for pair in pairs.keys()
        if pair.endswith("USD") and ".d" not in pair
    ]
    return usd_pairs

def get_data(symbol):
    url = "https://api.kraken.com/0/public/OHLC"
    params = {"pair": symbol, "interval": 60}
    r = requests.get(url, params=params, timeout=10)
    result = r.json().get("result", {})
    if not result:
        return None
    key = list(result.keys())[0]
    data = result[key]
    if len(data) < 60:
        return None
    df = pd.DataFrame(data, columns=["time","open","high","low","close","vwap","volume","count"])
    df = df[["time","open","high","low","close","volume"]].astype(float)
    return df

def analyze(df):
    df["rsi"] = ta.momentum.RSIIndicator(df["close"]).rsi()
    macd = ta.trend.MACD(df["close"])
    df["macd"] = macd.macd_diff()
    df["ema20"] = ta.trend.EMAIndicator(df["close"], 20).ema_indicator()
    df["ema50"] = ta.trend.EMAIndicator(df["close"], 50).ema_indicator()
    df["bb_high"] = ta.volatility.BollingerBands(df["close"]).bollinger_hband()
    df["bb_low"] = ta.volatility.BollingerBands(df["close"]).bollinger_lband()
    return df.iloc[-1]

def get_signal(row):
    if row["rsi"] < 35 and row["macd"] > 0 and row["ema20"] > row["ema50"]:
        return "BUY"
    elif row["rsi"] > 65 and row["macd"] < 0 and row["ema20"] < row["ema50"]:
        return "SELL"
    return None

def format_price(price):
    if price < 0.0001:
        return f"${price:.8f}"
    elif price < 1:
        return f"${price:.6f}"
    elif price < 100:
        return f"${price:.4f}"
    else:
        return f"${price:.2f}"

def build_message(coin, signal, row):
    price = row["close"]

    if signal == "BUY":
        entry_low  = price * 0.995   # এখনই কিনলে
        entry_high = price * 1.005   # একটু উঠলে
        tp1 = price * 1.03           # ৩% লাভ
        tp2 = price * 1.06           # ৬% লাভ
        tp3 = price * 1.10           # ১০% লাভ
        sl  = price * 0.97           # ৩% loss এ stop

        msg = (
            f"🟢 <b>BUY SIGNAL — {coin}</b>\n"
            f"━━━━━━━━━━━━━━━━\n"
            f"💰 Current Price : {format_price(price)}\n"
            f"\n"
            f"📥 <b>Buy Zone</b>\n"
            f"   Low  : {format_price(entry_low)}\n"
            f"   High : {format_price(entry_high)}\n"
            f"\n"
            f"🎯 <b>Take Profit</b>\n"
            f"   TP1 : {format_price(tp1)}  (+3%)\n"
            f"   TP2 : {format_price(tp2)}  (+6%)\n"
            f"   TP3 : {format_price(tp3)}  (+10%)\n"
            f"\n"
            f"🛑 <b>Stop Loss</b> : {format_price(sl)}  (-3%)\n"
            f"\n"
            f"📊 RSI : {row['rsi']:.1f} | EMA20 : {format_price(row['ema20'])}\n"
            f"━━━━━━━━━━━━━━━━\n"
            f"⚠️ নিজে বিশ্লেষণ করে trade করুন"
        )

    else:  # SELL
        exit_low  = price * 0.995
        exit_high = price * 1.005
        tp1 = price * 0.97           # ৩% নামলে profit
        tp2 = price * 0.94           # ৬% নামলে profit
        tp3 = price * 0.90           # ১০% নামলে profit
        sl  = price * 1.03           # ৩% উঠলে stop

        msg = (
            f"🔴 <b>SELL SIGNAL — {coin}</b>\n"
            f"━━━━━━━━━━━━━━━━\n"
            f"💰 Current Price : {format_price(price)}\n"
            f"\n"
            f"📤 <b>Sell Zone</b>\n"
            f"   Low  : {format_price(exit_low)}\n"
            f"   High : {format_price(exit_high)}\n"
            f"\n"
            f"🎯 <b>Take Profit</b>\n"
            f"   TP1 : {format_price(tp1)}  (-3%)\n"
            f"   TP2 : {format_price(tp2)}  (-6%)\n"
            f"   TP3 : {format_price(tp3)}  (-10%)\n"
            f"\n"
            f"🛑 <b>Stop Loss</b> : {format_price(sl)}  (+3%)\n"
            f"\n"
            f"📊 RSI : {row['rsi']:.1f} | EMA20 : {format_price(row['ema20'])}\n"
            f"━━━━━━━━━━━━━━━━\n"
            f"⚠️ নিজে বিশ্লেষণ করে trade করুন"
        )

    return msg

def send_telegram(msg):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    requests.post(url, data={"chat_id": CHAT_ID, "text": msg, "parse_mode": "HTML"})

print("Fetching all USD pairs from Kraken...")
all_pairs = get_all_usd_pairs()
print(f"Total pairs found: {len(all_pairs)}")

signals_found = 0

for coin in all_pairs:
    try:
        df = get_data(coin)
        if df is None:
            continue
        row = analyze(df)
        signal = get_signal(row)
        if signal:
            msg = build_message(coin, signal, row)
            send_telegram(msg)
            print(f"Signal sent: {coin} - {signal}")
            signals_found += 1
        else:
            print(f"No signal: {coin} | RSI: {row['rsi']:.1f}")
        time.sleep(0.5)
    except Exception as e:
        print(f"Error {coin}: {e}")

print(f"Bot run complete. Signals found: {signals_found}")
