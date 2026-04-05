import bot.state as state
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
from config import Config
from bot.ai_engine import analyze_token
from bot.scanner import get_new_solana_tokens
from bot.risk import get_positions, get_trade_history
from bot.monitor import get_portfolio_summary, format_signal_message

# Simpan state input manual
waiting_for_buy = {}

def auth_required(func):
    async def wrapper(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        chat_id = update.effective_chat.id if update.effective_chat else None
        if chat_id != Config.CHAT_ID:
            return
        return await func(update, ctx)
    return wrapper

def main_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🟢 Auto ON", callback_data="auto_on"),
            InlineKeyboardButton("🔴 Auto OFF", callback_data="auto_off"),
        ],
        [
            InlineKeyboardButton("📊 Status", callback_data="status"),
            InlineKeyboardButton("📈 Posisi", callback_data="positions"),
        ],
        [
            InlineKeyboardButton("🔍 Scan", callback_data="scan"),
            InlineKeyboardButton("📜 History", callback_data="history"),
        ],
        [
            InlineKeyboardButton("💸 Buy Manual", callback_data="buy_manual"),
            InlineKeyboardButton("⚙️ Config", callback_data="config"),
        ],
        [
            InlineKeyboardButton("📊 Summary", callback_data="summary"),
        ],
    ])

@auth_required
async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    status = "🟢 AKTIF" if state.auto_trade_enabled else "🔴 NONAKTIF"
    msg = (
        f"🤖 *Solana Memecoin Trading Bot*\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"Auto Trading: {status}\n"
        f"Max Buy: `{Config.MAX_BUY_SOL} SOL`\n"
        f"Stop Loss: `{Config.STOP_LOSS_PCT}%`\n"
        f"Take Profit: `{Config.TAKE_PROFIT_PCT}%`\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"Pilih menu di bawah:"
    )
    await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=main_keyboard())

@auth_required
async def handle_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    text = update.message.text.strip()

    if chat_id in waiting_for_buy:
        # Kalau user ketik /start atau cancel, clear state
        if text.lower() in ["/start", "cancel", "batal", "stop", "undo"]:
            del waiting_for_buy[chat_id]
            await update.message.reply_text("❌ Buy manual dibatalkan.", reply_markup=main_keyboard())
            return
        step = waiting_for_buy[chat_id].get("step")

        if step == "address":
            waiting_for_buy[chat_id]["address"] = text
            waiting_for_buy[chat_id]["step"] = "amount"
            await update.message.reply_text(
                f"✅ Token: `{text}`\n\nMasukkan jumlah SOL (contoh: `0.1`):",
                parse_mode="Markdown"
            )

        elif step == "amount":
            try:
                amount = float(text)
                if amount <= 0:
                    raise ValueError
            except ValueError:
                await update.message.reply_text("❌ Jumlah tidak valid. Masukkan angka, contoh: `0.1`", parse_mode="Markdown")
                return

            address = waiting_for_buy[chat_id]["address"]
            del waiting_for_buy[chat_id]

            await update.message.reply_text(
                f"⏳ Executing buy...\n🪙 Token: `{address}`\n💰 Amount: `{amount} SOL`",
                parse_mode="Markdown"
            )

            from bot.trading import TradingEngine
            trader = TradingEngine()
            result = await trader.buy_token(address, amount)

            if result.get("success"):
                sig = result.get("signature", "")
                await update.message.reply_text(
                    f"✅ *Buy Berhasil!*\n"
                    f"🪙 Token: `{address}`\n"
                    f"💰 Amount: `{amount} SOL`\n"
                    f"🔗 [Lihat TX](https://solscan.io/tx/{sig})",
                    parse_mode="Markdown",
                    reply_markup=main_keyboard()
                )
            else:
                await update.message.reply_text(
                    f"❌ *Buy Gagal:* `{result.get('error')}`",
                    parse_mode="Markdown",
                    reply_markup=main_keyboard()
                )

async def button_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.from_user.id != Config.CHAT_ID:
        return

    data = query.data
    chat_id = query.message.chat_id

    if data == "auto_on":
        state.set_auto_trade(True)
        await query.edit_message_text(
            "🟢 *Auto Trading AKTIF!*\nBot akan beli otomatis kalau AI confidence >= 70%",
            parse_mode="Markdown", reply_markup=main_keyboard()
        )
    elif data == "auto_off":
        state.set_auto_trade(False)
        await query.edit_message_text(
            "🔴 *Auto Trading NONAKTIF*\nBot hanya kirim sinyal",
            parse_mode="Markdown", reply_markup=main_keyboard()
        )
    elif data == "buy_manual":
        waiting_for_buy[chat_id] = {"step": "address"}
        cancel_kb = InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="cancel_buy")]])
        await query.edit_message_text(
            "💸 *Buy Manual*\n\nKirim token address yang mau dibeli:",
            parse_mode="Markdown",
            reply_markup=cancel_kb
        )
    elif data == "cancel_buy":
        if chat_id in waiting_for_buy:
            del waiting_for_buy[chat_id]
        await query.edit_message_text("❌ Buy manual dibatalkan.", reply_markup=main_keyboard())
    elif data == "status":
        from bot.trading import TradingEngine
        trader = TradingEngine()
        balance = await trader.get_wallet_balance()
        summary = await get_portfolio_summary(balance)
        await query.edit_message_text(summary, parse_mode="Markdown", reply_markup=main_keyboard())
    elif data == "positions":
        positions = get_positions()
        if not positions:
            msg = "📭 Tidak ada posisi aktif"
        else:
            from bot.scanner import get_token_by_address
            import aiohttp
            msg = f"📈 *Posisi Aktif ({len(positions)}):*\n\n"
            async with aiohttp.ClientSession() as session:
                for pos in positions:
                    current = await get_token_by_address(session, pos["token_address"])
                    cur_price = current["price_usd"] if current else 0
                    entry = pos["entry_price"]
                    if entry and cur_price:
                        pct = ((cur_price - entry) / entry) * 100
                        pnl_emoji = "🟢" if pct >= 0 else "🔴"
                        pnl_str = f"{pnl_emoji} `{pct:+.1f}%`"
                    else:
                        pnl_str = "❓"
                    short_ca = pos['token_address'][:4] + "..." + pos['token_address'][-4:]
                    msg += (
                        f"🪙 *{pos['symbol']}* {pnl_str}\n"
                        f"  Entry: `${entry:.8f}`\n"
                        f"  Now:   `${cur_price:.8f}`\n"
                        f"  Size: `{pos['amount_sol']:.4f} SOL`\n"
                        f"  CA: `{pos['token_address']}`\n"
                        f"  SL: `${pos['stop_loss']:.8f}`\n"
                        f"  TP: `${pos['take_profit']:.8f}`\n\n"
                    )
        await query.edit_message_text(msg, parse_mode="Markdown", reply_markup=main_keyboard())
    elif data == "scan":
        await query.edit_message_text("🔍 Scanning token...", reply_markup=main_keyboard())
        tokens = await get_new_solana_tokens(10)
        if not tokens:
            msg = "❌ Tidak ada token yang memenuhi filter"
        else:
            msg = f"🔍 *{len(tokens)} Token Ditemukan:*\n\n"
            for t in tokens[:5]:
                msg += (
                    f"🪙 *{t['symbol']}* `${t['price_usd']:.8f}`\n"
                    f"  MC: `${t.get('market_cap',0):,.0f}` | M5: `${t.get('volume_m5',0):,.0f}`\n"
                    f"  Buys: `{t.get('buys_m5',0)}` | Ratio: `{t.get('buy_sell_ratio',0):.1f}`\n\n"
                )
        await query.edit_message_text(msg, parse_mode="Markdown", reply_markup=main_keyboard())
    elif data == "summary":
        from bot.risk import get_alltime_summary
        s = get_alltime_summary()
        net_emoji = "🟢" if s["net_pnl"] >= 0 else "🔴"
        msg = "📊 *Summary All-Time*\n"
        msg += "━━━━━━━━━━━━━━━━\n"
        msg += f"💼 Total Trade: `{s['total_trades']}`\n"
        msg += f"📈 Posisi Aktif: `{s['active_positions']}`\n\n"
        msg += f"🟢 Profit: `{s['win_count']}`\n"
        msg += f"🔴 Loss: `{s['loss_count']}`\n"
        msg += f"🎯 Winrate: `{s['winrate']:.1f}%`\n\n"
        msg += f"💰 Total Profit: `+{s['total_profit']:.4f} SOL`\n"
        msg += f"📉 Total Loss: `{s['total_loss']:.4f} SOL`\n"
        msg += f"{net_emoji} Net PnL: `{s['net_pnl']:+.4f} SOL`"
        await query.edit_message_text(msg, parse_mode="Markdown", reply_markup=main_keyboard())
    elif data == "history":
        trades = get_trade_history(10)
        if not trades:
            msg = "📭 Belum ada riwayat trade"
        else:
            msg = "📜 *Riwayat Trade:*\n\n"
            for t in trades:
                emoji = "🟢" if t['action'] == 'BUY' else "🔴"
                msg += f"{emoji} *{t['symbol']}* {t['action']} `{t['amount_sol']:.4f}` SOL\n"
                msg += f"  `{t['timestamp'][:16]}`\n\n"
        await query.edit_message_text(msg, parse_mode="Markdown", reply_markup=main_keyboard())
    elif data == "config":
        msg = (
            "⚙️ *Konfigurasi Bot:*\n"
            f"💰 Max Buy: `{Config.MAX_BUY_SOL} SOL`\n"
            f"🛑 Stop Loss: `{Config.STOP_LOSS_PCT}%`\n"
            f"🎯 Take Profit: `{Config.TAKE_PROFIT_PCT}%`\n"
            f"💧 Min Liquidity: `${Config.MIN_LIQUIDITY:,.0f}`\n"
            f"📊 Min Volume: `${Config.MIN_VOLUME:,.0f}`\n"
            f"⏱ Scan: `{Config.SCAN_INTERVAL}s`\n"
            f"🧠 Model: `{Config.GROQ_MODEL}`"
        )
        await query.edit_message_text(msg, parse_mode="Markdown", reply_markup=main_keyboard())

def setup_bot() -> Application:
    app = Application.builder().token(Config.TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_start))
    app.add_handler(CallbackQueryHandler(button_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_agent_message))
    return app

async def handle_agent_message(update, ctx):
    """Handle pesan biasa sebagai AI agent chat"""
    from telegram.ext import ContextTypes
    chat_id = update.effective_chat.id
    if chat_id != Config.CHAT_ID:
        return

    # Skip kalau lagi waiting for buy input
    if chat_id in waiting_for_buy:
        await handle_message(update, ctx)
        return

    user_msg = update.message.text.strip()

    # Ambil context real-time
    import bot.state as state
    from bot.trading import TradingEngine
    from bot.risk import get_positions
    from bot.agent import chat_with_agent

    trader = TradingEngine()
    balance = await trader.get_wallet_balance()
    positions = get_positions()

    # Inject current price real-time ke positions untuk AI
    from bot.scanner import get_token_by_address
    import aiohttp
    async with aiohttp.ClientSession() as session:
        for pos in positions:
            current = await get_token_by_address(session, pos["token_address"])
            if current:
                pos["current_price"] = current["price_usd"]
                entry = pos["entry_price"]
                pos["pct_change"] = round(((current["price_usd"] - entry) / entry) * 100, 2)
            else:
                pos["current_price"] = 0
                pos["pct_change"] = 0

    from bot.risk import get_trade_history, get_alltime_summary
    trade_history = get_trade_history(10)
    summary = get_alltime_summary()
    context = {
        "auto_trade": state.auto_trade_enabled,
        "balance": balance,
        "positions": positions,
        "trade_history": trade_history,
        "summary": summary,
        "config": {
            "max_buy": Config.MAX_BUY_SOL,
            "stop_loss": Config.STOP_LOSS_PCT,
            "take_profit": Config.TAKE_PROFIT_PCT,
        }
    }

    # Typing indicator
    await update.message.chat.send_action("typing")

    user_id = update.message.from_user.id
    result = await chat_with_agent(user_msg, context, user_id=user_id)
    reply = result["reply"]
    action = result["action"]

    # Eksekusi action
    action_type = action.get("type", "none")

    if action_type == "auto_on":
        state.set_auto_trade(True)
        reply += "\n\n✅ Auto trading diaktifkan!"

    elif action_type == "auto_off":
        state.set_auto_trade(False)
        reply += "\n\n🔴 Auto trading dinonaktifkan!"

    elif action_type == "buy":
        addr = action.get("address")
        amount = float(action.get("amount", Config.MAX_BUY_SOL))
        if addr:
            await update.message.reply_text(f"⏳ Executing buy `{amount}` SOL...", parse_mode="Markdown")
            buy_result = await trader.buy_token(addr, amount)
            if buy_result.get("success"):
                sig = buy_result.get("signature", "")
                reply += f"\n\n✅ Buy berhasil!\n🔗 [TX](https://solscan.io/tx/{sig})"
            else:
                reply += f"\n\n❌ Buy gagal: {buy_result.get('error')}"

    elif action_type == "sell":
        addr = action.get("address")
        # Cari address dari symbol kalau user bilang nama token
        if not addr:
            from bot.risk import get_positions
            symbol = action.get("symbol", "").upper()
            for p in get_positions():
                if p["symbol"].upper() == symbol:
                    addr = p["token_address"]
                    break
        if addr:
            from bot.risk import get_positions, close_position
            pos = next((p for p in get_positions() if p["token_address"] == addr), None)
            total_tokens = pos.get("amount_tokens", 0) if pos else 0
            moonbag = action.get("moonbag", True)
            # Kalau amount_tokens 0, pakai 100% string (sell semua)
            if total_tokens <= 0:
                sell_tokens = 0  # akan trigger 100% di API
                moonbag = False
            else:
                sell_tokens = int(total_tokens * 0.90) if moonbag else total_tokens
            sell_result = await trader.sell_token(addr, sell_tokens)
            if sell_result.get("success"):
                sig = sell_result.get("signature", "")
                mb_text = f"\n🌙 Moonbag 10% tersisa" if moonbag and sell_tokens < total_tokens else ""
                reply += f"\n\n✅ Sell berhasil!{mb_text}\n🔗 [TX](https://solscan.io/tx/{sig})"
                close_position(addr)
            else:
                reply += f"\n\n❌ Sell gagal: {sell_result.get('error')}"

    elif action_type == "set_config":
        key = action.get("key")
        value = action.get("value")
        if key and value is not None:
            import sys, importlib
            main_module = sys.modules.get('__main__') or importlib.import_module('main')
            if key == "MAX_POSITIONS":
                main_module.MAX_POSITIONS = int(value)
            else:
                setattr(Config, key, float(value))
            reply += f"\n\n⚙️ Config `{key}` diubah ke `{value}`"

    # Inject hasil action ke history biar AI tau apa yang terjadi
    from bot.agent import add_to_history
    if reply != result["reply"]:  # ada action result yang ditambah
        action_result = reply.replace(result["reply"], "").strip()
        add_to_history(user_id, "system", f"Hasil eksekusi action: {action_result}")

    # Escape karakter berbahaya dari AI reply
    # Hanya escape underscore yang bukan bagian dari formatting
    safe_reply = reply
    await update.message.reply_text(safe_reply, reply_markup=main_keyboard())
