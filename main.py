import os
import requests
import yfinance as yf
import feedparser
from datetime import datetime, timedelta

TOKEN = os.environ["TELEGRAM_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

gold = yf.Ticker("GC=F")
hist = gold.history(period="2d")

current = round(hist["Close"].iloc[-1], 2)
previous = round(hist["Close"].iloc[-2], 2)

change = round(current - previous, 2)
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

Change: {change}

Trend: {trend}

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
