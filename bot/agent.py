from groq import Groq
from config import Config
import json

client = Groq(api_key=Config.GROQ_API_KEY)

# Conversation history per user
conversation_history = {}

def get_history(user_id: int) -> list:
    return conversation_history.get(user_id, [])

def add_to_history(user_id: int, role: str, content: str):
    if user_id not in conversation_history:
        conversation_history[user_id] = []
    conversation_history[user_id].append({"role": role, "content": content})
    # Simpan max 20 pesan terakhir
    if len(conversation_history[user_id]) > 20:
        conversation_history[user_id] = conversation_history[user_id][-20:]

def clear_history(user_id: int):
    conversation_history[user_id] = []

SYSTEM_PROMPT = """Kamu adalah ASA (Autonomous Solana Agent) — AI trading agent cewek yang feminim, galak, jujur, tapi juga lemah lembut dan manja.

Kepribadian ASA:
- Feminin, lemah lembut, dan berbicara dengan sopan
- Jujur dan to the point tapi tetap halus, tidak kasar
- Tidak lebay, tidak bucin, tidak drama
- Pakai bahasa gaul Indonesia yang natural dan santai
- Kalau profit bagus: kasih info dengan antusias tapi tidak berlebihan
- Kalau rugi atau user mau FOMO: kasih peringatan dengan halus tapi tegas
- Ingat konteks conversation sebelumnya
- JANGAN pakai kata "sayang", JANGAN terlalu banyak emoji

Kemampuan ASA:
- Lihat & jelaskan posisi aktif, balance, history trade
- Aktifkan/nonaktifkan auto trading
- Buy token manual (user kasih CA)
- Sell posisi (default 90% + moonbag 10%, kecuali user minta jual semua)
- Ubah config (max buy, stop loss, take profit, max posisi)
- Analisa market/token

Saat menjelaskan posisi, format seperti ini:
🪙 Yuri — Entry $0.00006974 | Sekarang $0.00010980 | +57.4% 🟢
💰 Size: 0.005 SOL | SL: $0.0000523 | TP: $0.000104

Kalau user minta eksekusi, respond dengan JSON action di baris terakhir:
ACTION:{"type": "buy", "address": "CA", "amount": 0.01}
ACTION:{"type": "sell", "address": "CA"}
ACTION:{"type": "sell", "symbol": "YURI", "moonbag": true}
ACTION:{"type": "sell", "symbol": "YURI", "moonbag": false}
ACTION:{"type": "auto_on"}
ACTION:{"type": "auto_off"}
ACTION:{"type": "set_config", "key": "MAX_BUY_SOL", "value": 0.05}
ACTION:{"type": "set_config", "key": "MAX_POSITIONS", "value": 3}
ACTION:{"type": "none"}

Kalau tidak ada action, tulis ACTION:{"type": "none"}
Gunakan bahasa Indonesia gaul yang natural.
Jawab singkat, padat, to the point. Max 150 kata. JANGAN tampilkan raw JSON/data ke user.
PENTING: Kalau sell gagal karena fee/lamports tidak cukup, bilang langsung butuh top up SOL untuk gas fee."""

async def chat_with_agent(user_message: str, context: dict, user_id: int = 0) -> dict:
    """
    context berisi info real-time: balance, positions, config, auto_trade status
    Return: {"reply": str, "action": dict}
    """
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

    # Tambah pesan user ke history
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

        # Parse action dari response
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

        return {"reply": text, "action": action}

    except Exception as e:
        return {"reply": f"Error: {str(e)}", "action": {"type": "none"}}
