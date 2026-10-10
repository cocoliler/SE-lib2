from __future__ import annotations

import os
import time
from dataclasses import dataclass

try:
    from dotenv import load_dotenv  # type: ignore
except ImportError:  # pragma: no cover - 仅当用户未安装 python-dotenv 时触发
    def load_dotenv() -> bool:  # type: ignore
        return False

try:
    from openai import OpenAI  # type: ignore
except ImportError:  # pragma: no cover - 仅当用户未安装 openai 时触发
    OpenAI = None  # type: ignore


@dataclass
class LLMClient:
    api_key: str
    base_url: str
    model: str
    max_retries: int = 3

    @classmethod
    def from_env(cls) -> "LLMClient":
        load_dotenv()

        api_key = os.getenv("LLM_API_KEY", "").strip()
        base_url = os.getenv("LLM_BASE_URL", "https://api.openai.com/v1").strip()
        model = os.getenv("LLM_MODEL", "").strip()

        if not api_key:
            raise RuntimeError(
                "未配置 LLM_API_KEY，请复制 .env.example 为 .env 并填写 API Key。"
            )
        if not model:
            raise RuntimeError(
                "未配置 LLM_MODEL，请在 .env 中填写模型名称。"
            )

        return cls(api_key=api_key, base_url=base_url, model=model)

    def complete(self, system_prompt: str, user_prompt: str, temperature: float = 0.2) -> str:
        if OpenAI is None:
            raise RuntimeError(
                "缺少依赖 openai，请先 `pip install openai python-dotenv` 或 `pip install -r requirements.txt`。"
            )
        client = OpenAI(api_key=self.api_key, base_url=self.base_url)

        last_error: Exception | None = None

        for attempt in range(self.max_retries):
            try:
                response = client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    temperature=temperature,
                )

                content = response.choices[0].message.content
                if not content:
                    raise RuntimeError("LLM 返回了空内容。")
                return content.strip()

            except Exception as exc:
                last_error = exc
                if attempt == self.max_retries - 1:
                    break

                time.sleep(2**attempt)

        raise RuntimeError(
            f"LLM 调用失败，已重试 {self.max_retries} 次：{last_error}"
        )
