import os
import requests
import yfinance as yf
import feedparser
from datetime import datetime, timedelta
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
import anthropic

# =========================
# CONFIG
# =========================
TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
ANTHROPIC_API_KEY = (os.environ.get("ANTHROPIC_API_KEY") or "").strip()

analyzer = SentimentIntensityAnalyzer()
claude = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

# =========================
# DATA
# =========================
gold = yf.Ticker("GC=F")

df     = gold.history(period="1y")   # ใช้หลัก: EMA, RSI, Regime, Trend
df_1m  = gold.history(period="1mo")  # Trend 1 เดือน
df_5d  = gold.history(period="5d")   # Trend 5 วัน

price = float(df["Close"].iloc[-1])
prev  = float(df["Close"].iloc[-2])
change = round(price - prev, 2)

# =========================
# EMA — คำนวณครั้งเดียวจาก df (1y) แล้ว slice
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
# ATR (14) — สำหรับ TP/SL แบบ dynamic
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
# RSI (14) — คำนวณจาก df (1y) เพื่อข้อมูลเพียงพอ
# =========================
delta = df["Close"].diff()
gain  = delta.where(delta > 0, 0.0)
loss  = -delta.where(delta < 0, 0.0)

avg_gain = gain.ewm(alpha=1/14, adjust=False).mean()
avg_loss = loss.ewm(alpha=1/14, adjust=False).mean()

rs  = avg_gain / avg_loss
rsi = float((100 - (100 / (1 + rs))).iloc[-1])

# =========================
# EMA POSITION
# =========================
def pos(p, e):
    return "🟢 เหนือ" if p > e else "🔴 ใต้"

ema_block = f"""📊 EMA STATUS
EMA20  : {round(ema20,2)}  ({pos(price, ema20)})
EMA50  : {round(ema50,2)}  ({pos(price, ema50)})
EMA200 : {round(ema200,2)} ({pos(price, ema200)})"""

# =========================
# TREND SCORE
# =========================
def trend_score_df(d):
    """คืนค่า 0–3 ตามจำนวนเงื่อนไข bullish ที่เป็นจริง"""
    s = 0
    p = float(d["Close"].iloc[-1])
    e20  = float(d["EMA20"].iloc[-1])
    e50  = float(d["EMA50"].iloc[-1])
    e200 = float(d["EMA200"].iloc[-1])
    if p   > e20:  s += 1
    if e20 > e50:  s += 1
    if e50 > e200: s += 1
    return s

# ถ่วงน้ำหนัก: 5d=30%, 1m=35%, 1y=35% → max = 9 * 1/3 ≈ 3 แต่ normalize ต่อท้าย
raw_trend = (
    trend_score_df(df_5d) * 0.30 +
    trend_score_df(df_1m) * 0.35 +
    trend_score_df(df)    * 0.35
)
# raw_trend อยู่ในช่วง 0–3 → normalize เป็น -1 ถึง +1
trend_normalized = (raw_trend / 3) * 2 - 1  # -1=full bear, +1=full bull

# =========================
# REGIME
# =========================
if price > ema20 > ema50 > ema200:
    regime = "📈 Uptrend"
elif price < ema20 < ema50 < ema200:
    regime = "📉 Downtrend"
elif rsi < 25:
    regime = "⚠️ Oversold"
elif rsi > 75:
    regime = "⚠️ Overbought"
else:
    regime = "➖ Sideway"

# =========================
# NEWS — แปลโดย Claude API
# =========================
def translate_news_claude(titles: list[str]) -> list[str]:
    """แปลหัวข้อข่าวภาษาอังกฤษเป็นภาษาไทยที่อ่านเข้าใจง่าย"""
    if not ANTHROPIC_API_KEY:
        return titles  # fallback ถ้าไม่มี key

    numbered = "\n".join(f"{i+1}. {t}" for i, t in enumerate(titles))
    prompt = (
        "แปลหัวข้อข่าวการเงินต่อไปนี้เป็นภาษาไทยที่อ่านเข้าใจง่าย กระชับ และถูกต้องตามบริบทการลงทุน "
        "ไม่ต้องแปลตรงตัวทุกคำ ให้ได้ใจความที่ชัดเจน ตอบเฉพาะหัวข้อที่แปลแล้ว ไม่ต้องมีคำอธิบายเพิ่ม "
        "รูปแบบ: หมายเลข. หัวข้อภาษาไทย\n\n"
        f"{numbered}"
    )

    message = claude.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=800,
        messages=[{"role": "user", "content": prompt}]
    )

    lines = message.content[0].text.strip().split("\n")
    result = []
    for line in lines:
        # ตัดหมายเลขนำหน้าออก เช่น "1. " หรือ "1) "
        line = line.strip()
        if line and line[0].isdigit():
            line = line.split(".", 1)[-1].strip()
            line = line.split(")", 1)[-1].strip()
        if line:
            result.append(line)

    # กรณี Claude ตอบน้อยกว่า ให้ fallback เป็น title เดิม
    while len(result) < len(titles):
        result.append(titles[len(result)])

    return result[:len(titles)]

def sentiment_label(score: float) -> tuple[str, float, str]:
    if score > 0.3:
        return "🟢 ขาขึ้นแรง", 0.6,  "Strong Bullish"
    elif score > 0.1:
        return "🟢 ขาขึ้น",   0.2,  "Bullish"
    elif score < -0.3:
        return "🔴 ขาลงแรง", -0.6, "Strong Bearish"
    elif score < -0.1:
        return "🔴 ขาลง",   -0.2, "Bearish"
    else:
        return "⚪ เป็นกลาง", 0.0,  "Neutral"

feed = feedparser.parse(
    "https://feeds.finance.yahoo.com/rss/2.0/headline?s=GC=F&region=US&lang=en-US"
)

raw_titles = [item.title for item in feed.entries[:6]]
thai_titles = translate_news_claude(raw_titles)

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
# SIGNAL — normalize รวม trend + sentiment
# =========================
avg_sentiment = sum(n["expected"] for n in news_items) / max(len(news_items), 1)
# avg_sentiment อยู่ในช่วง -0.6 ถึง +0.6

# รวมสัญญาณ: trend 60%, sentiment 40%
combined = trend_normalized * 0.60 + avg_sentiment * 0.40

# map combined (-1 ถึง +1) → prob (0 ถึง 100)
prob = round(max(0, min(100, 50 + combined * 50)), 2)

if prob >= 65:
    signal = "BUY 📈"
elif prob <= 35:
    signal = "SELL 📉"
else:
    signal = "HOLD ⏳"

confidence = int(min(95, abs(prob - 50) * 2))

# =========================
# TP / SL — ใช้ ATR แทน fixed %
# =========================
def tp_sl_atr(signal, price, atr):
    if "BUY" in signal:
        return (
            round(price + atr * 0.8, 2),
            round(price + atr * 1.5, 2),
            round(price + atr * 2.5, 2),
            round(price - atr * 0.8, 2),
            round(price - atr * 1.5, 2),
            round(price - atr * 2.2, 2),
        )
    elif "SELL" in signal:
        return (
            round(price - atr * 0.8, 2),
            round(price - atr * 1.5, 2),
            round(price - atr * 2.5, 2),
            round(price + atr * 0.8, 2),
            round(price + atr * 1.5, 2),
            round(price + atr * 2.2, 2),
        )
    else:
        return (
            round(price + atr * 0.8, 2),
            round(price + atr * 1.5, 2),
            round(price + atr * 2.5, 2),
            round(price - atr * 0.8, 2),
            round(price - atr * 1.5, 2),
            round(price - atr * 2.2, 2),
        )

tp1, tp2, tp3, sl1, sl2, sl3 = tp_sl_atr(signal, price, atr)

# =========================
# NEWS TEXT
# =========================
news_text = "📰 วิเคราะห์ข่าวรายตัว\n"
for i, n in enumerate(news_items, 1):
    news_text += f"""
🧾 ข่าว #{i}
{n['label_th']} ({n['label_en']})
📊 Sentiment : {n['sentiment']:+.2f}
📰 EN : {n['title_en']}
🇹🇭 TH : {n['title_th']}
{'─'*20}"""

# =========================
# TIME
# =========================
now = (datetime.utcnow() + timedelta(hours=7)).strftime("%d/%m/%Y %H:%M")

# =========================
# MESSAGE
# =========================
message = f"""
🤖📊 AI HEDGE FUND v11

🕒 {now}

💰 PRICE  : {round(price, 2)}
📉 CHANGE : {change:+}
📊 REGIME : {regime}

📊 TREND  : {round(raw_trend, 2)}/3.0
📈 RSI    : {round(rsi, 2)}
📰 SENTIMENT AVG : {avg_sentiment:+.2f}

🎯 SIGNAL     : {signal}
🔥 CONFIDENCE : {confidence}%
🎯 PROBABILITY: {prob}%

💰 TP / SL  (ATR={round(atr,2)})
TP1 : {tp1}
TP2 : {tp2}
TP3 : {tp3}

SL1 : {sl1}
SL2 : {sl2}
SL3 : {sl3}

────────────────────
{ema_block}

────────────────────
{news_text}
"""

# =========================
# SEND TELEGRAM
# =========================
if TOKEN and CHAT_ID:
    resp = requests.post(
        f"https://api.telegram.org/bot{TOKEN}/sendMessage",
        data={"chat_id": CHAT_ID, "text": message}
    )
    print("Telegram:", resp.status_code)

print(message)
print("DONE")
