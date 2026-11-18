"""AI providers. Gemini (generativelanguage REST API) with strict JSON-schema output.

Prompts insist on grounding: the model only sees the transcript, chat sample, signal
scores and (optionally) keyframes, and is told never to invent events or quotes.
Outputs are validated; quotes in generated text are checked against the transcript.
"""
from __future__ import annotations

import base64
import json
import logging
import re
from typing import Literal, Protocol

import httpx
from pydantic import BaseModel, Field, ValidationError, field_validator

log = logging.getLogger(__name__)
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

MOMENT_TYPES = ["funny_reaction", "shocking_moment", "gameplay_highlight", "argument", "emotional",
                "announcement", "skill_display", "fail", "hype", "conversation", "other"]


class AIError(RuntimeError):
    pass


class MomentEvaluation(BaseModel):
    interesting: bool
    viral_score: int = Field(ge=0, le=100)
    moment_type: str
    reason: str
    suggested_title: str
    start_offset: float
    end_offset: float

    @field_validator("moment_type")
    @classmethod
    def _type(cls, v: str) -> str:
        return v if v in MOMENT_TYPES else "other"


class ClipContent(BaseModel):
    title: str = Field(max_length=100)
    youtube_title: str = Field(max_length=100)
    tiktok_description: str = Field(max_length=2200)
    instagram_caption: str = Field(max_length=2200)
    hook: str = Field(max_length=150)
    hashtags: list[str] = Field(max_length=15)

    @field_validator("hashtags")
    @classmethod
    def _tags(cls, v: list[str]) -> list[str]:
        out = []
        for t in v:
            t = re.sub(r"[^\w]", "", t.lstrip("#"), flags=re.UNICODE)
            if t and f"#{t}" not in out:
                out.append(f"#{t}")
        return out[:15]


class MomentContext(BaseModel):
    creator_name: str
    stream_title: str
    transcript: str
    chat_sample: list[str]
    signals: dict
    pre_seconds: float
    post_seconds: float
    language: str
    keyframes_jpeg: list[bytes] = []


class ContentContext(BaseModel):
    creator_name: str
    stream_title: str
    transcript: str
    moment_type: str | None
    reason: str | None
    language: Literal["en", "sq"]
    hashtag_template: str


class AIProvider(Protocol):
    def evaluate_moment(self, ctx: MomentContext) -> MomentEvaluation: ...
    def generate_content(self, ctx: ContentContext) -> ClipContent: ...


LANG_NAMES = {"en": "English", "sq": "Albanian"}

_MOMENT_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "interesting": {"type": "BOOLEAN"},
        "viral_score": {"type": "INTEGER"},
        "moment_type": {"type": "STRING", "enum": MOMENT_TYPES},
        "reason": {"type": "STRING"},
        "suggested_title": {"type": "STRING"},
        "start_offset": {"type": "NUMBER"},
        "end_offset": {"type": "NUMBER"},
    },
    "required": ["interesting", "viral_score", "moment_type", "reason", "suggested_title", "start_offset", "end_offset"],
}

_CONTENT_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "title": {"type": "STRING"},
        "youtube_title": {"type": "STRING"},
        "tiktok_description": {"type": "STRING"},
        "instagram_caption": {"type": "STRING"},
        "hook": {"type": "STRING"},
        "hashtags": {"type": "ARRAY", "items": {"type": "STRING"}},
    },
    "required": ["title", "youtube_title", "tiktok_description", "instagram_caption", "hook", "hashtags"],
}


class GeminiProvider:
    def __init__(self, api_key: str, model: str = "gemini-2.5-flash", transport: httpx.BaseTransport | None = None):
        if not api_key:
            raise AIError("Gemini API key is not configured (Settings → AI, or GEMINI_API_KEY)")
        self.api_key, self.model = api_key, model
        self._client = httpx.Client(timeout=90, transport=transport)

    def _call(self, parts: list[dict], schema: dict, temperature: float = 0.4) -> dict:
        body = {
            "contents": [{"role": "user", "parts": parts}],
            "generationConfig": {"responseMimeType": "application/json", "responseSchema": schema,
                                 "temperature": temperature},
        }
        resp = self._client.post(GEMINI_URL.format(model=self.model), json=body,
                                 headers={"x-goog-api-key": self.api_key})
        if resp.status_code >= 400:
            raise AIError(f"Gemini API error {resp.status_code}: {resp.text[:300]}")
        data = resp.json()
        try:
            text = data["candidates"][0]["content"]["parts"][0]["text"]
            return json.loads(text)
        except (KeyError, IndexError, json.JSONDecodeError) as exc:
            block = data.get("promptFeedback", {}).get("blockReason")
            raise AIError(f"Gemini returned no usable JSON{f' (blocked: {block})' if block else ''}") from exc

    def evaluate_moment(self, ctx: MomentContext) -> MomentEvaluation:
        prompt = f"""You review candidate highlight moments from a livestream by "{ctx.creator_name}" titled "{ctx.stream_title}".
The detected event is at offset 0 s. Footage covers -{ctx.pre_seconds:.0f} s to +{ctx.post_seconds:.0f} s.

Automatic signal scores (0-1): {json.dumps(ctx.signals, default=str)}

Transcript of the footage (offsets in seconds relative to the event):
{ctx.transcript or "(no speech detected)"}

Sample of live chat messages around the event:
{chr(10).join("- " + m for m in ctx.chat_sample[:60]) or "(no chat)"}

{"Keyframes from the footage are attached in chronological order." if ctx.keyframes_jpeg else ""}

Decide whether this is a genuinely interesting, self-contained clip for short-form video.
Rules:
- Base your judgement ONLY on the transcript, chat and images provided. Do not invent events.
- Chat spikes alone are not enough; the footage itself must contain the moment.
- viral_score 0-100; be strict: ordinary talking or idle gameplay scores below 50.
- start_offset (negative, >= -{ctx.pre_seconds:.0f}) and end_offset (positive, <= {ctx.post_seconds:.0f}) should
  include the setup and the complete reaction without cutting sentences.
- suggested_title in {LANG_NAMES.get(ctx.language, "English")}, max 70 characters, no fabricated quotes.
"""
        parts: list[dict] = [{"text": prompt}]
        for jpg in ctx.keyframes_jpeg[:6]:
            parts.append({"inline_data": {"mime_type": "image/jpeg", "data": base64.b64encode(jpg).decode()}})
        raw = self._call(parts, _MOMENT_SCHEMA, temperature=0.2)
        try:
            ev = MomentEvaluation.model_validate(raw)
        except ValidationError as exc:
            raise AIError(f"invalid moment evaluation: {exc}") from exc
        ev.start_offset = max(-ctx.pre_seconds, min(0.0, ev.start_offset))
        ev.end_offset = min(ctx.post_seconds, max(0.0, ev.end_offset))
        return ev

    def generate_content(self, ctx: ContentContext) -> ClipContent:
        lang = LANG_NAMES[ctx.language]
        prompt = f"""Write social media copy for a short vertical clip from {ctx.creator_name}'s livestream "{ctx.stream_title}".
Moment type: {ctx.moment_type or "unknown"}. Why it was selected: {ctx.reason or "n/a"}.

Transcript of the clip:
{ctx.transcript or "(no speech)"}

Rules:
- Write everything in {lang}.
- Only describe what is present in the transcript/moment description. Never invent events, outcomes or
  quotations. If you quote, copy words exactly from the transcript.
- title: max 70 chars. youtube_title: max 90 chars and should work as a YouTube Shorts title.
- tiktok_description and instagram_caption: 1-3 sentences, engaging, no hashtags inside.
- hook: max 12 words to overlay at the start.
- hashtags: 5-10 relevant hashtags; consider this template: {ctx.hashtag_template}
"""
        raw = self._call([{"text": prompt}], _CONTENT_SCHEMA, temperature=0.7)
        try:
            content = ClipContent.model_validate(raw)
        except ValidationError as exc:
            raise AIError(f"invalid content: {exc}") from exc
        return strip_unverified_quotes(content, ctx.transcript)


def strip_unverified_quotes(content: ClipContent, transcript: str) -> ClipContent:
    """Remove quoted text that does not appear verbatim in the transcript."""
    norm_t = re.sub(r"\s+", " ", transcript.lower())

    def clean(text: str) -> str:
        def repl(m: re.Match) -> str:
            q = m.group(2)
            return m.group(0) if re.sub(r"\s+", " ", q.lower()).strip() in norm_t else q
        return re.sub(r"([\"“”])([^\"“”]{3,200})[\"“”]", repl, text)

    data = content.model_dump()
    for key in ("title", "youtube_title", "tiktok_description", "instagram_caption", "hook"):
        data[key] = clean(data[key])
    return ClipContent.model_validate(data)


class HeuristicProvider:
    """Used only when AI is disabled AND the owner turned off ``require_ai_evaluation``."""

    def evaluate_moment(self, ctx: MomentContext) -> MomentEvaluation:
        combined = float(ctx.signals.get("combined", 0))
        audio = float(ctx.signals.get("audio") or 0)
        mtype = "funny_reaction" if (ctx.signals.get("laughter") or 0) > 0.5 else ("hype" if audio > 0.5 else "other")
        return MomentEvaluation(interesting=combined >= 0.6, viral_score=int(round(combined * 100)), moment_type=mtype,
                                reason="Selected by signal heuristics (AI evaluation disabled).",
                                suggested_title=ctx.stream_title[:70] or "Livestream highlight",
                                start_offset=-ctx.pre_seconds, end_offset=ctx.post_seconds)

    def generate_content(self, ctx: ContentContext) -> ClipContent:
        title = (ctx.stream_title or f"{ctx.creator_name} highlight")[:70]
        tags = [t for t in ctx.hashtag_template.split() if t.startswith("#")]
        return ClipContent(title=title, youtube_title=title, tiktok_description=title, instagram_caption=title,
                           hook=title[:60], hashtags=tags)


def get_provider(cfg, api_key: str | None) -> AIProvider | None:
    if cfg.ai.provider == "gemini" and api_key:
        return GeminiProvider(api_key, cfg.ai.model)
    return None
