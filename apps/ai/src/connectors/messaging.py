"""
Messaging Connector ABC — capability interface for chat/notification delivery.

Concrete implementations:

* :class:`connectors.slack_connector.SlackConnector`
"""

from __future__ import annotations

from abc import abstractmethod
from typing import Any

from .base import Connector


class MessagingConnector(Connector):
    """Capability interface for messaging / notification platforms.

    Every messaging connector must implement the methods below.  Return
    values carry ``source`` and ``fetched_at`` metadata.
    """

    def capability(self) -> str:
        return "messaging"

    # ------------------------------------------------------------------
    # Required messaging methods
    # ------------------------------------------------------------------

    @abstractmethod
    def send_message(self, channel: str, text: str) -> dict[str, Any]:
        """Send a text message to a channel.

        Parameters
        ----------
        channel:
            Channel identifier (e.g. Slack channel ID or channel name).
        text:
            Message body.

        Returns
        -------
        dict
            Status dict with at minimum:

            .. code-block:: python

                {"ok": True, "channel": "C12345"}
        """
        ...

    @abstractmethod
    def get_messages(self, channel: str, limit: int = 20) -> list[dict[str, Any]]:
        """Fetch recent messages from a channel.

        Parameters
        ----------
        channel:
            Channel identifier.
        limit:
            Maximum number of messages to return.

        Returns
        -------
        list[dict]
            Each entry contains at minimum:

            .. code-block:: python

                {
                    "text": "Hello world",
                    "user": "U12345",
                    "channel": "C12345",
                    "timestamp": "1714567890.000100",
                    "source": "slack",
                    "fetched_at": "2026-07-26T12:00:00Z",
                }
        """
        ...
