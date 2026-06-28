"""Wrapper around the OpenAI API supporting chat, vision, image gen and voice."""
from __future__ import annotations

import base64
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

# `IMAGE_MODEL` is the public selector id used in keyboards/state. Actual
# generation tries several real model ids in order, since which one an account
# has access to varies.
IMAGE_MODEL = "dall-e-3"
IMAGE_MODEL_CANDIDATES = ["gpt-image-1", "dall-e-3", "dall-e-2"]
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


@dataclass
class ImageResult:
    kind: str  # "url" or "bytes"
    url: str | None = None
    data: bytes | None = None
    model: str = ""


async def generate_image(prompt: str) -> ImageResult:
    """Generate an image, trying the available image models in order.

    Different models return data differently: DALL·E returns a URL, while
    gpt-image-1 returns base64. We normalise both into an ImageResult.
    """
    last_err: Exception | None = None
    for model in IMAGE_MODEL_CANDIDATES:
        try:
            kwargs: dict = {"model": model, "prompt": prompt, "n": 1, "size": "1024x1024"}
            if model == "dall-e-3":
                kwargs["quality"] = "standard"
            resp = await client.images.generate(**kwargs)
            item = resp.data[0]
            if getattr(item, "url", None):
                return ImageResult(kind="url", url=item.url, model=model)
            if getattr(item, "b64_json", None):
                return ImageResult(kind="bytes", data=base64.b64decode(item.b64_json), model=model)
        except Exception as e:  # noqa: BLE001
            last_err = e
            log.warning("image model %s unavailable: %s", model, e)
            continue
    raise RuntimeError(last_err or "No image model available")


async def edit_image(
    prompt: str,
    image_bytes: bytes,
    filename: str = "image.png",
    content_type: str = "image/png",
) -> ImageResult:
    """Transform/edit an existing image given a text prompt (gpt-image-1)."""
    resp = await client.images.edit(
        model="gpt-image-1",
        image=(filename, image_bytes, content_type),
        prompt=prompt,
        size="1024x1024",
    )
    item = resp.data[0]
    if getattr(item, "b64_json", None):
        return ImageResult(kind="bytes", data=base64.b64decode(item.b64_json), model="gpt-image-1")
    if getattr(item, "url", None):
        return ImageResult(kind="url", url=item.url, model="gpt-image-1")
    raise RuntimeError("No image returned from edit")


async def transcribe_voice(file_path: str) -> str:
    """Transcribe a voice/audio file with Whisper."""
    with open(file_path, "rb") as f:
        resp = await client.audio.transcriptions.create(model="whisper-1", file=f)
    return resp.text.strip()


# ─────────────────────── Embeddings & helpers ───────────────────────

async def embed_text(text: str) -> list[float]:
    """Return an embedding vector for `text`."""
    resp = await client.embeddings.create(model=settings.embed_model, input=text[:8000])
    return resp.data[0].embedding


async def summarize_title(transcript: str) -> str:
    """Produce a short 3–6 word title summarising a conversation."""
    resp = await client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "system",
                "content": "Summarise the conversation as a concise 3-6 word title. "
                "No quotes, no trailing punctuation. Reply with the title only.",
            },
            {"role": "user", "content": transcript[:4000]},
        ],
        temperature=0.3,
        max_tokens=20,
    )
    return (resp.choices[0].message.content or "").strip().strip('"')[:80]


# Controlled vocabulary the auto-classifier may assign for user segmentation.
TAG_VOCABULARY = [
    "tech_user",
    "developer",
    "creative",
    "business",
    "student",
    "researcher",
    "casual_user",
    "power_user",
    "image_lover",
    "polite",
    "low_quality",
    "spammer",
]


async def classify_tags(transcript: str) -> list[str]:
    """Classify a user (from a sample of their messages) into segmentation tags."""
    resp = await client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "system",
                "content": (
                    "You segment chatbot users. Given a sample of a user's messages, "
                    "pick 1-3 tags that best describe them from this exact list: "
                    + ", ".join(TAG_VOCABULARY)
                    + ". Reply with ONLY the chosen tags, comma-separated, no extra text."
                ),
            },
            {"role": "user", "content": transcript[:4000]},
        ],
        temperature=0.0,
        max_tokens=30,
    )
    raw = (resp.choices[0].message.content or "").lower()
    return [t for t in TAG_VOCABULARY if t in raw][:3]


# Human-friendly labels for the segmentation tags shown to users.
TAG_LABELS = {
    "tech_user": "🧑‍💻 Tech user",
    "developer": "👨‍💻 Developer",
    "creative": "🎨 Creative",
    "business": "💼 Business-minded",
    "student": "🎓 Student",
    "researcher": "🔬 Researcher",
    "casual_user": "💬 Casual user",
    "power_user": "⚡ Power user",
    "image_lover": "🖼 Visual creator",
    "polite": "🙏 Polite",
    "low_quality": "🫧 Low-signal",
    "spammer": "🚯 Spammy",
}


def tag_label(tag: str) -> str:
    return TAG_LABELS.get(tag, f"🏷 {tag}")


async def classify_primary_tag(transcript: str) -> str | None:
    """Pick the single best segmentation tag for a user (or None)."""
    tags = await classify_tags(transcript)
    return tags[0] if tags else None


async def express_user(display_name: str, profile: dict, language: str | None = None) -> str:
    """Write a short, fun 'expose' of a group member from their group data only."""
    lang = language or "English"
    facts: list[str] = [f"Total group messages seen: {profile['total']}"]
    if profile.get("top_emojis"):
        facts.append("Most-used emojis: " + " ".join(f"{e}×{c}" for e, c in profile["top_emojis"]))
    if profile.get("top_words"):
        facts.append("Favorite words: " + ", ".join(f"{w} ({c})" for w, c in profile["top_words"]))
    if profile.get("types"):
        facts.append("Message types: " + ", ".join(f"{k}={v}" for k, v in profile["types"].items()))
    samples = "\n".join(f"- {s[:160]}" for s in profile.get("samples", [])[:15])

    system = (
        "You are a witty Telegram group bot. Based ONLY on the group-chat data "
        f"provided, write a short, FUN, friendly 'expose' of the member {display_name}. "
        "2-4 sentences. Be playful, warm and a little cheeky — never mean, insulting "
        "or offensive. Call out their signature emoji, a catchphrase, or a favorite "
        f"word if any, and one fun observation. Write the ENTIRE reply in {lang}. "
        "Do not invent facts beyond the data."
    )
    resp = await client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": f"Member: {display_name}\nData:\n" + "\n".join(facts)
             + (f"\n\nSample messages:\n{samples}" if samples else "")},
        ],
        temperature=0.9,
        max_tokens=320,
    )
    return (resp.choices[0].message.content or "").strip()


async def format_lyrics(raw: str) -> str:
    """Reformat an automatic transcription into clean, line-broken lyrics."""
    resp = await client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "system",
                "content": (
                    "You are given an automatic transcription of a song. Reformat it "
                    "into clean lyrics: one natural lyrical line per line, with correct "
                    "capitalization and light punctuation. Preserve the wording. Remove "
                    "non-lyric artifacts like 'thanks for watching', 'subscribe', or "
                    "channel mentions. Output ONLY the lyrics, nothing else."
                ),
            },
            {"role": "user", "content": raw[:6000]},
        ],
        temperature=0.2,
        max_tokens=1500,
    )
    return (resp.choices[0].message.content or raw).strip()


async def generate_reengagement(
    transcript: str, persona: str | None = None, segment: str | None = None
) -> str:
    """Write a short, warm follow-up question to re-engage a quiet user."""
    system = (
        "A user you were chatting with has been quiet for a day. Based on their "
        "previous conversation below, write ONE short, warm, natural message "
        "(1-2 sentences) that asks a specific, relevant follow-up question to "
        "restart the chat. Reference what they actually discussed — do not greet "
        "generically. No quotes, no preamble."
    )
    if persona:
        system += f"\nKeep this assistant persona: {persona}"
    if segment:
        system += f"\nThe user is a '{segment}' type — tailor the tone accordingly."
    resp = await client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": transcript[:3000]},
        ],
        temperature=0.8,
        max_tokens=120,
    )
    return (resp.choices[0].message.content or "").strip()
