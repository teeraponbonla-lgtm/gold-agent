import os
import requests
import yfinance as yf
import feedparser
from datetime import datetime, timedelta
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

# =========================
# CONFIG
# =========================
TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

analyzer = SentimentIntensityAnalyzer()

# =========================
# SAFE FUNCTION
# =========================
def safe_last(series, default=0):
    try:
        if series is None or len(series) == 0:
            return default
        return series.iloc[-1]
    except:
        return default


def safe_prev(series, default=0):
    try:
        if series is None or len(series) < 2:
            return default
        return series.iloc[-2]
    except:
        return default


# =========================
# DATA
# =========================
gold = yf.Ticker("GC=F")

df_1y = gold.history(period="1y")
df_1m = gold.history(period="1mo")
df_5d = gold.history(period="5d")

# กัน data ว่าง
if df_1y is None or df_1y.empty:
    raise Exception("❌ No data from yfinance")

price = round(safe_last(df_1y["Close"]), 2)
prev = round(safe_prev(df_1y["Close"]), 2)
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
# TREND SCORE
# =========================
def trend_score(df):
    try:
        score = 0
        if df["Close"].iloc[-1] > df["EMA20"].iloc[-1]:
            score += 1
        if df["EMA20"].iloc[-1] > df["EMA50"].iloc[-1]:
            score += 1
        return score
    except:
        return 0


score = 0
score += trend_score(df_5d) * 2
score += trend_score(df_1m) * 3
score += trend_score(df_1y) * 5

# =========================
# RSI (SAFE)
# =========================
delta = df_5d["Close"].diff()

gain = delta.where(delta > 0, 0)
loss = -delta.where(delta < 0, 0)

avg_gain = gain.ewm(alpha=1/14, adjust=False).mean()
avg_loss = loss.ewm(alpha=1/14, adjust=False).mean()

rs = avg_gain / avg_loss
rsi_raw = safe_last(100 - (100 / (1 + rs)), 50)

rsi = round(rsi_raw if rsi_raw is not None else 50, 2)

# =========================
# NEWS AI SENTIMENT (SAFE)
# =========================
feed = feedparser.parse(
    "https://feeds.finance.yahoo.com/rss/2.0/headline?s=GC=F&region=US&lang=en-US"
)

news_list = []
news_score = 0

entries = getattr(feed, "entries", [])

for item in entries[:5]:
    try:
        sentiment = analyzer.polarity_scores(item.title)["compound"]

        if sentiment > 0.1:
            tag = "🟢 บวกต่อทอง"
        elif sentiment < -0.1:
            tag = "🔴 ลบต่อทอง"
        else:
            tag = "⚪ เป็นกลาง"

        news_score += sentiment
        news_list.append(f"{tag} ({sentiment:.2f}) • {item.title}")

    except:
        continue

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
# MESSAGE (SAFE JOIN)
# =========================
news_text = "\n".join(news_list) if news_list else "ไม่มีข่าว"

message = f"""
🤖📊 AI Gold Analyst v5 Ultimate (PRO VERSION - SAFE)

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

{news_text}

⚠️ AI วิเคราะห์เพื่อประกอบการตัดสินใจ ไม่ใช่คำแนะนำลงทุน
"""

# =========================
# SEND TELEGRAM (SAFE)
# =========================
if TOKEN and CHAT_ID:
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    try:
        requests.post(url, data={
            "chat_id": CHAT_ID,
            "text": message
        })
    except Exception as e:
        print("Telegram error:", e)
else:
    print("Missing TELEGRAM_TOKEN or TELEGRAM_CHAT_ID")

print("DONE")
