"""Docs mapper: build a tree of .md files, detect orphans, report coverage."""

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from .links import extract_links


@dataclass
class DocNode:
    """A documentation file node."""
    path: str
    relative_path: str
    title: Optional[str] = None
    headings: int = 0
    word_count: int = 0
    links_out: list[str] = field(default_factory=list)  # relative paths this file links to
    links_in: list[str] = field(default_factory=list)  # files that link to this file
    is_orphan: bool = False


@dataclass
class DocsMap:
    """Map of documentation files in a directory."""
    root_dir: str
    nodes: dict[str, DocNode] = field(default_factory=dict)  # relative_path -> DocNode

    @property
    def total_files(self) -> int:
        return len(self.nodes)

    @property
    def orphan_files(self) -> list[DocNode]:
        return [n for n in self.nodes.values() if n.is_orphan]

    @property
    def total_words(self) -> int:
        return sum(n.word_count for n in self.nodes.values())

    def summary(self) -> dict:
        return {
            "root_dir": self.root_dir,
            "total_files": self.total_files,
            "orphan_files": len(self.orphan_files),
            "total_words": self.total_words,
            "total_headings": sum(n.headings for n in self.nodes.values()),
        }


def _extract_title(content: str) -> Optional[str]:
    """Extract the first h1 heading as the document title."""
    for line in content.split("\n"):
        match = re.match(r'^#\s+(.+)', line)
        if match:
            return match.group(1).strip()
    return None


def _count_words(content: str) -> int:
    """Count words in Markdown content (excluding code blocks)."""
    in_code_block = False
    words = 0
    for line in content.split("\n"):
        if line.strip().startswith("```"):
            in_code_block = not in_code_block
            continue
        if not in_code_block:
            # Remove Markdown syntax for cleaner count
            clean = re.sub(r'[#*_`\[\]\(\)!|>]', ' ', line)
            words += len(clean.split())
    return words


def _count_headings(content: str) -> int:
    """Count headings in Markdown content."""
    count = 0
    in_code_block = False
    for line in content.split("\n"):
        if line.strip().startswith("```"):
            in_code_block = not in_code_block
            continue
        if not in_code_block and re.match(r'^#{1,6}\s+', line):
            count += 1
    return count


def build_docs_map(
    directory: str,
    recursive: bool = True,
    exclude_patterns: Optional[list[str]] = None,
) -> DocsMap:
    """
    Build a map of all Markdown files in a directory.

    Args:
        directory: Root directory to scan
        recursive: Include subdirectories
        exclude_patterns: Glob patterns to exclude (e.g., ["node_modules/**"])
    """
    root = Path(directory).resolve()
    docs_map = DocsMap(root_dir=str(root))

    exclude = set(exclude_patterns or [])

    # Find all .md files
    if recursive:
        md_files = list(root.rglob("*.md"))
    else:
        md_files = list(root.glob("*.md"))

    # Filter excludes
    filtered_files = []
    for f in md_files:
        relative = str(f.relative_to(root))
        skip = False
        for pattern in exclude:
            if Path(relative).match(pattern):
                skip = True
                break
        if not skip:
            filtered_files.append(f)

    # Build nodes
    for filepath in filtered_files:
        relative = str(filepath.relative_to(root))
        content = filepath.read_text(encoding="utf-8", errors="replace")

        node = DocNode(
            path=str(filepath),
            relative_path=relative,
            title=_extract_title(content),
            headings=_count_headings(content),
            word_count=_count_words(content),
        )

        # Extract outgoing links
        links = extract_links(str(filepath))
        for link in links:
            if not link.is_external:
                url = link.url.split("#")[0]
                if url:
                    # Resolve relative path
                    target = (filepath.parent / url).resolve()
                    try:
                        target_relative = str(target.relative_to(root))
                        node.links_out.append(target_relative)
                    except ValueError:
                        pass  # Link points outside docs dir

        docs_map.nodes[relative] = node

    # Calculate incoming links and detect orphans
    all_relative_paths = set(docs_map.nodes.keys())

    for rel_path, node in docs_map.nodes.items():
        for target in node.links_out:
            if target in docs_map.nodes:
                docs_map.nodes[target].links_in.append(rel_path)

    # Mark orphans (files not linked from anywhere else)
    # README.md and index.md are not considered orphans
    root_files = {"readme.md", "index.md", "changelog.md", "contributing.md", "license.md"}

    for rel_path, node in docs_map.nodes.items():
        if rel_path.lower() in root_files:
            continue
        if not node.links_in:
            node.is_orphan = True

    return docs_map


def format_docs_tree(docs_map: DocsMap) -> str:
    """Format the docs map as an ASCII tree."""
    lines = []
    lines.append(f"Docs Map: {docs_map.root_dir}")
    lines.append(f"Files: {docs_map.total_files} | Words: {docs_map.total_words:,} | Orphans: {len(docs_map.orphan_files)}")
    lines.append("")

    # Sort by path
    sorted_nodes = sorted(docs_map.nodes.values(), key=lambda n: n.relative_path)

    for node in sorted_nodes:
        # Build display
        title = node.title or "(no title)"
        orphan_tag = " [ORPHAN]" if node.is_orphan else ""
        in_count = len(node.links_in)
        out_count = len(node.links_out)

        lines.append(f"  {node.relative_path}")
        lines.append(f"    Title: {title}{orphan_tag}")
        lines.append(f"    Words: {node.word_count:,} | Headings: {node.headings} | Links: {out_count} out, {in_count} in")

    if docs_map.orphan_files:
        lines.append("")
        lines.append("Orphan Files (not linked from anywhere):")
        for node in docs_map.orphan_files:
            lines.append(f"  - {node.relative_path}")

    return "\n".join(lines)
