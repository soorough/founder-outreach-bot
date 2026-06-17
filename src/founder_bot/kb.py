import os

_FILES = ["profile.md", "proof.md", "reviews.md", "angles.md"]


def load_kb(kb_dir: str) -> str:
    """Concatenate known knowledge-base markdown files into one prompt-ready string."""
    parts: list[str] = []
    for filename in _FILES:
        path = os.path.join(kb_dir, filename)
        if not os.path.isfile(path):
            continue
        with open(path, "r", encoding="utf-8") as handle:
            content = handle.read().strip()
        if content:
            section = os.path.splitext(filename)[0]
            parts.append(f"# {section}\n\n{content}")
    return "\n\n".join(parts)
