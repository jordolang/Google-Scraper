#!/usr/bin/env python3
"""Advance the project version and write the change into CHANGELOG.md.

The scheme (see "Versioning" in the README):

* a **feature** advances the number by a tenth — 1.0 → 1.1 → 1.2, and any
  letter suffix is dropped, because the fixes it recorded are now shipped.
* a **fix or small adjustment** advances the letter — 1.2 → 1.2a → 1.2b → 1.2c
  (and after 1.2z, 1.2aa).

A commit is a feature when its subject starts with ``feat``/``feature`` (a
Conventional-Commits prefix, optional scope and ``!``), or when it carries an
explicit ``[feature]`` / ``[minor]`` tag.  Everything else — fixes, docs,
chores, refactors — is a fix-level change.  A push containing any feature
commit is a feature bump: one push, one version.

Run by .github/workflows/version.yml on every push to main, and usable by hand::

    python scripts/bump_version.py --commit "feat: add phone lookup"
    python scripts/bump_version.py --dry-run --commit "fix: typo"
"""

from __future__ import annotations

import argparse
import re
import string
import subprocess
import sys
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
VERSION_FILE = REPO_ROOT / "VERSION"
CHANGELOG_FILE = REPO_ROOT / "CHANGELOG.md"

#: A version is a number and an optional letter suffix: 1.0, 1.2, 1.2c, 1.2aa.
_VERSION_RE = re.compile(r"^(\d+)\.(\d+)([a-z]*)$")

#: Subjects that mean "this is a new feature": a leading feat:/feature: prefix,
#: or an explicit [feature] / [minor] tag anywhere in the subject.
_FEATURE_RE = re.compile(
    r"^(feat|feature)(\([^)]*\))?!?:|\[(feature|minor)\]", re.IGNORECASE
)


def is_feature(subject: str) -> bool:
    """True when a commit subject announces a new feature."""
    return bool(_FEATURE_RE.search(str(subject).strip()))

#: How a commit subject is filed in the changelog.
_SECTIONS = (
    ("Added", re.compile(r"^(feat|feature)(\([^)]*\))?!?:", re.IGNORECASE)),
    ("Fixed", re.compile(r"^(fix|bug|bugfix|hotfix)(\([^)]*\))?!?:", re.IGNORECASE)),
    ("Documentation", re.compile(r"^docs?(\([^)]*\))?!?:", re.IGNORECASE)),
    ("Changed", re.compile(r"")),  # everything else
)

#: Commits that are pure bookkeeping — never worth a changelog line.
_NOISE_RE = re.compile(
    r"^(chore\(release\)|release|bump version|merge branch|merge pull request)",
    re.IGNORECASE,
)


class Version:
    """A version like ``1.2c``: a number, and a letter suffix for its fixes."""

    def __init__(self, major: int, minor: int, letters: str = "") -> None:
        self.major = major
        self.minor = minor
        self.letters = letters

    @classmethod
    def parse(cls, text: str) -> "Version":
        match = _VERSION_RE.match(str(text).strip().lstrip("vV"))
        if not match:
            raise ValueError(f"not a version: {text!r} (expected e.g. 1.0 or 1.2c)")
        return cls(int(match.group(1)), int(match.group(2)), match.group(3))

    def __str__(self) -> str:
        return f"{self.major}.{self.minor}{self.letters}"

    def __eq__(self, other: object) -> bool:
        return str(self) == str(other)

    def bump_feature(self) -> "Version":
        """1.2c → 1.3.  A feature supersedes the fixes that came before it."""
        return Version(self.major, self.minor + 1)

    def bump_fix(self) -> "Version":
        """1.2 → 1.2a → 1.2b … → 1.2z → 1.2aa."""
        return Version(self.major, self.minor, _next_letters(self.letters))


def _next_letters(letters: str) -> str:
    """Advance a spreadsheet-style suffix: "" → a → b … z → aa → ab."""
    if not letters:
        return "a"
    chars = list(letters)
    position = len(chars) - 1
    while position >= 0:
        if chars[position] != "z":
            chars[position] = string.ascii_lowercase[
                string.ascii_lowercase.index(chars[position]) + 1
            ]
            return "".join(chars)
        chars[position] = "a"  # carry
        position -= 1
    return "a" + "".join(chars)


def next_version(current: Version, subjects: list[str]) -> Version:
    """The version a push of ``subjects`` lands on.

    One push is one bump: any feature in the batch makes it a feature bump.
    """
    if any(is_feature(subject) for subject in subjects):
        return current.bump_feature()
    return current.bump_fix()


def _clean(subject: str) -> str:
    """Strip the Conventional-Commits prefix for display."""
    return re.sub(r"^\w+(\([^)]*\))?!?:\s*", "", subject.strip()).strip()


def _noteworthy(subjects: list[str]) -> list[str]:
    return [s.strip() for s in subjects if s.strip() and not _NOISE_RE.match(s.strip())]


def changelog_entry(version: Version, subjects: list[str], when: date | None = None) -> str:
    """Render one release section, grouping commits by what they were."""
    when = when or date.today()
    grouped: dict[str, list[str]] = {}
    for subject in _noteworthy(subjects):
        for heading, pattern in _SECTIONS:
            if pattern.pattern == "" or pattern.match(subject):
                grouped.setdefault(heading, []).append(_clean(subject))
                break

    lines = [f"## [{version}] - {when.isoformat()}", ""]
    for heading, _pattern in _SECTIONS:
        if heading not in grouped:
            continue
        lines.append(f"### {heading}")
        lines.extend(f"- {item}" for item in grouped[heading])
        lines.append("")
    if len(lines) == 2:  # nothing but noise
        lines.extend(["### Changed", "- Maintenance.", ""])
    return "\n".join(lines)


def prepend_entry(changelog: str, entry: str) -> str:
    """Insert a release section directly under the changelog's preamble.

    Newest release first; the preamble (title + how-versioning-works blurb) is
    whatever precedes the first ``## [`` heading.
    """
    index = changelog.find("\n## [")
    if index == -1:  # first ever entry
        return f"{changelog.rstrip()}\n\n{entry.rstrip()}\n"
    preamble = changelog[:index].rstrip("\n")
    releases = changelog[index:].lstrip("\n")
    return f"{preamble}\n\n{entry.rstrip()}\n\n{releases}"


def git_subjects(since_ref: str | None = None) -> list[str]:
    """Commit subjects introduced by this push (falls back to the last commit)."""
    args = ["git", "log", "--no-merges", "--format=%s"]
    args.append(f"{since_ref}..HEAD" if since_ref else "-1")
    result = subprocess.run(args, capture_output=True, text=True, check=False)
    return [line for line in result.stdout.splitlines() if line.strip()]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--commit", action="append", default=[], dest="commits",
        help="Commit subject (repeatable). Defaults to reading git history.",
    )
    parser.add_argument("--since", help="Bump using commits in <since>..HEAD")
    parser.add_argument("--version-file", type=Path, default=VERSION_FILE)
    parser.add_argument("--changelog", type=Path, default=CHANGELOG_FILE)
    parser.add_argument("--dry-run", action="store_true", help="Print, write nothing")
    args = parser.parse_args(argv)

    subjects = args.commits or git_subjects(args.since)
    if not subjects:
        print("No commits to version.", file=sys.stderr)
        return 1

    current = Version.parse(args.version_file.read_text())
    upcoming = next_version(current, subjects)
    kind = "feature" if upcoming.minor != current.minor else "fix"
    print(f"{current} → {upcoming}  ({kind}; {len(subjects)} commit(s))")

    if args.dry_run:
        print(changelog_entry(upcoming, subjects))
        return 0

    args.version_file.write_text(f"{upcoming}\n")
    changelog = args.changelog.read_text() if args.changelog.exists() else "# Changelog\n"
    args.changelog.write_text(prepend_entry(changelog, changelog_entry(upcoming, subjects)))
    print(f"Wrote {args.version_file} and {args.changelog}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
