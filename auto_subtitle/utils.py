import os
import argparse
from typing import Iterator, TextIO


def str2bool(string):
    string = string.lower()
    str2val = {"true": True, "false": False}

    if string in str2val:
        return str2val[string]
    else:
        raise ValueError(
            f"Expected one of {set(str2val.keys())}, got {string}")


def format_timestamp(seconds: float, always_include_hours: bool = False):
    assert seconds >= 0, "non-negative timestamp expected"
    milliseconds = round(seconds * 1000.0)

    hours = milliseconds // 3_600_000
    milliseconds -= hours * 3_600_000

    minutes = milliseconds // 60_000
    milliseconds -= minutes * 60_000

    seconds = milliseconds // 1_000
    milliseconds -= seconds * 1_000

    hours_marker = f"{hours:02d}:" if always_include_hours or hours > 0 else ""
    return f"{hours_marker}{minutes:02d}:{seconds:02d},{milliseconds:03d}"


def write_srt(transcript: Iterator[dict], file: TextIO):
    for i, segment in enumerate(transcript, start=1):
        print(
            f"{i}\n"
            f"{format_timestamp(segment['start'], always_include_hours=True)} --> "
            f"{format_timestamp(segment['end'], always_include_hours=True)}\n"
            f"{segment['text'].strip().replace('-->', '->')}\n",
            file=file,
            flush=True,
        )


def _break_lines(tokens: list, width: int) -> list:
    """Split tokens into lines of at most `width` characters, using as few
    lines as possible and, among those, the most evenly filled ones.
    Returns the index ranges (start, end) of each line."""
    n = len(tokens)
    # best[i] = (line count, raggedness, next break) for tokens[i:]
    best = [None] * n + [(0, 0, n)]
    for i in range(n - 1, -1, -1):
        length = -1
        for j in range(i + 1, n + 1):
            length += len(tokens[j - 1]) + 1
            if length > width and j > i + 1:
                break  # a single over-long word still gets a line of its own
            lines, cost, _ = best[j]
            candidate = (lines + 1, cost + max(width - length, 0) ** 2, j)
            if best[i] is None or candidate[:2] < best[i][:2]:
                best[i] = candidate

    ranges, i = [], 0
    while i < n:
        ranges.append((i, best[i][2]))
        i = best[i][2]
    return ranges


def split_segments(segments: Iterator[dict], max_lines: int, max_line_width: int) -> list:
    """Split Whisper segments into cues of at most `max_lines` lines of
    `max_line_width` characters (0 = no limit), using word-level timestamps
    for timing. Cues never span two segments, so pauses between segments are
    kept. Each cue keeps its words in "lines" for word-by-word animation."""
    cues = []
    for segment in segments:
        words = [w for w in segment.get("words") or [] if w["word"].strip()]
        if not words:
            cues.append(segment)
            continue

        tokens = [w["word"].strip() for w in words]
        lines = _break_lines(tokens, max_line_width or float("inf"))
        for k in range(0, len(lines), max_lines):
            group = lines[k:k + max_lines]
            first, last = group[0][0], group[-1][1] - 1
            cues.append({
                "start": words[first]["start"],
                "end": words[last]["end"],
                "text": "\n".join(" ".join(tokens[a:b]) for a, b in group),
                "lines": [[{**words[i], "word": tokens[i]} for i in range(a, b)]
                          for a, b in group],
            })
    return cues


def hex2ass(colour: str) -> str:
    """Convert '#RRGGBB' or '#RRGGBBAA' (AA = opacity, FF = opaque) to ASS '&HAABBGGRR'."""
    value = colour.strip().lstrip("#")
    if len(value) not in (6, 8) or any(c not in "0123456789abcdefABCDEF" for c in value):
        raise argparse.ArgumentTypeError(
            f"expected a hex colour like '#1B2A4A' or '#1B2A4AFF', got {colour}")

    r, g, b = value[0:2], value[2:4], value[4:6]
    opacity = int(value[6:8], 16) if len(value) == 8 else 0xFF
    # ASS stores transparency, not opacity: 00 = opaque, FF = invisible
    return f"&H{0xFF - opacity:02X}{b}{g}{r}".upper()


# Subtitle positions mapped to ASS (v4+) numpad-style alignment values
POSITIONS = {
    "bottom-left": 1, "bottom": 2, "bottom-right": 3,
    "left": 4, "center": 5, "right": 6,
    "top-left": 7, "top": 8, "top-right": 9,
}

# ffmpeg's subtitles filter interprets force_style's Alignment using the legacy
# SSA scheme (1-3 bottom, +4 top, +8 middle), so convert before using it there.
LEGACY_ALIGNMENT = {1: 1, 2: 2, 3: 3, 4: 9, 5: 10, 6: 11, 7: 5, 8: 6, 9: 7}


def filename(path):
    return os.path.splitext(os.path.basename(path))[0]
