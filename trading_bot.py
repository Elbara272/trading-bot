import logging
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
import pandas as pd
import numpy as np
import requests
from datetime import datetime
import time

# ===== إعدادات البوت =====
BOT_TOKEN = "8929145469:AAEXqpswl4bqVMkgfJrCbD-nCFYJ9eMjer0"

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# ===== الأسواق المتاحة =====
MARKETS = {
    "forex": {
        "EUR/USD": "EURUSD=X",
        "GBP/USD": "GBPUSD=X",
        "USD/JPY": "USDJPY=X",
        "USD/CHF": "USDCHF=X",
        "AUD/USD": "AUDUSD=X",
    },
    "metals": {
        "Gold 🥇": "GC=F",
        "Silver 🥈": "SI=F",
    },
    "crypto": {
        "Bitcoin ₿": "BTC-USD",
        "Ethereum 💎": "ETH-USD",
        "BNB": "BNB-USD",
    }
}

def get_price_data(symbol: str, period: str = "5d", interval: str = "1h"):
    """جلب بيانات السعر من Yahoo Finance"""
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
        params = {
            "range": period,
            "interval": interval,
            "includePrePost": False
        }
        headers = {"User-Agent": "Mozilla/5.0"}
        response = requests.get(url, params=params, headers=headers, timeout=10)
        data = response.json()
        
        chart = data["chart"]["result"][0]
        timestamps = chart["timestamp"]
        closes = chart["indicators"]["quote"][0]["close"]
        highs = chart["indicators"]["quote"][0]["high"]
        lows = chart["indicators"]["quote"][0]["low"]
        volumes = chart["indicators"]["quote"][0].get("volume", [0]*len(closes))
        
        df = pd.DataFrame({
            "timestamp": timestamps,
            "close": closes,
            "high": highs,
            "low": lows,
            "volume": volumes
        }).dropna()
        
        return df
    except Exception as e:
        logger.error(f"Error fetching data for {symbol}: {e}")
        return None

def calculate_rsi(prices, period=14):
    """حساب مؤشر RSI"""
    delta = prices.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    return rsi

def calculate_macd(prices, fast=12, slow=26, signal=9):
    """حساب مؤشر MACD"""
    ema_fast = prices.ewm(span=fast, adjust=False).mean()
    ema_slow = prices.ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram

def calculate_bollinger_bands(prices, period=20, std_dev=2):
    """حساب Bollinger Bands"""
    sma = prices.rolling(window=period).mean()
    std = prices.rolling(window=period).std()
    upper = sma + (std * std_dev)
    lower = sma - (std * std_dev)
    return upper, sma, lower

def calculate_ema(prices, period):
    """حساب المتوسط المتحرك الأسي"""
    return prices.ewm(span=period, adjust=False).mean()

def analyze_market(symbol: str, market_name: str):
    """تحليل شامل للسوق وإعطاء توصية"""
    df = get_price_data(symbol)
    if df is None or len(df) < 30:
        return None
    
    prices = df["close"]
    current_price = prices.iloc[-1]
    
    # حساب المؤشرات
    rsi = calculate_rsi(prices)
    macd_line, signal_line, histogram = calculate_macd(prices)
    upper_bb, middle_bb, lower_bb = calculate_bollinger_bands(prices)
    ema9 = calculate_ema(prices, 9)
    ema21 = calculate_ema(prices, 21)
    
    # آخر قيم
    rsi_val = rsi.iloc[-1]
    macd_val = macd_line.iloc[-1]
    signal_val = signal_line.iloc[-1]
    hist_val = histogram.iloc[-1]
    upper_val = upper_bb.iloc[-1]
    lower_val = lower_bb.iloc[-1]
    ema9_val = ema9.iloc[-1]
    ema21_val = ema21.iloc[-1]
    
    # نقاط التحليل
    buy_signals = 0
    sell_signals = 0
    reasons = []
    
    # RSI
    if rsi_val < 35:
        buy_signals += 2
        reasons.append(f"RSI منخفض ({rsi_val:.1f}) → إشارة شراء قوية")
    elif rsi_val < 45:
        buy_signals += 1
        reasons.append(f"RSI ({rsi_val:.1f}) → ميل للشراء")
    elif rsi_val > 65:
        sell_signals += 2
        reasons.append(f"RSI مرتفع ({rsi_val:.1f}) → إشارة بيع قوية")
    elif rsi_val > 55:
        sell_signals += 1
        reasons.append(f"RSI ({rsi_val:.1f}) → ميل للبيع")
    
    # MACD
    if macd_val > signal_val and hist_val > 0:
        buy_signals += 2
        reasons.append("MACD فوق الإشارة → زخم صاعد")
    elif macd_val < signal_val and hist_val < 0:
        sell_signals += 2
        reasons.append("MACD تحت الإشارة → زخم هابط")
    
    # Bollinger Bands
    if current_price <= lower_val:
        buy_signals += 2
        reasons.append("السعر عند الحد السفلي لـ BB → فرصة شراء")
    elif current_price >= upper_val:
        sell_signals += 2
        reasons.append("السعر عند الحد العلوي لـ BB → فرصة بيع")
    
    # EMA Crossover
    if ema9_val > ema21_val:
        buy_signals += 1
        reasons.append("EMA9 فوق EMA21 → اتجاه صاعد")
    else:
        sell_signals += 1
        reasons.append("EMA9 تحت EMA21 → اتجاه هابط")
    
    # تحديد التوصية
    total = buy_signals + sell_signals
    if total == 0:
        return None
    
    buy_pct = (buy_signals / total) * 100
    
    if buy_signals > sell_signals:
        signal = "🟢 شراء / BUY"
        strength = "قوية جداً" if buy_pct >= 75 else "متوسطة" if buy_pct >= 60 else "ضعيفة"
        confidence = int(buy_pct)
    elif sell_signals > buy_signals:
        signal = "🔴 بيع / SELL"
        sell_pct = (sell_signals / total) * 100
        strength = "قوية جداً" if sell_pct >= 75 else "متوسطة" if sell_pct >= 60 else "ضعيفة"
        confidence = int(sell_pct)
    else:
        signal = "⚪️ محايد / NEUTRAL"
        strength = "لا توصية"
        confidence = 50
    
    # حساب الدعم والمقاومة
    recent_high = df["high"].tail(20).max()
    recent_low = df["low"].tail(20).min()
    
    return {
        "market": market_name,
        "symbol": symbol,
        "price": current_price,
        "signal": signal,
        "strength": strength,
        "confidence": confidence,
        "rsi": rsi_val,
        "macd": macd_val,
        "histogram": hist_val,
        "support": recent_low,
        "resistance": recent_high,
        "reasons": reasons[:3],  # أهم 3 أسباب
        "time": datetime.now().strftime("%H:%M:%S")
    }

def format_signal_message(analysis: dict) -> str:
    """تنسيق رسالة التوصية"""
    confidence_bar = "█" * (analysis["confidence"] // 10) + "░" * (10 - analysis["confidence"] // 10)
    
    msg = f"""
📊 *تحليل {analysis['market']}*
━━━━━━━━━━━━━━━━━━

💰 *السعر الحالي:* `{analysis['price']:.5f}`

🎯 *التوصية:* {analysis['signal']}
💪 *قوة الإشارة:* {analysis['strength']}
📈 *نسبة الثقة:* {analysis['confidence']}%
`{confidence_bar}`

━━━━━━━━━━━━━━━━━━
📉 *المؤشرات التقنية:*
• RSI: `{analysis['rsi']:.1f}`
• MACD: `{analysis['macd']:.5f}`

🏔 *المقاومة:* `{analysis['resistance']:.5f}`
🏔 *الدعم:* `{analysis['support']:.5f}`

━━━━━━━━━━━━━━━━━━
🔍 *أسباب التحليل:*
"""
    for reason in analysis["reasons"]:
        msg += f"• {reason}\n"
    
    msg += f"""
━━━━━━━━━━━━━━━━━━
⚠️ *تحذير:* هذا تحليل تقني فقط، التداول ينطوي على مخاطر.
🕐 *وقت التحليل:* {analysis['time']}
"""
    return msg

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """أمر البداية"""
    keyboard = [
        [InlineKeyboardButton("💱 فوركس", callback_data="cat_forex"),
         InlineKeyboardButton("🥇 معادن", callback_data="cat_metals")],
        [InlineKeyboardButton("₿ عملات رقمية", callback_data="cat_crypto")],
        [InlineKeyboardButton("📊 تحليل كل الأسواق", callback_data="analyze_all")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "🤖 *بوت التداول الاحترافي*\n\n"
        "مرحباً! أنا بوت تحليل الأسواق المالية\n"
        "أستخدم مؤشرات RSI، MACD، وBollinger Bands\n\n"
        "اختر السوق الذي تريد تحليله:",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة الأزرار"""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    
    if data.startswith("cat_"):
        category = data.replace("cat_", "")
        markets = MARKETS.get(category, {})
        
        keyboard = []
        row = []
        for i, (name, symbol) in enumerate(markets.items()):
            row.append(InlineKeyboardButton(name, callback_data=f"analyze_{symbol}_{name}"))
            if len(row) == 2:
                keyboard.append(row)
                row = []
        if row:
            keyboard.append(row)
        keyboard.append([InlineKeyboardButton("🔙 رجوع", callback_data="back_main")])
        
        await query.edit_message_text(
            "اختر الزوج للتحليل:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    
    elif data.startswith("analyze_") and data != "analyze_all":
        parts = data.split("_", 2)
        symbol = parts[1]
        market_name = parts[2] if len(parts) > 2 else symbol
        
        await query.edit_message_text("⏳ جاري التحليل... انتظر لحظة")
        
        analysis = analyze_market(symbol, market_name)
        
        if analysis:
            msg = format_signal_message(analysis)
            keyboard = [[
                InlineKeyboardButton("🔄 تحديث", callback_data=f"analyze_{symbol}_{market_name}"),
                InlineKeyboardButton("🔙 رجوع", callback_data="back_main")
            ]]
            await query.edit_message_text(
                msg,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode="Markdown"
            )
        else:
            await query.edit_message_text(
                "❌ تعذر جلب البيانات، حاول مرة ثانية",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 رجوع", callback_data="back_main")
                ]])
            )
    
    elif data == "analyze_all":
        await query.edit_message_text("⏳ جاري تحليل كل الأسواق... قد يستغرق دقيقة")
        
        results = []
        for category, markets in MARKETS.items():
            for name, symbol in markets.items():
                analysis = analyze_market(symbol, name)
                if analysis:
                    results.append(analysis)
                await asyncio.sleep(0.5)
        
        if results:
            msg = "📊 *ملخص كل الأسواق*\n━━━━━━━━━━━━━━━━\n\n"
            for r in results:
                msg += f"*{r['market']}*: {r['signal']} ({r['confidence']}%)\n"
            msg += f"\n🕐 {datetime.now().strftime('%H:%M:%S')}"
            
            await query.edit_message_text(
                msg,
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 رجوع", callback_data="back_main")
                ]]),
                parse_mode="Markdown"
            )
        else:
            await query.edit_message_text("❌ تعذر جلب البيانات")
    
    elif data == "back_main":
        keyboard = [
            [InlineKeyboardButton("💱 فوركس", callback_data="cat_forex"),
             InlineKeyboardButton("🥇 معادن", callback_data="cat_metals")],
            [InlineKeyboardButton("₿ عملات رقمية", callback_data="cat_crypto")],
            [InlineKeyboardButton("📊 تحليل كل الأسواق", callback_data="analyze_all")]
        ]
        await query.edit_message_text(
            "🤖 *بوت التداول الاحترافي*\n\nاختر السوق:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )

def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))
    
    print("✅ البوت شغال!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
