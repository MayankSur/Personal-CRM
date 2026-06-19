from __future__ import annotations

import json
from typing import Literal
from urllib import request

from .recommender import Recommendation


Provider = Literal["anthropic", "openai"]


def enhance_recommendation_prompts(
    recommendations: list[Recommendation],
    *,
    provider: Provider,
    api_key: str,
    model: str,
    owner_context: str = "",
) -> None:
    for rec in recommendations:
        rec.prompt = _enhance_single_prompt(
            rec,
            provider=provider,
            api_key=api_key,
            model=model,
            owner_context=owner_context,
        )


def _enhance_single_prompt(
    rec: Recommendation,
    *,
    provider: Provider,
    api_key: str,
    model: str,
    owner_context: str,
) -> str:
    system = (
        "You are a thoughtful relationship coach. Return one concise message draft in plain text. "
        "No markdown, no greeting preamble, no explanation. Keep it natural and specific."
    )
    user = (
        f"Person: {rec.full_name}\n"
        f"Group: {rec.group_name}\n"
        f"Days since outgoing message: {rec.days_since_outgoing}\n"
        f"Reason: {rec.reason}\n"
        f"Base prompt: {rec.prompt}\n"
        f"Owner context: {owner_context or 'No extra context provided.'}\n"
        "Write a message I can send now."
    )

    if provider == "anthropic":
        return _call_anthropic(system=system, user=user, api_key=api_key, model=model)
    if provider == "openai":
        return _call_openai(system=system, user=user, api_key=api_key, model=model)

    raise ValueError(f"Unsupported provider: {provider}")


def _call_anthropic(*, system: str, user: str, api_key: str, model: str) -> str:
    payload = {
        "model": model,
        "max_tokens": 220,
        "system": system,
        "messages": [{"role": "user", "content": user}],
    }
    req = request.Request(
        url="https://api.anthropic.com/v1/messages",
        method="POST",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "content-type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        },
    )
    with request.urlopen(req, timeout=30) as resp:
        body = json.loads(resp.read().decode("utf-8"))
    content = body.get("content") or []
    for block in content:
        if block.get("type") == "text" and block.get("text"):
            return block["text"].strip()
    return ""


def _call_openai(*, system: str, user: str, api_key: str, model: str) -> str:
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": 0.7,
    }
    req = request.Request(
        url="https://api.openai.com/v1/chat/completions",
        method="POST",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "content-type": "application/json",
            "authorization": f"Bearer {api_key}",
        },
    )
    with request.urlopen(req, timeout=30) as resp:
        body = json.loads(resp.read().decode("utf-8"))
    choices = body.get("choices") or []
    if not choices:
        return ""
    msg = choices[0].get("message") or {}
    return (msg.get("content") or "").strip()
