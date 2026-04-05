import aiohttp
import base64
import requests
from solana.rpc.async_api import AsyncClient
from solana.rpc.types import TxOpts
from solders.keypair import Keypair
from solders.transaction import VersionedTransaction
import base58
from config import Config

SOL_MINT = "So11111111111111111111111111111111111111112"
PUMP_API = "https://pumpportal.fun/api/trade-local"

class TradingEngine:
    def __init__(self):
        self.client  = AsyncClient(Config.RPC_URL)
        self.keypair = Keypair.from_bytes(base58.b58decode(Config.WALLET_KEY))
        self.wallet_address = str(self.keypair.pubkey())

    async def get_wallet_balance(self) -> float:
        response = await self.client.get_balance(self.keypair.pubkey())
        return response.value / 1e9

    async def _sign_and_send(self, tx_bytes: bytes) -> dict:
        try:
            tx = VersionedTransaction.from_bytes(tx_bytes)
            signed_tx = VersionedTransaction(tx.message, [self.keypair])
            result = await self.client.send_raw_transaction(
                bytes(signed_tx),
                opts=TxOpts(skip_preflight=False, preflight_commitment="confirmed")
            )
            return {"success": True, "signature": str(result.value)}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def buy_token(self, token_address: str, amount_sol: float, dex: str = None, pair_address: str = None) -> dict:
        try:
            # Pakai requests sync (sesuai docs resmi pumpportal)
            import asyncio
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(None, lambda: requests.post(
                url=PUMP_API,
                data={
                    "publicKey":        self.wallet_address,
                    "action":           "buy",
                    "mint":             token_address,
                    "denominatedInSol": "true",
                    "amount":           amount_sol,
                    "slippage":         15,
                    "priorityFee":      0.005,
                    "pool":             "auto"
                }
            ))

            if response.status_code != 200:
                return {"success": False, "error": f"Pump HTTP {response.status_code}: {response.text}"}

            tx_bytes = response.content
            if not tx_bytes:
                return {"success": False, "error": "No TX data"}

            return await self._sign_and_send(tx_bytes)
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def buy_token_jupiter(self, token_address: str, amount_sol: float) -> dict:
        return await self.buy_token(token_address, amount_sol)

    async def sell_token(self, token_address: str, amount_tokens: int = 0, dex: str = None) -> dict:
        try:
            import asyncio
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(None, lambda: requests.post(
                url=PUMP_API,
                data={
                    "publicKey":        self.wallet_address,
                    "action":           "sell",
                    "mint":             token_address,
                    "denominatedInSol": "false",
                    "amount":           "100%" if amount_tokens <= 0 else str(amount_tokens),
                    "slippage":         15,
                    "priorityFee":      0.005,
                    "pool":             "auto"
                }
            ))

            if response.status_code != 200:
                return {"success": False, "error": f"Pump HTTP {response.status_code}: {response.text}"}

            tx_bytes = response.content
            if not tx_bytes:
                return {"success": False, "error": "No TX data"}

            return await self._sign_and_send(tx_bytes)
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def sell_token_jupiter(self, token_address: str, amount_tokens: int) -> dict:
        return await self.sell_token(token_address, amount_tokens)
