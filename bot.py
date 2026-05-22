import os
import requests
import pandas as pd
import ta
import time

TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
CHAT_ID = os.environ["CHAT_ID"]

COINS = [
    # Layer 1
    "XBTUSD", "ETHUSD", "SOLUSD", "XRPUSD",
    "ADAUSD", "AVAXUSD", "DOTUSD", "NEARUSD",
    "ATOMUSD", "ICPUSD", "ALGOUSD", "XLMUSD",
    "VETUSD", "FILUSD", "HBARUSD", "XTZUSD",
    "MINAUSD", "FLOWUSD", "KAVAUSD", "KSMUSD",
    "STXUSD", "SUIUSD", "APTUSD",

    # Layer 2
    "ARBUSD", "OPUSD", "POLUSD", "LRCUSD",

    # DeFi
    "UNIUSD", "AAVEUSD", "MKRUSD", "COMPUSD",
    "SNXUSD", "CRVUSD", "YFIUSD", "BALUSD",
    "ZRXUSD", "OCEANUSD", "GMXUSD", "DYDXUSD",
    "LDOUSD", "RPLUSD",

    # Meme
    "DOGEUSD", "PEPEUSD", "WIFUSD", "BONKUSD",

    # Gaming/NFT
    "AXSUUD", "MANAUSD", "SANDUSD", "GALAUSD",
    "CHZUSD", "ENJUSD",

    # AI
    "FETUSD", "AGIXUSD", "RENDERUSD", "TAOUSD",

    # Others
    "LINKUSD", "TRXUSD", "LTCUSD", "BNBUSD",
    "DOGEUSD", "INJUSD", "APEUSD", "GMTUSD",
    "BATUSD", "ANKRUSD", "STORJUSD", "QNTUSD",
    "XMRUSD", "ZECUSD", "DASHUSD", "BCHUSD",
    "ETCUSD", "EOSUSD", "WLDUSD", "TIAUSD",
    "PYTHUSD", "JUPUSD", "ENAUSD", "DYMUSD",
    "BLURUSD", "ARUSD", "NMRUSD", "GNOUSD",
    "OXTUSD", "RENUSD", "KNCUSD", "OMGUSD",
    "SCUSD", "POWRUSD", "RLCUSD", "MLNUSD",
]

def get_data(symbol):
    url = "https://api.kraken.com/0/public/OHLC"
    params = {"pair": symbol, "interval": 60}
    r = requests.get(url, params=params, timeout=10)
    result = r.json()["result"]
    key = list(result.keys())[0]
    data = result[key]
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

for coin in COINS:
    try:
        df = get_data(coin)
        row = analyze(df)
        signal = get_signal(row)
        display = coin.replace("USD", "/USDT").replace("XBT", "BTC")
        if signal:
            msg = (f"⚡ <b>{display}</b>\n"
                   f"Signal: {signal}\n"
                   f"💰 Price: ${row['close']:.4f}\n"
                   f"📊 RSI: {row['rsi']:.1f}\n"
                   f"📈 EMA20: ${row['ema20']:.4f}")
            send_telegram(msg)
            print(f"Signal sent: {display} - {signal}")
        else:
            print(f"No signal: {display} | RSI: {row['rsi']:.1f}")
        time.sleep(1)
    except Exception as e:
        print(f"Error {coin}: {e}")

print("Bot run complete.")
