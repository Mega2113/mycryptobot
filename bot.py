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

def get_data(symbol, interval=240):
    url = "https://api.kraken.com/0/public/OHLC"
    params = {"pair": symbol, "interval": interval}
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
    # RSI
    df["rsi"] = ta.momentum.RSIIndicator(df["close"]).rsi()
    # MACD
    macd = ta.trend.MACD(df["close"])
    df["macd"] = macd.macd_diff()
    # EMA
    df["ema20"] = ta.trend.EMAIndicator(df["close"], 20).ema_indicator()
    df["ema50"] = ta.trend.EMAIndicator(df["close"], 50).ema_indicator()
    df["ema200"] = ta.trend.EMAIndicator(df["close"], 200).ema_indicator()
    # Bollinger Bands
    bb = ta.volatility.BollingerBands(df["close"])
    df["bb_high"] = bb.bollinger_hband()
    df["bb_low"] = bb.bollinger_lband()
    df["bb_mid"] = bb.bollinger_mavg()
    # Volume MA
    df["vol_ma"] = df["volume"].rolling(20).mean()
    # ATR (volatility)
    df["atr"] = ta.volatility.AverageTrueRange(df["high"] if "high" in df else df["close"],
                                                df["low"] if "low" in df else df["close"],
                                                df["close"]).average_true_range()
    return df

def get_market_trend(df):
    last = df.iloc[-1]
    # EMA200 এর উপরে থাকলে Bull, নিচে থাকলে Bear
    if last["close"] > last["ema200"]:
        return "BULL"
    return "BEAR"

def get_support_resistance(df):
    # শেষ ৫০ candle এর high/low থেকে support/resistance
    recent = df.tail(50)
    resistance = recent["close"].max()
    support = recent["close"].min()
    return support, resistance

def check_volume(df):
    last = df.iloc[-1]
    # Volume যদি average এর ১.৫ গুণ বেশি হয়
    return last["volume"] > last["vol_ma"] * 1.5

def check_candlestick(df):
    last = df.iloc[-1]
    prev = df.iloc[-2]
    
    # Bullish Engulfing
    bullish_engulfing = (
        prev["close"] < prev["open"] and
        last["close"] > last["open"] and
        last["close"] > prev["open"] and
        last["open"] < prev["close"]
    )
    
    # Bearish Engulfing
    bearish_engulfing = (
        prev["close"] > prev["open"] and
        last["close"] < last["open"] and
        last["close"] < prev["open"] and
        last["open"] > prev["close"]
    )
    
    # Hammer (Bullish)
    body = abs(last["close"] - last["open"])
    lower_wick = min(last["close"], last["open"]) - last["low"] if "low" in last else 0
    hammer = lower_wick > body * 2 and last["close"] > last["open"]
    
    return bullish_engulfing or hammer, bearish_engulfing

def check_multi_timeframe(symbol):
    # ১H timeframe চেক
    df_1h = get_data(symbol, interval=60)
    if df_1h is None:
        return None, None
    df_1h = analyze(df_1h)
    last_1h = df_1h.iloc[-1]
    
    rsi_1h = last_1h["rsi"]
    macd_1h = last_1h["macd"]
    
    buy_1h = rsi_1h < 40 and macd_1h > 0
    sell_1h = rsi_1h > 60 and macd_1h < 0
    
    return buy_1h, sell_1h

def get_signal(df):
    last = df.iloc[-1]
    
    # Basic indicators
    rsi = last["rsi"]
    macd = last["macd"]
    ema20 = last["ema20"]
    ema50 = last["ema50"]
    price = last["close"]
    bb_low = last["bb_low"]
    bb_high = last["bb_high"]
    
    # Market trend
    trend = get_market_trend(df)
    
    # Volume
    high_volume = check_volume(df)
    
    # Candlestick
    bullish_candle, bearish_candle = check_candlestick(df)
    
    # Support/Resistance
    support, resistance = get_support_resistance(df)
    
    # BUY conditions (সব মিলতে হবে)
    buy_conditions = [
        rsi < 35,                    # Oversold
        macd > 0,                    # MACD positive
        ema20 > ema50,               # Uptrend
        trend == "BULL",             # Bull market
        price <= bb_low * 1.02,      # Bollinger band এর নিচে
        high_volume,                 # High volume
    ]
    
    # SELL conditions (সব মিলতে হবে)
    sell_conditions = [
        rsi > 65,                    # Overbought
        macd < 0,                    # MACD negative
        ema20 < ema50,               # Downtrend
        trend == "BEAR",             # Bear market
        price >= bb_high * 0.98,     # Bollinger band এর উপরে
        high_volume,                 # High volume
    ]
    
    buy_score = sum(buy_conditions)
    sell_score = sum(sell_conditions)
    
    # কমপক্ষে ৫/৬ condition মিলতে হবে
    if buy_score >= 5:
        return "BUY", buy_score, support, resistance
    elif sell_score >= 5:
        return "SELL", sell_score, support, resistance
    
    return None, 0, support, resistance

def format_price(price):
    if price < 0.0001:
        return f"${price:.8f}"
    elif price < 1:
        return f"${price:.6f}"
    elif price < 100:
        return f"${price:.4f}"
    else:
        return f"${price:.2f}"

def build_message(coin, signal, row, score, support, resistance):
    price = row["close"]
    atr = row["atr"]

    if signal == "BUY":
        entry_low  = price * 0.998
        entry_high = price * 1.002
        tp1 = price + (atr * 1.5)
        tp2 = price + (atr * 3.0)
        tp3 = price + (atr * 5.0)
        sl  = price - (atr * 1.5)
        strength = "⭐⭐⭐⭐⭐" if score == 6 else "⭐⭐⭐⭐"

        msg = (
            f"🟢 <b>BUY SIGNAL — {coin}</b>\n"
            f"━━━━━━━━━━━━━━━━\n"
            f"💪 Signal Strength : {strength}\n"
            f"💰 Current Price : {format_price(price)}\n"
            f"\n"
            f"📥 <b>Buy Zone</b>\n"
            f"   Low  : {format_price(entry_low)}\n"
            f"   High : {format_price(entry_high)}\n"
            f"\n"
            f"🎯 <b>Take Profit</b>\n"
            f"   TP1 : {format_price(tp1)}\n"
            f"   TP2 : {format_price(tp2)}\n"
            f"   TP3 : {format_price(tp3)}\n"
            f"\n"
            f"🛑 <b>Stop Loss</b> : {format_price(sl)}\n"
            f"\n"
            f"📊 RSI : {row['rsi']:.1f} | MACD : {row['macd']:.4f}\n"
            f"📈 Support : {format_price(support)}\n"
            f"📉 Resistance : {format_price(resistance)}\n"
            f"━━━━━━━━━━━━━━━━\n"
            f"⚠️ নিজে বিশ্লেষণ করে trade করুন"
        )

    else:
        entry_low  = price * 0.998
        entry_high = price * 1.002
        tp1 = price - (atr * 1.5)
        tp2 = price - (atr * 3.0)
        tp3 = price - (atr * 5.0)
        sl  = price + (atr * 1.5)
        strength = "⭐⭐⭐⭐⭐" if score == 6 else "⭐⭐⭐⭐"

        msg = (
            f"🔴 <b>SELL SIGNAL — {coin}</b>\n"
            f"━━━━━━━━━━━━━━━━\n"
            f"💪 Signal Strength : {strength}\n"
            f"💰 Current Price : {format_price(price)}\n"
            f"\n"
            f"📤 <b>Sell Zone</b>\n"
            f"   Low  : {format_price(entry_low)}\n"
            f"   High : {format_price(entry_high)}\n"
            f"\n"
            f"🎯 <b>Take Profit</b>\n"
            f"   TP1 : {format_price(tp1)}\n"
            f"   TP2 : {format_price(tp2)}\n"
            f"   TP3 : {format_price(tp3)}\n"
            f"\n"
            f"🛑 <b>Stop Loss</b> : {format_price(sl)}\n"
            f"\n"
            f"📊 RSI : {row['rsi']:.1f} | MACD : {row['macd']:.4f}\n"
            f"📈 Support : {format_price(support)}\n"
            f"📉 Resistance : {format_price(resistance)}\n"
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
        df = get_data(coin, interval=240)
        if df is None:
            continue
        df = analyze(df)
        signal, score, support, resistance = get_signal(df)
        
        if signal:
            # Multi timeframe confirm
            buy_1h, sell_1h = check_multi_timeframe(coin)
            
            if signal == "BUY" and not buy_1h:
                print(f"Skip {coin}: 1H not confirmed")
                continue
            if signal == "SELL" and not sell_1h:
                print(f"Skip {coin}: 1H not confirmed")
                continue
            
            last = df.iloc[-1]
            msg = build_message(coin, signal, last, score, support, resistance)
            send_telegram(msg)
            print(f"Signal sent: {coin} - {signal} (score: {score}/6)")
            signals_found += 1
            time.sleep(1)
        else:
            print(f"No signal: {coin} | RSI: {df.iloc[-1]['rsi']:.1f}")
        
        time.sleep(0.5)
    except Exception as e:
        print(f"Error {coin}: {e}")

print(f"Bot run complete. Signals found: {signals_found}")
