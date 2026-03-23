"""Link checker: validate relative and external links in Markdown files."""

import re
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse


@dataclass
class LinkInfo:
    """Information about a link found in Markdown."""
    file: str
    line: int
    text: str
    url: str
    is_external: bool
    is_image: bool = False
    anchor: Optional[str] = None


@dataclass
class LinkCheckResult:
    """Result of checking a single link."""
    link: LinkInfo
    status: str  # "ok", "broken", "redirect", "timeout", "error", "skipped"
    status_code: Optional[int] = None
    redirect_url: Optional[str] = None
    error: Optional[str] = None


@dataclass
class LinkReport:
    """Report for all checked links."""
    results: list[LinkCheckResult] = field(default_factory=list)
    files_checked: int = 0

    @property
    def broken_links(self) -> list[LinkCheckResult]:
        return [r for r in self.results if r.status == "broken"]

    @property
    def redirected_links(self) -> list[LinkCheckResult]:
        return [r for r in self.results if r.status == "redirect"]

    @property
    def ok_links(self) -> list[LinkCheckResult]:
        return [r for r in self.results if r.status == "ok"]

    def summary(self) -> dict:
        statuses = {}
        for r in self.results:
            statuses[r.status] = statuses.get(r.status, 0) + 1
        return {
            "total_links": len(self.results),
            "files_checked": self.files_checked,
            "by_status": statuses,
        }


# Regex to find Markdown links: [text](url) and ![alt](url)
LINK_PATTERN = re.compile(
    r'(!?)\[([^\]]*)\]\(([^)]+)\)'
)

# Also match reference-style links: [text][ref] and [ref]: url
REF_DEF_PATTERN = re.compile(r'^\[([^\]]+)\]:\s+(.+)$', re.MULTILINE)


def extract_links(filepath: str) -> list[LinkInfo]:
    """Extract all links from a Markdown file."""
    content = Path(filepath).read_text(encoding="utf-8", errors="replace")
    links = []

    # Extract inline links
    for i, line in enumerate(content.split("\n"), 1):
        # Skip code blocks (simple check)
        if line.strip().startswith("```"):
            continue

        for match in LINK_PATTERN.finditer(line):
            is_image = match.group(1) == "!"
            text = match.group(2)
            url = match.group(3).strip()

            # Parse anchor
            anchor = None
            if "#" in url:
                parts = url.split("#", 1)
                if not parts[0]:  # Internal anchor like #section
                    anchor = parts[1]
                else:
                    anchor = parts[1]

            parsed = urlparse(url)
            is_external = bool(parsed.scheme and parsed.scheme in ("http", "https"))

            links.append(LinkInfo(
                file=filepath,
                line=i,
                text=text,
                url=url,
                is_external=is_external,
                is_image=is_image,
                anchor=anchor,
            ))

    # Extract reference definitions
    for match in REF_DEF_PATTERN.finditer(content):
        url = match.group(2).strip()
        parsed = urlparse(url)
        is_external = bool(parsed.scheme and parsed.scheme in ("http", "https"))
        # Find line number
        line_num = content[:match.start()].count("\n") + 1

        links.append(LinkInfo(
            file=filepath,
            line=line_num,
            text=f"[{match.group(1)}]",
            url=url,
            is_external=is_external,
        ))

    return links


def check_relative_link(link: LinkInfo) -> LinkCheckResult:
    """Check if a relative link target exists."""
    file_dir = Path(link.file).parent
    url = link.url.split("#")[0]  # Remove anchor

    if not url:
        # Just an anchor reference
        return LinkCheckResult(link=link, status="ok")

    target = (file_dir / url).resolve()

    if target.exists():
        return LinkCheckResult(link=link, status="ok")
    else:
        return LinkCheckResult(
            link=link,
            status="broken",
            error=f"File not found: {target}",
        )


def check_external_link(link: LinkInfo, timeout: float = 10.0) -> LinkCheckResult:
    """Check if an external URL is reachable."""
    try:
        import requests

        # Use HEAD first (faster), fall back to GET
        try:
            resp = requests.head(
                link.url,
                timeout=timeout,
                allow_redirects=True,
                headers={"User-Agent": "md-lintfix/0.1 link-checker"},
            )
        except requests.exceptions.ConnectionError:
            resp = requests.get(
                link.url,
                timeout=timeout,
                allow_redirects=True,
                headers={"User-Agent": "md-lintfix/0.1 link-checker"},
                stream=True,
            )

        if resp.status_code < 400:
            if resp.history:
                return LinkCheckResult(
                    link=link,
                    status="redirect",
                    status_code=resp.status_code,
                    redirect_url=resp.url,
                )
            return LinkCheckResult(link=link, status="ok", status_code=resp.status_code)
        else:
            return LinkCheckResult(
                link=link,
                status="broken",
                status_code=resp.status_code,
                error=f"HTTP {resp.status_code}",
            )

    except ImportError:
        return LinkCheckResult(
            link=link, status="skipped",
            error="requests library not installed",
        )
    except Exception as e:
        error_type = type(e).__name__
        if "Timeout" in error_type or "timeout" in str(e).lower():
            return LinkCheckResult(link=link, status="timeout", error=str(e))
        return LinkCheckResult(link=link, status="error", error=f"{error_type}: {e}")


def check_links(
    filepaths: list[str],
    check_external: bool = True,
    external_timeout: float = 10.0,
    max_workers: int = 5,
) -> LinkReport:
    """
    Check all links in the given Markdown files.

    Args:
        filepaths: List of Markdown file paths
        check_external: Whether to check external URLs
        external_timeout: Timeout for external URL checks
        max_workers: Max parallel workers for external checks
    """
    report = LinkReport()

    # Extract all links
    all_links = []
    for filepath in filepaths:
        links = extract_links(filepath)
        all_links.extend(links)
        report.files_checked += 1

    # Check relative links (fast, synchronous)
    external_links = []
    for link in all_links:
        if link.is_external:
            external_links.append(link)
        else:
            result = check_relative_link(link)
            report.results.append(result)

    # Check external links (parallel)
    if check_external and external_links:
        # Deduplicate URLs
        seen_urls: dict[str, LinkCheckResult] = {}

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {}
            for link in external_links:
                if link.url not in seen_urls:
                    future = executor.submit(check_external_link, link, external_timeout)
                    futures[future] = link

            for future in as_completed(futures):
                result = future.result()
                seen_urls[result.link.url] = result
                report.results.append(result)

            # Add results for duplicate URLs
            for link in external_links:
                if link.url in seen_urls and link is not seen_urls[link.url].link:
                    cached = seen_urls[link.url]
                    report.results.append(LinkCheckResult(
                        link=link,
                        status=cached.status,
                        status_code=cached.status_code,
                        redirect_url=cached.redirect_url,
                        error=cached.error,
                    ))
    elif not check_external:
        for link in external_links:
            report.results.append(LinkCheckResult(link=link, status="skipped"))

    return report
