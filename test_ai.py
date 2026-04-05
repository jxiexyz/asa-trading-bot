import asyncio
from bot.scanner import get_new_solana_tokens
from bot.ai_engine import analyze_token

async def test():
    tokens = await get_new_solana_tokens(20)
    for t in tokens[:3]:
        signal = analyze_token(t)
        sym = t['symbol']
        sig = signal['signal']
        conf = signal['confidence']
        reason = signal['reason']
        tp = signal['exit_strategy']['take_profit_pct']
        sl = signal['exit_strategy']['stop_loss_pct']
        print(f"{sym}: {sig} {conf}% | {reason} | TP:{tp}% SL:{sl}%")

asyncio.run(test())
