import asyncio
import aiohttp

async def test():
    url = "https://transaction-v1.raydium.io/compute/swap-base-in"
    params = {
        "inputMint": "So11111111111111111111111111111111111111112",
        "outputMint": "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263",
        "amount": 10000000,
        "slippageBps": 500,
        "txVersion": "V0"
    }
    async with aiohttp.ClientSession() as session:
        async with session.get(url, params=params) as resp:
            data = await resp.json()
    print(json.dumps(data, indent=2)[:300])

import json
asyncio.run(test())
