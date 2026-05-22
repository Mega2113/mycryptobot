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
    return df.iloc[-1]

def get_signal(row):
    if row["rsi"] < 35 and row["macd"] > 0 and row["ema20"] > row["ema50"]:
        return "BUY 🟢"
    elif row["rsi"] > 65 and row["macd"] < 0 and row["ema20"] < row["ema50"]:
        return "SELL 🔴"
    return None

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
            msg = (f"⚡ <b>{coin}</b>\n"
                   f"Signal: {signal}\n"
                   f"💰 Price: ${row['close']:.6f}\n"
                   f"📊 RSI: {row['rsi']:.1f}\n"
                   f"📈 EMA20: ${row['ema20']:.6f}")
            send_telegram(msg)
            print(f"Signal sent: {coin} - {signal}")
            signals_found += 1
        else:
            print(f"No signal: {coin} | RSI: {row['rsi']:.1f}")
        time.sleep(0.5)
    except Exception as e:
        print(f"Error {coin}: {e}")

print(f"Bot run complete. Signals found: {signals_found}")
