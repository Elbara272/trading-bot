import logging
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
import requests
from datetime import datetime

BOT_TOKEN = "8929145469:AAEXqpswl4bqVMkgfJrCbD-nCFYJ9eMjer0"

logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

MARKETS = {
    "forex": {
        "EUR/USD 🇪🇺": "EURUSD=X",
        "GBP/USD 🇬🇧": "GBPUSD=X",
        "USD/JPY 🇯🇵": "USDJPY=X",
        "AUD/USD 🇦🇺": "AUDUSD=X",
    },
    "metals": {
        "Gold 🥇": "GC=F",
        "Silver 🥈": "SI=F",
    },
    "crypto": {
        "Bitcoin ₿": "BTC-USD",
        "Ethereum 💎": "ETH-USD",
        "BNB 🔶": "BNB-USD",
    }
}

def get_price_data(symbol):
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
        params = {"range": "5d", "interval": "1h"}
        headers = {"User-Agent": "Mozilla/5.0"}
        r = requests.get(url, params=params, headers=headers, timeout=10)
        data = r.json()
        closes = data["chart"]["result"][0]["indicators"]["quote"][0]["close"]
        highs = data["chart"]["result"][0]["indicators"]["quote"][0]["high"]
        lows = data["chart"]["result"][0]["indicators"]["quote"][0]["low"]
        closes = [x for x in closes if x is not None]
        highs = [x for x in highs if x is not None]
        lows = [x for x in lows if x is not None]
        return closes, highs, lows
    except Exception as e:
        logger.error(f"Error: {e}")
        return None, None, None

def calc_rsi(prices, period=14):
    if len(prices) < period + 1:
        return 50
    gains, losses = [], []
    for i in range(1, len(prices)):
        diff = prices[i] - prices[i-1]
        gains.append(max(diff, 0))
        losses.append(max(-diff, 0))
    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period
    if avg_loss == 0:
        return 100
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

def calc_ema(prices, period):
    if len(prices) < period:
        return prices[-1]
    k = 2 / (period + 1)
    ema = sum(prices[:period]) / period
    for p in prices[period:]:
        ema = p * k + ema * (1 - k)
    return ema

def analyze(symbol, name):
    closes, highs, lows = get_price_data(symbol)
    if not closes or len(closes) < 20:
        return None

    price = closes[-1]
    rsi = calc_rsi(closes)
    ema9 = calc_ema(closes, 9)
    ema21 = calc_ema(closes, 21)
    
    # MACD
    ema12 = calc_ema(closes, 12)
    ema26 = calc_ema(closes, 26) if len(closes) >= 26 else ema12
    macd = ema12 - ema26

    buy = 0
    sell = 0

    if rsi < 35: buy += 2
    elif rsi < 45: buy += 1
    elif rsi > 65: sell += 2
    elif rsi > 55: sell += 1

    if ema9 > ema21: buy += 1
    else: sell += 1

    if macd > 0: buy += 1
    else: sell += 1

    support = min(lows[-20:])
    resistance = max(highs[-20:])

    total = buy + sell
    if buy > sell:
        signal = "🟢 شراء / BUY"
        conf = int((buy/total)*100)
    elif sell > buy:
        signal = "🔴 بيع / SELL"
        conf = int((sell/total)*100)
    else:
        signal = "⚪️ محايد"
        conf = 50

    return {
        "name": name, "price": price, "signal": signal,
        "conf": conf, "rsi": rsi, "macd": macd,
        "support": support, "resistance": resistance,
        "time": datetime.now().strftime("%H:%M")
    }

def fmt(a):
    bar = "█" * (a["conf"]//10) + "░" * (10 - a["conf"]//10)
    return (
        f"📊 *{a['name']}*\n"
        f"━━━━━━━━━━━━━━━\n"
        f"💰 السعر: `{a['price']:.5f}`\n"
        f"🎯 التوصية: {a['signal']}\n"
        f"📈 الثقة: {a['conf']}%\n"
        f"`{bar}`\n"
        f"━━━━━━━━━━━━━━━\n"
        f"📉 RSI: `{a['rsi']:.1f}`\n"
        f"📊 MACD: `{a['macd']:.5f}`\n"
        f"🔻 دعم: `{a['support']:.5f}`\n"
        f"🔺 مقاومة: `{a['resistance']:.5f}`\n"
        f"━━━━━━━━━━━━━━━\n"
        f"⚠️ للتعليم فقط\n"
        f"🕐 {a['time']}"
    )

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = [
        [InlineKeyboardButton("💱 فوركس", callback_data="cat_forex"),
         InlineKeyboardButton("🥇 معادن", callback_data="cat_metals")],
        [InlineKeyboardButton("₿ عملات رقمية", callback_data="cat_crypto")],
    ]
    await update.message.reply_text(
        "🤖 *بوت التداول الاحترافي*\n\nاختر السوق:",
        reply_markup=InlineKeyboardMarkup(kb),
        parse_mode="Markdown"
    )

async def btn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    d = q.data

    if d.startswith("cat_"):
        cat = d[4:]
        markets = MARKETS.get(cat, {})
        kb = []
        row = []
        for name, sym in markets.items():
            row.append(InlineKeyboardButton(name, callback_data=f"a_{sym}|{name}"))
            if len(row) == 2:
                kb.append(row)
                row = []
        if row:
            kb.append(row)
        kb.append([InlineKeyboardButton("🔙 رجوع", callback_data="back")])
        await q.edit_message_text("اختر الزوج:", reply_markup=InlineKeyboardMarkup(kb))

    elif d.startswith("a_"):
        parts = d[2:].split("|")
        sym, name = parts[0], parts[1]
        await q.edit_message_text("⏳ جاري التحليل...")
        a = analyze(sym, name)
        if a:
            kb = [[
                InlineKeyboardButton("🔄 تحديث", callback_data=d),
                InlineKeyboardButton("🔙 رجوع", callback_data="back")
            ]]
            await q.edit_message_text(fmt(a), reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")
        else:
            await q.edit_message_text("❌ خطأ في جلب البيانات",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙", callback_data="back")]]))

    elif d == "back":
        kb = [
            [InlineKeyboardButton("💱 فوركس", callback_data="cat_forex"),
             InlineKeyboardButton("🥇 معادن", callback_data="cat_metals")],
            [InlineKeyboardButton("₿ عملات رقمية", callback_data="cat_crypto")],
        ]
        await q.edit_message_text("🤖 *بوت التداول*\n\nاختر السوق:",
            reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")

def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(btn))
    logger.info("البوت شغال!")
    app.run_polling()

if __name__ == "__main__":
    main()
