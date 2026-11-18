"""Pure chat analytics: velocity, spikes, unique users, emoji bursts, repetition, spam."""
from __future__ import annotations

import math
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass, field

# Unicode emoji ranges + YouTube custom emote shortcodes like :face-blue-smiling: or :_partyhat:
EMOJI_RE = re.compile(
    "[\U0001F300-\U0001FAFF\U00002600-\U000027BF\U0001F000-\U0001F2FF\U0001F900-\U0001F9FF⭐❤]"
)
SHORTCODE_RE = re.compile(r":[A-Za-z0-9_\-]{2,40}:")
URL_RE = re.compile(r"https?://|www\.", re.I)
REPEAT_CHARS_RE = re.compile(r"(.)\1{2,}")
LAUGH_RE = re.compile(r"\b(?:a?ha(?:ha)+h?|lo+l+|lmf?ao+|xd+|kkk+|jaja+|hahah?|ahah)\b", re.I)
HYPE_WORDS = {"omg", "wtf", "no way", "wow", "clip it", "clip that", "clip", "lets go", "let's go", "insane",
              "bruh", "pog", "poggers", "w", "l", "rip", "o zot", "shif", "uau", "hahaha"}


@dataclass
class ChatMessage:
    author_id: str | None
    text: str
    ts: float  # epoch seconds


@dataclass
class WindowFeatures:
    message_count: int = 0
    filtered_count: int = 0
    unique_authors: int = 0
    emoji_count: int = 0
    question_count: int = 0
    laugh_count: int = 0
    hype_count: int = 0
    top_phrase: str | None = None
    top_phrase_share: float = 0.0
    velocity: float = 0.0  # messages / second (filtered)
    spam_removed: int = 0
    phrases: list[tuple[str, int]] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items()}


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).lower().strip()
    text = REPEAT_CHARS_RE.sub(r"\1\1", text)
    text = re.sub(r"\s+", " ", text)
    return text


def count_emoji(text: str) -> int:
    return len(EMOJI_RE.findall(text)) + len(SHORTCODE_RE.findall(text))


def is_spam(msg: ChatMessage, seen_by_author: Counter) -> bool:
    if URL_RE.search(msg.text):
        return True
    if len(msg.text) > 300:
        return True
    norm = normalize(msg.text)
    key = (msg.author_id, norm)
    seen_by_author[key] += 1
    # the same author repeating the same message more than twice in a window is flooding
    return seen_by_author[key] > 2


def window_features(messages: list[ChatMessage], window_seconds: float) -> WindowFeatures:
    f = WindowFeatures()
    f.message_count = len(messages)
    seen: Counter = Counter()
    kept: list[ChatMessage] = []
    for m in messages:
        if is_spam(m, seen):
            f.spam_removed += 1
        else:
            kept.append(m)
    f.filtered_count = len(kept)
    f.unique_authors = len({m.author_id for m in kept if m.author_id})
    phrases: Counter = Counter()
    for m in kept:
        f.emoji_count += count_emoji(m.text)
        if "?" in m.text:
            f.question_count += 1
        norm = normalize(m.text)
        if LAUGH_RE.search(norm):
            f.laugh_count += 1
        if any(w == norm or f" {w} " in f" {norm} " for w in HYPE_WORDS):
            f.hype_count += 1
        stripped = EMOJI_RE.sub("", SHORTCODE_RE.sub("", norm)).strip()
        if stripped:
            phrases[stripped[:60]] += 1
    if phrases:
        f.phrases = phrases.most_common(5)
        phrase, cnt = f.phrases[0]
        if cnt >= 3:
            f.top_phrase = phrase
            f.top_phrase_share = cnt / max(1, f.filtered_count)
    f.velocity = f.filtered_count / window_seconds if window_seconds else 0.0
    return f


def zscore(value: float, history: list[float], poisson: bool = True) -> float:
    """Robust z-score of value against history. Poisson floor avoids explosions on quiet chats."""
    if not history:
        return 0.0
    mean = sum(history) / len(history)
    var = sum((h - mean) ** 2 for h in history) / len(history)
    std = math.sqrt(var)
    if poisson:
        std = max(std, math.sqrt(max(mean, 1.0)))
    std = max(std, 1e-6)
    return (value - mean) / std


def z_to_score(z: float, lo: float = 1.0, hi: float = 4.0) -> float:
    if z <= lo:
        return 0.0
    if z >= hi:
        return 1.0
    return (z - lo) / (hi - lo)


@dataclass
class ChatScores:
    chat: float
    emoji: float
    unique_users: float
    details: dict


def score_chat(current: WindowFeatures, baseline: list[WindowFeatures]) -> ChatScores:
    counts = [b.filtered_count for b in baseline]
    z_count = zscore(current.filtered_count, counts)
    chat = z_to_score(z_count)
    # repeated reactions / laughter / hype reinforce a spike, never create one alone
    reinforcement = min(0.25, current.top_phrase_share * 0.3 + (current.laugh_count + current.hype_count)
                        / max(1, current.filtered_count) * 0.25)
    if chat > 0:
        chat = min(1.0, chat + reinforcement)
    z_emoji = zscore(current.emoji_count, [b.emoji_count for b in baseline])
    z_unique = zscore(current.unique_authors, [b.unique_authors for b in baseline])
    return ChatScores(
        chat=round(chat, 4),
        emoji=round(z_to_score(z_emoji), 4),
        unique_users=round(z_to_score(z_unique), 4),
        details={"z_count": round(z_count, 3), "z_emoji": round(z_emoji, 3), "z_unique": round(z_unique, 3),
                 "velocity": round(current.velocity, 3), "top_phrase": current.top_phrase,
                 "top_phrase_share": round(current.top_phrase_share, 3), "laughs": current.laugh_count,
                 "hype": current.hype_count, "questions": current.question_count,
                 "spam_removed": current.spam_removed, "messages": current.filtered_count,
                 "unique_authors": current.unique_authors, "emoji": current.emoji_count},
    )
