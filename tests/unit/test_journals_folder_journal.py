# Copyright © 2012-2023 jrnl contributors
# License: https://www.gnu.org/licenses/gpl-3.0.html

import datetime
import pathlib
from unittest import mock

import pytest

from jrnl.journals.Entry import Entry
from jrnl.journals.FolderJournal import Folder
from jrnl.journals.Journal import Journal
from jrnl.os_compat import UTF8_BOM


@pytest.mark.parametrize(
    "inputs_and_outputs",
    [
        [
            "/2020/01",
            ["02.txt", "03.txt", "31.txt"],
            ["/2020/01/02.txt", "/2020/01/03.txt", "/2020/01/31.txt"],
        ],
        [
            "/2020/02",  # leap year
            ["02.txt", "03.txt", "28.txt", "29.txt", "31.txt", "39.txt"],
            [
                "/2020/02/02.txt",
                "/2020/02/03.txt",
                "/2020/02/28.txt",
                "/2020/02/29.txt",
            ],
        ],
        [
            "/2100/02",  # not a leap year
            ["01.txt", "28.txt", "29.txt", "39.txt"],
            ["/2100/02/01.txt", "/2100/02/28.txt"],
        ],
        [
            "/2023/04",
            ["29.txt", "30.txt", "31.txt", "39.txt"],
            ["/2023/04/29.txt", "/2023/04/30.txt"],
        ],
    ],
)
def test_get_day_files_expected_filtering(inputs_and_outputs):
    year_month_path, glob_filenames, expected_output = inputs_and_outputs

    year_month_path = pathlib.Path(year_month_path)

    glob_files = map(lambda x: year_month_path / x, glob_filenames)
    expected_output = list(map(lambda x: str(pathlib.PurePath(x)), expected_output))

    with (
        mock.patch("pathlib.Path.glob", return_value=glob_files),
        mock.patch.object(pathlib.Path, "is_file", return_value=True),
    ):
        actual_output = list(Folder._get_day_files(year_month_path))
        actual_output.sort()

        expected_output.sort()

        assert actual_output == expected_output


def test_dateless_timeformat_preserves_same_day_entries(tmp_path):
    # Regression for #2006: with a timeformat that carries no date component
    # (e.g. "%H:%M"), a second entry added on the same day must not overwrite
    # the earlier one. The folder path (YYYY/MM/DD) is authoritative for the
    # date, so entries must round-trip regardless of the timeformat.
    kwargs = {"journal": str(tmp_path / "journal"), "timeformat": "%H:%M"}

    journal = Folder("test", **kwargs)
    morning = Entry(
        journal, date=datetime.datetime(2020, 1, 15, 9, 0), text="Morning entry"
    )
    morning.modified = True
    journal.entries = [morning]
    journal.write()

    journal = Folder("test", **kwargs).open()
    evening = Entry(
        journal, date=datetime.datetime(2020, 1, 15, 17, 0), text="Evening entry"
    )
    evening.modified = True
    journal.entries.append(evening)
    journal.write()

    journal = Folder("test", **kwargs).open()
    texts = " ".join(e.text for e in journal.entries)
    assert len(journal.entries) == 2
    assert "Morning entry" in texts
    assert "Evening entry" in texts


def _make_file_journal(tmp_path):
    return Journal("test", journal=str(tmp_path / "journal.txt"))


def test_parse_strips_bom_before_first_date_header(tmp_path):
    # A BOM before the first entry's date header must not hide the header or
    # leak into the first entry's title.
    journal = _make_file_journal(tmp_path)
    journal_file = tmp_path / "journal.txt"
    journal_file.write_bytes(UTF8_BOM + b"[2020-01-02 09:00] First title\r\nBody\r\n")

    journal.open()

    assert len(journal.entries) == 1
    entry = journal.entries[0]
    assert entry.date == datetime.datetime(2020, 1, 2, 9, 0)
    assert entry.title == "First title"
    assert entry.body == "Body"


def test_parse_normalizes_crlf_old_log_on_first_save(tmp_path):
    journal = _make_file_journal(tmp_path)
    journal_file = tmp_path / "journal.txt"
    crlf_content = (
        b"[2020-01-02 09:00] First title.\r\nFirst body line\r\n\r\n"
        b"[2020-01-03 10:00] Second title\r\n"
    )
    journal_file.write_bytes(crlf_content)

    journal.open()

    assert all("\r" not in e.text for e in journal.entries)
    assert journal.entries[0].body == "First body line"
    assert "\r" not in journal.pprint()

    # First save normalizes the whole file ...
    journal.write()
    first_save = journal_file.read_bytes()
    assert b"\r" not in first_save

    # ... and saving again leaves the bytes identical.
    journal = _make_file_journal(tmp_path)
    journal.open()
    journal.write()
    assert journal_file.read_bytes() == first_save


def test_lf_only_journal_round_trips_byte_for_byte(tmp_path):
    journal = _make_file_journal(tmp_path)
    journal_file = tmp_path / "journal.txt"
    # Canonical on-disk form: body immediately follows the title, and entries
    # are separated by a blank line.
    original = (
        b"[2020-01-02 09:00] First title.\nFirst body line\n\n"
        b"[2020-01-03 10:00] Second title\n"
    )
    journal_file.write_bytes(original)

    journal.open()
    journal.write()

    assert journal_file.read_bytes() == original


def test_new_entry_normalizes_crlf(tmp_path):
    journal = _make_file_journal(tmp_path)
    entry = journal.new_entry("My title\r\nbody one\r\nbody two\r\n")

    assert entry.title == "My title"
    assert entry.body == "body one\nbody two"


def test_folder_crlf_log_only_rewrites_affected_date(tmp_path):
    kwargs = {"journal": str(tmp_path / "journal"), "timeformat": "%Y-%m-%d %H:%M"}

    day29 = tmp_path / "journal" / "2020" / "08" / "29.txt"
    day31 = tmp_path / "journal" / "2020" / "08" / "31.txt"
    day29.parent.mkdir(parents=True)
    day29.write_bytes(b"[2020-08-29 09:00] Old CRLF title.\r\nOld body\r\n")
    day31.write_bytes(b"[2020-08-31 09:00] Other CRLF title.\r\nOther body\r\n")

    journal = Folder("test", **kwargs).open()

    # A new entry on the 29th rewrites only the 29th's file.
    new_entry = Entry(
        journal,
        date=datetime.datetime(2020, 8, 29, 12, 0),
        text="Brand new entry",
    )
    new_entry.modified = True
    journal.entries.append(new_entry)
    journal.write()

    assert b"\r" not in day29.read_bytes()
    assert b"Brand new entry" in day29.read_bytes()
    # The untouched date keeps its original CRLF bytes.
    assert day31.read_bytes() == (
        b"[2020-08-31 09:00] Other CRLF title.\r\nOther body\r\n"
    )
