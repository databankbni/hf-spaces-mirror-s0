import os
import logging
import asyncio
from typing import Dict, List, Optional
from telethon import TelegramClient
from telethon.sessions import StringSession
from utils.credentials import credential_pool, CredentialType, Credential
import config

logger = logging.getLogger("TELEGRAM")

class TelegramClientManager:
    def __init__(self):
        self.api_id = os.getenv("API_ID") or os.getenv("TELEGRAM_API_ID")
        self.api_hash = os.getenv("API_HASH") or os.getenv("TELEGRAM_API_HASH")
        self.clients: Dict[str, TelegramClient] = {}
        self.active_client_type: Optional[CredentialType] = None
        
        if not self.api_id or not self.api_hash:
            logger.critical("TELEGRAM_API_ID and TELEGRAM_API_HASH environment variables are required.")

    async def get_client_for_credential(self, cred: Credential) -> Optional[TelegramClient]:
        """
        Creates, connects, and authorizes a Telethon client from a credential.
        Caches it in self.clients.
        """
        if cred.name in self.clients:
            client = self.clients[cred.name]
            if client.is_connected():
                return client
            try:
                await client.connect()
                return client
            except Exception as e:
                logger.error(f"Reconnecting cached client {cred.name} failed: {e}")
                self.clients.pop(cred.name)

        if not self.api_id or not self.api_hash:
            return None

        client = None
        try:
            if cred.type == CredentialType.TELEGRAM_SESSION:
                # Initialize using User string session in-memory
                logger.telegram(f"Initializing user client for session {cred.name}...")
                client = TelegramClient(
                    StringSession(cred.value),
                    int(self.api_id),
                    self.api_hash
                )
                await client.connect()
                
                # Check if authorized
                if not await client.is_user_authorized():
                    logger.error(f"User session {cred.name} is NOT authorized or expired.")
                    cred.mark_invalid()
                    return None
                    
            elif cred.type == CredentialType.TELEGRAM_BOT_TOKEN:
                # Initialize bot client in-memory
                logger.telegram(f"Initializing bot client for token {cred.name}...")
                client = TelegramClient(
                    StringSession(""),  # In-memory session, does not write SQLite files
                    int(self.api_id),
                    self.api_hash
                )
                await client.start(bot_token=cred.value)
                
            if client:
                self.clients[cred.name] = client
                self.active_client_type = cred.type
                credential_pool.report_success(cred)
                logger.success(f"Telegram client '{cred.name}' successfully connected.")
                return client
                
        except Exception as e:
            logger.error(f"Failed to start Telegram client for {cred.name}: {e}")
            credential_pool.report_failure(cred, str(e))
            if client and client.is_connected():
                await client.disconnect()
            return None
            
        return None

    async def get_healthy_client(self) -> Optional[TelegramClient]:
        """
        Finds first available healthy credential (session or bot token)
        and returns its connected Telethon client.
        Loops through candidates in case of initialization failures.
        """
        # Collect healthy user sessions and bot tokens
        sessions = [c for c in credential_pool.credentials[CredentialType.TELEGRAM_SESSION] if c.is_available()]
        bots = [c for c in credential_pool.credentials[CredentialType.TELEGRAM_BOT_TOKEN] if c.is_available()]
        
        # Prioritize sessions, then bots
        candidates = sessions + bots
        
        if not candidates:
            logger.error("No healthy Telegram credentials found in pool.")
            return None
            
        for cred in candidates:
            cred.mark_busy()
            client = await self.get_client_for_credential(cred)
            cred.mark_idle()
            if client:
                return client
                
        logger.error("All available Telegram credentials failed to initialize.")
        return None

    async def disconnect_all(self):
        logger.system("Disconnecting all active Telegram clients...")
        for name, client in list(self.clients.items()):
            try:
                if client.is_connected():
                    await client.disconnect()
                logger.system(f"Client '{name}' disconnected.")
            except Exception as e:
                logger.error(f"Error disconnecting client {name}: {e}")
        self.clients.clear()
        self.active_client_type = None

    def is_bot_active(self) -> bool:
        return self.active_client_type == CredentialType.TELEGRAM_BOT_TOKEN

# Global manager instance
client_manager = TelegramClientManager()
