from __future__ import annotations
import os

class NotificationSink:
    """Environment-compatible notification seam; no token is read into evidence."""
    def __init__(self,send=None,environ=None):self.send,self.environ=send or (lambda _message:None),environ or os.environ
    def enabled(self):return self.environ.get("TG_ENABLED","").lower() in {"1","true","yes"} and bool(self.environ.get("TG_BOT_TOKEN")) and bool(self.environ.get("TG_CHAT_ID"))
    def notify(self,message):
        if self.enabled():self.send(message)
