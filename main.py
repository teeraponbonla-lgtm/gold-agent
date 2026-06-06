import os
import requests
import yfinance as yf
import feedparser
from datetime import datetime, timedelta
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

# =========================
# CONFIG
# =========================
TOKEN = os.environ["TELEGRAM_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

analyzer = SentimentIntensityAnalyzer()

# =========================
# DATA
# =========================
gold = yf.Ticker("GC=F")

df_1y = gold.history(period="1y")
df_1m = gold.history(period="1mo")
df_5d = gold.history(period="5d")

price = round(df_1y["Close"].iloc[-1], 2)
prev = round(df_1y["Close"].iloc[-2], 2)
change = round(price - prev, 2)

# =========================
# EMA FUNCTION
# =========================
def add_ema(df):
    df["EMA20"] = df["Close"].ewm(span=20, adjust=False).mean()
    df["EMA50"] = df["Close"].ewm(span=50, adjust=False).mean()
    return df

df_1y = add_ema(df_1y)
df_1m = add_ema(df_1m)
df_5d = add_ema(df_5d)

# =========================
# TREND SCORE (MULTI TIMEFRAME)
# =========================
def trend_score(df):
    score = 0
    if df["Close"].iloc[-1] > df["EMA20"].iloc[-1]:
        score += 1
    if df["EMA20"].iloc[-1] > df["EMA50"].iloc[-1]:
        score += 1
    return score

score = 0
score += trend_score(df_5d) * 2
score += trend_score(df_1m) * 3
score += trend_score(df_1y) * 5

# =========================
# RSI (SHORT TERM)
# =========================
delta = df_5d["Close"].diff()
gain = delta.where(delta > 0, 0)
loss = -delta.where(delta < 0, 0)

avg_gain = gain.ewm(alpha=1/14, adjust=False).mean()
avg_loss = loss.ewm(alpha=1/14, adjust=False).mean()

rs = avg_gain / avg_loss
rsi = 100 - (100 / (1 + rs))
rsi = round(rsi.iloc[-1], 2)

# =========================
# NEWS AI SENTIMENT
# =========================
feed = feedparser.parse(
    "https://feeds.finance.yahoo.com/rss/2.0/headline?s=GC=F&region=US&lang=en-US"
)

news_list = []
news_score = 0

for item in feed.entries[:5]:
    sentiment = analyzer.polarity_scores(item.title)["compound"]

    if sentiment > 0.1:
        tag = "🟢 บวกต่อทอง"
    elif sentiment < -0.1:
        tag = "🔴 ลบต่อทอง"
    else:
        tag = "⚪ เป็นกลาง"

    news_score += sentiment
    news_list.append(f"{tag} ({sentiment:.2f}) • {item.title}")

# =========================
# FINAL SCORE ENGINE
# =========================
final_score = score + (news_score * 3)

if final_score >= 8:
    signal = "BUY 📈"
elif final_score <= -8:
    signal = "SELL 📉"
else:
    signal = "HOLD ➖"

confidence = min(95, int(abs(final_score) * 10) + 50)

# =========================
# RISK ZONE
# =========================
if rsi < 30:
    risk = "⚠️ Oversold (เสี่ยงเด้ง)"
elif rsi > 70:
    risk = "⚠️ Overbought (เสี่ยงย่อ)"
else:
    risk = "ปกติ"

# =========================
# TREND LABEL
# =========================
if change > 0:
    trend = "Bullish 📈"
elif change < 0:
    trend = "Bearish 📉"
else:
    trend = "Sideway ➖"

# =========================
# TIME
# =========================
now = (datetime.now() + timedelta(hours=7)).strftime("%d/%m/%Y %H:%M")

# =========================
# MESSAGE
# =========================
message = f"""
🤖📊 AI Gold Analyst v5 Ultimate (PRO VERSION)

🕒 {now}

💰 Price: {price}
📉 Change: {change}

📊 Trend: {trend}

📈 RSI: {rsi}
⚠️ Risk: {risk}

🧠 Market Score: {final_score:.2f}
🎯 Signal: {signal}
🔥 Confidence: {confidence}%

🧠 News Impact Score: {round(news_score,2)}

📰 NEWS BREAKDOWN

{chr(10).join(news_list)}

⚠️ AI วิเคราะห์เพื่อประกอบการตัดสินใจ ไม่ใช่คำแนะนำลงทุน
"""

# =========================
# SEND TELEGRAM
# =========================
url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"

requests.post(url, data={
    "chat_id": CHAT_ID,
    "text": message
})
