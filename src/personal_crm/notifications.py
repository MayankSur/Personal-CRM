from __future__ import annotations

import json
from urllib import request


def send_whatsapp_text(
    *,
    access_token: str,
    phone_number_id: str,
    to_number: str,
    message: str,
) -> dict:
    payload = {
        "messaging_product": "whatsapp",
        "to": to_number,
        "type": "text",
        "text": {"body": message},
    }
    req = request.Request(
        url=f"https://graph.facebook.com/v20.0/{phone_number_id}/messages",
        method="POST",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "content-type": "application/json",
            "authorization": f"Bearer {access_token}",
        },
    )
    with request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))
