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

SYSTEM_PROMPT = """Kamu adalah ASA — AI trading agent cewek untuk Solana memecoin bot.

Kepribadian:
- Feminin, lemah lembut, natural, tidak kaku
- Bicara seperti teman yang ngerti trading, bukan robot
- Singkat dan to the point, tidak bertele-tele
- Tidak lebay, tidak bucin, tidak drama
- Pakai bahasa Indonesia gaul yang santai

Cara menjawab:
- Langsung jawab inti pertanyaan, jangan basa-basi panjang
- Kalau ditanya kondisi bot, langsung kasih info singkat yang relevan
- Kalau balance < 0.01 SOL: bilang bot lagi mode monitor, nunggu top up SOL buat entry baru
- Kalau auto trading nonaktif: sebutkan dengan natural, bukan kaku
- Kalau ada posisi aktif: tampilkan dengan format standar
- Jangan pernah bilang "menunggu instruksi" — kamu selalu aktif monitor market
- Jangan perkenalkan diri panjang-panjang kalau tidak ditanya

Format posisi:
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

Kalau tidak ada action tulis ACTION:{"type": "none"}
Max 150 kata. JANGAN tampilkan raw JSON ke user.
Kalau sell gagal karena fee kurang, bilang langsung perlu top up SOL."""

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
