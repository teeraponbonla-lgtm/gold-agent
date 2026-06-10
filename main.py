import os
import requests
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

# =========================
# CONFIG
# =========================
TOKEN          = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID        = os.environ.get("TELEGRAM_CHAT_ID")

# =========================
# DATA — Multi-Timeframe
# =========================
gold = yf.Ticker("GC=F")

df_1d  = gold.history(period="6mo",  interval="1d")
df_4h  = gold.history(period="60d",  interval="60m")   # yfinance ไม่มี 4h ใช้ 1h แล้ว resample
df_1h  = gold.history(period="7d",   interval="60m")
df_30m = gold.history(period="5d",   interval="30m")

# resample 1h → 4h
df_4h = df_4h.resample("4h").agg({
    "Open": "first", "High": "max",
    "Low": "min",    "Close": "last",
    "Volume": "sum"
}).dropna()

# =========================
# EMA
# =========================
def add_ema(d):
    d = d.copy()
    d["EMA20"]  = d["Close"].ewm(span=20,  adjust=False).mean()
    d["EMA50"]  = d["Close"].ewm(span=50,  adjust=False).mean()
    d["EMA200"] = d["Close"].ewm(span=200, adjust=False).mean()
    return d

df_1d  = add_ema(df_1d)
df_4h  = add_ema(df_4h)
df_1h  = add_ema(df_1h)
df_30m = add_ema(df_30m)

price = float(df_30m["Close"].iloc[-1])

# =========================
# ATR (14) จาก 1H
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

atr_1h = calc_atr(df_1h)

# =========================
# RSI (14) จาก 1H
# =========================
delta    = df_1h["Close"].diff()
gain     = delta.where(delta > 0, 0.0)
loss     = -delta.where(delta < 0, 0.0)
avg_gain = gain.ewm(alpha=1/14, adjust=False).mean()
avg_loss = loss.ewm(alpha=1/14, adjust=False).mean()
rs       = avg_gain / avg_loss
rsi_1h   = float((100 - (100 / (1 + rs))).iloc[-1])

# =========================
# เงื่อนไข 1: TREND (1D + 4H)
# =========================
def get_trend(d):
    p    = float(d["Close"].iloc[-1])
    e20  = float(d["EMA20"].iloc[-1])
    e50  = float(d["EMA50"].iloc[-1])
    e200 = float(d["EMA200"].iloc[-1])
    if p > e20 > e50:
        return "bull"
    elif p < e20 < e50:
        return "bear"
    else:
        return "neutral"

trend_1d = get_trend(df_1d)
trend_4h = get_trend(df_4h)

# เทรนด์ต้องตรงกันทั้ง 1D และ 4H
if trend_1d == "bull" and trend_4h == "bull":
    master_trend = "bull"
elif trend_1d == "bear" and trend_4h == "bear":
    master_trend = "bear"
else:
    master_trend = "neutral"

trend_ok = master_trend in ("bull", "bear")

# =========================
# เงื่อนไข 2: SUPPORT / RESISTANCE (Pivot Points จาก 1D + EMA)
# =========================
def pivot_levels(d, lookback=20):
    """หา Swing High/Low จาก lookback แท่ง"""
    highs = d["High"].rolling(5, center=True).max()
    lows  = d["Low"].rolling(5, center=True).min()
    swing_highs = d["High"][d["High"] == highs].dropna().tail(lookback)
    swing_lows  = d["Low"][d["Low"] == lows].dropna().tail(lookback)
    return list(swing_highs.values), list(swing_lows.values)

res_levels, sup_levels = pivot_levels(df_1d)

# EMA 20/50/200 จาก 4H เป็นแนวรับ/แนวต้านเพิ่มเติม
ema_levels = [
    float(df_4h["EMA20"].iloc[-1]),
    float(df_4h["EMA50"].iloc[-1]),
    float(df_4h["EMA200"].iloc[-1]),
]

all_resistance = sorted(res_levels + [e for e in ema_levels if e > price])
all_support    = sorted([e for e in sup_levels + [e for e in ema_levels if e < price]], reverse=True)

zone_pct = 0.003  # ราคาต้องอยู่ในโซน ±0.3% ของแนวรับ/แนวต้าน

nearest_sup = next((s for s in all_support    if abs(price - s) / price <= zone_pct), None)
nearest_res = next((r for r in all_resistance if abs(price - r) / price <= zone_pct), None)

in_support_zone    = nearest_sup is not None
in_resistance_zone = nearest_res is not None
sr_zone_ok         = in_support_zone or in_resistance_zone

# โซนที่อยู่
if in_support_zone:
    zone_label = f"🟩 แนวรับ ~{round(nearest_sup,2)}"
    zone_bias  = "bull"
elif in_resistance_zone:
    zone_label = f"🟥 แนวต้าน ~{round(nearest_res,2)}"
    zone_bias  = "bear"
else:
    zone_label = "⬜ ไม่อยู่ในโซน"
    zone_bias  = "neutral"

# =========================
# เงื่อนไข 3: EMA CONFIRM (1H)
# =========================
ema20_1h  = float(df_1h["EMA20"].iloc[-1])
ema50_1h  = float(df_1h["EMA50"].iloc[-1])

if zone_bias == "bull":
    # ราคาเหนือ EMA20 หรือ EMA20 เหนือ EMA50
    ema_confirm = price > ema20_1h or ema20_1h > ema50_1h
elif zone_bias == "bear":
    # ราคาใต้ EMA20 หรือ EMA20 ใต้ EMA50
    ema_confirm = price < ema20_1h or ema20_1h < ema50_1h
else:
    ema_confirm = False

# =========================
# เงื่อนไข 4: PRICE ACTION (30M — แท่งปิดล่าสุด)
# =========================
def check_price_action(d, bias):
    """ตรวจ Engulfing และ Pin Bar บนแท่งล่าสุด"""
    if len(d) < 3:
        return False, "ข้อมูลไม่พอ"

    c0 = d.iloc[-1]   # แท่งล่าสุด
    c1 = d.iloc[-2]   # แท่งก่อนหน้า

    o0, h0, l0, cl0 = c0["Open"], c0["High"], c0["Low"], c0["Close"]
    o1, h1, l1, cl1 = c1["Open"], c1["High"], c1["Low"], c1["Close"]

    body0  = abs(cl0 - o0)
    range0 = h0 - l0
    wick_upper = h0 - max(o0, cl0)
    wick_lower = min(o0, cl0) - l0

    signals = []

    # --- Bullish Engulfing ---
    if bias == "bull":
        if cl1 < o1 and cl0 > o0:           # แท่งก่อนลง แท่งนี้ขึ้น
            if o0 <= cl1 and cl0 >= o1:      # กลืนกิน body
                signals.append("🕯 Bullish Engulfing")

    # --- Bearish Engulfing ---
    if bias == "bear":
        if cl1 > o1 and cl0 < o0:
            if o0 >= cl1 and cl0 <= o1:
                signals.append("🕯 Bearish Engulfing")

    # --- Bullish Pin Bar ---
    if bias == "bull":
        if range0 > 0 and body0 / range0 < 0.35 and wick_lower > body0 * 2:
            signals.append("📌 Bullish Pin Bar")

    # --- Bearish Pin Bar ---
    if bias == "bear":
        if range0 > 0 and body0 / range0 < 0.35 and wick_upper > body0 * 2:
            signals.append("📌 Bearish Pin Bar")

    return len(signals) > 0, ", ".join(signals) if signals else "ไม่มีสัญญาณ"

pa_ok, pa_signal = check_price_action(df_30m, zone_bias)

# =========================
# เงื่อนไข 5: RR อย่างน้อย 1:2
# =========================
rr_ok    = False
rr_label = ""
entry = tp = sl = None

if zone_bias == "bull" and nearest_sup:
    sl    = round(nearest_sup - atr_1h * 0.5, 2)
    entry = round(price, 2)
    risk  = entry - sl
    tp    = round(entry + risk * 2, 2)
    rr    = round((tp - entry) / (entry - sl), 2) if (entry - sl) > 0 else 0
    rr_ok = rr >= 2.0
    rr_label = f"RR = 1:{rr}"

elif zone_bias == "bear" and nearest_res:
    sl    = round(nearest_res + atr_1h * 0.5, 2)
    entry = round(price, 2)
    risk  = sl - entry
    tp    = round(entry - risk * 2, 2)
    rr    = round((entry - tp) / (sl - entry), 2) if (sl - entry) > 0 else 0
    rr_ok = rr >= 2.0
    rr_label = f"RR = 1:{rr}"

# =========================
# รวมเงื่อนไขทั้ง 4
# =========================
conditions = {
    "✅ เทรนด์ (1D+4H)" if trend_ok     else "❌ เทรนด์ (1D+4H)":     trend_ok,
    "✅ โซน S/R"         if sr_zone_ok   else "❌ โซน S/R":             sr_zone_ok,
    "✅ EMA Confirm"     if ema_confirm  else "❌ EMA Confirm":         ema_confirm,
    "✅ Price Action"    if pa_ok        else "❌ Price Action":        pa_ok,
    f"✅ {rr_label}"     if rr_ok        else f"❌ RR < 1:2":           rr_ok,
}

all_pass = all(conditions.values())

# =========================
# ถ้าไม่ครบเงื่อนไข → จบ ไม่ส่ง Telegram
# =========================
if not all_pass:
    cond_text = "\n".join(conditions.keys())
    print(f"[SKIP] เงื่อนไขไม่ครบ:\n{cond_text}")
    exit(0)

# =========================
# ถ้าครบทุกเงื่อนไข → สร้างสัญญาณ
# =========================
signal     = "ซื้อ 📈" if zone_bias == "bull" else "ขาย 📉"
trend_text = "📈 ขาขึ้น" if master_trend == "bull" else "📉 ขาลง"
now        = (datetime.utcnow() + timedelta(hours=7)).strftime("%d/%m/%Y %H:%M")

cond_text = "\n".join(conditions.keys())

message = f"""🚨 AI GOLD SIGNAL 🚨

🕒 {now}
💰 ราคา : {round(price, 2)}

━━━━━━━━━━━━━━━━━━━━
✅ เงื่อนไขครบทั้ง 4 ข้อ
━━━━━━━━━━━━━━━━━━━━
{cond_text}

📊 รายละเอียด
🔹 เทรนด์หลัก  : {trend_text}  (1D: {trend_1d} | 4H: {trend_4h})
🔹 โซน         : {zone_label}
🔹 Price Action : {pa_signal}
🔹 RSI (1H)    : {round(rsi_1h, 2)}
🔹 ATR (1H)    : {round(atr_1h, 2)}

━━━━━━━━━━━━━━━━━━━━
🎯 สัญญาณ : {signal}

📌 Entry : {entry}
🎯 TP    : {tp}
🛑 SL    : {sl}
📐 {rr_label}
━━━━━━━━━━━━━━━━━━━━
⚠️ ใช้ประกอบการตัดสินใจเท่านั้น
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
