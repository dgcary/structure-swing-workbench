"""OpenAI-compatible chat-completions client for the LLM plan adapter.

httpx is imported lazily so core modules never depend on it; errors surface
as :class:`LlmError` with Chinese messages for the workbench UI.
"""

from __future__ import annotations

from collections.abc import Callable

from app.services.llm_plan import LlmError


class LlmClient:
    def __init__(
        self,
        base_url: str,
        model: str,
        api_key: str | None = None,
        timeout: float = 60.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.timeout = timeout

    def complete(self, system: str, user: str) -> str:
        import httpx

        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": 0,
        }
        try:
            response = httpx.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=payload,
                timeout=self.timeout,
            )
        except httpx.HTTPError as exc:
            raise LlmError(f"LLM 请求失败：网络错误（{exc.__class__.__name__}）") from exc
        if response.status_code != 200:
            raise LlmError(f"LLM 请求失败：HTTP {response.status_code}")
        try:
            data = response.json()
            content = data["choices"][0]["message"]["content"]
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise LlmError("LLM 返回格式无法解析") from exc
        if not isinstance(content, str) or not content.strip():
            raise LlmError("LLM 返回空内容")
        return content


def get_llm_completer(
    base_url: str, model: str, api_key: str | None
) -> Callable[[str, str], str]:
    """返回可注入的 complete(system, user) -> str。"""

    client = LlmClient(base_url, model, api_key)
    return client.complete
