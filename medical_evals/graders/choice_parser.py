"""Parse single-choice answers from model completions."""

import re
from typing import Optional


def parse_choice(text: str) -> Optional[str]:
    """Return one unambiguous A/B/C/D choice, or ``None``."""
    normalized = str(text).strip().upper()
    think_end = normalized.rfind("</THINK>")
    if think_end >= 0:
        normalized = normalized[think_end + len("</THINK>") :].strip()
        final_choice = re.match(
            r"^\s*(?:\*\*)?\s*([ABCD])(?:\s*(?:[.)。:：]|\*\*)|\s*$)",
            normalized,
        )
        if final_choice:
            return final_choice.group(1)
    if re.fullmatch(r"[ABCD]", normalized):
        return normalized
    marked = re.findall(
        r"(?:答案|选项|选择|最终答案)\s*(?:是|为)?\s*(?:：|:)?\s*([ABCD])\b",
        normalized,
    )
    if len(set(marked)) == 1:
        return marked[0]
    return None
