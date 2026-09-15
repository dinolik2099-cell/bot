from __future__ import annotations
import os
import json
from urllib.request import Request, urlopen

class NotificationSink:
    """Environment-compatible sink; durable outbox delivery is at-least-once, never exactly-once."""
    def __init__(self,send=None,environ=None,transport=None,timeout_seconds=10):
        self.environ=environ or os.environ;self.transport=transport or urlopen;self.timeout_seconds=timeout_seconds
        self.send=send or self._telegram_send
    def enabled(self):return self.environ.get("TG_ENABLED","").lower() in {"1","true","yes"} and bool(self.environ.get("TG_BOT_TOKEN")) and bool(self.environ.get("TG_CHAT_ID"))
    def notify(self,message):
        if self.enabled():self.send(message)
    def _telegram_send(self,message):
        # Do not include credential values in exceptions, reports or payloads.
        token=self.environ["TG_BOT_TOKEN"];chat_id=self.environ["TG_CHAT_ID"]
        payload=json.dumps({"chat_id":chat_id,"text":str(message)},separators=(",",":"),ensure_ascii=False).encode("utf-8")
        request=Request(f"https://api.telegram.org/bot{token}/sendMessage",data=payload,headers={"Content-Type":"application/json"},method="POST")
        response=self.transport(request,timeout=self.timeout_seconds)
        try:
            status=getattr(response,"status",getattr(response,"code",200))
            if status is not None and int(status)>=400:raise RuntimeError("telegram_delivery_rejected")
        finally:
            close=getattr(response,"close",None)
            if callable(close):close()
