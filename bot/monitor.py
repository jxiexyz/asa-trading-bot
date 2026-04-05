from bot.risk import get_positions, get_trade_history

async def get_portfolio_summary(wallet_balance: float) -> str:
    positions = get_positions()
    msg = "📊 *Portfolio Monitor*\n"
    msg += f"━━━━━━━━━━━━━━━━\n"
    msg += f"💰 Balance: `{wallet_balance:.4f} SOL`\n\n"
    if not positions:
        msg += "📭 Tidak ada posisi aktif\n"
    else:
        msg += f"📈 *Posisi Aktif ({len(positions)}):*\n"
        for pos in positions:
            msg += (
                f"\n🪙 *{pos['symbol']}*\n"
                f"  Entry: `${pos['entry_price']:.8f}`\n"
                f"  Size: `{pos['amount_sol']:.4f} SOL`\n"
                f"  SL: `${pos['stop_loss']:.8f}`\n"
                f"  TP: `${pos['take_profit']:.8f}`\n"
            )
    trades = get_trade_history(5)
    if trades:
        msg += f"\n📜 *5 Trade Terakhir:*\n"
        for t in trades:
            emoji = "🟢" if t['action'] == 'BUY' else "🔴"
            msg += f"{emoji} {t['symbol']} {t['action']} `{t['amount_sol']:.4f}` SOL\n"
    return msg

def format_signal_message(token: dict, signal: dict) -> str:
    emoji_map = {"BUY": "🟢", "SELL": "🔴", "HOLD": "🟡"}
    risk_emoji = {"LOW": "✅", "MEDIUM": "⚠️", "HIGH": "🚨"}
    return (
        f"{emoji_map.get(signal['signal'], '❓')} *AI Signal: {signal['signal']}*\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"🪙 Token: *{token['name']}* ({token['symbol']})\n"
        f"💵 Price: `${token['price_usd']:.8f}`\n"
        f"📊 Market Cap: `${token.get('market_cap', 0):,.0f}`\n"
        f"💧 Liquidity: `${token.get('liquidity', 0):,.0f}`\n"
        f"📈 Volume 24h: `${token.get('volume_24h', 0):,.0f}`\n"
        f"⏱ 1h Change: `{token.get('price_change_1h', 0):.1f}%`\n"
        f"🧠 Confidence: `{signal['confidence']}%`\n"
        f"{risk_emoji.get(signal['risk_level'], '⚠️')} Risk: `{signal['risk_level']}`\n"
        f"💡 Reason: _{signal.get('reason', '-')}_\n"
        f"💰 Suggested: `{signal.get('suggested_amount_sol', 0):.3f} SOL`\n"
        f"🏦 DEX: `{token.get('dex', '-')}`\n"
        f"📋 CA: `{token.get('address', '-')}`\n"
        f"🔗 Chart: {token.get('url', '-')}"
    )
