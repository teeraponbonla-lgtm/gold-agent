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
# EMA
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
# RSI (Wilder)
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
trend = "Sideway ➖"
if change > 0:
    trend = "Bullish 📈"
elif change < 0:
    trend = "Bearish 📉"

# =========================
# SIGNAL (basic logic)
# =========================
signal = "SIDEWAY ➖"
confidence = 50

if current < ema20 and ema20 < ema50:
    signal = "SELL 📉"
    confidence = 75

elif current > ema20 and ema20 > ema50:
    signal = "BUY 📈"
    confidence = 75

if rsi < 25:
    signal = "WATCH REBOUND ⚠️"
    confidence = 60

# =========================
# NEWS SENTIMENT AI (KEYWORD)
# =========================
def analyze_news(title):
    title = title.lower()

    bullish_keywords = [
        "inflation", "rate cut", "dovish", "weak dollar",
        "recession", "safe haven", "gold demand",
        "geopolitical", "crisis", "uncertainty"
    ]

    bearish_keywords = [
        "rate hike", "hawkish", "strong dollar",
        "bond yields rise", "risk-on", "stock rally",
        "fed tightening", "economic growth"
    ]

    score = 0

    for w in bullish_keywords:
        if w in title:
            score += 1

    for w in bearish_keywords:
        if w in title:
            score -= 1

    if score > 0:
        return "🟢 บวกต่อทอง"
    elif score < 0:
        return "🔴 ลบต่อทอง"
    else:
        return "⚪ เป็นกลาง"

# =========================
# NEWS FETCH
# =========================
feed = feedparser.parse(
    "https://feeds.finance.yahoo.com/rss/2.0/headline?s=GC=F&region=US&lang=en-US"
)

news = []
news_score = 0

for item in feed.entries[:5]:
    sentiment = analyze_news(item.title)

    if "🟢" in sentiment:
        news_score += 1
    elif "🔴" in sentiment:
        news_score -= 1

    news.append(f"{sentiment} • {item.title}")

# =========================
# NEWS IMPACT SUMMARY
# =========================
if news_score > 0:
    news_trend = "🟢 ข่าวรวมเป็นบวกต่อทอง"
elif news_score < 0:
    news_trend = "🔴 ข่าวรวมเป็นลบต่อทอง"
else:
    news_trend = "⚪ ข่าวออกกลาง ๆ"

# =========================
# TIME
# =========================
thai_time = datetime.now() + timedelta(hours=7)
now = thai_time.strftime("%d/%m/%Y %H:%M")

# =========================
# MESSAGE
# =========================
message = f"""
📊 AI Gold Analyst (v3 - AI News Sentiment)

🕒 {now} น.

💰 Gold Price: {current}
📉 Change: {change}

📊 EMA
EMA20 : {ema20}
EMA50 : {ema50}
EMA100: {ema100}
EMA200: {ema200}

📈 RSI14 : {rsi}

📌 Trend: {trend}

🎯 Signal: {signal}
🔥 Confidence: {confidence}%

📰 News Sentiment: {news_trend}

🧠 ข่าวล่าสุด

{chr("\n").join(news)}

⚠️ ใช้เพื่อประกอบการตัดสินใจเท่านั้น
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
