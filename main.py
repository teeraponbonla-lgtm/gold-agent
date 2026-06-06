import os
import requests
import yfinance as yf
import feedparser
from datetime import datetime, timedelta

TOKEN = os.environ["TELEGRAM_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

gold = yf.Ticker("GC=F")
hist = gold.history(period="1y")

current = round(hist["Close"].iloc[-1], 2)
previous = round(hist["Close"].iloc[-2], 2)

change = round(current - previous, 2)
hist["EMA20"] = hist["Close"].ewm(span=20).mean()
hist["EMA50"] = hist["Close"].ewm(span=50).mean()
hist["EMA100"] = hist["Close"].ewm(span=100).mean()
hist["EMA200"] = hist["Close"].ewm(span=200).mean()

ema20 = round(hist["EMA20"].iloc[-1], 2)
ema50 = round(hist["EMA50"].iloc[-1], 2)
ema100 = round(hist["EMA100"].iloc[-1], 2)
ema200 = round(hist["EMA200"].iloc[-1], 2)

signal = "SIDEWAY ➖"
confidence = 50

if current > ema20 > ema50 > ema100 > ema200:
    signal = "BUY 📈"
    confidence = 85

elif current < ema20 < ema50 < ema100 < ema200:
    signal = "SELL 📉"
    confidence = 85

elif current > ema20 and current > ema50:
    signal = "BUY 📈"
    confidence = 70

elif current < ema20 and current < ema50:
    signal = "SELL 📉"
    confidence = 70
# ===== NEWS =====

feed = feedparser.parse(
    "https://feeds.finance.yahoo.com/rss/2.0/headline?s=GC=F&region=US&lang=en-US"
)

news = []

for item in feed.entries[:3]:
    news.append("• " + item.title)

if change > 0:
    trend = "Bullish 📈"
elif change < 0:
    trend = "Bearish 📉"
else:
    trend = "Sideway ➖"

thai_time = datetime.now() + timedelta(hours=7)
now = thai_time.strftime("%d/%m/%Y %H:%M")
message = f"""
📊 AI Gold Analyst

🕒 {now} น.

Gold Price: {current}

EMA20 : {ema20}
EMA50 : {ema50}
EMA100: {ema100}
EMA200: {ema200}

Change: {change}

Trend: {trend}

🎯 Signal: {signal}

🔥 Confidence: {confidence}%

📰 ข่าวล่าสุด

{chr(10).join(news)}

⚠️ ใช้เป็นข้อมูลประกอบการตัดสินใจ
"""

url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"

requests.post(
    url,
    data={
        "chat_id": CHAT_ID,
        "text": message
    }
)
