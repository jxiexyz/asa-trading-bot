import sqlite3
from datetime import datetime
from config import Config

DB_PATH = "trades.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS trades (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        token_address TEXT,
        token_symbol TEXT,
        action TEXT,
        amount_sol REAL,
        price_usd REAL,
        tx_signature TEXT,
        timestamp TEXT,
        pnl REAL DEFAULT 0
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS positions (
        token_address TEXT PRIMARY KEY,
        token_symbol TEXT,
        entry_price REAL,
        amount_sol REAL,
        amount_tokens INTEGER,
        timestamp TEXT,
        stop_loss REAL,
        take_profit REAL
    )''')
    conn.commit()
    conn.close()

def add_trade(token_address, symbol, action, amount_sol, price_usd, tx_sig):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        "INSERT INTO trades (token_address, token_symbol, action, amount_sol, price_usd, tx_signature, timestamp) VALUES (?,?,?,?,?,?,?)",
        (token_address, symbol, action, amount_sol, price_usd, tx_sig, datetime.now().isoformat())
    )
    conn.commit()
    conn.close()

def open_position(token_address, symbol, entry_price, amount_sol, amount_tokens):
    sl = entry_price * (1 - Config.STOP_LOSS_PCT / 100)
    tp = entry_price * (1 + Config.TAKE_PROFIT_PCT / 100)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        "INSERT OR REPLACE INTO positions VALUES (?,?,?,?,?,?,?,?)",
        (token_address, symbol, entry_price, amount_sol, amount_tokens, datetime.now().isoformat(), sl, tp)
    )
    conn.commit()
    conn.close()

def get_positions() -> list:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT * FROM positions")
    rows = c.fetchall()
    conn.close()
    columns = ["token_address", "symbol", "entry_price", "amount_sol", "amount_tokens", "timestamp", "stop_loss", "take_profit"]
    return [dict(zip(columns, row)) for row in rows]

def close_position(token_address: str):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM positions WHERE token_address=?", (token_address,))
    conn.commit()
    conn.close()

def get_trade_history(limit=20) -> list:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT * FROM trades ORDER BY timestamp DESC LIMIT ?", (limit,))
    rows = c.fetchall()
    conn.close()
    columns = ["id", "token_address", "symbol", "action", "amount_sol", "price_usd", "tx_sig", "timestamp", "pnl"]
    return [dict(zip(columns, row)) for row in rows]

def check_stop_loss_take_profit(current_prices: dict) -> list:
    positions = get_positions()
    to_close = []
    for pos in positions:
        current = current_prices.get(pos["token_address"], 0)
        if current <= 0:
            continue
        if current <= pos["stop_loss"]:
            to_close.append({"position": pos, "reason": "STOP_LOSS", "price": current})
        elif current >= pos["take_profit"]:
            to_close.append({"position": pos, "reason": "TAKE_PROFIT", "price": current})
    return to_close

def get_alltime_summary() -> dict:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    # Total trades
    c.execute("SELECT COUNT(*) FROM trades")
    total_trades = c.fetchone()[0]
    
    # Total buy & sell
    c.execute("SELECT COUNT(*) FROM trades WHERE action='BUY'")
    total_buy = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM trades WHERE action='SELL'")
    total_sell = c.fetchone()[0]
    
    # Profit & Loss dari pnl column
    c.execute("SELECT SUM(pnl) FROM trades WHERE pnl > 0")
    total_profit = c.fetchone()[0] or 0
    c.execute("SELECT SUM(pnl) FROM trades WHERE pnl < 0")
    total_loss = c.fetchone()[0] or 0
    c.execute("SELECT COUNT(*) FROM trades WHERE pnl > 0")
    win_count = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM trades WHERE pnl < 0")
    loss_count = c.fetchone()[0]
    
    # Posisi aktif
    c.execute("SELECT COUNT(*) FROM positions")
    active_positions = c.fetchone()[0]
    
    conn.close()
    
    total_closed = win_count + loss_count
    winrate = (win_count / total_closed * 100) if total_closed > 0 else 0
    
    return {
        "total_trades": total_trades,
        "total_buy": total_buy,
        "total_sell": total_sell,
        "active_positions": active_positions,
        "total_profit": total_profit,
        "total_loss": total_loss,
        "net_pnl": total_profit + total_loss,
        "win_count": win_count,
        "loss_count": loss_count,
        "winrate": winrate,
    }
