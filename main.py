import os
import requests
import yfinance as yf
import feedparser
from datetime import datetime, timedelta

# =========================
# CONFIG
# =========================
TOKEN = os.environ["TELEGRAM_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

# =========================
# GOLD DATA
# =========================
gold = yf.Ticker("GC=F")
hist = gold.history(period="1y")

current = round(hist["Close"].iloc[-1], 2)
previous = round(hist["Close"].iloc[-2], 2)
change = round(current - previous, 2)

# =========================
# EMA CALC
# =========================
hist["EMA20"] = hist["Close"].ewm(span=20, adjust=False).mean()
hist["EMA50"] = hist["Close"].ewm(span=50, adjust=False).mean()
hist["EMA100"] = hist["Close"].ewm(span=100, adjust=False).mean()
hist["EMA200"] = hist["Close"].ewm(span=200, adjust=False).mean()

ema20 = round(hist["EMA20"].iloc[-1], 2)
ema50 = round(hist["EMA50"].iloc[-1], 2)
ema100 = round(hist["EMA100"].iloc[-1], 2)
ema200 = round(hist["EMA200"].iloc[-1], 2)

# =========================
# RSI (WILDER METHOD FIXED)
# =========================
delta = hist["Close"].diff()

gain = delta.where(delta > 0, 0)
loss = -delta.where(delta < 0, 0)

avg_gain = gain.ewm(alpha=1/14, adjust=False).mean()
avg_loss = loss.ewm(alpha=1/14, adjust=False).mean()

rs = avg_gain / avg_loss
hist["RSI"] = 100 - (100 / (1 + rs))

rsi = round(hist["RSI"].iloc[-1], 2)

# =========================
# TREND
# =========================
if change > 0:
    trend = "Bullish 📈"
elif change < 0:
    trend = "Bearish 📉"
else:
    trend = "Sideway ➖"

# =========================
# SIGNAL LOGIC (IMPROVED)
# =========================
signal = "SIDEWAY ➖"
confidence = 50

bull_strong = current > ema20 > ema50 > ema100 > ema200
bear_strong = current < ema20 < ema50 < ema100 < ema200

bull_mid = current > ema20 and ema20 > ema50
bear_mid = current < ema20 and ema20 < ema50

if bull_strong and rsi < 70:
    signal = "BUY 📈"
    confidence = 90

elif bear_strong and rsi > 30:
    signal = "SELL 📉"
    confidence = 90

elif bull_mid and rsi < 60:
    signal = "BUY 📈"
    confidence = 70

elif bear_mid and rsi > 40:
    signal = "SELL 📉"
    confidence = 70

# RSI EXTREME FILTER
if rsi < 25:
    signal = "WATCH REBOUND ⚠️"
    confidence = 60

# =========================
# NEWS
# =========================
feed = feedparser.parse(
    "https://feeds.finance.yahoo.com/rss/2.0/headline?s=GC=F&region=US&lang=en-US"
)

news = ["• " + item.title for item in feed.entries[:3]]

# =========================
# TIME
# =========================
thai_time = datetime.now() + timedelta(hours=7)
now = thai_time.strftime("%d/%m/%Y %H:%M")

# =========================
# MESSAGE
# =========================
message = f"""
📊 AI Gold Analyst (v2)

🕒 {now} น.

Gold Price: {current}

EMA20 : {ema20}
EMA50 : {ema50}
EMA100: {ema100}
EMA200: {ema200}

RSI14 : {rsi}

Change: {change}

Trend: {trend}

🎯 Signal: {signal}

🔥 Confidence: {confidence}%

📰 ข่าวล่าสุด

{chr(10).join(news)}

⚠️ ใช้เป็นข้อมูลประกอบการตัดสินใจเท่านั้น
"""

# =========================
# SEND TO TELEGRAM
# =========================
url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"

requests.post(
    url,
    data={
        "chat_id": CHAT_ID,
        "text": message
    }
)
