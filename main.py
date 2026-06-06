import os
import requests
import yfinance as yf

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

message = f"""
📈 XAUUSD REPORT

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
