"""Markdown auto-fixer: normalize headings, blank lines, tables, and more."""

import re
from pathlib import Path
from typing import Optional
from dataclasses import dataclass


@dataclass
class FixResult:
    """Result of fixing a file."""
    file: str
    original_lines: int
    fixed_lines: int
    changes: list[str]
    modified: bool = False


def fix_file(filepath: str, write: bool = True) -> FixResult:
    """
    Auto-fix common Markdown issues in a file.

    Fixes:
    - Trailing whitespace
    - Consecutive blank lines (max 1)
    - Heading spacing (ensure space after #)
    - Table alignment
    - Code fence normalization
    - List indentation (normalize to 2-space)

    Args:
        filepath: Path to Markdown file
        write: If True, overwrite the file; if False, dry run
    """
    path = Path(filepath)
    content = path.read_text(encoding="utf-8", errors="replace")
    original_content = content
    lines = content.split("\n")
    changes: list[str] = []

    fixed_lines = []
    in_code_block = False
    consecutive_blanks = 0
    i = 0

    while i < len(lines):
        line = lines[i]

        # Track code blocks
        stripped = line.strip()
        if stripped.startswith("```"):
            if in_code_block:
                in_code_block = False
            else:
                in_code_block = True
                # Normalize fence (use ```)
                indent = len(line) - len(line.lstrip())
                prefix = " " * indent
                fence_lang = stripped[3:].strip()
                old_line = line
                line = prefix + "```" + (fence_lang if fence_lang else "")
                if line != old_line:
                    changes.append(f"L{i+1}: Normalized code fence")

            fixed_lines.append(line)
            i += 1
            continue

        if in_code_block:
            fixed_lines.append(line)
            i += 1
            continue

        # Fix trailing whitespace (preserve intentional line breaks: 2+ trailing spaces)
        if line.rstrip() != line:
            trailing = len(line) - len(line.rstrip())
            if trailing >= 2 and line.strip():
                # Intentional line break, normalize to exactly 2 spaces
                old_line = line
                line = line.rstrip() + "  "
                if line != old_line:
                    changes.append(f"L{i+1}: Normalized line break spaces")
            elif line.strip():
                old_line = line
                line = line.rstrip()
                if line != old_line:
                    changes.append(f"L{i+1}: Removed trailing whitespace")

        # Fix consecutive blank lines
        if not line.strip():
            consecutive_blanks += 1
            if consecutive_blanks > 2:
                changes.append(f"L{i+1}: Removed extra blank line")
                i += 1
                continue
        else:
            consecutive_blanks = 0

        # Fix heading spacing
        heading_match = re.match(r'^(#{1,6})([^\s#])', line)
        if heading_match:
            old_line = line
            hashes = heading_match.group(1)
            rest = line[len(hashes):]
            line = hashes + " " + rest
            changes.append(f"L{i+1}: Added space after heading marker")

        # Remove trailing hashes from headings
        heading_trailing = re.match(r'^(#{1,6}\s+.*?)\s+#+\s*$', line)
        if heading_trailing:
            old_line = line
            line = heading_trailing.group(1)
            changes.append(f"L{i+1}: Removed trailing heading hashes")

        # Fix list indentation (normalize odd indentation)
        list_match = re.match(r'^(\s+)([-*+]|\d+\.)\s', line)
        if list_match:
            indent = len(list_match.group(1))
            if indent % 2 != 0:
                # Round to nearest even
                new_indent = ((indent + 1) // 2) * 2
                line = " " * new_indent + line.lstrip()
                changes.append(f"L{i+1}: Fixed list indentation ({indent} -> {new_indent})")

        fixed_lines.append(line)
        i += 1

    # Ensure file ends with single newline
    while fixed_lines and not fixed_lines[-1].strip():
        fixed_lines.pop()
    fixed_lines.append("")

    fixed_content = "\n".join(fixed_lines)
    modified = fixed_content != original_content

    result = FixResult(
        file=filepath,
        original_lines=len(lines),
        fixed_lines=len(fixed_lines),
        changes=changes,
        modified=modified,
    )

    if write and modified:
        path.write_text(fixed_content, encoding="utf-8")

    return result


def fix_table(table_lines: list[str]) -> list[str]:
    """
    Fix table alignment: align columns by padding cells.

    Args:
        table_lines: Lines that form a markdown table (including separator)
    """
    if len(table_lines) < 2:
        return table_lines

    # Parse cells
    rows = []
    separator_idx = -1
    for i, line in enumerate(table_lines):
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if i > 0 and all(re.match(r'^:?-+:?$', c.strip()) for c in cells if c.strip()):
            separator_idx = i
        rows.append(cells)

    if separator_idx < 0 or not rows:
        return table_lines

    # Find max width per column
    num_cols = max(len(row) for row in rows)
    col_widths = [0] * num_cols
    for row in rows:
        for j, cell in enumerate(row):
            if j < num_cols:
                col_widths[j] = max(col_widths[j], len(cell))

    # Ensure minimum width of 3 for separator
    col_widths = [max(w, 3) for w in col_widths]

    # Rebuild table
    fixed = []
    for i, row in enumerate(rows):
        cells = []
        for j in range(num_cols):
            cell = row[j] if j < len(row) else ""
            if i == separator_idx:
                # Separator: preserve alignment markers
                original = row[j] if j < len(row) else "---"
                left_align = original.startswith(":")
                right_align = original.endswith(":")
                if left_align and right_align:
                    cells.append(":" + "-" * (col_widths[j] - 2) + ":")
                elif right_align:
                    cells.append("-" * (col_widths[j] - 1) + ":")
                elif left_align:
                    cells.append(":" + "-" * (col_widths[j] - 1))
                else:
                    cells.append("-" * col_widths[j])
            else:
                cells.append(cell.ljust(col_widths[j]))
        fixed.append("| " + " | ".join(cells) + " |")

    return fixed


def fix_tables_in_content(content: str) -> str:
    """Find and fix all tables in markdown content."""
    lines = content.split("\n")
    result = []
    table_buffer = []
    in_table = False

    for line in lines:
        is_table_line = line.strip().startswith("|") and line.strip().endswith("|")

        if is_table_line:
            in_table = True
            table_buffer.append(line)
        else:
            if in_table and table_buffer:
                # Process the accumulated table
                fixed = fix_table(table_buffer)
                result.extend(fixed)
                table_buffer = []
                in_table = False
            result.append(line)

    # Handle table at end of file
    if table_buffer:
        fixed = fix_table(table_buffer)
        result.extend(fixed)

    return "\n".join(result)


def fix_files(filepaths: list[str], write: bool = True) -> list[FixResult]:
    """Fix multiple Markdown files."""
    results = []
    for filepath in filepaths:
        result = fix_file(filepath, write=write)
        results.append(result)
    return results
