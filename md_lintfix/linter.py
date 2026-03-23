"""Markdown linter: check for common issues and style violations."""

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class LintIssue:
    """A single lint issue."""
    file: str
    line: int
    column: int
    rule: str
    severity: str  # "error", "warning", "info"
    message: str
    fixable: bool = False

    def __str__(self):
        return f"{self.file}:{self.line}:{self.column} [{self.rule}] {self.message}"


@dataclass
class LintConfig:
    """Linter configuration."""
    max_line_length: int = 120
    max_heading_length: int = 80
    allow_duplicate_headings: bool = False
    require_code_fence_lang: bool = True
    max_consecutive_blank_lines: int = 1
    heading_style: str = "atx"  # "atx" (#) or "setext" (underlines)
    list_indent: int = 2
    check_trailing_whitespace: bool = True
    first_heading_level: int = 1  # expected first heading level


@dataclass
class LintResult:
    """Result of linting one or more files."""
    issues: list[LintIssue] = field(default_factory=list)
    files_checked: int = 0

    @property
    def error_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == "error")

    @property
    def warning_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == "warning")

    @property
    def fixable_count(self) -> int:
        return sum(1 for i in self.issues if i.fixable)

    @property
    def passed(self) -> bool:
        return self.error_count == 0

    def summary(self) -> dict:
        return {
            "files_checked": self.files_checked,
            "total_issues": len(self.issues),
            "errors": self.error_count,
            "warnings": self.warning_count,
            "fixable": self.fixable_count,
        }


def lint_file(filepath: str, config: Optional[LintConfig] = None) -> list[LintIssue]:
    """Lint a single Markdown file."""
    if config is None:
        config = LintConfig()

    path = Path(filepath)
    content = path.read_text(encoding="utf-8", errors="replace")
    lines = content.split("\n")
    issues: list[LintIssue] = []

    headings = []
    in_code_block = False
    consecutive_blanks = 0
    prev_list_indent = -1

    for i, line in enumerate(lines):
        lineno = i + 1

        # Track code blocks
        if line.strip().startswith("```"):
            if in_code_block:
                in_code_block = False
                continue
            else:
                in_code_block = True
                # Check for language tag
                fence_content = line.strip()[3:].strip()
                if config.require_code_fence_lang and not fence_content:
                    issues.append(LintIssue(
                        file=filepath, line=lineno, column=1,
                        rule="code-fence-lang",
                        severity="warning",
                        message="Code fence missing language tag",
                        fixable=False,
                    ))
                continue

        if in_code_block:
            continue

        # Trailing whitespace
        if config.check_trailing_whitespace and line.rstrip() != line and line.strip():
            issues.append(LintIssue(
                file=filepath, line=lineno, column=len(line.rstrip()) + 1,
                rule="trailing-whitespace",
                severity="warning",
                message="Trailing whitespace",
                fixable=True,
            ))

        # Line length
        if len(line) > config.max_line_length and not line.strip().startswith("|"):
            # Skip tables and links
            if not re.match(r'^\s*\[.*\]\(.*\)\s*$', line):
                issues.append(LintIssue(
                    file=filepath, line=lineno, column=config.max_line_length + 1,
                    rule="line-length",
                    severity="info",
                    message=f"Line length {len(line)} exceeds {config.max_line_length}",
                    fixable=False,
                ))

        # Consecutive blank lines
        if not line.strip():
            consecutive_blanks += 1
            if consecutive_blanks > config.max_consecutive_blank_lines + 1:
                issues.append(LintIssue(
                    file=filepath, line=lineno, column=1,
                    rule="consecutive-blanks",
                    severity="warning",
                    message=f"More than {config.max_consecutive_blank_lines} consecutive blank lines",
                    fixable=True,
                ))
        else:
            consecutive_blanks = 0

        # Heading checks
        heading_match = re.match(r'^(#{1,6})\s+(.*)', line)
        if heading_match:
            level = len(heading_match.group(1))
            heading_text = heading_match.group(2).rstrip()

            # Remove trailing # from headings
            heading_text = re.sub(r'\s+#+\s*$', '', heading_text)

            headings.append((lineno, level, heading_text))

            # Heading length
            if len(heading_text) > config.max_heading_length:
                issues.append(LintIssue(
                    file=filepath, line=lineno, column=1,
                    rule="heading-length",
                    severity="warning",
                    message=f"Heading too long ({len(heading_text)} > {config.max_heading_length})",
                    fixable=False,
                ))

            # No space after #
            if re.match(r'^#{1,6}[^\s#]', line):
                issues.append(LintIssue(
                    file=filepath, line=lineno, column=level + 1,
                    rule="heading-space",
                    severity="error",
                    message="No space after heading marker",
                    fixable=True,
                ))

        # List indentation
        list_match = re.match(r'^(\s*)([-*+]|\d+\.)\s', line)
        if list_match:
            indent = len(list_match.group(1))
            if indent > 0 and indent % config.list_indent != 0:
                issues.append(LintIssue(
                    file=filepath, line=lineno, column=1,
                    rule="list-indent",
                    severity="warning",
                    message=f"List indent {indent} not a multiple of {config.list_indent}",
                    fixable=True,
                ))

    # Heading hierarchy check
    _check_heading_hierarchy(filepath, headings, config, issues)

    # Duplicate headings check
    if not config.allow_duplicate_headings:
        _check_duplicate_headings(filepath, headings, issues)

    return issues


def _check_heading_hierarchy(
    filepath: str,
    headings: list[tuple[int, int, str]],
    config: LintConfig,
    issues: list[LintIssue],
):
    """Check heading hierarchy: no level skipping."""
    if not headings:
        return

    # First heading should be h1
    first_line, first_level, _ = headings[0]
    if first_level != config.first_heading_level:
        issues.append(LintIssue(
            file=filepath, line=first_line, column=1,
            rule="heading-hierarchy",
            severity="warning",
            message=f"First heading is h{first_level}, expected h{config.first_heading_level}",
            fixable=False,
        ))

    # No skipping levels (e.g., h1 -> h3)
    prev_level = 0
    for lineno, level, text in headings:
        if prev_level > 0 and level > prev_level + 1:
            issues.append(LintIssue(
                file=filepath, line=lineno, column=1,
                rule="heading-skip",
                severity="error",
                message=f"Heading level skipped: h{prev_level} -> h{level}",
                fixable=False,
            ))
        prev_level = level


def _check_duplicate_headings(
    filepath: str,
    headings: list[tuple[int, int, str]],
    issues: list[LintIssue],
):
    """Check for duplicate heading text at the same level."""
    seen: dict[str, int] = {}
    for lineno, level, text in headings:
        key = f"{level}:{text.lower().strip()}"
        if key in seen:
            issues.append(LintIssue(
                file=filepath, line=lineno, column=1,
                rule="duplicate-heading",
                severity="warning",
                message=f"Duplicate heading '{text}' (first at line {seen[key]})",
                fixable=False,
            ))
        else:
            seen[key] = lineno


def lint_files(filepaths: list[str], config: Optional[LintConfig] = None) -> LintResult:
    """Lint multiple Markdown files."""
    result = LintResult()
    for filepath in filepaths:
        issues = lint_file(filepath, config)
        result.issues.extend(issues)
        result.files_checked += 1
    return result
