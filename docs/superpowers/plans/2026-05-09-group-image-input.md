# Group-Bound Image Input Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let users in a bound WeChat group send images while chatting with AI; the bot fetches the image via a Windows-side bridge that uploads to Qiniu, then feeds the public URL into a multimodal LLM call so subsequent PRD generation can reason about the picture.

**Architecture:** Add a stand-alone `vworkapi-bridge` service (FastAPI on the Windows host) that wraps `vworkApi 9001` download + Qiniu SDK upload behind a single `/fetch-image` endpoint. The backend's `wechat_gateway` recognizes `msg_type=14`, dispatches to a new `GroupImageHandler` (parallel to `GroupMessageRouter`) which calls the bridge, persists `messages.media_url`, and runs `PMAgent.chat` with the OpenAI-style multimodal message. `BaseLLM` is extended to preserve `list[dict]` content; each adapter handles vision in its own way (OpenAI passthrough, Anthropic format conversion, Claude CLI textualizes URL, Ollama discards image with a warning).

**Tech Stack:** FastAPI, SQLAlchemy 2 async, Alembic, asyncpg, httpx, qiniu-python SDK, pydantic-settings, anthropic SDK, OpenAI HTTP API.

**Spec:** `docs/superpowers/specs/2026-05-09-group-image-input-design.md`

---

## File Map

**Create:**
- `backend/alembic/versions/h2b3c4d5e6f7_add_media_to_messages.py` — DB migration
- `backend/app/services/image_bridge_client.py` — HTTP client for bridge
- `backend/app/services/group_image_handler.py` — Image-message entrypoint
- `backend/tests/e2e_image_input.py` — Backend image flow tests
- `vworkapi-bridge/pyproject.toml`
- `vworkapi-bridge/.env.example`
- `vworkapi-bridge/README.md`
- `vworkapi-bridge/app/__init__.py`
- `vworkapi-bridge/app/config.py`
- `vworkapi-bridge/app/main.py`
- `vworkapi-bridge/app/vworkapi_client.py`
- `vworkapi-bridge/app/qiniu_uploader.py`
- `vworkapi-bridge/app/tmp_storage.py`
- `vworkapi-bridge/tests/e2e_bridge.py`

**Modify:**
- `backend/app/models/message.py` — Add `media_url`, `media_type`
- `backend/app/services/project_service.py` — `add_message` accepts media kwargs
- `backend/app/config.py` — `image_bridge_url`, `image_bridge_token`, `image_bridge_timeout_seconds`
- `backend/app/llm/base.py` — Preserve `list[dict]` content
- `backend/app/llm/openai_adapter.py` — Pass-through multimodal content
- `backend/app/llm/claude_adapter.py` — Convert OpenAI→Anthropic vision format
- `backend/app/llm/claude_cli_adapter.py` — Inline image URL as text
- `backend/app/llm/ollama_adapter.py` — Warn + drop image when present
- `backend/app/agents/pm_agent.py` — `_build_messages` emits multimodal when `media_url` present
- `backend/app/gateway/wechat_gateway.py` — Branch on `msg_type=14`

---

## Pre-flight

- [ ] **Step 0: Confirm migration head**

```bash
cd /Users/gujiwei/python/superUserAI/backend && /Users/gujiwei/python/superUserAI/.venv/bin/alembic current
```
Expected: `g1a2b3c4d5e6 (head)`

If different, **stop** — Task 1 stacks on this revision.

---

## Task 1: Add `media_url` + `media_type` to `messages`

**Files:**
- Create: `backend/alembic/versions/h2b3c4d5e6f7_add_media_to_messages.py`
- Modify: `backend/app/models/message.py:11-23`

- [ ] **Step 1: Write the migration**

Create `backend/alembic/versions/h2b3c4d5e6f7_add_media_to_messages.py`:

```python
"""add media_url + media_type to messages

Revision ID: h2b3c4d5e6f7
Revises: g1a2b3c4d5e6
Create Date: 2026-05-09 12:00:00.000000

"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = 'h2b3c4d5e6f7'
down_revision: str | Sequence[str] | None = 'g1a2b3c4d5e6'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        'messages',
        sa.Column('media_url', sa.Text(), nullable=True),
    )
    op.add_column(
        'messages',
        sa.Column('media_type', sa.String(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('messages', 'media_type')
    op.drop_column('messages', 'media_url')
```

- [ ] **Step 2: Apply migration up/down/up to verify symmetry**

```bash
cd /Users/gujiwei/python/superUserAI/backend && /Users/gujiwei/python/superUserAI/.venv/bin/alembic upgrade head && /Users/gujiwei/python/superUserAI/.venv/bin/alembic downgrade -1 && /Users/gujiwei/python/superUserAI/.venv/bin/alembic upgrade head
```
Expected: 3 "Running upgrade/downgrade" log lines, last reaching `h2b3c4d5e6f7`.

- [ ] **Step 3: Update Message model**

Edit `backend/app/models/message.py`. Replace the class body with:

```python
class Message(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"))
    wechat_user_id: Mapped[str] = mapped_column(index=True)
    role: Mapped[str]
    content: Mapped[str] = mapped_column(Text)
    msg_type: Mapped[int | None]
    media_url: Mapped[str | None] = mapped_column(Text)
    media_type: Mapped[str | None]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    project: Mapped[Project] = relationship("Project", back_populates="messages")
```

- [ ] **Step 4: Sanity check imports**

```bash
/Users/gujiwei/python/superUserAI/.venv/bin/python -c "from app.models.message import Message; print(sorted(Message.__table__.columns.keys()))"
```
Expected: list contains `media_url`, `media_type`.

- [ ] **Step 5: Commit**

```bash
cd /Users/gujiwei/python/superUserAI && git add backend/alembic/versions/h2b3c4d5e6f7_*.py backend/app/models/message.py && git commit -m "feat(db): add media_url + media_type to messages"
```

---

## Task 2: Config — image bridge settings

**Files:**
- Modify: `backend/app/config.py`

- [ ] **Step 1: Append three settings**

Edit `backend/app/config.py`. Add these fields **immediately before** `claude_cli_executable`:

```python
    image_bridge_url: str = ""              # http://1.94.215.136:9100
    image_bridge_token: str = ""            # shared secret with vworkapi-bridge
    image_bridge_timeout_seconds: float = 30.0
```

- [ ] **Step 2: Verify settings load**

```bash
/Users/gujiwei/python/superUserAI/.venv/bin/python -c "from app.config import get_settings; s = get_settings(); print(repr(s.image_bridge_url), repr(s.image_bridge_token), s.image_bridge_timeout_seconds)"
```
Expected: `'' '' 30.0`

- [ ] **Step 3: Commit**

```bash
cd /Users/gujiwei/python/superUserAI && git add backend/app/config.py && git commit -m "feat(config): add image bridge settings"
```

---

## Task 3: ProjectService.add_message — accept media kwargs

**Files:**
- Modify: `backend/app/services/project_service.py:104-122`

- [ ] **Step 1: Extend signature**

Replace the existing `add_message` method with:

```python
    async def add_message(
        self,
        project_id: int,
        wechat_user_id: str,
        role: str,
        content: str,
        msg_type: int | None = None,
        media_url: str | None = None,
        media_type: str | None = None,
    ) -> Message:
        message = Message(
            project_id=project_id,
            wechat_user_id=wechat_user_id,
            role=role,
            content=content,
            msg_type=msg_type,
            media_url=media_url,
            media_type=media_type,
        )
        self.db.add(message)
        await self.db.flush()
        return message
```

- [ ] **Step 2: Smoke test**

```bash
/Users/gujiwei/python/superUserAI/.venv/bin/python -c "
import inspect
from app.services.project_service import ProjectService
sig = inspect.signature(ProjectService.add_message)
assert 'media_url' in sig.parameters and 'media_type' in sig.parameters
print('add_message media kwargs ok')
"
```
Expected: `add_message media kwargs ok`

- [ ] **Step 3: Commit**

```bash
cd /Users/gujiwei/python/superUserAI && git add backend/app/services/project_service.py && git commit -m "feat(project_service): add_message accepts media_url/media_type"
```

---

## Task 4: BaseLLM — preserve `list[dict]` content

**Files:**
- Modify: `backend/app/llm/base.py:29-65`

The current `_normalize_messages` flattens list content to a string and discards image parts. Add a parallel `_normalize_messages_keep_multimodal` that preserves the structure when content is a list, while still coercing string-only content. Keep the legacy method around for adapters that don't yet support vision.

- [ ] **Step 1: Add new method**

Edit `backend/app/llm/base.py`. After `_normalize_messages` (currently ending at line 65), append a new classmethod:

```python
    @classmethod
    def _normalize_messages_keep_multimodal(
        cls,
        messages: Sequence[Mapping[str, Any]],
    ) -> list[dict[str, Any]]:
        """Like _normalize_messages but preserves list[dict] content (for vision)."""
        normalized: list[dict[str, Any]] = []
        for message in messages:
            role = str(message.get("role", "user"))
            content = message.get("content", "")
            if isinstance(content, list):
                # Validate each part — keep only known shapes.
                clean_parts: list[dict[str, Any]] = []
                for part in content:
                    if isinstance(part, str):
                        clean_parts.append({"type": "text", "text": part})
                        continue
                    if not isinstance(part, dict):
                        continue
                    ptype = part.get("type")
                    if ptype == "text" and isinstance(part.get("text"), str):
                        clean_parts.append({"type": "text", "text": part["text"]})
                    elif ptype == "image_url":
                        url_obj = part.get("image_url") or {}
                        url = url_obj.get("url") if isinstance(url_obj, dict) else None
                        if isinstance(url, str) and url:
                            clean_parts.append({
                                "type": "image_url",
                                "image_url": {"url": url},
                            })
                if clean_parts:
                    normalized.append({"role": role, "content": clean_parts})
                else:
                    # All parts dropped — fall back to empty string.
                    normalized.append({"role": role, "content": ""})
            else:
                normalized.append({
                    "role": role,
                    "content": cls._coerce_content(content),
                })
        return normalized

    @staticmethod
    def _has_image_content(message: Mapping[str, Any]) -> bool:
        content = message.get("content")
        if not isinstance(content, list):
            return False
        return any(
            isinstance(p, dict) and p.get("type") == "image_url"
            for p in content
        )
```

- [ ] **Step 2: Smoke test**

```bash
/Users/gujiwei/python/superUserAI/.venv/bin/python -c "
from app.llm.base import BaseLLM
msgs = [
    {'role': 'user', 'content': 'hi'},
    {'role': 'user', 'content': [
        {'type': 'text', 'text': 'see this'},
        {'type': 'image_url', 'image_url': {'url': 'https://x.com/a.jpg'}},
    ]},
]
out = BaseLLM._normalize_messages_keep_multimodal(msgs)
assert out[0] == {'role': 'user', 'content': 'hi'}
assert out[1]['content'][1]['type'] == 'image_url'
assert BaseLLM._has_image_content(msgs[1])
assert not BaseLLM._has_image_content(msgs[0])
print('multimodal normalization ok')
"
```
Expected: `multimodal normalization ok`

- [ ] **Step 3: Commit**

```bash
cd /Users/gujiwei/python/superUserAI && git add backend/app/llm/base.py && git commit -m "feat(llm/base): add multimodal-preserving message normalizer"
```

---

## Task 5: OpenAIAdapter — pass through multimodal

**Files:**
- Modify: `backend/app/llm/openai_adapter.py:34-69`

- [ ] **Step 1: Switch chat() to multimodal normalizer**

Edit `backend/app/llm/openai_adapter.py`. Replace `chat` and `stream_chat` payload construction with the multimodal-aware version:

In `chat`:
```python
    async def chat(
        self,
        messages: Sequence[Mapping[str, Any]],
        **kwargs: Any,
    ) -> LLMResponse:
        payload = {
            "model": self.model,
            "messages": self._normalize_messages_keep_multimodal(messages),
            "stream": False,
            **kwargs,
        }
        response = await self._client.post(self._endpoint, json=payload)
        response.raise_for_status()

        data = response.json()
        choice = (data.get("choices") or [{}])[0]
        message = choice.get("message") or {}

        return LLMResponse(
            content=self._coerce_content(message.get("content", "")),
            model=data.get("model", self.model),
            finish_reason=choice.get("finish_reason"),
            raw=data,
        )
```

In `stream_chat` (only the payload line changes):
```python
        payload = {
            "model": self.model,
            "messages": self._normalize_messages_keep_multimodal(messages),
            "stream": True,
            **kwargs,
        }
```

- [ ] **Step 2: Smoke test the adapter still constructs valid payloads**

```bash
/Users/gujiwei/python/superUserAI/.venv/bin/python -c "
from app.llm.openai_adapter import OpenAIAdapter
adapter = OpenAIAdapter(api_key='test')
msgs = [{'role': 'user', 'content': [
    {'type': 'text', 'text': 'hi'},
    {'type': 'image_url', 'image_url': {'url': 'https://x.com/a.jpg'}},
]}]
norm = adapter._normalize_messages_keep_multimodal(msgs)
assert norm[0]['content'][1]['type'] == 'image_url'
print('openai multimodal payload ok')
"
```
Expected: `openai multimodal payload ok`

- [ ] **Step 3: Commit**

```bash
cd /Users/gujiwei/python/superUserAI && git add backend/app/llm/openai_adapter.py && git commit -m "feat(llm/openai): pass through multimodal content"
```

---

## Task 6: ClaudeAdapter — convert OpenAI→Anthropic vision format

**Files:**
- Modify: `backend/app/llm/claude_adapter.py:42-68`

Anthropic format uses `{"type":"image","source":{"type":"url","url":"..."}}`. Convert from OpenAI's `{"type":"image_url","image_url":{"url":"..."}}` inside `_prepare_messages`.

- [ ] **Step 1: Replace `_prepare_messages` to handle multimodal content**

Edit `backend/app/llm/claude_adapter.py`. Replace `_prepare_messages` with:

```python
    @staticmethod
    def _convert_content_to_anthropic(content: Any) -> Any:
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            blocks: list[dict[str, Any]] = []
            for part in content:
                if not isinstance(part, dict):
                    continue
                ptype = part.get("type")
                if ptype == "text":
                    text = part.get("text")
                    if isinstance(text, str) and text:
                        blocks.append({"type": "text", "text": text})
                elif ptype == "image_url":
                    url_obj = part.get("image_url") or {}
                    url = url_obj.get("url") if isinstance(url_obj, dict) else None
                    if isinstance(url, str) and url:
                        blocks.append({
                            "type": "image",
                            "source": {"type": "url", "url": url},
                        })
            return blocks if blocks else ""
        return ""

    def _prepare_messages(
        self,
        messages: Sequence[Mapping[str, Any]],
    ) -> tuple[str | None, list[dict[str, Any]]]:
        system_parts: list[str] = []
        claude_messages: list[dict[str, Any]] = []

        for message in self._normalize_messages_keep_multimodal(messages):
            role = message["role"]
            content = message["content"]

            if role == "system":
                # System prompts are always plain text.
                if isinstance(content, list):
                    text = "".join(
                        p.get("text", "") for p in content
                        if isinstance(p, dict) and p.get("type") == "text"
                    )
                    if text:
                        system_parts.append(text)
                elif content:
                    system_parts.append(content)
                continue

            converted = self._convert_content_to_anthropic(content)
            if role == "assistant":
                claude_messages.append({"role": "assistant", "content": converted})
            else:
                claude_messages.append({"role": "user", "content": converted})

        if not claude_messages:
            claude_messages.append({"role": "user", "content": " "})

        system_prompt = "\n\n".join(system_parts) or None
        return system_prompt, claude_messages
```

- [ ] **Step 2: Smoke test conversion**

```bash
/Users/gujiwei/python/superUserAI/.venv/bin/python -c "
from app.llm.claude_adapter import ClaudeAdapter
result = ClaudeAdapter._convert_content_to_anthropic([
    {'type': 'text', 'text': 'hi'},
    {'type': 'image_url', 'image_url': {'url': 'https://x.com/a.jpg'}},
])
assert result == [
    {'type': 'text', 'text': 'hi'},
    {'type': 'image', 'source': {'type': 'url', 'url': 'https://x.com/a.jpg'}},
], result
assert ClaudeAdapter._convert_content_to_anthropic('plain') == 'plain'
print('claude conversion ok')
"
```
Expected: `claude conversion ok`

- [ ] **Step 3: Commit**

```bash
cd /Users/gujiwei/python/superUserAI && git add backend/app/llm/claude_adapter.py && git commit -m "feat(llm/claude): convert OpenAI multimodal to Anthropic format"
```

---

## Task 7: ClaudeCLIAdapter — inline image URL as text

**Files:**
- Modify: `backend/app/llm/claude_cli_adapter.py:36-83`

The CLI's headless mode (`-p`) doesn't reliably accept image attachments across versions. Strategy: turn `image_url` parts into a `[image: <URL>]` token in the text. The CLI proxy may or may not actually fetch it, but the URL is preserved verbatim so a future CLI upgrade gets richer behavior for free.

- [ ] **Step 1: Replace `chat` body**

Edit `backend/app/llm/claude_cli_adapter.py`. Replace the `chat` method with:

```python
    async def chat(
        self,
        messages: Sequence[Mapping[str, Any]],
        **kwargs: Any,
    ) -> LLMResponse:
        # Use multimodal-preserving normalizer first, then flatten image_url parts
        # into "[image: <URL>]" tokens before handing to the legacy CLI pipeline.
        flattened = self._flatten_to_text(
            self._normalize_messages_keep_multimodal(messages)
        )
        base_system, conversation = self._split_system(flattened)
        history, current_user = self._partition_last_user(conversation)
        composed_system = self._compose_system(base_system, history)

        cmd = [
            self._executable,
            "-p", current_user or "(空消息)",
            "--output-format", "text",
            "--tools", "",
        ]
        if composed_system:
            cmd += ["--append-system-prompt", composed_system]

        logger.info("Invoking claude CLI for PM chat (history=%d msgs)", len(history))

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout_b, stderr_b = await asyncio.wait_for(
                proc.communicate(), timeout=self._timeout
            )
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            raise RuntimeError("Claude CLI timed out") from None

        if proc.returncode != 0:
            tail = stderr_b.decode("utf-8", errors="replace").strip()[-1000:]
            raise RuntimeError(
                f"Claude CLI exited with {proc.returncode}: {tail or '(no stderr)'}"
            )

        return LLMResponse(
            content=stdout_b.decode("utf-8", errors="replace").strip(),
            model=self.model,
            finish_reason="stop",
            raw=None,
        )
```

- [ ] **Step 2: Add `_flatten_to_text` helper at the bottom of the class**

After `_compose_system` (currently last static method around line 125), add:

```python
    @staticmethod
    def _flatten_to_text(messages: list[dict[str, Any]]) -> list[dict[str, str]]:
        """Turn multimodal content blocks into plain text with [image: URL] tokens."""
        out: list[dict[str, str]] = []
        for m in messages:
            content = m.get("content", "")
            if isinstance(content, list):
                parts: list[str] = []
                for p in content:
                    if not isinstance(p, dict):
                        continue
                    if p.get("type") == "text" and isinstance(p.get("text"), str):
                        parts.append(p["text"])
                    elif p.get("type") == "image_url":
                        url = (p.get("image_url") or {}).get("url")
                        if isinstance(url, str) and url:
                            parts.append(f"[image: {url}]")
                out.append({"role": m["role"], "content": "\n".join(parts)})
            else:
                out.append({"role": m["role"], "content": str(content)})
        return out
```

Also update the imports at the top of `claude_cli_adapter.py` — replace `from typing import Any` with:

```python
from typing import Any
```

(this is the same; just confirm `Any` is imported — it already is at line 17.)

- [ ] **Step 3: Smoke test**

```bash
/Users/gujiwei/python/superUserAI/.venv/bin/python -c "
from app.llm.claude_cli_adapter import ClaudeCLIAdapter
flat = ClaudeCLIAdapter._flatten_to_text([
    {'role': 'user', 'content': [
        {'type': 'text', 'text': 'see this'},
        {'type': 'image_url', 'image_url': {'url': 'https://x/a.jpg'}},
    ]},
    {'role': 'assistant', 'content': 'noted'},
])
assert flat[0]['content'] == 'see this\n[image: https://x/a.jpg]'
assert flat[1]['content'] == 'noted'
print('claude_cli flatten ok')
"
```
Expected: `claude_cli flatten ok`

- [ ] **Step 4: Commit**

```bash
cd /Users/gujiwei/python/superUserAI && git add backend/app/llm/claude_cli_adapter.py && git commit -m "feat(llm/claude_cli): inline image URL as [image: ...] token"
```

---

## Task 8: OllamaAdapter — drop image with warning

**Files:**
- Modify: `backend/app/llm/ollama_adapter.py:27-78`

YAGNI: don't try to do "image-to-description" fallback in v1; just drop image parts and log a warning. Add a follow-up TODO in the spec if Ollama-with-vision becomes a real need.

- [ ] **Step 1: Add logger + drop helper**

Edit `backend/app/llm/ollama_adapter.py`. Add at the top after imports:

```python
import logging

logger = logging.getLogger(__name__)
```

Add this method to `OllamaAdapter`:

```python
    @classmethod
    def _strip_images(
        cls,
        messages: Sequence[Mapping[str, Any]],
    ) -> list[dict[str, str]]:
        normalized = cls._normalize_messages_keep_multimodal(messages)
        out: list[dict[str, str]] = []
        for m in normalized:
            content = m["content"]
            if isinstance(content, list):
                texts = [
                    p.get("text", "") for p in content
                    if isinstance(p, dict) and p.get("type") == "text"
                ]
                if any(
                    isinstance(p, dict) and p.get("type") == "image_url"
                    for p in content
                ):
                    logger.warning(
                        "ollama_adapter: dropping image parts (provider lacks vision); "
                        "consider switching llm_provider for image-input flows"
                    )
                out.append({"role": m["role"], "content": "\n".join(texts)})
            else:
                out.append({"role": m["role"], "content": content})
        return out
```

- [ ] **Step 2: Switch `chat`/`stream_chat` to use the strip helper**

Replace the `messages=` line in both methods:
```python
            "messages": self._strip_images(messages),
```

- [ ] **Step 3: Smoke test**

```bash
/Users/gujiwei/python/superUserAI/.venv/bin/python -c "
from app.llm.ollama_adapter import OllamaAdapter
out = OllamaAdapter._strip_images([
    {'role': 'user', 'content': [
        {'type': 'text', 'text': 'see this'},
        {'type': 'image_url', 'image_url': {'url': 'https://x/a.jpg'}},
    ]},
])
assert out[0]['content'] == 'see this'
print('ollama strip ok')
"
```
Expected: `ollama strip ok` (plus a `WARNING` log line).

- [ ] **Step 4: Commit**

```bash
cd /Users/gujiwei/python/superUserAI && git add backend/app/llm/ollama_adapter.py && git commit -m "feat(llm/ollama): drop image parts with warning (no vision fallback in v1)"
```

---

## Task 9: PMAgent — emit multimodal when `media_url` present

**Files:**
- Modify: `backend/app/agents/pm_agent.py:70-99`

- [ ] **Step 1: Replace `_build_messages`**

Edit `backend/app/agents/pm_agent.py`. Replace `_build_messages` with:

```python
    def _build_messages(
        self,
        project: Project,
        repo: Repo,
        history: Sequence[Message],
    ) -> list[dict[str, Any]]:
        messages: list[dict[str, Any]] = [
            {
                "role": "system",
                "content": SYSTEM_PROMPT.format(
                    project_title=project.title,
                    repo_name=repo.name,
                ),
            }
        ]
        for item in history:
            role = self._normalize_role(item.role)
            if getattr(item, "media_url", None):
                content_parts: list[dict[str, Any]] = []
                text = (item.content or "").strip() or "[图片]"
                content_parts.append({"type": "text", "text": text})
                content_parts.append({
                    "type": "image_url",
                    "image_url": {"url": item.media_url},
                })
                messages.append({"role": role, "content": content_parts})
            else:
                messages.append({"role": role, "content": item.content})
        return messages
```

Also update the import at the top of `pm_agent.py`:

```python
from typing import Any
```

(insert after `from collections.abc import Sequence`).

- [ ] **Step 2: Smoke test**

```bash
/Users/gujiwei/python/superUserAI/.venv/bin/python -c "
from dataclasses import dataclass
from app.agents.pm_agent import PMAgent

@dataclass
class P: title='t'
@dataclass
class R: name='r'
@dataclass
class M: role='user'; content='hello'; media_url='https://x/a.jpg'

agent = PMAgent.__new__(PMAgent)
out = agent._build_messages(P(), R(), [M()])
assert out[1]['content'][1]['image_url']['url'] == 'https://x/a.jpg'
print('pm_agent multimodal build ok')
"
```
Expected: `pm_agent multimodal build ok`

- [ ] **Step 3: Commit**

```bash
cd /Users/gujiwei/python/superUserAI && git add backend/app/agents/pm_agent.py && git commit -m "feat(pm_agent): build multimodal messages from media_url history"
```

---

## Task 10: ImageBridgeClient — backend HTTP client for the bridge

**Files:**
- Create: `backend/app/services/image_bridge_client.py`

- [ ] **Step 1: Implement client + error type**

Create `backend/app/services/image_bridge_client.py`:

```python
from __future__ import annotations

import logging
from dataclasses import dataclass

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)


@dataclass
class BridgeFetchResult:
    url: str
    media_type: str
    size: int


class BridgeError(Exception):
    """Raised when the bridge call fails. `short` is a user-facing 1-line summary."""

    def __init__(self, short: str, detail: str = "") -> None:
        super().__init__(detail or short)
        self.short = short
        self.detail = detail


class ImageBridgeClient:
    def __init__(self) -> None:
        self.settings = get_settings()

    async def fetch_image(
        self,
        cdn_key: str,
        aes_key: str,
        size: int,
        img_type: int,
        msg_id: str,
    ) -> BridgeFetchResult:
        if not self.settings.image_bridge_url:
            raise BridgeError(short="未配置 bridge", detail="image_bridge_url is empty")

        url = self.settings.image_bridge_url.rstrip("/") + "/fetch-image"
        headers = {"Content-Type": "application/json"}
        if self.settings.image_bridge_token:
            headers["X-Bridge-Token"] = self.settings.image_bridge_token

        payload = {
            "cdn_key": cdn_key,
            "aes_key": aes_key,
            "size": size,
            "img_type": img_type,
            "msg_id": msg_id,
        }

        try:
            async with httpx.AsyncClient(
                timeout=self.settings.image_bridge_timeout_seconds
            ) as client:
                response = await client.post(url, json=payload, headers=headers)
        except httpx.TimeoutException as exc:
            raise BridgeError(short="bridge 超时", detail=str(exc)) from exc
        except httpx.HTTPError as exc:
            raise BridgeError(short="bridge 不可达", detail=str(exc)) from exc

        if response.status_code == 401:
            raise BridgeError(short="bridge token 错误", detail=response.text[:200])
        if response.status_code == 413:
            raise BridgeError(short="图太大", detail=response.text[:200])
        if response.status_code >= 500:
            raise BridgeError(
                short="bridge 内部错误",
                detail=f"HTTP {response.status_code}: {response.text[:200]}",
            )
        if response.status_code != 200:
            raise BridgeError(
                short=f"bridge HTTP {response.status_code}",
                detail=response.text[:200],
            )

        data = response.json()
        if not isinstance(data, dict) or "url" not in data:
            raise BridgeError(short="bridge 返回格式异常", detail=str(data)[:200])

        return BridgeFetchResult(
            url=data["url"],
            media_type=data.get("media_type", "image/jpeg"),
            size=int(data.get("size", size)),
        )
```

- [ ] **Step 2: Smoke test (no bridge running)**

```bash
/Users/gujiwei/python/superUserAI/.venv/bin/python -c "
import asyncio
from app.services.image_bridge_client import ImageBridgeClient, BridgeError
async def go():
    c = ImageBridgeClient()
    try:
        await c.fetch_image('a', 'b', 1, 2, 'm1')
    except BridgeError as e:
        print('expected error:', e.short)
asyncio.run(go())
"
```
Expected: `expected error: 未配置 bridge`

- [ ] **Step 3: Commit**

```bash
cd /Users/gujiwei/python/superUserAI && git add backend/app/services/image_bridge_client.py && git commit -m "feat(bridge_client): backend HTTP client with typed errors"
```

---

## Task 11: GroupImageHandler — image dispatch

**Files:**
- Create: `backend/app/services/group_image_handler.py`

- [ ] **Step 1: Implement handler**

Create `backend/app/services/group_image_handler.py`:

```python
from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.pm_agent import has_ready_marker, strip_ready_marker
from app.config import get_settings
from app.gateway.wechat_client import WeChatClient
from app.services.image_bridge_client import BridgeError, ImageBridgeClient
from app.services.message_handler import MessageHandler
from app.services.project_service import ProjectService
from app.services.session_manager import SessionManager
from shared.constants import ProjectStatus

logger = logging.getLogger(__name__)


class GroupImageHandler:
    def __init__(
        self,
        db: AsyncSession,
        wechat: WeChatClient,
        bridge_client: ImageBridgeClient | None = None,
        llm=None,
    ) -> None:
        self.db = db
        self.wechat = wechat
        self.settings = get_settings()
        self.bridge = bridge_client or ImageBridgeClient()
        self.session_manager = SessionManager(db)
        self.project_service = ProjectService(db)
        # MessageHandler also wires PMAgent for us
        self.handler = MessageHandler(db, wechat)
        if llm is not None:
            # Allow tests to inject a stub LLM
            self.handler.pm_agent.llm = llm

    async def try_handle(
        self,
        wechat_user_id: str,
        group_id: str,
        image_meta: dict[str, Any],
        msg_id: str,
    ) -> bool:
        """Returns True iff the group is bound and the image was attempted."""
        repo = await self.project_service.get_repo_by_wechat_group_id(group_id)
        if repo is None:
            return False

        try:
            await self._handle_bound(repo, wechat_user_id, group_id, image_meta, msg_id)
            await self.db.commit()
        except Exception:
            logger.exception(
                "group_image handler failed group=%s repo=%s sender=%s msg_id=%s",
                group_id, repo.id, wechat_user_id, msg_id,
            )
            await self.db.rollback()
        return True

    async def _handle_bound(
        self,
        repo,
        wechat_user_id: str,
        group_id: str,
        image_meta: dict[str, Any],
        msg_id: str,
    ) -> None:
        # 1. Resolve user (auto-activate same as text path).
        user, just_created = await self.session_manager.get_or_create_user_for_bound_group(
            wechat_user_id,
            auto_activate=self.settings.group_bound_auto_activate,
        )
        if just_created:
            logger.info(
                "auto_activate user=%s via bound_group=%s repo=%s (image)",
                wechat_user_id, group_id, repo.id,
            )
        if user.role != "admin" and not user.is_active:
            return  # whitelist gate, silent

        # 2. Must have an active drafting project.
        session = await self.session_manager.get_session(user)
        if session.active_project_id is None:
            return
        project = await self.project_service.get_project(session.active_project_id)
        if project is None or project.status != ProjectStatus.DRAFTING.value:
            return

        # 3. Validate image_meta shape.
        try:
            cdn_key = str(image_meta["cdn_key"])
            aes_key = str(image_meta["aes_key"])
            size = int(image_meta["size"])
            img_type = int(image_meta.get("img_type", 2))
        except (KeyError, TypeError, ValueError):
            logger.warning("group_image bad meta group=%s msg_id=%s meta=%s",
                           group_id, msg_id, image_meta)
            return

        # 4. Fetch via bridge.
        try:
            result = await self.bridge.fetch_image(
                cdn_key=cdn_key, aes_key=aes_key, size=size,
                img_type=img_type, msg_id=msg_id,
            )
        except BridgeError as exc:
            logger.warning(
                "group_image bridge fail group=%s msg_id=%s short=%s detail=%s",
                group_id, msg_id, exc.short, exc.detail,
            )
            await self._reply_at(
                group_id, wechat_user_id,
                f"@{wechat_user_id} 刚才那张图我读不到（{exc.short}），"
                "能用文字补充一下吗？",
            )
            return

        # 5. Persist image as a message row.
        await self.project_service.add_message(
            project.id, wechat_user_id, "user", "[图片]",
            media_url=result.url, media_type=result.media_type,
        )

        # 6. Run PMAgent over full history (now includes the image).
        history = await self.project_service.get_messages(project.id)
        ai_reply = await self.handler.pm_agent.chat(project, repo, history, "")
        await self.project_service.add_message(
            project.id, wechat_user_id, "assistant", ai_reply,
        )

        # 7. Send reply with [READY_TO_CONFIRM] strip.
        if has_ready_marker(ai_reply):
            cleaned = strip_ready_marker(ai_reply)
            hint = self.handler.pm_agent.build_confirm_hint()
            ai_reply = (cleaned + hint) if cleaned else hint.lstrip()

        await self._reply_at(group_id, wechat_user_id, f"@{wechat_user_id} {ai_reply}")

    async def _reply_at(self, group_id: str, sender_id: str, msg: str) -> None:
        try:
            await self.wechat.send_at_group(group_id, [sender_id], msg)
        except Exception:
            logger.exception(
                "group_image send_at_group failed group=%s sender=%s",
                group_id, sender_id,
            )
```

- [ ] **Step 2: Import smoke test**

```bash
/Users/gujiwei/python/superUserAI/.venv/bin/python -c "
from app.services.group_image_handler import GroupImageHandler
import inspect
sig = inspect.signature(GroupImageHandler.try_handle)
assert {'wechat_user_id','group_id','image_meta','msg_id'} <= set(sig.parameters)
print('group_image_handler import ok')
"
```
Expected: `group_image_handler import ok`

- [ ] **Step 3: Commit**

```bash
cd /Users/gujiwei/python/superUserAI && git add backend/app/services/group_image_handler.py && git commit -m "feat(group_image_handler): image dispatch via bridge + PMAgent"
```

---

## Task 12: wechat_gateway — branch on `msg_type=14`

**Files:**
- Modify: `backend/app/gateway/wechat_gateway.py`

- [ ] **Step 1: Replace `receive_message` body**

Edit `backend/app/gateway/wechat_gateway.py`. Replace the existing `receive_message` function with:

```python
async def _process_bound_group_image_async(
    user_id: str,
    group_id: str,
    image_meta: dict,
    msg_id: str,
) -> None:
    from app.services.group_image_handler import GroupImageHandler

    async with AsyncSessionLocal() as db:
        try:
            handler = GroupImageHandler(db, wechat)
            await handler.try_handle(user_id, group_id, image_meta, msg_id)
        except Exception:
            logger.exception(
                "group_image processing failed user_id=%s group_id=%s msg_id=%s",
                user_id, group_id, msg_id,
            )


@router.post("/msg")
async def receive_message(
    message: VWorkMessage,
    background_tasks: BackgroundTasks,
) -> dict[str, str]:
    if message.is_self_msg == 1:
        logger.debug("Ignoring self message: msg_id=%s", message.msg_id)
        return {"status": "ok"}

    # Image branch: only groups, only when content is the expected dict shape.
    if message.msg_type == VWorkMsgType.IMAGE.value:
        if not message.sender:
            return {"status": "ok"}  # ignore private images
        if not isinstance(message.content, dict):
            logger.warning("image msg with non-dict content: msg_id=%s", message.msg_id)
            return {"status": "ok"}
        sender_id = message.sender
        group_id: str | None = message.user_id
        logger.info(
            "Received WeChat image: msg_id=%s user=%s group=%s",
            message.msg_id, sender_id, group_id,
        )
        background_tasks.add_task(
            _process_bound_group_image_async,
            sender_id, group_id, message.content, message.msg_id,
        )
        return {"status": "ok"}

    if message.msg_type != VWorkMsgType.TEXT.value:
        logger.info(
            "Ignoring non-text non-image message: msg_id=%s msg_type=%s",
            message.msg_id, message.msg_type,
        )
        return {"status": "ok"}

    if not isinstance(message.content, str):
        logger.warning("Ignoring text payload with non-string content: msg_id=%s", message.msg_id)
        return {"status": "ok"}

    is_group = bool(message.sender)
    if is_group:
        at_list = message.at_list or []
        if message.self_user_id not in at_list and "notify@all" not in at_list:
            logger.debug(
                "Ignoring group message without @bot: msg_id=%s group_id=%s sender=%s",
                message.msg_id, message.user_id, message.sender,
            )
            return {"status": "ok"}
        sender_id = message.sender
        group_id = message.user_id
        content_text = _strip_at_prefix(message.content)
    else:
        sender_id = message.user_id
        group_id = None
        content_text = message.content

    if group_id is not None:
        logger.info(
            "Received WeChat group message: msg_id=%s user=%s group=%s",
            message.msg_id, sender_id, group_id,
        )
        background_tasks.add_task(
            _process_bound_group_message_async, sender_id, group_id, content_text
        )
        return {"status": "ok"}

    command = parse_command(content_text)
    logger.info(
        "Received WeChat message: msg_id=%s user=%s group=%s command=%s",
        message.msg_id, sender_id, group_id, command.type,
    )
    background_tasks.add_task(_process_message_async, sender_id, command, group_id)
    return {"status": "ok"}
```

- [ ] **Step 2: Run group_chat regression**

```bash
/Users/gujiwei/python/superUserAI/.venv/bin/python /Users/gujiwei/python/superUserAI/backend/tests/e2e_group_chat.py
```
Expected: 3 "ok" lines + `all e2e_group_chat checks passed`

- [ ] **Step 3: Commit**

```bash
cd /Users/gujiwei/python/superUserAI && git add backend/app/gateway/wechat_gateway.py && git commit -m "feat(gateway): branch image messages to GroupImageHandler"
```

---

## Task 13: vworkapi-bridge — project skeleton

**Files:**
- Create: `vworkapi-bridge/pyproject.toml`
- Create: `vworkapi-bridge/.env.example`
- Create: `vworkapi-bridge/README.md`
- Create: `vworkapi-bridge/app/__init__.py`
- Create: `vworkapi-bridge/app/config.py`

- [ ] **Step 1: Project metadata**

Create `vworkapi-bridge/pyproject.toml`:

```toml
[build-system]
requires = ["setuptools>=69.0"]
build-backend = "setuptools.build_meta"

[project]
name = "vworkapi-bridge"
version = "0.1.0"
requires-python = ">=3.10"
dependencies = [
    "fastapi>=0.110,<1.0",
    "uvicorn[standard]>=0.29,<1.0",
    "httpx>=0.27,<1.0",
    "qiniu>=7.13,<8.0",
    "pydantic-settings>=2.0,<3.0",
]

[tool.setuptools.packages.find]
where = ["."]
include = ["app*"]
```

- [ ] **Step 2: .env.example**

Create `vworkapi-bridge/.env.example`:

```
QINIU_AK=
QINIU_SK=
QINIU_BUCKET=
QINIU_DOMAIN=https://cdn.example.qiniu.com
IMAGE_BRIDGE_TOKEN=
VWORKAPI_HOST=127.0.0.1
VWORKAPI_PORT=8989
TMP_DIR=C:\\tmp\\superuserai-images
MAX_IMAGE_BYTES=10485760
```

- [ ] **Step 3: Config module**

Create `vworkapi-bridge/app/__init__.py` (empty file) and `vworkapi-bridge/app/config.py`:

```python
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parents[1] / ".env",
        env_file_encoding="utf-8",
    )

    qiniu_ak: str = ""
    qiniu_sk: str = ""
    qiniu_bucket: str = ""
    qiniu_domain: str = ""
    image_bridge_token: str = ""
    vworkapi_host: str = "127.0.0.1"
    vworkapi_port: int = 8989
    tmp_dir: str = "/tmp/superuserai-images"
    max_image_bytes: int = 10 * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    return Settings()
```

- [ ] **Step 4: README**

Create `vworkapi-bridge/README.md`:

```markdown
# vworkapi-bridge

A small FastAPI service that runs alongside vworkApi on the Windows host.
Exposes one endpoint `POST /fetch-image` that:

1. Calls local vworkApi (`type=9001`) to download an image to a temp file.
2. Uploads the file to Qiniu via the SDK.
3. Returns the public CDN URL to the caller.

## Install (Windows)

```bat
:: Python 3.10+ required
python -m venv .venv
.venv\Scripts\activate
pip install -e .
copy .env.example .env
notepad .env   :: fill in QINIU_* and IMAGE_BRIDGE_TOKEN
```

## Run

```bat
uvicorn app.main:app --host 0.0.0.0 --port 9100
```

For long-running deployment, register as a Windows service via `nssm`:

```bat
nssm install vworkapi-bridge "C:\path\to\.venv\Scripts\uvicorn.exe" ^
  "app.main:app --host 0.0.0.0 --port 9100"
nssm start vworkapi-bridge
```

## Auth

Every request must include `X-Bridge-Token: <IMAGE_BRIDGE_TOKEN>` matching the
.env value.
```

- [ ] **Step 5: Smoke test config loads**

```bash
cd /Users/gujiwei/python/superUserAI/vworkapi-bridge && /Users/gujiwei/python/superUserAI/.venv/bin/pip install -e . > /dev/null && /Users/gujiwei/python/superUserAI/.venv/bin/python -c "from app.config import get_settings; print('config ok', get_settings().vworkapi_port)"
```
Expected: `config ok 8989`

- [ ] **Step 6: Commit**

```bash
cd /Users/gujiwei/python/superUserAI && git add vworkapi-bridge/ && git commit -m "feat(bridge): scaffold vworkapi-bridge project"
```

---

## Task 14: vworkapi-bridge — core modules

**Files:**
- Create: `vworkapi-bridge/app/vworkapi_client.py`
- Create: `vworkapi-bridge/app/qiniu_uploader.py`
- Create: `vworkapi-bridge/app/tmp_storage.py`

- [ ] **Step 1: tmp_storage**

Create `vworkapi-bridge/app/tmp_storage.py`:

```python
from __future__ import annotations

import os
import re
from pathlib import Path

_SAFE_RE = re.compile(r"[^A-Za-z0-9_.-]")


def _safe_name(s: str) -> str:
    return _SAFE_RE.sub("_", s)[:64]


class TmpStorage:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def allocate(self, msg_id: str) -> Path:
        name = _safe_name(msg_id) + ".jpg"
        return self.root / name

    def cleanup(self, path: Path) -> None:
        try:
            if path.exists():
                os.remove(path)
        except Exception:
            pass  # leave behind; cron/manual cleanup if needed
```

- [ ] **Step 2: vworkapi_client**

Create `vworkapi-bridge/app/vworkapi_client.py`:

```python
from __future__ import annotations

import httpx


class VWorkApiError(Exception):
    pass


class VWorkApiClient:
    def __init__(self, host: str, port: int) -> None:
        self.url = f"http://{host}:{port}/api"

    async def download_image(
        self,
        cdn_key: str,
        aes_key: str,
        size: int,
        img_type: int,
        save_path: str,
    ) -> None:
        payload = {
            "type": 9001,
            "cdn_key": cdn_key,
            "aes_key": aes_key,
            "size": size,
            "img_type": img_type,
            "save_path": save_path,
        }
        async with httpx.AsyncClient(timeout=60.0) as client:
            try:
                response = await client.post(self.url, json=payload)
            except httpx.HTTPError as exc:
                raise VWorkApiError(f"http error: {exc}") from exc

        if response.status_code != 200:
            raise VWorkApiError(f"vworkapi HTTP {response.status_code}: {response.text[:200]}")

        data = response.json()
        if data.get("errno") != 0:
            raise VWorkApiError(
                f"vworkapi errno={data.get('errno')} errmsg={data.get('errmsg')}"
            )
```

- [ ] **Step 3: qiniu_uploader**

Create `vworkapi-bridge/app/qiniu_uploader.py`:

```python
from __future__ import annotations

import asyncio
import hashlib
import imghdr
import logging
from pathlib import Path

from qiniu import Auth, put_file  # type: ignore

logger = logging.getLogger(__name__)


class QiniuUploadError(Exception):
    pass


class QiniuUploader:
    def __init__(self, ak: str, sk: str, bucket: str, domain: str) -> None:
        if not (ak and sk and bucket and domain):
            raise QiniuUploadError("qiniu credentials/bucket/domain not configured")
        self.bucket = bucket
        self.domain = domain.rstrip("/")
        self.auth = Auth(ak, sk)

    @staticmethod
    def _sha256(path: Path) -> str:
        h = hashlib.sha256()
        with path.open("rb") as f:
            while True:
                chunk = f.read(1024 * 64)
                if not chunk:
                    break
                h.update(chunk)
        return h.hexdigest()

    @staticmethod
    def _detect_media_type(path: Path) -> tuple[str, str]:
        kind = imghdr.what(path) or "jpeg"
        ext_map = {"jpeg": "jpg", "png": "png", "gif": "gif", "webp": "webp"}
        ext = ext_map.get(kind, "jpg")
        media_type = f"image/{kind if kind != 'jpg' else 'jpeg'}"
        return ext, media_type

    async def upload(self, path: Path, key_prefix: str = "sua/") -> tuple[str, str]:
        if not path.exists():
            raise QiniuUploadError(f"file not found: {path}")

        loop = asyncio.get_running_loop()
        ext, media_type = await loop.run_in_executor(None, self._detect_media_type, path)
        sha = await loop.run_in_executor(None, self._sha256, path)
        key = f"{key_prefix}{sha}.{ext}"

        token = self.auth.upload_token(self.bucket, key, 3600)

        def _do_put() -> tuple[dict | None, object]:
            return put_file(token, key, str(path))

        ret, info = await loop.run_in_executor(None, _do_put)
        status = getattr(info, "status_code", None)
        if status != 200 or not ret or "key" not in ret:
            raise QiniuUploadError(
                f"qiniu upload failed: status={status} info={info} ret={ret}"
            )
        return f"{self.domain}/{ret['key']}", media_type
```

- [ ] **Step 4: Smoke test imports**

```bash
cd /Users/gujiwei/python/superUserAI/vworkapi-bridge && /Users/gujiwei/python/superUserAI/.venv/bin/python -c "
from app.tmp_storage import TmpStorage
from app.vworkapi_client import VWorkApiClient
from app.qiniu_uploader import QiniuUploader, QiniuUploadError
print('bridge core imports ok')
"
```
Expected: `bridge core imports ok`

- [ ] **Step 5: Commit**

```bash
cd /Users/gujiwei/python/superUserAI && git add vworkapi-bridge/app/tmp_storage.py vworkapi-bridge/app/vworkapi_client.py vworkapi-bridge/app/qiniu_uploader.py && git commit -m "feat(bridge): vworkapi client + qiniu uploader + tmp storage"
```

---

## Task 15: vworkapi-bridge — FastAPI app + endpoint

**Files:**
- Create: `vworkapi-bridge/app/main.py`

- [ ] **Step 1: Implement main.py**

Create `vworkapi-bridge/app/main.py`:

```python
from __future__ import annotations

import logging
from typing import Annotated

from fastapi import FastAPI, Header, HTTPException, status
from pydantic import BaseModel, Field

from app.config import get_settings
from app.qiniu_uploader import QiniuUploadError, QiniuUploader
from app.tmp_storage import TmpStorage
from app.vworkapi_client import VWorkApiClient, VWorkApiError

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


class FetchImageRequest(BaseModel):
    cdn_key: str = Field(min_length=1)
    aes_key: str = Field(min_length=1)
    size: int = Field(ge=1)
    img_type: int = Field(default=2)
    msg_id: str = Field(min_length=1)


class FetchImageResponse(BaseModel):
    url: str
    media_type: str
    size: int


def _build_app() -> FastAPI:
    app = FastAPI(title="vworkapi-bridge", version="0.1.0")

    settings = get_settings()
    storage = TmpStorage(settings.tmp_dir)
    vw_client = VWorkApiClient(settings.vworkapi_host, settings.vworkapi_port)
    uploader = QiniuUploader(
        settings.qiniu_ak, settings.qiniu_sk,
        settings.qiniu_bucket, settings.qiniu_domain,
    )

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/fetch-image", response_model=FetchImageResponse)
    async def fetch_image(
        req: FetchImageRequest,
        x_bridge_token: Annotated[str | None, Header(alias="X-Bridge-Token")] = None,
    ) -> FetchImageResponse:
        if settings.image_bridge_token and x_bridge_token != settings.image_bridge_token:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="bad token")

        if req.size > settings.max_image_bytes:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail={"error": "image_too_large",
                        "size": req.size,
                        "limit": settings.max_image_bytes},
            )

        tmp_path = storage.allocate(req.msg_id)
        try:
            try:
                await vw_client.download_image(
                    cdn_key=req.cdn_key, aes_key=req.aes_key,
                    size=req.size, img_type=req.img_type,
                    save_path=str(tmp_path),
                )
            except VWorkApiError as exc:
                logger.warning("vworkapi 9001 failed: %s", exc)
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail={"error": f"vworkapi_9001_failed: {exc}"},
                ) from exc

            try:
                url, media_type = await uploader.upload(tmp_path, key_prefix="sua/")
            except QiniuUploadError as exc:
                logger.warning("qiniu upload failed: %s", exc)
                raise HTTPException(
                    status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                    detail={"error": f"qiniu_upload_failed: {exc}"},
                ) from exc

            actual_size = tmp_path.stat().st_size if tmp_path.exists() else req.size
            return FetchImageResponse(url=url, media_type=media_type, size=actual_size)
        finally:
            storage.cleanup(tmp_path)

    return app


app = _build_app()
```

- [ ] **Step 2: Smoke test the app constructs (without real qiniu creds)**

```bash
cd /Users/gujiwei/python/superUserAI/vworkapi-bridge && QINIU_AK=x QINIU_SK=y QINIU_BUCKET=z QINIU_DOMAIN=https://q.example.com /Users/gujiwei/python/superUserAI/.venv/bin/python -c "
from app.main import app
routes = [r.path for r in app.routes]
assert '/fetch-image' in routes and '/healthz' in routes
print('bridge app routes:', routes)
"
```
Expected: `bridge app routes: ['/openapi.json', '/docs', ..., '/healthz', '/fetch-image']`

- [ ] **Step 3: Commit**

```bash
cd /Users/gujiwei/python/superUserAI && git add vworkapi-bridge/app/main.py && git commit -m "feat(bridge): FastAPI app with /fetch-image and /healthz"
```

---

## Task 16: vworkapi-bridge — e2e test (mocked vworkApi + Qiniu)

**Files:**
- Create: `vworkapi-bridge/tests/__init__.py`
- Create: `vworkapi-bridge/tests/e2e_bridge.py`

- [ ] **Step 1: Empty test package**

```bash
mkdir -p /Users/gujiwei/python/superUserAI/vworkapi-bridge/tests && touch /Users/gujiwei/python/superUserAI/vworkapi-bridge/tests/__init__.py
```

- [ ] **Step 2: Write the e2e test**

Create `vworkapi-bridge/tests/e2e_bridge.py`:

```python
"""End-to-end smoke for vworkapi-bridge.

Mocks vworkApi 9001 and the Qiniu uploader so it runs without external
services. Uses FastAPI's TestClient.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# Provide minimal env so QiniuUploader.__init__ doesn't blow up.
os.environ.setdefault("QINIU_AK", "ak")
os.environ.setdefault("QINIU_SK", "sk")
os.environ.setdefault("QINIU_BUCKET", "bkt")
os.environ.setdefault("QINIU_DOMAIN", "https://cdn.example.com")
os.environ.setdefault("IMAGE_BRIDGE_TOKEN", "secret")
os.environ.setdefault("TMP_DIR", "/tmp/sua-bridge-test")

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.qiniu_uploader import QiniuUploader  # noqa: E402
from app.vworkapi_client import VWorkApiClient  # noqa: E402


client = TestClient(app)


def test_healthz() -> None:
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}
    print("healthz ok")


def test_unauthorized() -> None:
    r = client.post("/fetch-image", json={
        "cdn_key": "a", "aes_key": "b", "size": 100, "img_type": 2, "msg_id": "m1",
    })
    assert r.status_code == 401, r.text
    print("unauthorized ok")


def test_payload_too_large() -> None:
    r = client.post("/fetch-image",
        headers={"X-Bridge-Token": "secret"},
        json={"cdn_key": "a", "aes_key": "b", "size": 99999999999,
              "img_type": 2, "msg_id": "m2"})
    assert r.status_code == 413, r.text
    print("too large ok")


async def _fake_download_ok(self, *, cdn_key, aes_key, size, img_type, save_path):
    # Pretend vworkApi wrote a tiny jpg.
    Path(save_path).parent.mkdir(parents=True, exist_ok=True)
    Path(save_path).write_bytes(b"\xff\xd8\xff\xe0fake-jpg-bytes")


async def _fake_upload_ok(self, path, key_prefix="sua/"):
    return ("https://cdn.example.com/sua/abc.jpg", "image/jpeg")


async def _fake_download_fail(self, *, cdn_key, aes_key, size, img_type, save_path):
    from app.vworkapi_client import VWorkApiError
    raise VWorkApiError("simulated vworkapi crash")


def test_happy_path() -> None:
    with patch.object(VWorkApiClient, "download_image", _fake_download_ok), \
         patch.object(QiniuUploader, "upload", _fake_upload_ok):
        r = client.post(
            "/fetch-image",
            headers={"X-Bridge-Token": "secret"},
            json={"cdn_key": "a", "aes_key": "b", "size": 100,
                  "img_type": 2, "msg_id": "m3"},
        )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["url"] == "https://cdn.example.com/sua/abc.jpg"
    assert body["media_type"] == "image/jpeg"
    print("happy path ok")


def test_vworkapi_failure_502() -> None:
    with patch.object(VWorkApiClient, "download_image", _fake_download_fail):
        r = client.post(
            "/fetch-image",
            headers={"X-Bridge-Token": "secret"},
            json={"cdn_key": "a", "aes_key": "b", "size": 100,
                  "img_type": 2, "msg_id": "m4"},
        )
    assert r.status_code == 502, r.text
    print("vworkapi 502 ok")


def main() -> None:
    test_healthz()
    test_unauthorized()
    test_payload_too_large()
    test_happy_path()
    test_vworkapi_failure_502()
    print("\nall e2e_bridge checks passed")


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Run the test**

```bash
cd /Users/gujiwei/python/superUserAI/vworkapi-bridge && /Users/gujiwei/python/superUserAI/.venv/bin/python tests/e2e_bridge.py
```
Expected: 5 "ok" lines + `all e2e_bridge checks passed`

- [ ] **Step 4: Commit**

```bash
cd /Users/gujiwei/python/superUserAI && git add vworkapi-bridge/tests/ && git commit -m "test(bridge): e2e with mocked vworkapi + qiniu"
```

---

## Task 17: backend — image flow e2e test

**Files:**
- Create: `backend/tests/e2e_image_input.py`

- [ ] **Step 1: Write the test**

Create `backend/tests/e2e_image_input.py`:

```python
"""End-to-end smoke for GroupImageHandler — bridge mocked, LLM stubbed.

Without env: only verifies the unbound-group bypass path and pure helpers.
With BIND_GROUP_TEST_REPO_ID + BIND_GROUP_TEST_GROUP_ID + a sender that has an
active drafting project: runs the full happy path (bridge mocked).
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "shared"))

from app.database import AsyncSessionLocal  # noqa: E402
from app.services.group_image_handler import GroupImageHandler  # noqa: E402
from app.services.image_bridge_client import (  # noqa: E402
    BridgeError,
    BridgeFetchResult,
    ImageBridgeClient,
)


class RecordingWeChat:
    def __init__(self) -> None:
        self.sent: list = []

    async def send_text(self, *args, **kwargs):
        self.sent.append(("text", args, kwargs))
        return {"status": "ok"}

    async def send_at_group(self, group_id, at_list, msg):
        self.sent.append(("at_group", group_id, at_list, msg))
        return {"status": "ok"}


class StubLLM:
    async def chat(self, messages):
        class _R:
            content = "我看到了这张图，你想让我重点关注哪个区域？"
        return _R()


_SAMPLE_META = {
    "cdn_key": "k1", "aes_key": "a1", "size": 1234,
    "img_type": 2, "url": "", "auth_key": "", "md5": "x",
}


async def test_unbound_group_returns_handled_false() -> None:
    async with AsyncSessionLocal() as db:
        wechat = RecordingWeChat()
        handler = GroupImageHandler(db, wechat, llm=StubLLM())
        handled = await handler.try_handle(
            wechat_user_id="user-x",
            group_id="R:NOT_BOUND_TEST",
            image_meta=_SAMPLE_META,
            msg_id="msg-1",
        )
        assert handled is False
    print("unbound passthrough ok")


async def test_bridge_failure_replies_user() -> None:
    """When bridge raises, user gets a friendly fallback reply."""
    repo_id_env = os.environ.get("BIND_GROUP_TEST_REPO_ID")
    group_id_env = os.environ.get("BIND_GROUP_TEST_GROUP_ID")
    sender = os.environ.get("BIND_GROUP_TEST_SENDER")
    if not (repo_id_env and group_id_env and sender):
        print("set BIND_GROUP_TEST_REPO_ID/GROUP_ID/SENDER + create active drafting"
              " project for SENDER to run bridge_failure test")
        return

    async def boom(*a, **kw):
        raise BridgeError(short="bridge 不可达", detail="simulated")

    async with AsyncSessionLocal() as db:
        wechat = RecordingWeChat()
        handler = GroupImageHandler(db, wechat, llm=StubLLM())
        with patch.object(ImageBridgeClient, "fetch_image", boom):
            await handler.try_handle(
                wechat_user_id=sender, group_id=group_id_env,
                image_meta=_SAMPLE_META, msg_id="msg-fail-1",
            )
        sent = [s for s in wechat.sent if s[0] == "at_group"]
        assert sent, wechat.sent
        assert "读不到" in sent[-1][3]
    print("bridge failure user-reply ok")


async def test_happy_path() -> None:
    """Mock bridge to return a URL; assert message row written + reply sent."""
    repo_id_env = os.environ.get("BIND_GROUP_TEST_REPO_ID")
    group_id_env = os.environ.get("BIND_GROUP_TEST_GROUP_ID")
    sender = os.environ.get("BIND_GROUP_TEST_SENDER")
    if not (repo_id_env and group_id_env and sender):
        print("set BIND_GROUP_TEST_REPO_ID/GROUP_ID/SENDER to run happy path")
        return

    async def fake_fetch(self, **kw):
        return BridgeFetchResult(
            url="https://cdn.example.com/sua/test.jpg",
            media_type="image/jpeg",
            size=1234,
        )

    async with AsyncSessionLocal() as db:
        wechat = RecordingWeChat()
        handler = GroupImageHandler(db, wechat, llm=StubLLM())
        with patch.object(ImageBridgeClient, "fetch_image", fake_fetch):
            await handler.try_handle(
                wechat_user_id=sender, group_id=group_id_env,
                image_meta=_SAMPLE_META, msg_id="msg-happy-1",
            )
        sent = [s for s in wechat.sent if s[0] == "at_group"]
        assert sent and "看到了这张图" in sent[-1][3], wechat.sent
    print("happy path ok")


def main() -> None:
    asyncio.run(test_unbound_group_returns_handled_false())
    asyncio.run(test_bridge_failure_replies_user())
    asyncio.run(test_happy_path())
    print("all e2e_image_input checks passed")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run (without env, only bypass test runs)**

```bash
/Users/gujiwei/python/superUserAI/.venv/bin/python /Users/gujiwei/python/superUserAI/backend/tests/e2e_image_input.py
```
Expected: `unbound passthrough ok` + 2 skip messages + `all e2e_image_input checks passed`

- [ ] **Step 3: Commit**

```bash
cd /Users/gujiwei/python/superUserAI && git add backend/tests/e2e_image_input.py && git commit -m "test(image_input): bypass + bridge-failure + happy-path e2e"
```

---

## Task 18: Final regression sweep + manual smoke

**Files:** none (verification only).

- [ ] **Step 1: Run all backend e2e tests**

```bash
cd /Users/gujiwei/python/superUserAI/backend && for f in tests/e2e_*.py; do echo "=== $f ==="; /Users/gujiwei/python/superUserAI/.venv/bin/python "$f" 2>&1 | tail -3; done
```
Expected: every script ends with its own "passed" line; no `Traceback`.

- [ ] **Step 2: Run bridge tests**

```bash
cd /Users/gujiwei/python/superUserAI/vworkapi-bridge && /Users/gujiwei/python/superUserAI/.venv/bin/python tests/e2e_bridge.py
```
Expected: `all e2e_bridge checks passed`

- [ ] **Step 3: Restart backend on 2888 with new code**

(The user runs this — same pattern as the previous feature):

```bash
# stop existing
lsof -nP -iTCP:2888 -sTCP:LISTEN | awk 'NR>1 {print $2}' | xargs -r kill
# start
cd /Users/gujiwei/python/superUserAI/backend
/Users/gujiwei/python/superUserAI/.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 2888 --log-level info
```

- [ ] **Step 4: Configure bridge URL on backend**

Add to `backend/.env`:
```
image_bridge_url=http://1.94.215.136:9100
image_bridge_token=<same as bridge .env>
```

- [ ] **Step 5: Manual real-traffic smoke (optional)**

In a bound WeChat group:
1. `@bot 我想做个登录页` → AI asks clarifying question (active project opens).
2. Send a screenshot of an existing login page.
3. Verify backend log shows `Received WeChat image:` and `group_image bridge fetch_image` info entries; the bot replies in-group referencing the picture.

---

## Self-Review Notes

**Spec coverage:**
- §3 Data model (messages.media_url + media_type) → Task 1 ✓
- §4 vworkapi-bridge service → Tasks 13, 14, 15, 16 ✓
- §5.1 Backend file structure → covered across Tasks 1, 3, 9–12 ✓
- §5.2 LLM multimodal abstraction → Tasks 4, 5, 6, 7, 8 ✓
- §5.3 PMAgent multimodal build → Task 9 ✓
- §5.4 GroupImageHandler → Task 11 ✓
- §5.5 wechat_gateway IMAGE branch → Task 12 ✓
- §5.6 New config settings → Task 2 ✓
- §6 Error handling: bridge errors → Task 10 (typed) + Task 11 (user reply); 413 → Task 15; whitelist gate → Task 11; multiple images naturally handled (each becomes its own dispatch) ✓
- §7 Tests → Tasks 16, 17, 18 ✓
- §8 YAGNI exclusions: respected (no AI-output, no private chat, no Ollama vision fallback) ✓

**Placeholder check:** No `TBD` / `implement later` / "similar to Task N" instances. Each step contains the actual code.

**Type/name consistency:**
- `BridgeFetchResult.{url, media_type, size}` defined in Task 10, used in Task 11 and 17.
- `BridgeError.short` consumed in Task 11 and 17.
- `ImageBridgeClient.fetch_image(cdn_key, aes_key, size, img_type, msg_id)` signature stable across Tasks 10, 11, 17.
- `GroupImageHandler.try_handle(wechat_user_id, group_id, image_meta, msg_id)` matches Task 12's `_process_bound_group_image_async` call site.
- `add_message` signature with `media_url` / `media_type` (Task 3) used by Task 11.
- `_normalize_messages_keep_multimodal` (Task 4) called by Tasks 5–8.
- `_convert_content_to_anthropic` (Task 6) — only used inside `_prepare_messages` (Task 6).
- `_strip_images` (Task 8) used by `chat`/`stream_chat` in the same file.
- `_flatten_to_text` (Task 7) used by `chat` in the same file.

No drift detected.
