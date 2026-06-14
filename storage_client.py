"""
0G Storage Client
Uploads audit reports to 0G Storage network.
Returns content hash (merkle root) and retrieval URL.
"""

import os
import hashlib
import aiohttp
import logging
from typing import Optional

log = logging.getLogger("0G-Guardian.Storage")

OG_STORAGE_RPC = os.getenv("OG_STORAGE_RPC", "https://rpc-storage-testnet.0g.ai")
OG_STORAGE_INDEXER = os.getenv("OG_STORAGE_INDEXER", "https://indexer-storage-testnet-standard.0g.ai")


class ZeroGStorageClient:
    def __init__(self):
        self.rpc_url = OG_STORAGE_RPC
        self.indexer_url = OG_STORAGE_INDEXER
        self.timeout = aiohttp.ClientTimeout(total=60)

    async def upload(self, data: bytes, filename: str) -> dict:
        """
        Upload bytes to 0G Storage.
        Returns: { "hash": "0x...", "url": "...", "size": N }

        0G Storage SDK (zgstorage) is called via HTTP RPC.
        In production, use the official Python SDK: pip install 0g-storage-client
        """
        content_hash = self._compute_hash(data)

        try:
            result = await self._upload_via_rpc(data, filename, content_hash)
            log.info(f"Uploaded to 0G Storage: {content_hash} ({len(data)} bytes)")
            return result
        except Exception as e:
            log.error(f"0G Storage upload failed: {e}")
            # Fallback: return local hash for development
            return {
                "hash": content_hash,
                "url": f"{self.indexer_url}/file/{content_hash}",
                "size": len(data),
                "status": "local_fallback"
            }

    async def _upload_via_rpc(self, data: bytes, filename: str, content_hash: str) -> dict:
        """
        Upload to 0G Storage via JSON-RPC.
        Ref: https://docs.0g.ai/developer-hub/building-on-0g/storage-sdk
        """
        import base64

        payload = {
            "jsonrpc": "2.0",
            "method": "zgs_uploadFile",
            "params": [{
                "data": base64.b64encode(data).decode(),
                "filename": filename,
                "tags": ["guardian-audit", "security"]
            }],
            "id": 1
        }

        async with aiohttp.ClientSession(timeout=self.timeout) as session:
            async with session.post(
                self.rpc_url,
                json=payload,
                headers={"Content-Type": "application/json"}
            ) as resp:
                result = await resp.json()

                if "error" in result:
                    raise RuntimeError(f"0G Storage RPC error: {result['error']}")

                file_hash = result.get("result", {}).get("hash", content_hash)
                retrieval_url = f"{self.indexer_url}/file/{file_hash}"

                return {
                    "hash": file_hash,
                    "url": retrieval_url,
                    "size": len(data),
                    "status": "uploaded"
                }

    async def download(self, content_hash: str) -> Optional[bytes]:
        """Download a file from 0G Storage by its content hash."""
        try:
            async with aiohttp.ClientSession(timeout=self.timeout) as session:
                url = f"{self.indexer_url}/file/{content_hash}"
                async with session.get(url) as resp:
                    if resp.status == 200:
                        return await resp.read()
        except Exception as e:
            log.error(f"0G Storage download failed for {content_hash}: {e}")
        return None

    def _compute_hash(self, data: bytes) -> str:
        """Compute SHA-256 content hash (used as fallback / local reference)."""
        return "0x" + hashlib.sha256(data).hexdigest()
