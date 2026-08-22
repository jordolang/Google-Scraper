"""Tests for the automatic versioning scheme.

Features advance the number by a tenth (1.1 → 1.2); fixes advance the letter
(1.2 → 1.2a → 1.2b).  A feature drops the letters.
"""

from datetime import date
from pathlib import Path

import pytest

from scripts.bump_version import (
    Version,
    changelog_entry,
    is_feature,
    next_version,
    prepend_entry,
    main,
)


# --------------------------------------------------------------------------- #
#  parsing
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "text, expected",
    [("1.0", "1.0"), ("1.2c", "1.2c"), ("v2.10", "2.10"), (" 1.2aa\n", "1.2aa")],
)
def test_parse_roundtrips(text, expected):
    assert str(Version.parse(text)) == expected


@pytest.mark.parametrize("text", ["", "1", "1.2.3", "1.2C", "one.two", "1.2-beta"])
def test_parse_rejects_junk(text):
    with pytest.raises(ValueError):
        Version.parse(text)


# --------------------------------------------------------------------------- #
#  the scheme itself
# --------------------------------------------------------------------------- #
def test_a_feature_advances_a_tenth():
    assert Version.parse("1.0").bump_feature() == "1.1"
    assert Version.parse("1.1").bump_feature() == "1.2"


def test_a_feature_drops_the_fix_letters():
    # 1.2c means "1.2 plus three fixes"; the next feature ships them as 1.3.
    assert Version.parse("1.2c").bump_feature() == "1.3"


def test_fixes_advance_the_letter():
    version = Version.parse("1.2")
    for expected in ("1.2a", "1.2b", "1.2c"):
        version = version.bump_fix()
        assert version == expected


def test_the_users_worked_example():
    """Two features, then three fixes on top, is 1.2c."""
    version = Version.parse("1.0")
    version = next_version(version, ["feat: exports"])       # 1.1
    version = next_version(version, ["feat: phone lookup"])  # 1.2
    assert version == "1.2"
    for _ in range(3):
        version = next_version(version, ["fix: heavy bug"])
    assert version == "1.2c"


def test_letters_roll_over_past_z():
    assert Version.parse("1.2z").bump_fix() == "1.2aa"
    assert Version.parse("1.2aa").bump_fix() == "1.2ab"
    assert Version.parse("1.2az").bump_fix() == "1.2ba"


def test_the_tenth_keeps_counting_past_nine():
    assert Version.parse("1.9").bump_feature() == "1.10"


# --------------------------------------------------------------------------- #
#  classifying commits
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "subject",
    [
        "feat: add phone lookup",
        "feat(tui): add phone lookup",
        "feat!: drop the old CSV layout",
        "feature: add phone lookup",
        "FEAT: shouting still counts",
        "Add exports [feature]",
        "Rework the pipeline [minor]",
    ],
)
def test_feature_commits(subject):
    assert is_feature(subject)


@pytest.mark.parametrize(
    "subject",
    [
        "fix: contacts CSV clobbered itself",
        "docs: document the data layout",
        "chore: bump selenium",
        "refactor: split the pipeline",
        "featuring the new logo",  # a word that merely starts with "feat"
        "defeat the flaky test",
    ],
)
def test_fix_level_commits(subject):
    assert not is_feature(subject)


def test_one_push_is_one_bump_and_a_feature_wins():
    # Five commits, one of them a feature: a single feature bump, not five.
    subjects = ["fix: a", "fix: b", "feat: c", "docs: d", "chore: e"]
    assert next_version(Version.parse("1.4"), subjects) == "1.5"


def test_a_push_of_only_fixes_is_a_letter_bump():
    assert next_version(Version.parse("1.4"), ["fix: a", "docs: b"]) == "1.4a"


# --------------------------------------------------------------------------- #
#  the changelog
# --------------------------------------------------------------------------- #
def test_changelog_entry_groups_commits_by_kind():
    entry = changelog_entry(
        Version.parse("1.1"),
        ["feat: phone lookup", "fix: clobbered CSV", "docs: README", "tidy up imports"],
        when=date(2026, 7, 13),
    )
    assert "## [1.1] - 2026-07-13" in entry
    assert "### Added\n- phone lookup" in entry
    assert "### Fixed\n- clobbered CSV" in entry
    assert "### Documentation\n- README" in entry
    # Anything without a recognized prefix is still recorded, just as "Changed".
    assert "### Changed\n- tidy up imports" in entry


def test_changelog_entry_ignores_release_noise():
    entry = changelog_entry(
        Version.parse("1.1"),
        ["chore(release): v1.0 [skip ci]", "Merge pull request #7", "feat: real work"],
        when=date(2026, 7, 13),
    )
    assert "- real work" in entry
    assert "release" not in entry.lower().replace("## [1.1]", "")
    assert "Merge pull request" not in entry


def test_new_releases_go_on_top_under_the_preamble():
    changelog = (
        "# Changelog\n\nHow versions move: blah.\n\n"
        "## [1.0] - 2026-07-13\n\n### Added\n- The first release.\n"
    )
    updated = prepend_entry(changelog, changelog_entry(Version.parse("1.1"), ["feat: x"]))

    assert updated.startswith("# Changelog\n\nHow versions move: blah.\n")
    assert updated.index("## [1.1]") < updated.index("## [1.0]")
    assert "- The first release." in updated  # history is never lost
    # Entries stack cleanly instead of accreting blank lines with each release.
    assert "\n\n\n" not in updated


# --------------------------------------------------------------------------- #
#  end to end
# --------------------------------------------------------------------------- #
def test_main_writes_the_version_and_the_changelog(tmp_path, capsys):
    version_file = tmp_path / "VERSION"
    version_file.write_text("1.2c\n")
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text("# Changelog\n\n## [1.2] - 2026-07-01\n\n### Added\n- Old news.\n")

    code = main([
        "--commit", "feat: exports land in data/",
        "--version-file", str(version_file),
        "--changelog", str(changelog),
    ])

    assert code == 0
    assert version_file.read_text().strip() == "1.3"
    body = changelog.read_text()
    assert body.index("## [1.3]") < body.index("## [1.2]")
    assert "- exports land in data/" in body
    assert "1.2c → 1.3  (feature" in capsys.readouterr().out


def test_main_dry_run_changes_nothing(tmp_path):
    version_file = tmp_path / "VERSION"
    version_file.write_text("1.2\n")
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text("# Changelog\n")

    main([
        "--commit", "fix: a bug",
        "--dry-run",
        "--version-file", str(version_file),
        "--changelog", str(changelog),
    ])

    assert version_file.read_text().strip() == "1.2"
    assert changelog.read_text() == "# Changelog\n"


# --------------------------------------------------------------------------- #
#  release wiring
# --------------------------------------------------------------------------- #
def _workflow(name):
    yaml = pytest.importorskip("yaml")
    text = (Path(__file__).resolve().parent.parent
            / ".github" / "workflows" / name).read_text(encoding="utf-8")
    loaded = yaml.safe_load(text)
    # PyYAML parses a bare `on:` key as the boolean True.
    loaded["on"] = loaded.get("on", loaded.get(True))
    return loaded


def test_tagging_a_release_also_builds_and_publishes_the_windows_exe():
    """The release must carry the .exe, and only one wiring can deliver it.

    A tag pushed with GITHUB_TOKEN starts no new workflow run, so the Windows
    build cannot be triggered by the tag itself — version.yml has to call it
    inside the same run. If that call is dropped, releases silently ship with
    no Windows download.
    """
    version = _workflow("version.yml")
    windows = _workflow("windows-build.yml")

    job = version["jobs"]["windows"]
    assert job["uses"] == "./.github/workflows/windows-build.yml"
    assert job["with"]["tag"] == "${{ needs.bump.outputs.tag }}"
    assert job["permissions"]["contents"] == "write"

    # The tag it passes only exists when a release was actually cut.
    assert version["jobs"]["bump"]["outputs"]["tag"]
    assert job["if"].strip() == "needs.bump.outputs.tag != ''"

    # And the called workflow accepts it and publishes with it.
    assert "workflow_call" in windows["on"]
    assert "tag" in windows["on"]["workflow_call"]["inputs"]
    publish = [step for step in windows["jobs"]["build"]["steps"]
               if str(step.get("uses", "")).startswith("softprops/action-gh-release")]
    assert len(publish) == 1, "exactly one step should publish the release"
    assert publish[0]["with"]["tag_name"] == "${{ env.RELEASE_TAG }}"
    # One executable per architecture, both attached to the same release.
    assert "LocalLeadScraperPro-${{ matrix.arch }}.exe" in publish[0]["with"]["files"]


def test_all_four_desktop_builds_are_wired_into_the_release():
    """Windows and macOS, two architectures each, all on one release.

    Neither PyInstaller nor Qt cross-compiles, so every one of these needs its
    own runner — there is no way to produce them from a single job.
    """
    version = _workflow("version.yml")
    jobs = version["jobs"]
    assert jobs["windows"]["uses"] == "./.github/workflows/windows-build.yml"
    assert jobs["macos"]["uses"] == "./.github/workflows/macos-build.yml"
    for name in ("windows", "macos"):
        assert jobs[name]["with"]["tag"] == "${{ needs.bump.outputs.tag }}"
        assert jobs[name]["if"].strip() == "needs.bump.outputs.tag != ''"
        assert jobs[name]["permissions"]["contents"] == "write"

    mac = _workflow("macos-build.yml")
    by_arch = {e["arch"]: e for e in mac["jobs"]["build"]["strategy"]["matrix"]["include"]}
    assert set(by_arch) == {"intel", "apple-silicon"}
    # macos-13 is the last Intel runner; 14 and later are Apple Silicon.
    assert by_arch["intel"]["runner"] == "macos-13"
    assert by_arch["apple-silicon"]["runner"] == "macos-14"
    # Each must fetch the Chromium built for its own silicon.
    assert by_arch["intel"]["chromium"] == "Mac"
    assert by_arch["apple-silicon"]["chromium"] == "Mac_Arm"


def test_the_mac_workflow_publishes_a_zipped_bundle():
    """A .app is a directory; a release asset is one file."""
    mac = _workflow("macos-build.yml")
    steps = mac["jobs"]["build"]["steps"]
    names = [s.get("name") for s in steps]
    assert "Zip the bundle" in names
    publish = [s for s in steps
               if str(s.get("uses", "")).startswith("softprops/action-gh-release")]
    assert len(publish) == 1
    assert publish[0]["with"]["files"] == "${{ env.ASSET }}"
    assert publish[0]["if"].strip() == "env.RELEASE_TAG != ''"


def test_both_windows_architectures_are_built():
    """An ARM64 Windows machine should get a native build, not x64 emulation.

    Neither PyInstaller nor Qt cross-compiles, so the ARM64 executable has to
    be built on an ARM64 runner — there is no way to produce it from the x64
    job.
    """
    windows = _workflow("windows-build.yml")
    matrix = windows["jobs"]["build"]["strategy"]["matrix"]["include"]
    by_arch = {entry["arch"]: entry for entry in matrix}

    assert set(by_arch) == {"x64", "arm64"}
    assert by_arch["arm64"]["runner"] == "windows-11-arm"
    assert by_arch["x64"]["runner"] == "windows-latest"
    # Each build must fetch the browser for its own architecture; an x64
    # Chromium inside the ARM64 executable would defeat the point.
    assert by_arch["arm64"]["chromium"] == "Win_Arm64"
    assert by_arch["x64"]["chromium"] == "Win_x64"
    assert by_arch["arm64"]["python_arch"] == "arm64"


def test_the_windows_build_has_no_paths_filtered_tag_trigger():
    """A push trigger's `paths` filter applies to tag pushes as well.

    A tag push changes no files, so it can never satisfy the filter — a
    `tags:` entry sitting next to these paths looks like it publishes releases
    and silently never runs. That is exactly how v1.5 came out with no .exe
    attached. Releases come from workflow_call, the release event, or a manual
    dispatch instead.
    """
    windows = _workflow("windows-build.yml")
    push = windows["on"]["push"]
    assert "paths" in push
    assert "tags" not in push, (
        "a tags: filter here cannot fire alongside paths: — publish releases "
        "through workflow_call / release / workflow_dispatch instead")
    assert windows["on"]["release"]["types"] == ["published"]


def test_a_hand_published_release_gets_the_exe():
    """Publishing a release in the UI should attach the build to it."""
    windows = _workflow("windows-build.yml")
    tag = windows["jobs"]["build"]["env"]["RELEASE_TAG"]
    assert "github.event.release.tag_name" in tag
    assert "inputs.tag" in tag


def test_the_windows_build_checks_out_the_tag_it_was_asked_for():
    """Otherwise it would package whatever main had moved on to."""
    windows = _workflow("windows-build.yml")
    checkout = windows["jobs"]["build"]["steps"][0]
    assert checkout["uses"].startswith("actions/checkout")
    assert checkout["with"]["ref"] == (
        "${{ inputs.tag || github.event.release.tag_name || github.ref }}")
