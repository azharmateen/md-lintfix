"""Table of Contents generator for Markdown files."""

import re
from pathlib import Path
from typing import Optional


# TOC markers
TOC_START = "<!-- toc -->"
TOC_END = "<!-- /toc -->"


def extract_headings(content: str, max_depth: int = 3) -> list[tuple[int, str]]:
    """
    Extract headings from Markdown content.

    Args:
        content: Markdown content
        max_depth: Maximum heading depth (1-6)

    Returns:
        List of (level, text) tuples
    """
    headings = []
    in_code_block = False

    for line in content.split("\n"):
        stripped = line.strip()

        # Track code blocks
        if stripped.startswith("```"):
            in_code_block = not in_code_block
            continue

        if in_code_block:
            continue

        # Match ATX headings
        match = re.match(r'^(#{1,6})\s+(.+)', line)
        if match:
            level = len(match.group(1))
            if level <= max_depth:
                text = match.group(2).strip()
                # Remove trailing hashes
                text = re.sub(r'\s+#+\s*$', '', text)
                # Remove inline code for anchor but keep for display
                headings.append((level, text))

    return headings


def heading_to_anchor(text: str) -> str:
    """
    Convert heading text to GitHub-compatible anchor.

    Rules:
    - Lowercase
    - Remove special characters except hyphens and spaces
    - Replace spaces with hyphens
    - Remove leading/trailing hyphens
    """
    # Remove Markdown formatting
    anchor = re.sub(r'[`*_~]', '', text)
    # Remove HTML tags
    anchor = re.sub(r'<[^>]+>', '', anchor)
    # Remove images
    anchor = re.sub(r'!\[[^\]]*\]\([^)]*\)', '', anchor)
    # Keep link text
    anchor = re.sub(r'\[([^\]]*)\]\([^)]*\)', r'\1', anchor)
    # Lowercase
    anchor = anchor.lower()
    # Replace special chars with nothing, keep alphanumeric, spaces, hyphens
    anchor = re.sub(r'[^\w\s-]', '', anchor)
    # Replace spaces with hyphens
    anchor = re.sub(r'\s+', '-', anchor)
    # Remove leading/trailing hyphens
    anchor = anchor.strip('-')

    return anchor


def generate_toc(
    content: str,
    max_depth: int = 3,
    min_depth: int = 2,
    bullet: str = "-",
    indent: int = 2,
) -> str:
    """
    Generate a Table of Contents from Markdown content.

    Args:
        content: Markdown content
        max_depth: Maximum heading depth to include
        min_depth: Minimum heading depth to include (skip h1 title by default)
        bullet: List bullet character
        indent: Indentation per level
    """
    headings = extract_headings(content, max_depth)

    # Filter by min depth
    headings = [(level, text) for level, text in headings if level >= min_depth]

    if not headings:
        return ""

    # Track duplicate anchors (GitHub adds -1, -2, etc.)
    anchor_counts: dict[str, int] = {}
    lines = []

    for level, text in headings:
        anchor = heading_to_anchor(text)

        # Handle duplicates
        if anchor in anchor_counts:
            anchor_counts[anchor] += 1
            anchor = f"{anchor}-{anchor_counts[anchor]}"
        else:
            anchor_counts[anchor] = 0

        # Calculate indentation relative to min_depth
        depth = level - min_depth
        prefix = " " * (depth * indent)

        lines.append(f"{prefix}{bullet} [{text}](#{anchor})")

    return "\n".join(lines)


def insert_toc(
    filepath: str,
    max_depth: int = 3,
    min_depth: int = 2,
    write: bool = True,
) -> tuple[str, bool]:
    """
    Insert or update TOC in a Markdown file.

    Looks for <!-- toc --> and <!-- /toc --> markers.
    If not found, inserts after the first h1 heading.

    Args:
        filepath: Path to Markdown file
        max_depth: Max heading depth
        min_depth: Min heading depth
        write: Write changes to file

    Returns:
        (toc_content, was_modified)
    """
    path = Path(filepath)
    content = path.read_text(encoding="utf-8", errors="replace")

    toc = generate_toc(content, max_depth=max_depth, min_depth=min_depth)
    if not toc:
        return "", False

    toc_block = f"{TOC_START}\n\n{toc}\n\n{TOC_END}"

    # Check if markers exist
    if TOC_START in content and TOC_END in content:
        # Replace existing TOC
        pattern = re.compile(
            re.escape(TOC_START) + r'.*?' + re.escape(TOC_END),
            re.DOTALL,
        )
        new_content = pattern.sub(toc_block, content)
    else:
        # Insert after first h1
        lines = content.split("\n")
        insert_idx = 0
        for i, line in enumerate(lines):
            if re.match(r'^#\s+', line):
                insert_idx = i + 1
                break

        # Insert with blank lines
        lines.insert(insert_idx, "")
        lines.insert(insert_idx + 1, toc_block)
        lines.insert(insert_idx + 2, "")
        new_content = "\n".join(lines)

    modified = new_content != content

    if write and modified:
        path.write_text(new_content, encoding="utf-8")

    return toc, modified
