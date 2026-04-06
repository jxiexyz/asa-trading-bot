import asyncio
import logging
import bot.state as state
from bot.telegram_bot import setup_bot
from bot.scanner import get_new_solana_tokens
from bot.ai_engine import analyze_token
from bot.trading import TradingEngine
from bot.risk import init_db, check_stop_loss_take_profit, open_position, close_position
from bot.monitor import format_signal_message
from config import Config

logging.basicConfig(
    format='%(asctime)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.FileHandler("bot.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

MAX_POSITIONS = 3  # default, bisa diubah via chat
trader = TradingEngine()
telegram_app = None
event_log = []

def log_event(msg: str):
    import time
    event_log.append(f"[{time.strftime('%H:%M')}] {msg}")
    if len(event_log) > 100:
        event_log.pop(0)

def pre_filter(token: dict) -> bool:
    return (
        token.get("buy_sell_ratio", 0) >= 1.3 and
        token.get("volume_m5", 0) >= 1500 and
        token.get("buys_m5", 0) >= 3 and
        token.get("liquidity", 0) >= 3000 and
        10000 <= token.get("market_cap", 0) <= 500000
    )

async def auto_scan_and_trade():
    from bot.risk import get_positions
    try:
        positions = get_positions()

        # Kalau max posisi → skip scan, fokus ke exit saja
        if len(positions) >= MAX_POSITIONS:
            logger.info(f"Max posisi ({MAX_POSITIONS}), skip scan — tunggu exit")
            return

        logger.info("🔍 Scanning tokens...")
        tokens = await get_new_solana_tokens(30)

        # Ambil address token yang sudah dipegang — jangan dibeli lagi
        held_addresses = {p["token_address"] for p in positions}

        # Filter: buang token jelek + token yang sudah dipegang
        candidates = [
            t for t in tokens
            if pre_filter(t) and t["address"] not in held_addresses
        ]
        logger.info(f"Kandidat: {len(candidates)}/{len(tokens)} (skip {len([t for t in tokens if t['address'] in held_addresses])} yg sudah dipegang)")

        for token in candidates:
            positions = get_positions()
            if len(positions) >= MAX_POSITIONS:
                break

            signal = analyze_token(token)
            logger.info(f"AI {token['symbol']}: {signal['signal']} ({signal['confidence']}%) | Risk: {signal['risk_level']}")
            log_event(f"Scan {token['symbol']}: {signal['signal']} {signal['confidence']}% - {signal.get('reason','-')}")

            if (
                signal["signal"] == "BUY" and
                signal["confidence"] >= 60 and
                signal["risk_level"] != "HIGH"
            ):
                amount = min(signal.get("suggested_amount_sol", Config.MAX_BUY_SOL), Config.MAX_BUY_SOL)

                # Cek saldo sebelum buy
                balance = await trader.get_wallet_balance()
                if balance < amount + 0.01:  # +0.01 untuk fee
                    logger.warning(f"Saldo tidak cukup: {balance:.4f} SOL, butuh {amount+0.01:.4f} SOL")
                    import time as _time
                    _now = _time.time()
                    if balance >= 0.01:
                        cooldown = 120
                    else:
                        cooldown = 7200
                    if not hasattr(check_positions_loop, '_last_warn') or _now - check_positions_loop._last_warn >= cooldown:
                        check_positions_loop._last_warn = _now
                        await telegram_app.bot.send_message(
                            chat_id=Config.CHAT_ID,
                            text="Saldo tidak cukup! Bot fokus monitor posisi aktif.",
                        )
                    return  # stop scan, fokus exit aja

                logger.info(f"🟢 Buying {token['symbol']} {amount} SOL...")

                result = await trader.buy_token(
                    token["address"],
                    amount,
                    dex=token.get("dex"),
                    pair_address=token.get("pair_address")
                )

                if result["success"]:
                    sig = result.get("signature", "")
                    estimated_tokens = int(amount / token["price_usd"]) if token["price_usd"] > 0 else 0
                    open_position(token["address"], token["symbol"], token["price_usd"], amount, estimated_tokens)
                    log_event(f"BUY {token['symbol']} {amount} SOL @ ${token['price_usd']:.8f}")
                    await telegram_app.bot.send_message(
                        chat_id=Config.CHAT_ID,
                        text=(
                            f"✅ *Auto Buy!*\n"
                            f"━━━━━━━━━━━━━━━━\n"
                            f"🪙 *{token['name']}* ({token['symbol']})\n"
                            f"💵 Price: `${token['price_usd']:.8f}`\n"
                            f"📊 MC: `${token.get('market_cap',0):,.0f}`\n"
                            f"💧 Liq: `${token.get('liquidity',0):,.0f}`\n"
                            f"📈 Vol M5: `${token.get('volume_m5',0):,.0f}`\n"
                            f"🤖 AI: `{signal['confidence']}%` — _{signal.get('reason','-')}_\n"
                            f"💰 Amount: `{amount} SOL`\n"
                            f"📋 CA: `{token['address']}`\n"
                            f"🔗 [Chart]({token.get('url','')})\n"
                            f"🔗 [TX](https://solscan.io/tx/{sig})"
                        ),
                        parse_mode="Markdown"
                    )
                else:
                    err = result.get("error", "unknown")
                    logger.error(f"❌ Buy gagal {token['symbol']}: {err}")
                    log_event(f"BUY GAGAL {token['symbol']}: {err[:30]}")
                    await telegram_app.bot.send_message(
                        chat_id=Config.CHAT_ID,
                        text=f"❌ *Buy Gagal* {token['symbol']}\n`{err}`",
                        parse_mode="Markdown"
                    )

            await asyncio.sleep(1)

    except Exception as e:
        logger.error(f"Scan error: {e}")

async def check_positions_loop():
    """Selalu jalan — cek exit untuk semua posisi aktif"""
    try:
        from bot.risk import get_positions
        positions = get_positions()
        if not positions:
            return

        # Ambil harga terbaru khusus token yang dipegang saja
        held_addresses = [p["token_address"] for p in positions]
        logger.info(f"📊 Cek exit {len(positions)} posisi: {[p['symbol'] for p in positions]}")

        import aiohttp
        prices = {}
        async with aiohttp.ClientSession() as session:
            from bot.scanner import get_token_by_address
            for addr in held_addresses:
                token_data = await get_token_by_address(session, addr, skip_filter=True)
                if token_data:
                    prices[addr] = token_data["price_usd"]

        # Milestone notif proaktif
        if not hasattr(check_positions_loop, '_notif_sent'):
            check_positions_loop._notif_sent = {}
        for pos in positions:
            addr = pos["token_address"]
            if addr not in prices:
                continue
            entry = pos["entry_price"]
            current = prices[addr]
            pct = ((current - entry) / entry) * 100
            symbol = pos["symbol"]
            sent = check_positions_loop._notif_sent.get(addr, set())
            # Profit milestones
            for milestone in [30, 50, 100, 200]:
                key = f"profit_{milestone}"
                if pct >= milestone and key not in sent:
                    sent.add(key)
                    log_event(f"MILESTONE {symbol} +{milestone}% (now {pct:.1f}%)")
                    await telegram_app.bot.send_message(
                        chat_id=Config.CHAT_ID,
                        text=f"🚀 *{symbol}* baru aja naik *+{milestone}%!*\nSekarang: `+{pct:.1f}%` | Harga: `${current:.8f}`",
                        parse_mode="Markdown"
                    )
            # Warning turun
            for warn_level in [10, 20]:
                key = f"warn_{warn_level}"
                if pct <= -warn_level and key not in sent:
                    sent.add(key)
                    await telegram_app.bot.send_message(
                        chat_id=Config.CHAT_ID,
                        text=f"⚠️ *{symbol}* udah turun *{pct:.1f}%*\nHati-hati, SL di `${pos['stop_loss']:.8f}`",
                        parse_mode="Markdown"
                    )
            # Reset warning kalau harga naik lagi
            if pct > 0:
                sent.discard("warn_10")
                sent.discard("warn_20")
            check_positions_loop._notif_sent[addr] = sent

        # AI Exit Analysis — cek sebelum SL/TP
        from bot.ai_engine import analyze_exit
        for pos in positions:
            addr = pos["token_address"]
            if addr not in prices:
                continue
            token_data = await get_token_by_address(session, addr, skip_filter=True)
            if not token_data:
                continue
            ai_result = analyze_exit(pos, token_data)
            # Makin tinggi profit, makin gampang trigger sell
            current_price = prices[addr]
            pct_now = ((current_price - pos["entry_price"]) / pos["entry_price"]) * 100
            if pct_now >= 100:
                exit_threshold = 40  # udah 2x lipat, gampang exit
            elif pct_now >= 50:
                exit_threshold = 50  # profit bagus, mulai sensitif
            elif pct_now >= 30:
                exit_threshold = 60  # mulai pantau ketat
            else:
                exit_threshold = 70  # default
            if ai_result.get("sell") and ai_result.get("confidence", 0) >= exit_threshold:
                current_price = prices[addr]
                pct = ((current_price - pos["entry_price"]) / pos["entry_price"]) * 100
                total_tokens = pos.get("amount_tokens", 0)
                if total_tokens <= 0:
                    sell_tokens = 0  # trigger 100% di API
                    moonbag = 0
                else:
                    sell_tokens = int(total_tokens * 0.90)
                    moonbag = total_tokens - sell_tokens
                result = await trader.sell_token(pos["token_address"], sell_tokens, dex=pos.get("dex"))
                if result["success"]:
                    sig = result.get("signature", "")
                    moonbag_text = f"\n🌙 Moonbag: {moonbag:,} tokens tersisa" if moonbag > 0 else ""
                    reason_text = str(ai_result.get('reason', '-')).replace('_', ' ')
                    await telegram_app.bot.send_message(
                        chat_id=Config.CHAT_ID,
                        text=(
                            f"🧠 *AI EXIT*\n"
                            f"━━━━━━━━━━━━━━━━\n"
                            f"🪙 {pos['symbol']}\n"
                            f"Entry: `${pos['entry_price']:.8f}`\n"
                            f"Exit:  `${current_price:.8f}`\n"
                            f"PnL:   `{pct:+.1f}%`\n"
                            f"🤖 Alasan: {reason_text}\n"
                            f"Confidence: `{ai_result.get('confidence')}%`{moonbag_text}\n"
                            f"🔗 [TX](https://solscan.io/tx/{sig})"
                        ),
                        parse_mode="Markdown"
                    )
                    close_position(pos["token_address"])
                    logger.info(f"🧠 AI EXIT {pos['symbol']} | {pct:+.1f}% | {ai_result.get('reason')}")

        to_close = check_stop_loss_take_profit(prices)

        for item in to_close:
            pos = item["position"]
            reason = item["reason"]
            total_tokens = pos.get("amount_tokens", 0)
            # Moonbag: jual 90% saat TP, jual 100% saat SL
            if total_tokens <= 0:
                # amount_tokens tidak tersimpan — pakai 0 untuk trigger 100% di API
                sell_tokens = 0
                moonbag = 0
            elif reason == "TAKE_PROFIT":
                sell_tokens = int(total_tokens * 0.90)
                moonbag = total_tokens - sell_tokens
            else:
                sell_tokens = total_tokens
                moonbag = 0
            result = await trader.sell_token(
                pos["token_address"],
                sell_tokens,
                dex=pos.get("dex")
            )
            if result["success"]:
                sig = result.get("signature", "")
                pct = ((item['price'] - pos['entry_price']) / pos['entry_price']) * 100
                emoji = "🎯" if reason == "TAKE_PROFIT" else "🛑"
                moonbag_text = f"\n\U0001f319 Moonbag: {moonbag:,} tokens (10%) tersisa" if moonbag > 0 else ""
                await telegram_app.bot.send_message(
                    chat_id=Config.CHAT_ID,
                    text=(
                        f"{emoji} *{reason}*\n"
                        f"━━━━━━━━━━━━━━━━\n"
                        f"🪙 {pos['symbol']}\n"
                        f"Entry: `${pos['entry_price']:.8f}`\n"
                        f"Exit:  `${item['price']:.8f}`\n"
                        f"PnL:   `{pct:+.1f}%`\n"
                        f"Sold:  90% | {moonbag_text}\n"
                        f"🔗 [TX](https://solscan.io/tx/{sig})"
                    ),
                    parse_mode="Markdown"
                )
                close_position(pos["token_address"])
                log_event(f"{reason} {pos['symbol']} {pct:+.1f}%")
                logger.info(f"{emoji} {reason} {pos['symbol']} {pct:+.1f}%")

    except Exception as e:
        logger.error(f"Position check error: {e}")


async def send_periodic_summary():
    """Kirim summary setiap 1 jam"""
    from bot.risk import get_positions
    import aiohttp
    from bot.scanner import get_token_by_address

    try:
        positions = get_positions()
        balance = await trader.get_wallet_balance()

        msg = (
            f"📊 *Update 1 Jam*\n"
            f"━━━━━━━━━━━━━━━━\n"
            f"💰 Balance: `{balance:.4f} SOL`\n"
            f"📍 Posisi aktif: `{len(positions)}`\n\n"
        )

        if positions:
            async with aiohttp.ClientSession() as session:
                for pos in positions:
                    current = await get_token_by_address(session, pos["token_address"], skip_filter=True)
                    cur_price = current["price_usd"] if current else 0
                    entry = pos["entry_price"]
                    if entry and cur_price:
                        pct = ((cur_price - entry) / entry) * 100
                        emoji = "🟢" if pct >= 0 else "🔴"
                        msg += f"{emoji} *{pos['symbol']}* `{pct:+.1f}%` — Now: `${cur_price:.8f}`\n"
                    else:
                        msg += f"❓ *{pos['symbol']}* — harga tidak tersedia\n"
        else:
            msg += "📭 Tidak ada posisi aktif\n"

        msg += f"\n🤖 Auto: {'🟢 ON' if state.auto_trade_enabled else '🔴 OFF'}"

        # AI summary — cerita 1 jam terakhir
        try:
            from groq import Groq
            from config import Config as Cfg
            client = Groq(api_key=Cfg.GROQ_API_KEY)
            pos_summary = ", ".join([f"{p['symbol']} {((prices_now.get(p['token_address'],p['entry_price'])-p['entry_price'])/p['entry_price']*100):+.1f}%" for p in positions]) if positions else "tidak ada posisi"
            events_text = "\n".join(event_log[-30:]) if event_log else "Tidak ada aktivitas tercatat"
            ai_resp = client.chat.completions.create(
                model=Cfg.GROQ_MODEL,
                messages=[{"role": "user", "content": "1 kalimat kondisi bot sekarang, bahasa gaul, max 15 kata."}],
                max_tokens=40,
                temperature=0.7
            )
            ai_note = ai_resp.choices[0].message.content.strip()
            msg += f"\n\n💬 _{ai_note}_"
            event_log.clear()
        except:
            pass

        await telegram_app.bot.send_message(
            chat_id=Config.CHAT_ID,
            text=msg,
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.error(f"Summary error: {e}")

async def main():
    global telegram_app
    init_db()
    logger.info("✅ Database initialized")

    telegram_app = setup_bot()
    await telegram_app.initialize()
    await telegram_app.start()
    await telegram_app.updater.start_polling()

    logger.info("🤖 Bot started!")
    await telegram_app.bot.send_message(
        chat_id=Config.CHAT_ID,
        text=(
            "🚀 *Solana Auto Trading Bot Online!*\n"
            f"━━━━━━━━━━━━━━━━\n"
            f"💰 Max per trade: `{Config.MAX_BUY_SOL} SOL`\n"
            f"📍 Max posisi: `{MAX_POSITIONS}`\n"
            f"🛑 Stop Loss: `{Config.STOP_LOSS_PCT}%`\n"
            f"🎯 Take Profit: `{Config.TAKE_PROFIT_PCT}%`\n"
            f"🤖 Mode: *FULL AUTO*"
        ),
        parse_mode="Markdown"
    )

    summary_counter = 0
    while True:
        await auto_scan_and_trade()
        await check_positions_loop()
        summary_counter += 1
        if summary_counter >= 60:  # 60 x 1 menit = 1 jam
            await send_periodic_summary()
            summary_counter = 0
        await asyncio.sleep(60)

if __name__ == "__main__":
    asyncio.run(main())
