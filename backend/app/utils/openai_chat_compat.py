"""
OpenAI Chat Completions compatibility helpers.

This module keeps existing behavior for legacy models/providers while
gracefully adapting request parameters for GPT-5 family models.
"""

from __future__ import annotations

import inspect
from typing import Any, Dict, List, Optional
from openai import APIError, APIConnectionError, APITimeoutError


class ModelServiceError(RuntimeError):
    """Safe public error preserving only capability negotiation metadata."""

    def __init__(self, error: APIError):
        status = getattr(error, 'status_code', None)
        self.status_code = status if isinstance(status, int) and 100 <= status <= 599 else None
        self.outcome_unknown = isinstance(error, (APITimeoutError, APIConnectionError))
        if isinstance(error, APITimeoutError):
            message = '模型服務連線逾時，回覆結果未確認；已保留工作，不會自動重送。'
        elif isinstance(error, APIConnectionError):
            message = '無法連線到模型服務，請檢查網址、網路與憑證。'
        else:
            message = '模型服務未能完成請求' + (f'（HTTP {self.status_code}）' if self.status_code else '') + '，請檢查模型名稱、權限或服務狀態。'
        # A few providers reject JSON mode explicitly. Retain that fact so the
        # caller can perform its existing bounded fallback, but never retain
        # arbitrary provider text, request IDs, headers or credential echoes.
        body = getattr(error, 'body', None)
        detail = body.get('error', body) if isinstance(body, dict) else {}
        if not isinstance(detail, dict):
            detail = {}
        param = str(detail.get('param') or '').lower()
        code = str(detail.get('code') or '').lower()
        text = str(detail.get('message') or '').lower()
        format_rejection = (param == 'response_format' or param.startswith('response_format.')) or (
            'response_format' in text and (code in {'unsupported_parameter', 'unsupported_value', 'unknown_parameter', 'invalid_parameter'}
            or any(phrase in text for phrase in ('not support', 'unsupported', 'unknown parameter', 'unrecognized parameter'))))
        self.body = {'error': {'param': 'response_format', 'code': 'unsupported_parameter', 'message': 'response_format not supported'}} if format_rejection else {'error': {'code': 'model_request_failed'}}
        super().__init__(message)


async def _await_safe_completion(response):
    try:
        return await response
    except APIError as error:
        raise ModelServiceError(error) from None


def is_gpt5_family(model: Optional[str]) -> bool:
    """Return True when model belongs to GPT-5 family aliases/snapshots."""
    if not model:
        return False
    name = model.strip().lower()
    prefix, separator, unprefixed = name.partition('/')
    if separator and prefix in {'cx', 'codex', 'ocg', 'opencode-go', 'opencode'}:
        name = unprefixed
    return name.startswith("gpt-5")


def create_chat_completion(
    client: Any,
    *,
    model: str,
    messages: List[Dict[str, Any]],
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
    response_format: Optional[Dict[str, Any]] = None,
    tools: Optional[List[Dict[str, Any]]] = None,
    tool_choice: Optional[Any] = None,
) -> Any:
    """
    Create a chat completion with model-specific request parameters.

    Compatibility strategy:
    - For GPT-5 family, avoid sending temperature by default.
    - For token limit, use `max_completion_tokens` on GPT-5, `max_tokens` otherwise.
    - Preserve the legacy request shape for every non-GPT-5 model/provider.
    - Propagate provider errors unchanged instead of guessing from message text.
    """
    kwargs: Dict[str, Any] = {
        "model": model,
        "messages": messages,
    }

    if response_format is not None:
        kwargs["response_format"] = response_format
    if tools is not None:
        kwargs['tools'] = tools
        kwargs['parallel_tool_calls'] = False
    if tool_choice is not None:
        kwargs['tool_choice'] = tool_choice

    gpt5_family = is_gpt5_family(model)

    if temperature is not None and not gpt5_family:
        kwargs["temperature"] = temperature

    if max_tokens is not None:
        if gpt5_family:
            kwargs["max_completion_tokens"] = max_tokens
        else:
            kwargs["max_tokens"] = max_tokens

    try:
        response = client.chat.completions.create(**kwargs)
    except APIError as error:
        raise ModelServiceError(error) from None
    return _await_safe_completion(response) if inspect.isawaitable(response) else response


def extract_chat_completion_text(response: Any) -> str:
    """Extract plain text from chat completion response across SDK content shapes."""
    choices = getattr(response, "choices", None) or []
    if not choices:
        return ""

    message = getattr(choices[0], "message", None)
    if message is None:
        return ""

    content = getattr(message, "content", "")

    if isinstance(content, str):
        return content

    if isinstance(content, list):
        chunks: List[str] = []
        for item in content:
            if isinstance(item, dict):
                text_obj = item.get("text")
                if isinstance(text_obj, dict):
                    text_obj = text_obj.get("value")
                if isinstance(text_obj, str):
                    chunks.append(text_obj)
                elif isinstance(item.get("content"), str):
                    chunks.append(item["content"])
                continue

            text_obj = getattr(item, "text", None)
            if isinstance(text_obj, dict):
                text_obj = text_obj.get("value")
            if isinstance(text_obj, str):
                chunks.append(text_obj)
                continue

            content_obj = getattr(item, "content", None)
            if isinstance(content_obj, str):
                chunks.append(content_obj)

        return "".join(chunks).strip()

    return str(content or "")
