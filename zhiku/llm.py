"""模型客户端：兼容任意 OpenAI 风格 /chat/completions 接口。

零第三方依赖，纯标准库 urllib 实现，可对接：
  - DeepSeek：   LLM_BASE_URL=https://api.deepseek.com  LLM_MODEL=deepseek-flash
  - OpenAI：     LLM_BASE_URL=https://api.openai.com/v1 LLM_MODEL=gpt-4o-mini
  - Ollama 本地：LLM_BASE_URL=http://localhost:11434/v1 LLM_MODEL=qwen2.5

环境变量（亦可在命令行传入）：LLM_API_KEY / LLM_BASE_URL / LLM_MODEL
"""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request


class LLMError(Exception):
    """模型调用失败。"""


def load_dotenv(path: str | None = None):
    """极简 .env 加载:KEY=VALUE 写入 os.environ(不覆盖已存在的变量)。"""
    candidates = [path] if path else [
        os.path.join(os.getcwd(), ".env"),
        os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"),
    ]
    for p in candidates:
        if not p or not os.path.isfile(p):
            continue
        try:
            with open(p, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    k, v = line.split("=", 1)
                    k, v = k.strip(), v.strip().strip('"').strip("'")
                    if k and k not in os.environ:
                        os.environ[k] = v
        except OSError:
            pass


def default_config() -> dict:
    """从环境变量读取默认配置,并对常见平台做智能默认。"""
    load_dotenv()
    api_key = (
        os.environ.get("LLM_API_KEY")
        or os.environ.get("OPENAI_API_KEY")
        or os.environ.get("DEEPSEEK_API_KEY")
    )
    base_url = os.environ.get("LLM_BASE_URL") or os.environ.get("OPENAI_BASE_URL")
    model = os.environ.get("LLM_MODEL")

    if not base_url:
        if os.environ.get("DEEPSEEK_API_KEY") and not os.environ.get("OPENAI_API_KEY"):
            base_url = "https://api.deepseek.com"
            model = model or "deepseek-flash"
        else:
            base_url = "https://api.openai.com/v1"
            model = model or "gpt-4o-mini"
    return {"api_key": api_key, "base_url": base_url, "model": model}


def chat(
    messages: list[dict],
    config: dict | None = None,
    temperature: float = 0.3,
    max_tokens: int = 3000,
    timeout: int = 120,
    retries: int = 2,
) -> str:
    """调用模型,返回 assistant 文本。

    推理型模型(如 deepseek-flash)会把部分 token 花在 reasoning 上,
    偶发正文为空,因此自动重试 retries 次。
    """
    cfg = {**default_config(), **(config or {})}
    api_key = cfg.get("api_key")
    if not api_key:
        raise LLMError("未配置 LLM_API_KEY(可用 --mock 离线演示模式)")

    base = (cfg.get("base_url") or "https://api.openai.com/v1").rstrip("/")
    url = base + "/chat/completions"
    payload = {
        "model": cfg.get("model") or "gpt-4o-mini",
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }

    last_body = ""
    budget = max_tokens
    for _ in range(retries + 1):
        payload["max_tokens"] = budget
        req = urllib.request.Request(
            url,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json", "Authorization": "Bearer " + api_key},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                body = resp.read().decode("utf-8")
        except urllib.error.HTTPError as e:
            detail = ""
            try:
                detail = e.read().decode("utf-8")[:500]
            except Exception:
                pass
            raise LLMError(f"模型接口返回 {e.code}: {detail or e.reason}") from e
        except urllib.error.URLError as e:
            raise LLMError(f"无法连接模型接口 {url}: {e.reason}") from e

        last_body = body
        try:
            data = json.loads(body)
            msg = data["choices"][0]["message"]
            finish = data["choices"][0].get("finish_reason")
        except (json.JSONDecodeError, KeyError, IndexError, TypeError) as e:
            raise LLMError(f"模型返回格式异常: {body[:300]}") from e

        content = (msg.get("content") or "").strip()
        if content:
            return content

        # 正文为空大概率是 reasoning 把预算吃光了:翻倍再试,而不是直接报错
        if finish == "length" and budget < 8000:
            budget = min(budget * 2, 8000)

    raise LLMError(f"模型连续 {retries + 1} 次返回空内容: {last_body[:300]}")


def extract_json(text: str) -> dict | list:
    """从模型输出中稳健地抽取 JSON(容忍 ```json 代码块、前后缀说明)。"""
    if not text:
        raise LLMError("模型返回为空")

    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    candidate = fence.group(1).strip() if fence else text.strip()

    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        pass

    for open_ch, close_ch in (("{", "}"), ("[", "]")):
        start = candidate.find(open_ch)
        if start == -1:
            continue
        depth = 0
        for i in range(start, len(candidate)):
            if candidate[i] == open_ch:
                depth += 1
            elif candidate[i] == close_ch:
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(candidate[start : i + 1])
                    except json.JSONDecodeError:
                        break
    raise LLMError(f"无法从模型输出解析 JSON: {text[:300]}")


def config_from_args(args) -> dict:
    """把命令行参数合并进调用配置(仅覆盖显式传了值的项)。"""
    cfg = default_config()
    if getattr(args, "api_key", None):
        cfg["api_key"] = args.api_key
    if getattr(args, "base_url", None):
        cfg["base_url"] = args.base_url
    if getattr(args, "model", None):
        cfg["model"] = args.model
    return cfg
