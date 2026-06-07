import os
import requests
import yfinance as yf
import feedparser
from datetime import datetime, timedelta
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

# =========================
# CONFIG
# =========================
TOKEN          = os.environ.get("TELEGRAM_TOKEN_BTC")
CHAT_ID        = os.environ.get("TELEGRAM_CHAT_ID_BTC")
GEMINI_API_KEY = (os.environ.get("GEMINI_API_KEY") or "").strip()

analyzer = SentimentIntensityAnalyzer()

# =========================
# DATA — BTC-USD
# =========================
btc   = yf.Ticker("BTC-USD")
df    = btc.history(period="1y")     # หลัก: EMA, RSI, ATR, Trend
df_1m = btc.history(period="1mo")    # Trend 1 เดือน
df_5d = btc.history(period="5d")     # Trend 5 วัน

price  = float(df["Close"].iloc[-1])
prev   = float(df["Close"].iloc[-2])
change = round(price - prev, 2)

# =========================
# EMA
# =========================
def add_ema(d):
    d = d.copy()
    d["EMA20"]  = d["Close"].ewm(span=20,  adjust=False).mean()
    d["EMA50"]  = d["Close"].ewm(span=50,  adjust=False).mean()
    d["EMA200"] = d["Close"].ewm(span=200, adjust=False).mean()
    return d

df    = add_ema(df)
df_1m = add_ema(df_1m)
df_5d = add_ema(df_5d)

ema20  = float(df["EMA20"].iloc[-1])
ema50  = float(df["EMA50"].iloc[-1])
ema200 = float(df["EMA200"].iloc[-1])

# =========================
# ATR (14)
# =========================
def calc_atr(d, period=14):
    high  = d["High"]
    low   = d["Low"]
    close = d["Close"].shift(1)
    tr = (high - low).combine(
        (high - close).abs(), max
    ).combine(
        (low - close).abs(), max
    )
    return float(tr.ewm(span=period, adjust=False).mean().iloc[-1])

atr = calc_atr(df)

# =========================
# RSI (14)
# =========================
delta    = df["Close"].diff()
gain     = delta.where(delta > 0, 0.0)
loss     = -delta.where(delta < 0, 0.0)
avg_gain = gain.ewm(alpha=1/14, adjust=False).mean()
avg_loss = loss.ewm(alpha=1/14, adjust=False).mean()
rs       = avg_gain / avg_loss
rsi      = float((100 - (100 / (1 + rs))).iloc[-1])

# =========================
# EMA POSITION
# =========================
def pos(p, e):
    return "🟢 เหนือ" if p > e else "🔴 ต่ำกว่า"

ema_block = (
    f"📊 สถานะ EMA\n"
    f"EMA20  : {round(ema20,2)}  ({pos(price, ema20)})\n"
    f"EMA50  : {round(ema50,2)}  ({pos(price, ema50)})\n"
    f"EMA200 : {round(ema200,2)} ({pos(price, ema200)})"
)

# =========================
# TREND SCORE
# =========================
def trend_score_df(d):
    s    = 0
    p    = float(d["Close"].iloc[-1])
    e20  = float(d["EMA20"].iloc[-1])
    e50  = float(d["EMA50"].iloc[-1])
    e200 = float(d["EMA200"].iloc[-1])
    if p   > e20:  s += 1
    if e20 > e50:  s += 1
    if e50 > e200: s += 1
    return s

raw_trend = (
    trend_score_df(df_5d) * 0.30 +
    trend_score_df(df_1m) * 0.35 +
    trend_score_df(df)    * 0.35
)
trend_normalized = (raw_trend / 3) * 2 - 1

# =========================
# REGIME — BTC ผันผวนสูงกว่า ปรับ threshold
# =========================
if price > ema20 > ema50 > ema200:
    regime = "📈 ขาขึ้น"
elif price < ema20 < ema50 < ema200:
    regime = "📉 ขาลง"
elif rsi < 20:                          # BTC ใช้ 20 แทน 25
    regime = "⚠️ ซื้อมากเกิน"
elif rsi > 80:                          # BTC ใช้ 80 แทน 75
    regime = "⚠️ ขายมากเกิน"
else:
    regime = "➖ ทรงตัว"

# =========================
# TRANSLATE NEWS — Gemini API
# =========================
def translate_news_gemini(titles: list) -> list:
    if not GEMINI_API_KEY:
        return titles

    numbered = "\n".join(f"{i+1}. {t}" for i, t in enumerate(titles))
    prompt = (
        "แปลหัวข้อข่าวการเงินต่อไปนี้เป็นภาษาไทยที่อ่านเข้าใจง่าย กระชับ "
        "และถูกต้องตามบริบทการลงทุน ไม่ต้องแปลตรงตัวทุกคำ ให้ได้ใจความที่ชัดเจน "
        "ตอบเฉพาะหัวข้อที่แปลแล้ว ไม่ต้องมีคำอธิบายเพิ่ม "
        "รูปแบบ: หมายเลข. หัวข้อภาษาไทย\n\n"
        f"{numbered}"
    )

    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"gemini-3.1-flash-lite:generateContent?key={GEMINI_API_KEY}"
    )

    try:
        resp = requests.post(
            url,
            json={"contents": [{"parts": [{"text": prompt}]}]},
            timeout=30
        )
        resp.raise_for_status()
        text = resp.json()["candidates"][0]["content"]["parts"][0]["text"]

        lines  = text.strip().split("\n")
        result = []
        for line in lines:
            line = line.strip()
            if not line:
                continue
            if line and line[0].isdigit():
                line = line.split(".", 1)[-1].strip()
                line = line.split(")", 1)[-1].strip()
            if line:
                result.append(line)

        while len(result) < len(titles):
            result.append(titles[len(result)])

        return result[:len(titles)]

    except Exception as e:
        print(f"Gemini translate error: {e}")
        return titles

# =========================
# NEWS SENTIMENT
# =========================
def sentiment_label(score: float):
    if score > 0.3:
        return "🟢 ขาขึ้นแรง", 0.6,  "Strong Bullish"
    elif score > 0.1:
        return "🟢 ขาขึ้น",   0.2,  "Bullish"
    elif score < -0.3:
        return "🔴 ขาลงแรง", -0.6, "Strong Bearish"
    elif score < -0.1:
        return "🔴 ขาลง",   -0.2, "Bearish"
    else:
        return "⚪ เป็นกลาง",  0.0, "Neutral"

# RSS ข่าว BTC
feed = feedparser.parse(
    "https://feeds.finance.yahoo.com/rss/2.0/headline?s=BTC-USD&region=US&lang=en-US"
)
raw_titles  = [item.title for item in feed.entries[:6]]
thai_titles = translate_news_gemini(raw_titles)

news_items = []
for eng, th in zip(raw_titles, thai_titles):
    score = analyzer.polarity_scores(eng)["compound"]
    label_th, expected, label_en = sentiment_label(score)
    news_items.append({
        "title_en":  eng,
        "title_th":  th,
        "label_th":  label_th,
        "label_en":  label_en,
        "sentiment": score,
        "expected":  expected,
    })

# =========================
# SIGNAL
# =========================
avg_sentiment = sum(n["expected"] for n in news_items) / max(len(news_items), 1)
combined      = trend_normalized * 0.60 + avg_sentiment * 0.40
prob          = round(max(0, min(100, 50 + combined * 50)), 2)

if prob >= 65:
    signal = "ซื้อ 📈"
elif prob <= 35:
    signal = "ขาย 📉"
else:
    signal = "ถือ ⏳"

confidence = int(min(95, abs(prob - 50) * 2))

# =========================
# TP / SL — ATR (BTC ผันผวนสูง ใช้ multiplier กว้างขึ้น)
# =========================
def tp_sl_atr(signal, price, atr):
    if "ซื้อ" in signal:
        return (
            round(price + atr * 1.0, 2), round(price + atr * 2.0, 2), round(price + atr * 3.5, 2),
            round(price - atr * 1.0, 2), round(price - atr * 2.0, 2), round(price - atr * 3.0, 2),
        )
    elif "ขาย" in signal:
        return (
            round(price - atr * 1.0, 2), round(price - atr * 2.0, 2), round(price - atr * 3.5, 2),
            round(price + atr * 1.0, 2), round(price + atr * 2.0, 2), round(price + atr * 3.0, 2),
        )
    else:
        return (
            round(price + atr * 1.0, 2), round(price + atr * 2.0, 2), round(price + atr * 3.5, 2),
            round(price - atr * 1.0, 2), round(price - atr * 2.0, 2), round(price - atr * 3.0, 2),
        )

tp1, tp2, tp3, sl1, sl2, sl3 = tp_sl_atr(signal, price, atr)

# =========================
#
