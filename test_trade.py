import asyncio
from bot.trading import TradingEngine

async def test():
    trader = TradingEngine()
    balance = await trader.get_wallet_balance()
    print(f"Balance: {balance:.4f} SOL")

asyncio.run(test())
