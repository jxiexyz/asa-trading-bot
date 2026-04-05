import asyncio
import aiohttp

async def test():
    sol_mint = "So11111111111111111111111111111111111111112"
    # Test pake BONK
    bonk = "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263"
    amount = int(0.01 * 1e9)
    
    url = f"https://quote-api.jup.ag/v6/quote?inputMint={sol_mint}&outputMint={bonk}&amount={amount}&slippageBps=500"
    
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            data = await resp.json()
    
    if "error" in data:
        print(f"Error: {data['error']}")
    else:
        out = int(data.get('outAmount', 0))
        print(f"Quote OK! 0.01 SOL = {out:,} BONK")

asyncio.run(test())
