"""
Slack Messaging Connector — capability implementation of :class:`MessagingConnector`.

Provides message send and receive capabilities through the Slack Web API
using the ``slack_sdk``.  Supports mock mode for development.

Environment Variables (production mode):
    SLACK_BOT_TOKEN: Slack bot / user OAuth token (``xoxb-`` or ``xoxp-``)
    SLACK_WEBHOOK_URL: Slack Incoming Webhook URL (fallback for send)
"""

from __future__ import annotations

import logging
import os
from typing import Any

from .base import ConnectorConfig
from .messaging import MessagingConnector
from ..integrations.retry import circuit_breaker

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Mock seed data
# ---------------------------------------------------------------------------

_MOCK_MESSAGES: list[dict[str, Any]] = [
    {
        "text": "Good morning team! Here's the daily standup update...",
        "user": "U001",
        "channel": "C-general",
        "timestamp": "1714567890.000100",
    },
    {
        "text": "MRR crossed $15k this month! Great work everyone :tada:",
        "user": "U002",
        "channel": "C-general",
        "timestamp": "1714567891.000200",
    },
    {
        "text": "Deploying v2.4.1 to production — ETA 15 minutes",
        "user": "U003",
        "channel": "C-engineering",
        "timestamp": "1714567892.000300",
    },
]


class SlackConnector(MessagingConnector):
    """Slack messaging connector.

    Parameters
    ----------
    config: ConnectorConfig
        If ``config.mock_mode`` is *True* or no Slack token is configured,
        returns realistic seed data without network calls.

    Usage::

        config = ConnectorConfig(tenant_id="startup_abc", mock_mode=True)
        slack = SlackConnector(config)
        result = slack.send_message("#general", "Hello, world!")
    """

    def __init__(self, config: ConnectorConfig) -> None:
        super().__init__(config)
        self._bot_token = config.credentials.get(
            "bot_token", os.getenv("SLACK_BOT_TOKEN", "")
        )
        self._webhook_url = config.credentials.get(
            "webhook_url", os.getenv("SLACK_WEBHOOK_URL", "")
        )
        # Auto-enable mock when no credentials are configured
        if not self._has_credentials():
            logger.info(
                "SlackConnector[%s]: no credentials found, enabling mock mode",
                config.tenant_id,
            )
            self.config.mock_mode = True

    def name(self) -> str:
        return "slack"

    # ------------------------------------------------------------------
    # Health
    # ------------------------------------------------------------------

    @circuit_breaker("slack")
    def health(self) -> dict[str, Any]:
        if self.config.mock_mode:
            return {"status": "ok", "latency_ms": 0, "source": "slack_mock"}

        import time

        start = time.monotonic()
        try:
            client = self._get_client()
            resp = client.auth_test()
            elapsed = int((time.monotonic() - start) * 1000)
            return {
                "status": "ok",
                "latency_ms": elapsed,
                "source": "slack",
                "team": resp.get("team", ""),
                "user": resp.get("user", ""),
            }
        except Exception as exc:
            elapsed = int((time.monotonic() - start) * 1000)
            logger.warning("Slack health check failed: %s", exc)
            return {"status": "down", "latency_ms": elapsed, "error": str(exc)}

    # ------------------------------------------------------------------
    # Messaging methods
    # ------------------------------------------------------------------

    @circuit_breaker("slack_send")
    def send_message(self, channel: str, text: str) -> dict[str, Any]:
        if self.config.mock_mode:
            return self._add_metadata(
                {"ok": True, "channel": channel, "mock": True}, "slack_mock"
            )

        try:
            client = self._get_client()
            resp = client.chat_postMessage(channel=channel, text=text)
            return self._add_metadata(
                {
                    "ok": resp.get("ok", False),
                    "channel": resp.get("channel", channel),
                    "ts": resp.get("ts", ""),
                },
                "slack",
            )
        except Exception as exc:
            logger.error("Slack send_message failed: %s", exc)
            return self._error_result(
                "slack", partial_data={"ok": False, "channel": channel}, error=str(exc)
            )

    @circuit_breaker("slack_read")
    def get_messages(self, channel: str, limit: int = 20) -> list[dict[str, Any]]:
        if self.config.mock_mode:
            return [
                self._add_metadata(
                    {**m, "channel": channel}, "slack_mock"
                )
                for m in _MOCK_MESSAGES
            ][:limit]

        try:
            client = self._get_client()
            resp = client.conversations_history(channel=channel, limit=min(limit, 200))
            messages = []
            for msg in resp.get("messages", []):
                messages.append(self._add_metadata(
                    {
                        "text": msg.get("text", ""),
                        "user": msg.get("user", ""),
                        "channel": channel,
                        "timestamp": msg.get("ts", ""),
                    },
                    "slack",
                ))
            return messages
        except Exception as exc:
            logger.error("Slack get_messages failed: %s", exc)
            return [self._error_result("slack", error=str(exc))]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _has_credentials(self) -> bool:
        return bool(self._bot_token or self._webhook_url)

    def _get_client(self):
        """Lazy-init the Slack WebClient."""
        if not hasattr(self, "_client") or self._client is None:
            # Deferred import so slack_sdk is optional at install time
            from slack_sdk import WebClient

            self._client = WebClient(token=self._bot_token)
        return self._client
