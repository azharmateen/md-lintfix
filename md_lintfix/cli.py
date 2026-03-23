"""CLI for md-lintfix: lint, fix, toc, links, and map Markdown files."""

import sys
import glob as globmod

import click
from rich.console import Console
from rich.table import Table

console = Console()


def _expand_globs(patterns: tuple[str, ...]) -> list[str]:
    """Expand glob patterns to file paths."""
    files = []
    for pattern in patterns:
        matches = globmod.glob(pattern, recursive=True)
        files.extend(m for m in matches if m.endswith(".md"))
    # Deduplicate while preserving order
    seen = set()
    result = []
    for f in files:
        if f not in seen:
            seen.add(f)
            result.append(f)
    return result


@click.group()
@click.version_option(package_name="md-lintfix")
def cli():
    """Opinionated Markdown linter + auto-fixer."""
    pass


@cli.command()
@click.argument("files", nargs=-1, required=True)
@click.option("--max-line-length", default=120, help="Max line length")
@click.option("--allow-duplicates", is_flag=True, help="Allow duplicate headings")
@click.option("--no-fence-lang", is_flag=True, help="Don't require code fence language")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def lint(files, max_line_length, allow_duplicates, no_fence_lang, as_json):
    """Lint Markdown files for issues.

    Example: md-lintfix lint '*.md' 'docs/**/*.md'
    """
    import json
    from .linter import lint_files, LintConfig

    filepaths = _expand_globs(files)
    if not filepaths:
        console.print("[yellow]No .md files found matching patterns.[/yellow]")
        sys.exit(0)

    config = LintConfig(
        max_line_length=max_line_length,
        allow_duplicate_headings=allow_duplicates,
        require_code_fence_lang=not no_fence_lang,
    )

    result = lint_files(filepaths, config)

    if as_json:
        issues = [
            {"file": i.file, "line": i.line, "column": i.column,
             "rule": i.rule, "severity": i.severity, "message": i.message,
             "fixable": i.fixable}
            for i in result.issues
        ]
        click.echo(json.dumps({"summary": result.summary(), "issues": issues}, indent=2))
        sys.exit(0 if result.passed else 1)

    if not result.issues:
        console.print(f"\n[bold green]All clean![/bold green] {result.files_checked} files checked, no issues found.")
        sys.exit(0)

    # Group by file
    by_file: dict[str, list] = {}
    for issue in result.issues:
        by_file.setdefault(issue.file, []).append(issue)

    for filepath, issues in by_file.items():
        console.print(f"\n[bold]{filepath}[/bold]")
        for issue in issues:
            severity_style = {
                "error": "red",
                "warning": "yellow",
                "info": "dim",
            }.get(issue.severity, "white")

            fix_tag = " [dim](fixable)[/dim]" if issue.fixable else ""
            console.print(
                f"  L{issue.line}:{issue.column} "
                f"[{severity_style}]{issue.severity:7s}[/{severity_style}] "
                f"[dim]{issue.rule}[/dim] {issue.message}{fix_tag}"
            )

    s = result.summary()
    console.print(f"\n{s['total_issues']} issues ({s['errors']} errors, {s['warnings']} warnings, {s['fixable']} fixable)")
    sys.exit(0 if result.passed else 1)


@cli.command()
@click.argument("files", nargs=-1, required=True)
@click.option("--dry-run", is_flag=True, help="Show changes without writing")
def fix(files, dry_run):
    """Auto-fix Markdown files.

    Example: md-lintfix fix '*.md'
    """
    from .fixer import fix_files

    filepaths = _expand_globs(files)
    if not filepaths:
        console.print("[yellow]No .md files found matching patterns.[/yellow]")
        sys.exit(0)

    results = fix_files(filepaths, write=not dry_run)

    total_changes = 0
    for result in results:
        if result.changes:
            console.print(f"\n[bold]{result.file}[/bold]")
            for change in result.changes:
                console.print(f"  [green]+[/green] {change}")
            total_changes += len(result.changes)

    modified_count = sum(1 for r in results if r.modified)
    action = "Would fix" if dry_run else "Fixed"
    console.print(f"\n{action} {total_changes} issues in {modified_count}/{len(results)} files.")


@cli.command()
@click.argument("file", type=click.Path(exists=True))
@click.option("--max-depth", default=3, help="Max heading depth (1-6)")
@click.option("--min-depth", default=2, help="Min heading depth")
@click.option("--dry-run", is_flag=True, help="Print TOC without inserting")
def toc(file, max_depth, min_depth, dry_run):
    """Generate and insert Table of Contents.

    Example: md-lintfix toc README.md
    """
    from .toc import insert_toc, generate_toc
    from pathlib import Path

    if dry_run:
        content = Path(file).read_text(encoding="utf-8")
        toc_content = generate_toc(content, max_depth=max_depth, min_depth=min_depth)
        if toc_content:
            console.print(toc_content)
        else:
            console.print("[yellow]No headings found for TOC.[/yellow]")
        return

    toc_content, modified = insert_toc(file, max_depth=max_depth, min_depth=min_depth)

    if modified:
        console.print(f"[bold green]TOC inserted/updated in {file}[/bold green]")
        console.print(toc_content)
    else:
        console.print(f"[yellow]No changes needed for {file}[/yellow]")


@cli.command()
@click.argument("files", nargs=-1, required=True)
@click.option("--no-external", is_flag=True, help="Skip external URL checks")
@click.option("--timeout", default=10.0, help="External URL timeout (seconds)")
def links(files, no_external, timeout):
    """Check links in Markdown files.

    Example: md-lintfix links '*.md' 'docs/**/*.md'
    """
    from .links import check_links

    filepaths = _expand_globs(files)
    if not filepaths:
        console.print("[yellow]No .md files found.[/yellow]")
        sys.exit(0)

    console.print(f"Checking links in {len(filepaths)} files...")

    report = check_links(
        filepaths,
        check_external=not no_external,
        external_timeout=timeout,
    )

    # Display results
    has_problems = False

    for result in report.results:
        if result.status == "ok":
            continue

        has_problems = True
        link = result.link
        status_style = {
            "broken": "red",
            "redirect": "yellow",
            "timeout": "yellow",
            "error": "red",
            "skipped": "dim",
        }.get(result.status, "white")

        console.print(
            f"  [{status_style}]{result.status:8s}[/{status_style}] "
            f"{link.file}:{link.line} "
            f"[dim]{link.url}[/dim]"
        )
        if result.error:
            console.print(f"           {result.error}")
        if result.redirect_url:
            console.print(f"           -> {result.redirect_url}")

    s = report.summary()
    console.print(f"\nChecked {s['total_links']} links in {s['files_checked']} files")
    for status, count in s["by_status"].items():
        console.print(f"  {status}: {count}")

    broken = len(report.broken_links)
    sys.exit(1 if broken > 0 else 0)


@cli.command(name="map")
@click.argument("directory", type=click.Path(exists=True))
@click.option("--exclude", multiple=True, help="Glob patterns to exclude")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def docs_map(directory, exclude, as_json):
    """Map documentation structure and find orphan pages.

    Example: md-lintfix map ./docs
    """
    import json
    from .mapper import build_docs_map, format_docs_tree

    docs = build_docs_map(directory, exclude_patterns=list(exclude))

    if as_json:
        nodes = {
            rel: {
                "title": n.title,
                "headings": n.headings,
                "word_count": n.word_count,
                "links_out": n.links_out,
                "links_in": n.links_in,
                "is_orphan": n.is_orphan,
            }
            for rel, n in docs.nodes.items()
        }
        click.echo(json.dumps({"summary": docs.summary(), "nodes": nodes}, indent=2))
        return

    report = format_docs_tree(docs)
    console.print(report)


if __name__ == "__main__":
    cli()
