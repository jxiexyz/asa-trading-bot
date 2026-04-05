import asyncio
from bot.scanner import get_new_solana_tokens

async def test():
    tokens = await get_new_solana_tokens(20)
    print(f'Token ditemukan: {len(tokens)}')
    for t in tokens[:5]:
        sym = t['symbol']
        vm5 = t['volume_m5']
        buys = t['buys_m5']
        ratio = t['buy_sell_ratio']
        age = t['age_hours']
        print(f"{sym} vol_m5=${vm5:,.0f} buys={buys} ratio={ratio:.1f} age={age:.1f}h")

asyncio.run(test())
