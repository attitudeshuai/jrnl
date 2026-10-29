# Copyright © 2012-2023 jrnl contributors
# License: https://www.gnu.org/licenses/gpl-3.0.html

import json
import os

import pytest

from jrnl.journals.probe import DAYONE_TYPE
from jrnl.journals.probe import FILE_TYPE
from jrnl.journals.probe import FOLDER_TYPE
from jrnl.journals.probe import LOCKED
from jrnl.journals.probe import MISSING
from jrnl.journals.probe import READABLE
from jrnl.journals.probe import UNREADABLE
from jrnl.journals.probe import is_dayone_directory
from jrnl.journals.probe import probe_all_journals
from jrnl.journals.probe import probe_journal

DATA_JOURNALS = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "data", "journals"
)


def base_config(journals: dict) -> dict:
    return {
        "default_hour": 9,
        "default_minute": 0,
        "timeformat": "%Y-%m-%d %H:%M",
        "tagsymbols": "@",
        "encrypt": False,
        "highlight": True,
        "linewrap": 80,
        "indent_character": "|",
        "journals": journals,
    }


def journal_path(name: str) -> str:
    return os.path.join(DATA_JOURNALS, name)


def test_readable_single_file_reports_count_and_latest_entry_time():
    config = base_config({"default": journal_path("basic_onefile.journal")})

    report = probe_journal("default", config)

    assert report["status"] == READABLE
    assert report["type"] == FILE_TYPE
    assert report["entry_count"] == 3
    assert report["last_entry_time"] == "2020-09-24T09:14:00"
    assert "reason" not in report


def test_empty_plaintext_file_has_zero_entries_and_no_latest_time():
    config = base_config({"default": {"journal": journal_path("work.journal")}})

    report = probe_journal("default", config)

    assert report["status"] == READABLE
    assert report["type"] == FILE_TYPE
    assert report["entry_count"] == 0
    assert "last_entry_time" not in report


def test_missing_file_is_missing_not_empty():
    path = os.path.join(DATA_JOURNALS, "does", "not", "exist.journal")
    config = base_config({"default": path})

    report = probe_journal("default", config)

    assert report["status"] == MISSING
    assert report["type"] == FILE_TYPE
    assert report["path"] == path
    assert report["reason"]
    assert "entry_count" not in report
    assert "last_entry_time" not in report


def test_missing_path_with_trailing_separator_is_a_missing_folder():
    path = os.path.join(DATA_JOURNALS, "missing_folder") + os.sep
    config = base_config({"default": path})

    report = probe_journal("default", config)

    assert report["status"] == MISSING
    assert report["type"] == FOLDER_TYPE


def test_existing_folder_with_per_day_files_is_not_missing():
    config = base_config({"default": journal_path("basic_folder")})

    report = probe_journal("default", config)

    assert report["status"] == READABLE
    assert report["type"] == FOLDER_TYPE
    assert report["entry_count"] == 3
    assert report["last_entry_time"].startswith("2020-09-24")


def test_dayone_directory_is_detected_by_the_same_rule_as_opening():
    by_suffix = os.path.join(DATA_JOURNALS, "fresh.dayone")
    by_entries = os.path.join(DATA_JOURNALS, "whatever")

    assert is_dayone_directory(by_suffix, [])
    assert is_dayone_directory(by_entries, ["entries"])
    assert not is_dayone_directory(by_entries, ["random"])


def test_dayone_journal_reports_entries():
    config = base_config({"default": journal_path("basic_dayone.dayone")})

    report = probe_journal("default", config)

    assert report["status"] == READABLE
    assert report["type"] == DAYONE_TYPE
    assert report["entry_count"] == 3
    assert "last_entry_time" in report


def test_ordinary_directory_is_not_reported_as_a_journal():
    # empty_folder contains only an unrelated file, no YYYY/MM/DD.txt layout
    config = base_config({"default": journal_path("empty_folder")})

    report = probe_journal("default", config)

    assert report["status"] == READABLE
    assert report["type"] is None
    assert report["reason"]
    assert "entry_count" not in report


def test_configured_encrypted_existing_file_is_locked_without_count():
    config = base_config(
        {
            "default": {
                "journal": journal_path("basic_encrypted.journal"),
                "encrypt": True,
            }
        }
    )

    report = probe_journal("default", config)

    assert report["status"] == LOCKED
    assert report["type"] == FILE_TYPE
    assert "entry_count" not in report
    assert "last_entry_time" not in report
    assert "reason" not in report


def test_encrypted_data_on_disk_is_locked_even_without_config_flag():
    config = base_config({"default": journal_path("encrypted_v3.journal")})

    report = probe_journal("default", config)

    assert report["status"] == LOCKED
    assert report["type"] == FILE_TYPE


def test_missing_encrypted_journal_is_missing_not_locked():
    config = base_config(
        {"default": {"journal": journal_path("nope.journal"), "encrypt": True}}
    )

    report = probe_journal("default", config)

    assert report["status"] == MISSING
    assert "entry_count" not in report


def test_per_journal_settings_do_not_leak_between_journals():
    # The default journal is encrypted; the plain one must not be reported as
    # locked just because the config was already scoped for the default.
    config = base_config(
        {
            "default": {
                "journal": journal_path("basic_encrypted.journal"),
                "encrypt": True,
            },
            "plain": journal_path("simple.journal"),
        }
    )

    reports = probe_all_journals(config)["journals"]

    assert reports["default"]["status"] == LOCKED
    assert reports["plain"]["status"] == READABLE
    assert reports["plain"]["entry_count"] == 2


def test_one_problem_journal_does_not_stop_the_others():
    config = base_config(
        {
            "good": journal_path("basic_onefile.journal"),
            "gone": os.path.join(DATA_JOURNALS, "gone.journal"),
            "locked_one": {
                "journal": journal_path("basic_encrypted.journal"),
                "encrypt": True,
            },
            "random_dir": journal_path("empty_folder"),
        }
    )

    result = probe_all_journals(config)

    assert result["journals"]["good"]["status"] == READABLE
    assert result["journals"]["gone"]["status"] == MISSING
    assert result["journals"]["locked_one"]["status"] == LOCKED
    assert result["journals"]["random_dir"]["type"] is None

    problem_names = {p["journal"] for p in result["problems"]}
    assert problem_names == {"gone", "random_dir"}
    for problem in result["problems"]:
        assert problem["path"]
        assert problem["reason"]

    assert result["summary"] == {
        "total": 4,
        READABLE: 2,
        LOCKED: 1,
        MISSING: 1,
        UNREADABLE: 0,
        "problems": 2,
    }


def test_probe_reports_are_json_serializable():
    config = base_config(
        {
            "good": journal_path("basic_onefile.journal"),
            "gone": os.path.join(DATA_JOURNALS, "gone.journal"),
        }
    )

    json.dumps(probe_all_journals(config))


def test_probing_does_not_create_or_modify_anything(tmp_path):
    journal_file = tmp_path / "existing.journal"
    journal_file.write_text("[2020-01-02 03:04] hello\n", encoding="utf-8")
    missing_dir = tmp_path / "never_created"

    config = base_config(
        {
            "default": str(journal_file),
            "missing_file": str(tmp_path / "nope.journal"),
            "missing_folder": str(missing_dir) + os.sep,
        }
    )

    def snapshot():
        return {
            "file_exists": journal_file.exists(),
            "file_bytes": journal_file.read_bytes() if journal_file.exists() else None,
            "file_mtime_ns": journal_file.stat().st_mtime_ns
            if journal_file.exists()
            else None,
            "dir_exists": missing_dir.exists(),
            "entries": sorted(p.name for p in tmp_path.iterdir()),
        }

    before = snapshot()
    probe_all_journals(config)
    probe_all_journals(config)
    after = snapshot()

    assert before == after


@pytest.mark.skipif(
    hasattr(os, "geteuid") and os.geteuid() == 0,
    reason="root bypasses permissions",
)
def test_existing_but_unreadable_file_is_unreadable(tmp_path):
    journal_file = tmp_path / "secret.journal"
    journal_file.write_text("[2020-01-02 03:04] secret\n", encoding="utf-8")
    os.chmod(journal_file, 0)

    try:
        config = base_config({"default": str(journal_file)})
        report = probe_journal("default", config)

        assert report["status"] == UNREADABLE
        assert report["type"] == FILE_TYPE
        assert report["reason"]
        assert "entry_count" not in report
    finally:
        os.chmod(journal_file, 0o600)
