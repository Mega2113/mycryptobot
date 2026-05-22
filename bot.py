import os
import requests
import pandas as pd
import ta

TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
CHAT_ID = os.environ["CHAT_ID"]

COINS = {
    "BTC/USDT": "bitcoin",
    "ETH/USDT": "ethereum",
    "SOL/USDT": "solana",
    "BNB/USDT": "binancecoin",
    "XRP/USDT": "ripple"
}

def get_data(coin_id):
    url = f"https://api.coingecko.com/api/v3/coins/{coin_id}/ohlc"
    params = {"vs_currency": "usd", "days": "1"}
    r = requests.get(url, params=params)
    data = r.json()
    df = pd.DataFrame(data, columns=["time","open","high","low","close"])
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

for symbol, coin_id in COINS.items():
    try:
        df = get_data(coin_id)
        row = analyze(df)
        signal = get_signal(row)
        if signal:
            msg = (f"⚡ <b>{symbol}</b>\n"
                   f"Signal: {signal}\n"
                   f"💰 Price: ${row['close']:.4f}\n"
                   f"📊 RSI: {row['rsi']:.1f}\n"
                   f"📈 EMA20: ${row['ema20']:.4f}")
            send_telegram(msg)
            print(f"Signal sent: {symbol} - {signal}")
        else:
            print(f"No signal: {symbol} | RSI: {row['rsi']:.1f}")
    except Exception as e:
        print(f"Error {symbol}: {e}")

print("Bot run complete.")
