import os

_FILES = ["profile.md", "proof.md", "reviews.md", "angles.md"]


def load_kb(kb_dir: str) -> str:
    """Concatenate knowledge-base markdown into one prompt-ready string.

    For each section, a gitignored ``<name>.local.md`` (your real, private
    content) takes precedence over the committed ``<name>.md`` template.
    """
    parts: list[str] = []
    for filename in _FILES:
        base, ext = os.path.splitext(filename)
        local = os.path.join(kb_dir, f"{base}.local{ext}")
        path = local if os.path.isfile(local) else os.path.join(kb_dir, filename)
        if not os.path.isfile(path):
            continue
        with open(path, "r", encoding="utf-8") as handle:
            content = handle.read().strip()
        if content:
            section = os.path.splitext(filename)[0]
            parts.append(f"# {section}\n\n{content}")
    return "\n\n".join(parts)
