from groq import Groq
from config import Config
import json
import asyncio
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
        text = response.choices[0].message.content.strip()
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

async def qwen_risk_check(token_data: dict, groq_signal: dict) -> dict:
    """
    Qwen CFO — second opinion sebelum entry.
    Dipanggil HANYA kalau Groq udah bilang BUY confidence >= 60%.
    Return: {"approved": True/False, "risk": "LOW/MEDIUM/HIGH", "note": "..."}
    """
    prompt = f"""You are a crypto risk analyst (CFO). A trading bot CEO wants to buy this Solana memecoin.
Your job: give a quick risk assessment. Be strict and concise.

Token: {token_data.get('symbol')}
Market Cap: ${token_data.get('market_cap'):,.0f}
Liquidity: ${token_data.get('liquidity'):,.0f}
Volume M5: ${token_data.get('volume_m5'):,.0f}
Buy/Sell Ratio M5: {token_data.get('buy_sell_ratio'):.2f}
Price Change M5: {token_data.get('price_change_m5')}%
Age: {token_data.get('age_hours'):.1f} hours
CEO signal: {groq_signal.get('signal')} ({groq_signal.get('confidence')}% confident)
CEO reason: {groq_signal.get('reason')}

Respond ONLY with JSON:
{{"approved": true/false, "risk": "LOW" or "MEDIUM" or "HIGH", "note": "max 8 words reason"}}

Approve if fundamentals look solid. Reject if HIGH risk (rug pull signs, low liquidity, suspicious volume)."""

    try:
        response = client.chat.completions.create(
            model=Config.GROQ_MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=60,
            temperature=0.1
        )
        text = response.choices[0].message.content.strip()
        text = text.replace("```json", "").replace("```", "").strip()
        return json.loads(text)
    except Exception as e:
        # Kalau Qwen error/timeout → jangan block entry, approve aja
        return {"approved": True, "risk": "MEDIUM", "note": f"CFO unavailable: {str(e)[:20]}"}

def analyze_exit(position: dict, token_data: dict) -> dict:
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

Strategi: HIT AND RUN — amankan profit cepat!
Tanda bahaya:
- Volume M5 turun > 30% dari rata-rata H1
- Buy/Sell ratio < 0.9 (mulai banyak seller)
- Price change M5 negatif atau flat saat profit > 30%
- Momentum melambat = waktu keluar
- Kalau profit > 50%, sekecil apapun tanda bahaya = SELL
Prinsip: profit yang ada lebih berharga dari profit yang belum tentu datang.
Jawab HANYA dengan JSON:
{{"sell": true/false, "confidence": 0-100, "reason": "alasan singkat"}}
Jawab HANYA dengan JSON:
{{"sell": true/false, "confidence": 0-100, "reason": "alasan singkat"}}
"""
    try:
        response = client.chat.completions.create(
            model=Config.GROQ_MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=100,
            temperature=0.2
        )
        text = response.choices[0].message.content.strip()
        text = text.replace("```json", "").replace("```", "").strip()
        return json.loads(text)
    except Exception as e:
        return {"sell": False, "confidence": 0, "reason": f"Error: {e}"}
