from groq import Groq
from config import Config
import json

client = Groq(api_key=Config.GROQ_API_KEY)

def analyze_token(token_data: dict) -> dict:
    prompt = f"""
Kamu adalah AI trading analyst spesialis Solana memecoin.
Fokus utama: deteksi momentum volume m5 yang kuat untuk entry cepat.

Token Data:
- Symbol: {token_data.get('symbol')}
- Price: ${token_data.get('price_usd')}
- Market Cap: ${token_data.get('market_cap'):,.0f}
- Volume M5: ${token_data.get('volume_m5'):,.0f}
- Volume H1: ${token_data.get('volume_h1'):,.0f}
- Volume 24H: ${token_data.get('volume_24h'):,.0f}
- Buys M5: {token_data.get('buys_m5')}
- Sells M5: {token_data.get('sells_m5')}
- Buy/Sell Ratio M5: {token_data.get('buy_sell_ratio'):.2f}
- Price Change M5: {token_data.get('price_change_m5')}%
- Price Change 1H: {token_data.get('price_change_1h')}%
- Liquidity: ${token_data.get('liquidity'):,.0f}
- Age: {token_data.get('age_hours'):.1f} jam

Kriteria BUY yang kuat:
- Volume M5 besar relatif terhadap liquidity
- Buy/Sell ratio > 1.5
- Price change M5 positif
- Momentum naik

Tentukan juga exit strategy berdasarkan kondisi token.

Response dalam JSON:
{{
  "signal": "BUY" atau "HOLD",
  "confidence": 0-100,
  "reason": "alasan singkat max 10 kata",
  "risk_level": "LOW" atau "MEDIUM" atau "HIGH",
  "suggested_amount_sol": 0.01,
  "exit_strategy": {{
    "take_profit_pct": 30,
    "stop_loss_pct": 15,
    "time_limit_minutes": 30,
    "exit_reason": "alasan exit singkat"
  }}
}}

Hanya return JSON, tidak ada teks lain.
"""
    try:
        response = client.chat.completions.create(
            model=Config.GROQ_MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=400,
            temperature=0.2
        )
        text = response.choices[0].message.content
        # Clean response
        text = text.strip()
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        return json.loads(text.strip())
    except Exception as e:
        err = str(e)
        if "429" in err or "rate limit" in err.lower():
            return {"signal": "HOLD", "confidence": 0, "reason": "Rate limit, skip", "risk_level": "HIGH", "suggested_amount_sol": 0, "exit_strategy": {}}
        return {
            "signal": "HOLD",
            "confidence": 0,
            "reason": f"Error: {err[:30]}",
            "risk_level": "HIGH",
            "suggested_amount_sol": 0,
            "exit_strategy": {"take_profit_pct": 30, "stop_loss_pct": 15, "time_limit_minutes": 30, "exit_reason": "default"}
        }

def analyze_exit(position: dict, token_data: dict) -> dict:
    """AI analisa apakah posisi harus dijual sekarang (sebelum SL/TP)"""
    entry = position.get("entry_price", 0)
    current = token_data.get("price_usd", 0)
    pct = ((current - entry) / entry * 100) if entry else 0

    prompt = f"""
Kamu adalah AI exit analyst untuk Solana memecoin trading.
Tugasmu: putuskan apakah posisi ini harus DIJUAL SEKARANG sebelum kena SL/TP otomatis.

Posisi saat ini:
- Token: {position.get("symbol")}
- Entry: ${entry:.8f}
- Sekarang: ${current:.8f}
- PnL: {pct:+.1f}%
- Stop Loss: ${position.get("stop_loss", 0):.8f}
- Take Profit: ${position.get("take_profit", 0):.8f}

Market data terbaru:
- Volume M5: ${token_data.get("volume_m5", 0):,.0f}
- Volume H1: ${token_data.get("volume_h1", 0):,.0f}
- Buys M5: {token_data.get("buys_m5", 0)}
- Sells M5: {token_data.get("sells_m5", 0)}
- Buy/Sell Ratio M5: {token_data.get("buy_sell_ratio", 0):.2f}
- Price Change M5: {token_data.get("price_change_m5", 0):.1f}%
- Price Change 1H: {token_data.get("price_change_1h", 0):.1f}%
- Liquidity: ${token_data.get("liquidity", 0):,.0f}

Tanda bahaya yang harus diperhatikan:
- Volume M5 turun > 50% dari H1/12
- Buy/Sell ratio < 0.8 (seller dominan)
- Price change M5 negatif saat masih profit
- Momentum berbalik arah

Jawab HANYA dengan JSON ini, tanpa teks lain:
{{"sell": true/false, "confidence": 0-100, "reason": "alasan singkat"}}
"""
    try:
        from groq import Groq
        from config import Config
        client = Groq(api_key=Config.GROQ_API_KEY)
        response = client.chat.completions.create(
            model=Config.GROQ_MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=100,
            temperature=0.2
        )
        import json
        text = response.choices[0].message.content.strip()
        text = text.replace("```json", "").replace("```", "").strip()
        result = json.loads(text)
        return result
    except Exception as e:
        return {"sell": False, "confidence": 0, "reason": f"Error: {e}"}
