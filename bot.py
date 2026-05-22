import os
import requests
import pandas as pd
import ta

TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
CHAT_ID = os.environ["CHAT_ID"]

COINS = [
    "BTC/USDT", "ETH/USDT", "SOL/USDT",
    "BNB/USDT", "XRP/USDT", "DOGE/USDT",
    "ADA/USDT", "MATIC/USDT", "DOT/USDT",
    "AVAX/USDT", "LINK/USDT", "UNI/USDT"
]

def get_data(symbol):
    url = "https://api.bybit.com/v5/market/kline"
    params = {
        "category": "spot",
        "symbol": symbol.replace("/", ""),
        "interval": "60",
        "limit": 100
    }
    r = requests.get(url, params=params)
    data = r.json()["result"]["list"]
    df = pd.DataFrame(data, columns=["time","open","high","low","close","volume","turnover"])
    df = df[["time","open","high","low","close","volume"]].astype(float)
    df = df.iloc[::-1].reset_index(drop=True)
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

for coin in COINS:
    try:
        df = get_data(coin)
        row = analyze(df)
        signal = get_signal(row)
        if signal:
            msg = (f"⚡ <b>{coin}</b>\n"
                   f"Signal: {signal}\n"
                   f"💰 Price: ${row['close']:.4f}\n"
                   f"📊 RSI: {row['rsi']:.1f}\n"
                   f"📈 EMA20: ${row['ema20']:.4f}")
            send_telegram(msg)
            print(f"Signal sent: {coin} - {signal}")
        else:
            print(f"No signal: {coin} | RSI: {row['rsi']:.1f}")
    except Exception as e:
        print(f"Error {coin}: {e}")

print("Bot run complete.")
