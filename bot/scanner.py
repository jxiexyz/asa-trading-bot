import aiohttp
import logging
logger = logging.getLogger(__name__)
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

    filtered = filter_lowcap(unique)[:limit]
    
    # Filter anti-scam dari data Dexscreener (tanpa API tambahan)
    safe_tokens = []
    for t in filtered:
        # Skip kalau buy/sell ratio terlalu rendah (seller dominan)
        if t.get("buy_sell_ratio", 0) < 0.3:
            logger.info(f"🚨 Skip {t['symbol']} — seller dominan ({t.get('buy_sell_ratio'):.2f})")
            continue
        # Skip kalau liquidity terlalu tipis
        if t.get("liquidity", 0) < 1000:
            logger.info(f"🚨 Skip {t['symbol']} — liquidity tipis (${t.get('liquidity'):,.0f})")
            continue
        # Skip kalau volume M5 drop drastis vs H1
        vol_m5 = t.get("volume_m5", 0)
        vol_h1 = t.get("volume_h1", 1)
        if vol_h1 > 0 and (vol_m5 / (vol_h1 / 12)) < 0.1:
            logger.info(f"🚨 Skip {t['symbol']} — volume M5 drop drastis")
            continue
        safe_tokens.append(t)
    return safe_tokens


async def get_token_by_address(session, address: str, skip_filter: bool = False) -> dict:
    try:
        url = f"https://api.dexscreener.com/latest/dex/tokens/{address}"
        async with session.get(url) as resp:
            data = await resp.json()
        pairs = data.get("pairs", [])
        if not pairs:
            return None
        # Ambil pair dengan volume tertinggi
        pair = max(pairs, key=lambda p: p.get("volume", {}).get("h24", 0) or 0)
        if skip_filter:
            # Untuk cek harga posisi — skip filter ketat
            try:
                return {
                    "address": pair.get("baseToken", {}).get("address"),
                    "symbol": pair.get("baseToken", {}).get("symbol"),
                    "price_usd": float(pair.get("priceUsd", 0) or 0),
                    "volume_m5": pair.get("volume", {}).get("m5", 0) or 0,
                    "volume_h1": pair.get("volume", {}).get("h1", 0) or 0,
                    "buys_m5": pair.get("txns", {}).get("m5", {}).get("buys", 0) or 0,
                    "sells_m5": pair.get("txns", {}).get("m5", {}).get("sells", 0) or 0,
                    "buy_sell_ratio": (pair.get("txns", {}).get("m5", {}).get("buys", 0) or 0) / max(pair.get("txns", {}).get("m5", {}).get("sells", 1) or 1, 1),
                    "price_change_m5": pair.get("priceChange", {}).get("m5", 0) or 0,
                    "price_change_1h": pair.get("priceChange", {}).get("h1", 0) or 0,
                    "liquidity": pair.get("liquidity", {}).get("usd", 0) or 0,
                }
            except:
                return None
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
        if liquidity < 1000:
            return None
        if volume_m5 < 100:
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
    return [t for t in tokens if t.get('market_cap', 0) >= 5000 and t.get('market_cap', 0) <= 1000000]

async def get_current_price(address: str) -> float:
    try:
        async with aiohttp.ClientSession() as session:
            token = await get_token_by_address(session, address)
            if token:
                return token["price_usd"]
    except:
        pass
    return 0.0

async def check_rugcheck(session, address: str) -> dict:
    """Cek risk score token via RugCheck"""
    try:
        url = f"https://api.rugcheck.xyz/v1/tokens/{address}/report/summary"
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=2)) as resp:
            if resp.status != 200:
                return {"safe": True}  # kalau gagal, skip filter
            data = await resp.json()
            score = data.get("score", 0)
            risks = data.get("risks", [])
            risk_names = [r.get("name", "") for r in risks]
            
            # Bahaya kalau score > 500 atau ada risk kritis
            danger_risks = ["Freeze Authority", "Mint Authority", "High holder concentration", "Bundled supply"]
            has_danger = any(r in risk_names for r in danger_risks)
            
            return {
                "safe": score < 500 and not has_danger,
                "score": score,
                "risks": risk_names[:3]
            }
    except:
        return {"safe": True}  # timeout/error = skip filter
