"""The notification seam: one message type, one channel interface."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Notification:
    """A rendered message, independent of how it will be delivered.

    ``recipient`` is whatever address the channel needs - an email address
    today, a phone number or a device token for a future channel. ``kind`` and
    ``context`` let a channel re-render the message its own way (a push channel
    has no use for a three-paragraph body) without the caller knowing which
    channels are installed.
    """

    recipient: str
    subject: str
    body: str
    kind: str
    context: dict = field(default_factory=dict)


class NotificationChannel(ABC):
    """A way of getting notifications to members.

    Channels receive a *batch*. Delivering one at a time is what makes a
    100k-member overdue run slow, so the interface makes batching the default
    rather than an optimisation a channel has to remember.
    """

    #: Short identifier, used in logs and settings.
    name = 'channel'

    @abstractmethod
    def deliver(self, notifications):
        """Deliver ``notifications``; return how many were handed off."""
        raise NotImplementedError
