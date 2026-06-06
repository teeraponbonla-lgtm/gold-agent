import os
import requests
import yfinance as yf
from datetime import datetime, timedelta

TOKEN = os.environ["TELEGRAM_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

gold = yf.Ticker("GC=F")
hist = gold.history(period="2d")

current = round(hist["Close"].iloc[-1], 2)
previous = round(hist["Close"].iloc[-2], 2)

change = current - previous

if change > 0:
    trend = "Bullish 📈"
elif change < 0:
    trend = "Bearish 📉"
else:
    trend = "Sideway ➖"

thai_time = datetime.utcnow() + timedelta(hours=7)
now = thai_time.strftime("%d/%m/%Y %H:%M")
message = f"""
📊 AI Gold Analyst

🕒 {now} น.

Gold Price: {current}

Change: {change}

Trend: {trend}

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
