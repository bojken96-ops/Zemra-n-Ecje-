"""Transcript utilities and ASS subtitle rendering (4 styles, custom font/colour/position/animation)."""
from __future__ import annotations

import re
from dataclasses import dataclass

SENTENCE_END = re.compile(r"[.!?…]+[\"')\]]*$")
STOPWORDS = {"the", "a", "an", "and", "or", "but", "to", "of", "in", "on", "is", "it", "i", "you", "that", "this",
             "for", "with", "was", "so", "we", "he", "she", "they", "me", "my", "be", "are", "at", "do", "just",
             "dhe", "e", "të", "në", "një", "që", "u", "me", "për", "nga", "është", "ka", "se", "po", "jo", "i"}


@dataclass
class Word:
    start: float
    end: float
    text: str


def words_from_transcript(transcript: dict) -> list[Word]:
    words: list[Word] = []
    for seg in transcript.get("segments", []):
        seg_words = seg.get("words") or []
        if seg_words:
            for w in seg_words:
                t = w["word"].strip()
                if t:
                    words.append(Word(float(w["start"]), float(w["end"]), t))
        elif seg.get("text"):
            # edited/legacy segment without word timings: distribute evenly
            tokens = seg["text"].split()
            dur = (seg["end"] - seg["start"]) / max(1, len(tokens))
            for i, t in enumerate(tokens):
                words.append(Word(seg["start"] + i * dur, seg["start"] + (i + 1) * dur, t))
    return words


def sentences(words: list[Word]) -> list[tuple[float, float]]:
    """Sentence boundaries (start, end) built from word punctuation and pauses > 1.2 s."""
    out: list[tuple[float, float]] = []
    start = None
    for i, w in enumerate(words):
        if start is None:
            start = w.start
        nxt = words[i + 1] if i + 1 < len(words) else None
        if SENTENCE_END.search(w.text) or nxt is None or nxt.start - w.end > 1.2:
            out.append((start, w.end))
            start = None
    return out


def snap_boundaries(start: float, end: float, words: list[Word], max_shift: float,
                    min_len: float, max_len: float, media_duration: float) -> tuple[float, float]:
    """Move start/end outward (up to max_shift) so no sentence is cut in half; enforce min/max length."""
    for s, e in sentences(words):
        if s < start < e and start - s <= max_shift:
            start = max(0.0, s - 0.15)
        if s < end < e and e - end <= max_shift:
            end = min(media_duration, e + 0.25)
    if end - start > max_len:
        end = start + max_len
        # don't stop mid-sentence after truncation: cut at the last sentence end inside the limit
        ends = [e for s, e in sentences(words) if start < e <= end]
        if ends and end - ends[-1] < max_len * 0.3:
            end = min(media_duration, ends[-1] + 0.25)
    if end - start < min_len:
        missing = min_len - (end - start)
        start = max(0.0, start - missing / 2)
        end = min(media_duration, start + min_len)
    return round(start, 3), round(end, 3)


def shift_transcript(transcript: dict, offset: float, start: float, end: float) -> dict:
    """Re-base transcript timings to a trimmed clip [start, end] (offset = start)."""
    segs = []
    for seg in transcript.get("segments", []):
        words = [{**w, "start": round(w["start"] - offset, 3), "end": round(w["end"] - offset, 3)}
                 for w in seg.get("words", []) if w["end"] > start and w["start"] < end]
        if seg["end"] <= start or seg["start"] >= end:
            continue
        segs.append({"start": round(max(seg["start"], start) - offset, 3), "end": round(min(seg["end"], end) - offset, 3),
                     "text": " ".join(w["word"].strip() for w in words) if words else seg["text"], "words": words})
    return {**transcript, "segments": segs}


def transcript_text(transcript: dict | None, with_times: bool = False, offset: float = 0.0) -> str:
    if not transcript:
        return ""
    lines = []
    for seg in transcript.get("segments", []):
        if with_times:
            lines.append(f"[{seg['start'] + offset:+.1f}s] {seg['text']}")
        else:
            lines.append(seg["text"])
    return "\n".join(lines)


# ----------------------------------------------------------------------------- ASS rendering

def _ass_color(hex_rgb: str, alpha: int = 0) -> str:
    r, g, b = hex_rgb[1:3], hex_rgb[3:5], hex_rgb[5:7]
    return f"&H{alpha:02X}{b}{g}{r}".upper()


def _ts(t: float) -> str:
    t = max(0.0, t)
    h = int(t // 3600)
    m = int((t % 3600) // 60)
    s = t % 60
    return f"{h}:{m:02d}:{s:05.2f}"


def _escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("{", "(").replace("}", ")").replace("\n", " ")


def chunk_words(words: list[Word], max_words: int, max_gap: float = 0.8) -> list[list[Word]]:
    chunks: list[list[Word]] = []
    cur: list[Word] = []
    for w in words:
        if cur and (len(cur) >= max_words or w.start - cur[-1].end > max_gap or SENTENCE_END.search(cur[-1].text)):
            chunks.append(cur)
            cur = []
        cur.append(w)
    if cur:
        chunks.append(cur)
    return chunks


def is_keyword(word: str) -> bool:
    clean = re.sub(r"[^\w]", "", word.lower(), flags=re.UNICODE)
    return len(clean) >= 5 and clean not in STOPWORDS or word.rstrip(".").endswith("!") or clean.isdigit()


def render_ass(words: list[Word], style: dict, width: int = 1080, height: int = 1920) -> str:
    """style keys: style(clean|highlight|animated|minimal), font, font_size, primary_color, highlight_color,
    outline_color, position(bottom|middle|top), margin_v, max_words_per_line, uppercase."""
    kind = style.get("style", "clean")
    font = style.get("font", "Arial")
    size = int(style.get("font_size", 64))
    primary = style.get("primary_color", "#FFFFFF")
    highlight = style.get("highlight_color", "#FFD400")
    outline = style.get("outline_color", "#000000")
    align = {"bottom": 2, "middle": 5, "top": 8}[style.get("position", "bottom")]
    margin_v = int(style.get("margin_v", 320))
    max_words = int(style.get("max_words_per_line", 5))
    upper = bool(style.get("uppercase", False))

    if kind == "minimal":
        size, outline_w, shadow, bold, back = int(size * 0.75), 0, 0, 0, _ass_color("#000000", 0x60)
        border_style = 3  # opaque box
    else:
        outline_w, shadow, bold, back, border_style = 5 if kind != "clean" else 4, 1, -1, _ass_color("#000000", 0x80), 1
    if kind == "animated":
        max_words = min(max_words, 3)

    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{font},{size},{_ass_color(primary)},{_ass_color(highlight)},{_ass_color(outline)},{back},{bold},0,0,0,100,100,0,0,{border_style},{outline_w},{shadow},{align},60,60,{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines = []
    hl = _ass_color(highlight)
    for chunk in chunk_words(words, max_words):
        start, end = chunk[0].start, max(chunk[-1].end, chunk[0].start + 0.3)
        texts = [_escape(w.text.upper() if upper else w.text) for w in chunk]
        if kind == "clean" or kind == "minimal":
            lines.append(f"Dialogue: 0,{_ts(start)},{_ts(end)},Default,,0,0,0,,{' '.join(texts)}")
        elif kind == "highlight":
            parts = [f"{{\\c{hl}}}{t}{{\\r}}" if is_keyword(w.text) else t for w, t in zip(chunk, texts)]
            lines.append(f"Dialogue: 0,{_ts(start)},{_ts(end)},Default,,0,0,0,,{' '.join(parts)}")
        elif kind == "animated":
            # creator-style: pop-in scale animation, active word highlighted karaoke-style
            for i, w in enumerate(chunk):
                w_end = chunk[i + 1].start if i + 1 < len(chunk) else end
                parts = []
                for j, t in enumerate(texts):
                    parts.append(f"{{\\c{hl}\\fscx112\\fscy112}}{t}{{\\r}}" if j == i else t)
                pop = "{\\fad(40,0)\\t(0,90,\\fscx108\\fscy108)\\t(90,160,\\fscx100\\fscy100)}" if i == 0 else ""
                lines.append(f"Dialogue: 0,{_ts(w.start)},{_ts(max(w_end, w.start + 0.12))},Default,,0,0,0,,{pop}{' '.join(parts)}")
        else:
            raise ValueError(f"unknown subtitle style {kind}")
    return header + "\n".join(lines) + "\n"


def to_srt(words: list[Word], max_words: int = 7) -> str:
    def ts(t: float) -> str:
        ms = int(round(t * 1000))
        return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"
    out = []
    for i, chunk in enumerate(chunk_words(words, max_words), 1):
        out.append(f"{i}\n{ts(chunk[0].start)} --> {ts(chunk[-1].end)}\n{' '.join(w.text for w in chunk)}\n")
    return "\n".join(out)
