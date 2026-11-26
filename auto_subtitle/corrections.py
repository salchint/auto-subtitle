"""Fix recurring transcription mistakes with a simple replacement list.

The file holds one rule per line, `wrong words = right words`:

    # names the model keeps getting wrong
    costa rika = Costa Rica
    Costarica  = Costa Rica
    um =

Matching ignores case and surrounding punctuation and only matches whole
words. An empty right-hand side removes the words. Rules are applied to the
word-level timings too, so corrected words stay in sync for animations.
"""
import re
from typing import List, Tuple

Rule = Tuple[List[str], List[str]]

PUNCTUATION = "\"'“”‘’¿¡([{-.,!?;:)]}…。，！？：、"


def load_replacements(path: str) -> List[Rule]:
    rules = []
    with open(path, encoding="utf-8") as file:
        for number, line in enumerate(file, start=1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            wrong, sep, right = line.partition("=")
            if not sep or not wrong.strip():
                raise ValueError(
                    f"{path}:{number}: expected 'wrong words = right words', got {line!r}")
            rules.append(([w.lower() for w in wrong.split()], right.split()))
    # try longer patterns first, so 'costa rika' wins over a rule for 'rika'
    rules.sort(key=lambda rule: -len(rule[0]))
    return rules


def apply_replacements(segments: List[dict], rules: List[Rule]) -> List[dict]:
    if not rules:
        return segments
    corrected = [{**segment,
                  "text": _replace_text(segment["text"], rules),
                  **({"words": _replace_words(segment["words"], rules)} if segment.get("words") else {})}
                 for segment in segments]
    # drop segments that consisted only of removed words
    return [segment for segment in corrected if segment["text"].strip()]


def _replace_text(text: str, rules: List[Rule]) -> str:
    for wrong, right in rules:
        pattern = r"(?<!\w)" + r"\s+".join(map(re.escape, wrong)) + r"(?!\w)"
        if not right:
            # a removed word takes its trailing comma etc. with it: "Um, so" -> "so"
            pattern += r"[,;:]?\s*"
        text = re.sub(pattern, lambda _: " ".join(right), text, flags=re.IGNORECASE)
    text = re.sub(r"\s{2,}", " ", text)
    # punctuation orphaned by a removed word: drop it after another sentence
    # end ("works. ." -> "works."), otherwise reattach it ("I think ." -> "I think.")
    text = re.sub(r"(?<=[.!?])\s+[.!?,;:]+(?=\s|$)", "", text)
    text = re.sub(r"\s+([.!?,;:]+)(?=\s|$)", r"\1", text)
    return " " + text.strip()


def _split_punctuation(token: str):
    core = token.strip().strip(PUNCTUATION)
    stripped = token.strip()
    if not core:
        return stripped, "", ""
    start = stripped.index(core)
    return stripped[:start], core, stripped[start + len(core):]


def _replace_words(words: List[dict], rules: List[Rule]) -> List[dict]:
    out, i = [], 0
    while i < len(words):
        for wrong, right in rules:
            window = words[i:i + len(wrong)]
            if len(window) == len(wrong) and all(
                    _split_punctuation(w["word"])[1].lower() == p for w, p in zip(window, wrong)):
                trail = _split_punctuation(window[-1]["word"])[2]
                if not right and out and any(c in trail for c in ".!?") \
                        and not out[-1]["word"].rstrip().endswith((".", "!", "?")):
                    # keep the sentence end of a removed word: "I think um." -> "I think."
                    out[-1] = {**out[-1], "word": out[-1]["word"].rstrip().rstrip(",;:") + trail}
                out.extend(_respell(window, right))
                i += len(wrong)
                break
        else:
            out.append(words[i])
            i += 1
    return out


def _respell(window: List[dict], right: List[str]) -> List[dict]:
    """Replace the matched words with one word spanning their time, keeping
    outer punctuation. A multi-word replacement such as "Costa Rica" stays a
    single unit, so it is never split across lines and highlights as one."""
    if not right:
        return []
    lead = _split_punctuation(window[0]["word"])[0]
    trail = _split_punctuation(window[-1]["word"])[2]
    return [{
        "word": " " + lead + " ".join(right) + trail,
        "start": window[0]["start"],
        "end": window[-1]["end"],
        "probability": min(w.get("probability", 1.0) for w in window),
    }]
