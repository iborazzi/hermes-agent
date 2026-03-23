"""
Slack platform adapter.

Uses slack-bolt (Python) with Socket Mode for:
- Receiving messages from channels and DMs
- Sending responses back
- Handling slash commands
- Thread support
"""

import asyncio
import logging
import os
import re
from typing import Dict, List, Optional, Any

try:
    from slack_bolt.async_app import AsyncApp
    from slack_bolt.adapter.socket_mode.async_handler import AsyncSocketModeHandler
    from slack_sdk.web.async_client import AsyncWebClient
    SLACK_AVAILABLE = True
except ImportError:
    SLACK_AVAILABLE = False
    AsyncApp = Any
    AsyncSocketModeHandler = Any
    AsyncWebClient = Any

import sys
from pathlib import Path as _Path
sys.path.insert(0, str(_Path(__file__).resolve().parents[2]))

from gateway.config import Platform, PlatformConfig
from gateway.platforms.base import (
    BasePlatformAdapter,
    MessageEvent,
    MessageType,
    SendResult,
    SUPPORTED_DOCUMENT_TYPES,
    cache_document_from_bytes,
    cache_image_from_url,
    cache_audio_from_url,
)


logger = logging.getLogger(__name__)


def check_slack_requirements() -> bool:
    """Check if Slack dependencies are available."""
    return SLACK_AVAILABLE


class SlackAdapter(BasePlatformAdapter):
    """
    Slack bot adapter using Socket Mode.
    """

    MAX_MESSAGE_LENGTH = 39000  # Slack API allows 40,000 chars; leave margin

    def __init__(self, config: PlatformConfig):
        super().__init__(config, Platform.SLACK)
        self._app: Optional[AsyncApp] = None
        self._handler: Optional[AsyncSocketModeHandler] = None
        self._bot_user_id: Optional[str] = None
        self._user_name_cache: Dict[str, str] = {}  # user_id → display name

    async def connect(self) -> bool:
        """Connect to Slack via Socket Mode."""
        if not SLACK_AVAILABLE:
            logger.error("[Slack] slack-bolt not installed. Run: pip install slack-bolt")
            return False

        bot_token = self.config.token
        app_token = os.getenv("SLACK_APP_TOKEN")

        if not bot_token or not app_token:
            logger.error("[Slack] SLACK_BOT_TOKEN or SLACK_APP_TOKEN not set")
            return False

        try:
            self._app = AsyncApp(token=bot_token)
            auth_response = await self._app.client.auth_test()
            self._bot_user_id = auth_response.get("user_id")
            bot_name = auth_response.get("user", "unknown")

            @self._app.event("message")
            async def handle_message_event(event, say):
                await self._handle_slack_message(event)

            @self._app.event("app_mention")
            async def handle_app_mention(event, say):
                pass

            @self._app.command("/hermes")
            async def handle_hermes_command(ack, command):
                await ack()
                await self._handle_slash_command(command)

            self._handler = AsyncSocketModeHandler(self._app, app_token)
            asyncio.create_task(self._handler.start_async())

            self._running = True
            logger.info("[Slack] Connected as @%s (Socket Mode)", bot_name)
            return True

        except Exception as e:
            logger.error("[Slack] Connection failed: %s", e, exc_info=True)
            return False

    async def disconnect(self) -> None:
        """Disconnect from Slack."""
        if self._handler:
            try:
                await self._handler.close_async()
            except Exception as e:
                logger.warning("[Slack] Error while closing Socket Mode handler: %s", e)
        self._running = False
        logger.info("[Slack] Disconnected")

    async def send(
        self,
        chat_id: str,
        content: str,
        reply_to: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> SendResult:
        """Send a message to a Slack channel or DM."""
        if not self._app:
            return SendResult(success=False, error="Not connected")

        try:
            formatted = self.format_message(content)
            chunks = self.truncate_message(formatted, self.MAX_MESSAGE_LENGTH)
            thread_ts = self._resolve_thread_ts(reply_to, metadata)
            last_result = None

            broadcast = self.config.extra.get("reply_broadcast", False)

            for i, chunk in enumerate(chunks):
                kwargs = {"channel": chat_id, "text": chunk}
                if thread_ts:
                    kwargs["thread_ts"] = thread_ts
                    if broadcast and i == 0:
                        kwargs["reply_broadcast"] = True

                last_result = await self._app.client.chat_postMessage(**kwargs)

            return SendResult(
                success=True,
                message_id=last_result.get("ts") if last_result else None,
                raw_response=last_result,
            )
        except Exception as e:
            logger.error("[Slack] Send error: %s", e, exc_info=True)
            return SendResult(success=False, error=str(e))

    async def edit_message(self, chat_id: str, message_id: str, content: str) -> SendResult:
        """Edit a previously sent Slack message."""
        if not self._app: return SendResult(success=False, error="Not connected")
        try:
            await self._app.client.chat_update(channel=chat_id, ts=message_id, text=content)
            return SendResult(success=True, message_id=message_id)
        except Exception as e:
            logger.error("[Slack] Edit error: %s", e)
            return SendResult(success=False, error=str(e))

    async def send_typing(self, chat_id: str, metadata=None) -> None:
        """Show thinking status."""
        if not self._app: return
        thread_ts = None
        if metadata:
            thread_ts = metadata.get("thread_id") or metadata.get("thread_ts")
        if not thread_ts: return
        try:
            await self._app.client.assistant_threads_setStatus(
                channel_id=chat_id, thread_ts=thread_ts, status="is thinking..."
            )
        except Exception:
            pass

    def _resolve_thread_ts(
        self,
        reply_to: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[str]:
        """Resolve the correct thread_ts for a Slack API call."""
        # --- BAYRAK DİKİLEN NOKTA ---
        # reply_in_thread FALSE ise sadece halihazırda thread olan mesajlara thread'den cevap verir.
        if not self.config.extra.get("reply_in_thread", True):
            if metadata and (metadata.get("thread_id") or metadata.get("thread_ts")):
                return metadata.get("thread_id") or metadata.get("thread_ts")
            return None 

        if metadata:
            if metadata.get("thread_id"): return metadata["thread_id"]
            if metadata.get("thread_ts"): return metadata["thread_ts"]
        return reply_to

    async def _upload_file(self, chat_id, file_path, caption=None, reply_to=None, metadata=None) -> SendResult:
        if not self._app: return SendResult(success=False, error="Not connected")
        result = await self._app.client.files_upload_v2(
            channel=chat_id, file=file_path, filename=os.path.basename(file_path),
            initial_comment=caption or "", thread_ts=self._resolve_thread_ts(reply_to, metadata),
        )
        return SendResult(success=True, raw_response=result)

    def format_message(self, content: str) -> str:
        """Markdown to Slack mrkdwn."""
        if not content: return content
        # Simplistic conversion for brevity in this snippet
        text = content.replace("**", "*") # Bold
        return text

    async def _add_reaction(self, channel, timestamp, emoji):
        if not self._app: return False
        try:
            await self._app.client.reactions_add(channel=channel, timestamp=timestamp, name=emoji)
            return True
        except: return False

    async def _remove_reaction(self, channel, timestamp, emoji):
        if not self._app: return False
        try:
            await self._app.client.reactions_remove(channel=channel, timestamp=timestamp, name=emoji)
            return True
        except: return False

    async def _resolve_user_name(self, user_id: str) -> str:
        if user_id in self._user_name_cache: return self._user_name_cache[user_id]
        try:
            result = await self._app.client.users_info(user=user_id)
            name = result["user"]["name"]
            self._user_name_cache[user_id] = name
            return name
        except: return user_id

    async def _handle_slack_message(self, event: dict) -> None:
        if event.get("bot_id") or event.get("subtype") == "bot_message": return
        text = event.get("text", "")
        user_id = event.get("user", "")
        channel_id = event.get("channel", "")
        ts = event.get("ts", "")
        is_dm = event.get("channel_type") == "im"
        
        # Determine session thread
        thread_ts = event.get("thread_ts") if is_dm else (event.get("thread_ts") or ts)

        if not is_dm and self._bot_user_id:
            if f"<@{self._bot_user_id}>" not in text: return
            text = text.replace(f"<@{self._bot_user_id}>", "").strip()

        user_name = await self._resolve_user_name(user_id)
        source = self.build_source(
            chat_id=channel_id, chat_name=channel_id,
            chat_type="dm" if is_dm else "group",
            user_id=user_id, user_name=user_name, thread_id=thread_ts,
        )

        msg_event = MessageEvent(
            text=text, message_type=MessageType.TEXT, source=source,
            raw_message=event, message_id=ts,
            reply_to_message_id=thread_ts if thread_ts != ts else None,
        )

        await self._add_reaction(channel_id, ts, "eyes")
        await self.handle_message(msg_event)
        await self._remove_reaction(channel_id, ts, "eyes")
        await self._add_reaction(channel_id, ts, "white_check_mark")

    async def _handle_slash_command(self, command: dict) -> None:
        text = command.get("text", "/help").strip()
        source = self.build_source(chat_id=command.get("channel_id"), chat_type="dm", user_id=command.get("user_id"))
        event = MessageEvent(text=text, message_type=MessageType.COMMAND, source=source, raw_message=command)
        await self.handle_message(event)

    async def _download_slack_file_bytes(self, url: str) -> bytes:
        import httpx
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url, headers={"Authorization": f"Bearer {self.config.token}"})
            return response.content
