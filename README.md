# md-lintfix

**Opinionated Markdown linter + auto-fixer for consistent documentation.**

> Your docs have 47 trailing whitespace issues, 12 broken links, and 3 orphan pages. **md-lintfix** finds them all and fixes what it can.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)

## The Problem

Markdown is the universal documentation format, yet most projects have no consistency enforcement. Headings skip levels, links rot, tables drift out of alignment, and nobody generates a TOC. **md-lintfix** is a single tool that lints, fixes, checks links, generates TOCs, and maps your docs structure.

## Features

- **Lint** -- Heading hierarchy, duplicate headings, line length, trailing whitespace, code fence language tags, list indentation
- **Fix** -- Auto-fix: normalize headings, trim whitespace, collapse blank lines, align tables, fix indentation
- **Links** -- Check relative links (file exists?) and external URLs (HEAD request with timeout)
- **TOC** -- Generate/update Table of Contents between `<!-- toc -->` markers
- **Map** -- Build docs tree, detect orphan pages (not linked from anywhere), report coverage

## Install

```bash
pip install md-lintfix
```

## Quick Start

```bash
# Lint all Markdown files
md-lintfix lint '*.md' 'docs/**/*.md'

# Auto-fix issues
md-lintfix fix '*.md'

# Generate TOC in README
md-lintfix toc README.md

# Check all links (including external URLs)
md-lintfix links '**/*.md'

# Map docs structure and find orphans
md-lintfix map ./docs
```

## CLI Reference

| Command | Description |
|---------|-------------|
| `md-lintfix lint <files>` | Lint for issues (exit code 1 on errors) |
| `md-lintfix fix <files>` | Auto-fix issues |
| `md-lintfix toc <file>` | Generate/update TOC |
| `md-lintfix links <files>` | Check relative and external links |
| `md-lintfix map <dir>` | Map docs structure, find orphans |

## Lint Rules

| Rule | Severity | Fixable | Description |
|------|----------|---------|-------------|
| `heading-hierarchy` | warning | no | First heading should be h1 |
| `heading-skip` | error | no | No skipping levels (h1 -> h3) |
| `heading-space` | error | yes | Space required after # |
| `heading-length` | warning | no | Heading text too long |
| `duplicate-heading` | warning | no | Same heading text at same level |
| `trailing-whitespace` | warning | yes | Trailing spaces on lines |
| `consecutive-blanks` | warning | yes | More than 1 consecutive blank line |
| `code-fence-lang` | warning | no | Code fence missing language |
| `line-length` | info | no | Line exceeds max length |
| `list-indent` | warning | yes | Inconsistent list indentation |

## CI Integration

```yaml
# .github/workflows/docs.yml
- name: Lint docs
  run: |
    pip install md-lintfix
    md-lintfix lint '**/*.md'
    md-lintfix links '**/*.md' --no-external
```

## License

MIT
