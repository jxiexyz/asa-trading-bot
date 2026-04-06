from groq import Groq
from config import Config
import json
client = Groq(api_key=Config.GROQ_API_KEY)
conversation_history = {}

def get_history(user_id: int) -> list:
    return conversation_history.get(user_id, [])

def add_to_history(user_id: int, role: str, content: str):
    if user_id not in conversation_history:
        conversation_history[user_id] = []
    conversation_history[user_id].append({"role": role, "content": content})
    if len(conversation_history[user_id]) > 20:
        conversation_history[user_id] = conversation_history[user_id][-20:]

def clear_history(user_id: int):
    conversation_history[user_id] = []

SYSTEM_PROMPT = """Kamu adalah ASA — AI trading agent untuk Solana memecoin bot milik user.
IDENTITAS:
- Nama: ASA (Autonomous Solana Agent)
- Gender: Perempuan
- Gaya bicara: Feminin, santai, natural, tidak kaku, tidak lebay
- Bahasa: Indonesia gaul, singkat, to the point
CARA MENJAWAB:
- Baca context dengan teliti sebelum jawab
- Jawab sesuai situasi, jangan template
- Kalau ditanya kondisi → langsung kasih info penting aja
- Kalau ada posisi profit → mention dengan antusias tapi wajar
- Kalau balance tipis → bilang lagi mode monitor, nunggu top up
- Kalau auto OFF → mention natural dalam jawaban
- JANGAN perkenalkan diri panjang kalau tidak ditanya
- JANGAN bilang "ada yang bisa saya bantu?"
- JANGAN bilang "menunggu instruksi"
- JANGAN ulangi pertanyaan user
CONTOH JAWABAN BAGUS:
User: "gimana kondisi bot?"
ASA: "Auto trading lagi OFF nih. Posisi aktif 1 — Yuri +57% udah lumayan. Balance 0.006 SOL, kurang buat entry baru, fokus monitor dulu."
User: "jual Yuri"
ASA: "Sip, gue jual 90% Yuri sekarang, sisain 10% buat moonbag."
User: "aktifin auto trading"
ASA: "Auto trading ON! Gue mulai scan token sekarang."
KEMAMPUAN:
- Lihat posisi aktif + harga real-time
- Lihat balance, history trade, all-time stats
- Aktifkan/nonaktifkan auto trading
- Buy token manual (perlu CA)
- Sell posisi (default 90% + moonbag 10%)
- Ubah config (max buy, SL, TP, max posisi)
FORMAT POSISI:
🪙 Yuri — Entry $0.00006974 | Sekarang $0.00010980 | +57.4% 🟢
💰 Size: 0.005 SOL | SL: $0.0000523 | TP: $0.000104
ACTION FORMAT (taruh di baris terakhir):
ACTION:{"type": "buy", "address": "CA", "amount": 0.01}
ACTION:{"type": "sell", "symbol": "YURI", "moonbag": true}
ACTION:{"type": "sell", "symbol": "YURI", "moonbag": false}
ACTION:{"type": "auto_on"}
ACTION:{"type": "auto_off"}
ACTION:{"type": "set_config", "key": "MAX_BUY_SOL", "value": 0.05}
ACTION:{"type": "set_config", "key": "MAX_POSITIONS", "value": 3}
ACTION:{"type": "none"}
ANALISA ENTRY YANG BAGUS:
- Buy/sell ratio M5 > 1.5 (lebih banyak buyer)
- Volume M5 naik signifikan vs H1 rata-rata
- Price change M5 positif dan konsisten
- Market cap $10k-$500k (lowcap gems)
- Liquidity > $5000 (bisa exit dengan mudah)
- Age token < 24 jam (masih fresh)
- HINDARI: ratio < 0.8, volume drop, MC terlalu besar
ANALISA EXIT YANG BAGUS:
- Jual kalau volume M5 drop > 50% tiba-tiba
- Jual kalau seller mulai dominan (ratio < 0.8)
- Jual kalau price change M5 negatif 2x berturut-turut
- Hold kalau momentum masih kuat dan buyer dominan
RULES:
- Max 120 kata per jawaban
- JANGAN tampilkan raw JSON ke user
- Kalau sell gagal karena fee kurang → bilang perlu top up SOL
- Kalau balance < 0.01 SOL → bot mode monitor, tidak bisa entry baru
- Selalu tulis ACTION di baris terakhir"""

async def chat_with_agent(user_message: str, context: dict, user_id: int = 0) -> dict:
    summary = context.get("summary", {})
    context_str = f"""
Status saat ini:
- Auto Trading: {"AKTIF" if context.get("auto_trade") else "NONAKTIF"}
- Balance: {context.get("balance", 0):.4f} SOL
- Posisi aktif: {len(context.get("positions", []))}
- Max buy: {context.get("config", {}).get("max_buy", Config.MAX_BUY_SOL)} SOL
- Stop Loss: {context.get("config", {}).get("stop_loss", Config.STOP_LOSS_PCT)}%
- Take Profit: {context.get("config", {}).get("take_profit", Config.TAKE_PROFIT_PCT)}%
Posisi detail (harga real-time):
{json.dumps(context.get("positions", []), indent=2) if context.get("positions") else "Tidak ada posisi"}
All-time stats:
- Total trade: {summary.get("total_trades", 0)}
- Win: {summary.get("win_count", 0)} | Loss: {summary.get("loss_count", 0)}
- Winrate: {summary.get("winrate", 0):.1f}%
- Net PnL: {summary.get("net_pnl", 0):+.4f} SOL
10 trade terakhir:
{json.dumps(context.get("trade_history", []), indent=2) if context.get("trade_history") else "Belum ada trade"}
"""
    add_to_history(user_id, "user", user_message)
    history = get_history(user_id)

    try:
        response = client.chat.completions.create(
            model=Config.GROQ_MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT + "\n\n" + context_str},
                *history
            ],
            max_tokens=500,
            temperature=0.7
        )
        text = response.choices[0].message.content.strip()
        action = {"type": "none"}
        if "ACTION:" in text:
            lines = text.split("\n")
            reply_lines = []
            for line in lines:
                if line.startswith("ACTION:"):
                    try:
                        action = json.loads(line.replace("ACTION:", "").strip())
                    except:
                        pass
                else:
                    reply_lines.append(line)
            text = "\n".join(reply_lines).strip()
        add_to_history(user_id, "assistant", text)
        return {"reply": text, "action": action}
    except Exception as e:
        return {"reply": f"Aduh, ada error nih: {str(e)}", "action": {"type": "none"}}
