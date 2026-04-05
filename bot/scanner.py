import aiohttp
import time
from config import Config

async def get_new_solana_tokens(limit=30) -> list:
    # Ambil token dengan volume m5 tinggi
    url = "https://api.dexscreener.com/token-boosts/top/v1"
    tokens = []

    async with aiohttp.ClientSession() as session:
        # Source 1: boosted tokens (sering memecoin baru)
        try:
            async with session.get(url) as resp:
                boosted = await resp.json()
            for item in boosted[:20]:
                if item.get("chainId") != "solana":
                    continue
                addr = item.get("tokenAddress")
                if addr:
                    detail = await get_token_by_address(session, addr)
                    if detail:
                        tokens.append(detail)
        except:
            pass

        # Source 2: latest solana pairs sorted by volume
        try:
            search_url = "https://api.dexscreener.com/latest/dex/search?q=solana+meme"
            async with session.get(search_url) as resp:
                data = await resp.json()
            for pair in data.get("pairs", [])[:40]:
                if pair.get("chainId") != "solana":
                    continue
                token = parse_pair(pair)
                if token:
                    tokens.append(token)
        except:
            pass

    # Dedupe by address
    seen = set()
    unique = []
    for t in tokens:
        if t["address"] not in seen:
            seen.add(t["address"])
            unique.append(t)

    return filter_lowcap(unique)[:limit]


async def get_token_by_address(session, address: str) -> dict:
    try:
        url = f"https://api.dexscreener.com/latest/dex/tokens/{address}"
        async with session.get(url) as resp:
            data = await resp.json()
        pairs = data.get("pairs", [])
        if not pairs:
            return None
        # Ambil pair dengan volume tertinggi
        pair = max(pairs, key=lambda p: p.get("volume", {}).get("h24", 0) or 0)
        return parse_pair(pair)
    except:
        return None


def parse_pair(pair: dict) -> dict:
    try:
        liquidity = pair.get("liquidity", {}).get("usd", 0) or 0
        volume_24h = pair.get("volume", {}).get("h24", 0) or 0
        volume_m5 = pair.get("volume", {}).get("m5", 0) or 0
        volume_h1 = pair.get("volume", {}).get("h1", 0) or 0
        txns_m5 = pair.get("txns", {}).get("m5", {})
        buys_m5 = txns_m5.get("buys", 0) or 0
        sells_m5 = txns_m5.get("sells", 0) or 0

        # Filter minimum
        if liquidity < 3000:
            return None
        if volume_m5 < 500:  # minimal volume m5 $1000
            return None
        if buys_m5 == 0:
            return None
        # Hanya pump.fun dan meteora
        dex_id = pair.get("dexId", "").lower()
        if not any(d in dex_id for d in ["pump", "meteora", "dlmm", "raydium"]):
            return None

        symbol = pair.get("baseToken", {}).get("symbol", "")
        # Skip wrapped SOL & stables
        if symbol.upper() in ["SOL", "WSOL", "USDC", "USDT", "ETH", "BTC"]:
            return None

        created_at = pair.get("pairCreatedAt") or (time.time() * 1000)
        age_hours = ((time.time() * 1000) - created_at) / 3600000

        return {
            "address": pair.get("baseToken", {}).get("address"),
            "name": pair.get("baseToken", {}).get("name"),
            "symbol": symbol,
            "price_usd": float(pair.get("priceUsd", 0) or 0),
            "market_cap": pair.get("marketCap", 0) or 0,
            "volume_24h": volume_24h,
            "volume_h1": volume_h1,
            "volume_m5": volume_m5,
            "buys_m5": buys_m5,
            "sells_m5": sells_m5,
            "buy_sell_ratio": buys_m5 / max(sells_m5, 1),
            "liquidity": liquidity,
            "price_change_1h": pair.get("priceChange", {}).get("h1", 0) or 0,
            "price_change_24h": pair.get("priceChange", {}).get("h24", 0) or 0,
            "price_change_m5": pair.get("priceChange", {}).get("m5", 0) or 0,
            "dex": pair.get("dexId"),
            "pair_address": pair.get("pairAddress"),
            "age_hours": age_hours,
            "url": pair.get("url", ""),
        }
    except:
        return None

def filter_lowcap(tokens: list) -> list:
    return [t for t in tokens if t.get('market_cap', 0) >= 10000 and t.get('market_cap', 0) <= 500000]

async def get_current_price(address: str) -> float:
    try:
        async with aiohttp.ClientSession() as session:
            token = await get_token_by_address(session, address)
            if token:
                return token["price_usd"]
    except:
        pass
    return 0.0
