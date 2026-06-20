"""Wrapper around the OpenAI API supporting chat, vision, image gen and voice."""
from __future__ import annotations

import logging
from dataclasses import dataclass

from openai import AsyncOpenAI

from app.config import settings

log = logging.getLogger(__name__)

client = AsyncOpenAI(api_key=settings.openai_api_key)


@dataclass(frozen=True)
class ChatModel:
    id: str
    label: str
    description: str


# Catalogue of chat models offered to users. The bot degrades gracefully if the
# API key does not have access to a particular model.
CHAT_MODELS: list[ChatModel] = [
    ChatModel("gpt-4o", "🧠 GPT-4o", "Most capable multimodal flagship"),
    ChatModel("gpt-4o-mini", "⚡ GPT-4o mini", "Fast & cheap, great default"),
    ChatModel("gpt-4.1", "🚀 GPT-4.1", "Latest reasoning-strong model"),
    ChatModel("gpt-4.1-mini", "✨ GPT-4.1 mini", "Balanced speed & quality"),
    ChatModel("gpt-4-turbo", "🎯 GPT-4 Turbo", "Powerful long-context model"),
    ChatModel("o1-mini", "🔬 o1-mini", "Reasoning model for hard problems"),
    ChatModel("o3-mini", "🧩 o3-mini", "Newest compact reasoning model"),
    ChatModel("gpt-3.5-turbo", "💨 GPT-3.5 Turbo", "Lightweight & very fast"),
]

IMAGE_MODEL = "dall-e-3"
VISION_FALLBACK = "gpt-4o"  # used when a user sends a photo on a non-vision model

MODEL_IDS = {m.id for m in CHAT_MODELS}

# Reasoning models (o1/o3 family) do not accept a system role or temperature.
REASONING_PREFIXES = ("o1", "o3", "o4")


def is_reasoning_model(model: str) -> bool:
    return model.startswith(REASONING_PREFIXES)


def get_model_label(model_id: str) -> str:
    for m in CHAT_MODELS:
        if m.id == model_id:
            return m.label
    if model_id == IMAGE_MODEL:
        return "🎨 DALL·E 3"
    return model_id


@dataclass
class ChatResult:
    text: str
    model: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


async def chat_completion(
    model: str,
    messages: list[dict],
    system_prompt: str | None = None,
) -> ChatResult:
    """Run a chat completion and return text + token usage."""
    payload = list(messages)

    if system_prompt and not is_reasoning_model(model):
        payload = [{"role": "system", "content": system_prompt}] + payload

    kwargs: dict = {"model": model, "messages": payload}
    if not is_reasoning_model(model):
        kwargs["temperature"] = 0.7

    resp = await client.chat.completions.create(**kwargs)
    choice = resp.choices[0].message.content or ""
    usage = resp.usage
    return ChatResult(
        text=choice.strip(),
        model=model,
        prompt_tokens=getattr(usage, "prompt_tokens", 0) or 0,
        completion_tokens=getattr(usage, "completion_tokens", 0) or 0,
        total_tokens=getattr(usage, "total_tokens", 0) or 0,
    )


async def vision_completion(model: str, text: str, image_url: str) -> ChatResult:
    """Answer a question about an image (auto-uses a vision-capable model)."""
    use_model = model if model in ("gpt-4o", "gpt-4o-mini", "gpt-4.1", "gpt-4-turbo") else VISION_FALLBACK
    resp = await client.chat.completions.create(
        model=use_model,
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": text or "Describe this image in detail."},
                    {"type": "image_url", "image_url": {"url": image_url}},
                ],
            }
        ],
    )
    usage = resp.usage
    return ChatResult(
        text=(resp.choices[0].message.content or "").strip(),
        model=use_model,
        prompt_tokens=getattr(usage, "prompt_tokens", 0) or 0,
        completion_tokens=getattr(usage, "completion_tokens", 0) or 0,
        total_tokens=getattr(usage, "total_tokens", 0) or 0,
    )


async def generate_image(prompt: str) -> str:
    """Generate an image with DALL·E 3, returning a URL."""
    resp = await client.images.generate(
        model=IMAGE_MODEL,
        prompt=prompt,
        size="1024x1024",
        quality="standard",
        n=1,
    )
    return resp.data[0].url


async def transcribe_voice(file_path: str) -> str:
    """Transcribe a voice/audio file with Whisper."""
    with open(file_path, "rb") as f:
        resp = await client.audio.transcriptions.create(model="whisper-1", file=f)
    return resp.text.strip()
