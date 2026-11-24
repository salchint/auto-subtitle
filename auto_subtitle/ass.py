"""Write animated subtitles in Advanced SubStation Alpha (.ass) format.

libass (used by ffmpeg's subtitles filter) understands ASS override tags, which
lets us colour, fade and scale individual words over time.
"""
from typing import Iterator, TextIO

# Sizes in this tool are given relative to a 288px-high canvas, like ffmpeg's
# default for converted SRT subtitles, so both renderings look the same.
REFERENCE_HEIGHT = 288

# Pop animation: each word grows from 70% past full size, then settles.
POP_IN_MS, POP_SETTLE_MS = 80, 150


def ass_time(seconds: float) -> str:
    cs = round(max(seconds, 0) * 100)
    h, cs = divmod(cs, 360_000)
    m, cs = divmod(cs, 6_000)
    s, cs = divmod(cs, 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def escape(text: str) -> str:
    # braces start override blocks and backslashes start tags in ASS
    return text.replace("\\", "").replace("{", "(").replace("}", ")")


def split_colour(ass_colour: str):
    """'&HAABBGGRR' -> ('&HBBGGRR&', '&HAA&') for \\c and \\1a override tags."""
    return f"&H{ass_colour[4:]}&", f"&H{ass_colour[2:4]}&"


def write_ass(cues: Iterator[dict], file: TextIO, style: dict,
              width: int, height: int, animation: str):
    scale = height / REFERENCE_HEIGHT
    margin = round(10 * scale)
    print(
        "[Script Info]\n"
        "ScriptType: v4.00+\n"
        f"PlayResX: {width}\n"
        f"PlayResY: {height}\n"
        "ScaledBorderAndShadow: yes\n"
        "WrapStyle: 0\n"
        "\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, "
        "BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, "
        "BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
        # BorderStyle 4 (a libass extension) draws one box in BackColour behind
        # the whole event. Unlike BorderStyle 3, which boxes each differently
        # styled run separately, it leaves no seams where translucent boxes
        # overlap. The outline only pads the box, so it is made invisible.
        f"Style: Default,{style['font']},{style['font_size'] * scale:.1f},"
        f"{style['font_colour']},{style['font_colour']},&HFF000000,"
        f"{style['background_colour']},0,0,0,0,100,100,0,0,4,{scale:.2f},0,"
        f"{style['alignment']},{margin},{margin},{margin},1\n"
        "\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
        file=file,
    )

    def event(start, end, text, layer=0):
        print(f"Dialogue: {layer},{ass_time(start)},{ass_time(end)},Default,,0,0,0,,{text}",
              file=file)

    for cue in cues:
        lines = cue.get("lines")
        if not lines or animation == "none":
            event(cue["start"], cue["end"], escape(cue["text"].strip()).replace("\n", "\\N"))
            continue

        words = [w for line in lines for w in line]
        # each word's event lasts until the next word starts (or the cue ends)
        times = [max(w["start"], cue["start"]) for w in words] + [cue["end"]]
        for i in range(len(words)):
            start, end = times[i], max(times[i + 1], times[i])
            if animation == "karaoke":
                event(start, end, karaoke_text(lines, i, style))
            elif animation == "pop":
                # Layer 0: the line so far, with a fixed layout; unspoken words
                # (and the popping word) take up space but are invisible.
                event(start, end, pop_base_text(lines, i), layer=0)
                # Layer 1: only the popping word. Every other word is invisible
                # but still laid out, so the word scales around its own centre
                # without nudging the rest of the line.
                event(start, end, pop_word_text(lines, i, style), layer=1)


def _render(lines, word_tags) -> str:
    """Join words into ASS text, letting word_tags(index) prefix each word."""
    out, index = [], 0
    for line in lines:
        parts = []
        for word in line:
            parts.append(word_tags(index) + escape(word["word"]))
            index += 1
        out.append(" ".join(parts))
    return "\\N".join(out)


def karaoke_text(lines, active, style):
    highlight, _ = split_colour(style["highlight_colour"])
    normal, _ = split_colour(style["font_colour"])
    return _render(lines, lambda i:
                   f"{{\\c{highlight}}}" if i == active else
                   f"{{\\c{normal}}}" if i == active + 1 else "")


def pop_base_text(lines, active):
    # hide text from the active word on, but keep the box behind it
    return _render(lines, lambda i: "{\\1a&HFF&}" if i == active else "")


def pop_word_text(lines, active, style):
    _, alpha = split_colour(style["font_colour"])

    def tags(i):
        # \4a hides this layer's box; the base layer already draws it
        prefix = "\\4a&HFF&" if i == 0 else ""
        if i == 0 and active > 0:
            return f"{{{prefix}\\alpha&HFF&}}"
        if i == active:
            return (
                f"{{{prefix}\\1a&HFF&\\fscx70\\fscy70"
                f"\\t(0,{POP_IN_MS},\\1a{alpha}\\fscx112\\fscy112)"
                f"\\t({POP_IN_MS},{POP_SETTLE_MS},\\fscx100\\fscy100)}}"
            )
        if i == active + 1:
            # back to normal size so later (invisible) words don't shift the line
            return "{\\alpha&HFF&\\fscx100\\fscy100}"
        return ""
    return _render(lines, tags)
