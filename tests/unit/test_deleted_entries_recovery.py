# Copyright © 2012-2023 jrnl contributors
# License: https://www.gnu.org/licenses/gpl-3.0.html

import datetime
import os
from unittest import mock

import pytest

from jrnl.controller import _delete_search_results
from jrnl.exception import JrnlException
from jrnl.journals import DayOne
from jrnl.journals import Folder
from jrnl.journals import Journal
from jrnl.journals.Entry import Entry
from jrnl.journals.Journal import DELETED_ENTRIES_RECORD_MAGIC
from jrnl.journals.Journal import deleted_entries_record_filename
from jrnl.messages import MsgText

JOURNAL_TEXT = """\
[2020-08-29 11:11] Entry the first.
The first body with @tagone and @tagtwo.

[2020-08-31 14:32] A second entry in the series. *
The second body with @tagtwo.

[2020-09-24 09:14] The third entry finally.
The third body with @tagthree and @tagone.
"""


def _seed_onefile(tmp_path):
    journal = Journal("default", journal=str(tmp_path / "journal.txt"), tagsymbols="@")
    journal.entries = journal._parse(JOURNAL_TEXT)
    journal.sort()
    journal.write()


def _reopen_onefile(tmp_path):
    return Journal(
        "default", journal=str(tmp_path / "journal.txt"), tagsymbols="@"
    ).open()


def _open_onefile(tmp_path):
    _seed_onefile(tmp_path)
    return _reopen_onefile(tmp_path)


def _seed_folder(tmp_path):
    journal = Folder("default", journal=str(tmp_path / "journal"), tagsymbols="@")
    dates_and_titles = [
        (datetime.datetime(2020, 1, 1, 9, 0), "Solo day entry", "@alone"),
        (datetime.datetime(2020, 1, 2, 9, 0), "First of two same day", "@morning"),
        (datetime.datetime(2020, 1, 2, 17, 0), "Second of two same day", "@evening"),
    ]
    for date, title, tag in dates_and_titles:
        entry = Entry(journal, date=date, text=f"{title}\nBody text {tag}.")
        entry.modified = True
        journal.entries.append(entry)
    journal.write()


def _reopen_folder(tmp_path):
    return Folder("default", journal=str(tmp_path / "journal"), tagsymbols="@").open()


def _open_folder(tmp_path):
    _seed_folder(tmp_path)
    return _reopen_folder(tmp_path)


def _no_temp_files_left(directory):
    leftovers = []
    for root, _, files in os.walk(directory):
        leftovers += [f for f in files if f.startswith(".jrnl-") and f.endswith(".tmp")]
    return leftovers == []


# --- record location --- #


def test_record_filename_sits_next_to_journal():
    assert deleted_entries_record_filename(
        os.path.join("a", "journal.txt")
    ) == os.path.join("a", ".journal.txt.jrnl-deleted")
    assert deleted_entries_record_filename(
        os.path.join("a", "basic_folder")
    ) == os.path.join("a", ".basic_folder.jrnl-deleted")


def test_dayone_opts_out_of_recovery():
    assert Journal.supports_deleted_entries_recovery is True
    assert Folder.supports_deleted_entries_recovery is True
    assert DayOne.supports_deleted_entries_recovery is False


# --- single file journal --- #


def test_single_file_delete_writes_record_and_restore_is_byte_identical(tmp_path):
    journal = _open_onefile(tmp_path)
    original_bytes = (tmp_path / "journal.txt").read_bytes()
    original_entries = [
        (e.date, e.title, e.body, e.starred, set(e.tags)) for e in journal
    ]

    third = next(e for e in journal if "third" in e.title)
    journal.save_deleted_entries([third])
    journal.delete_entries([third])
    journal.write()

    # the deleted entry is gone from the journal, but preserved next to it
    reopened = _reopen_onefile(tmp_path)
    assert len(reopened) == 2
    assert all("third" not in e.title for e in reopened)
    assert os.path.exists(reopened.deleted_entries_filename())
    assert _no_temp_files_left(str(tmp_path))

    # restore puts the batch back exactly as it was
    assert reopened.restore_deleted_entries() == 1
    assert not os.path.exists(reopened.deleted_entries_filename())
    assert _no_temp_files_left(str(tmp_path))

    assert (tmp_path / "journal.txt").read_bytes() == original_bytes
    restored = _reopen_onefile(tmp_path)
    assert len(restored) == 3
    restored_tuples = [
        (e.date, e.title, e.body, e.starred, set(e.tags)) for e in restored
    ]
    assert restored_tuples == original_entries


def test_starred_flag_and_tags_are_restored(tmp_path):
    journal = _open_onefile(tmp_path)
    starred = next(e for e in journal if "second" in e.title)
    assert starred.starred is True

    journal.save_deleted_entries([starred])
    journal.delete_entries([starred])
    journal.write()

    reopened = _reopen_onefile(tmp_path)
    assert reopened.restore_deleted_entries() == 1
    restored = _reopen_onefile(tmp_path)
    restored_starred = next(e for e in restored if "second" in e.title)
    assert restored_starred.starred is True
    assert "@tagtwo" in restored_starred.tags


def test_second_restore_restores_nothing_and_does_not_duplicate(tmp_path):
    journal = _open_onefile(tmp_path)
    third = next(e for e in journal if "third" in e.title)
    journal.save_deleted_entries([third])
    journal.delete_entries([third])
    journal.write()

    reopened = _reopen_onefile(tmp_path)
    assert reopened.restore_deleted_entries() == 1
    assert reopened.restore_deleted_entries() is None
    assert len(_reopen_onefile(tmp_path)) == 3


def test_new_delete_overwrites_previous_record(tmp_path):
    journal = _open_onefile(tmp_path)
    first = next(e for e in journal if "first" in e.title)
    third = next(e for e in journal if "third" in e.title)

    journal.save_deleted_entries([first])
    journal.save_deleted_entries([third])

    reopened = _reopen_onefile(tmp_path)
    recovered = reopened._load_deleted_entries()
    assert len(recovered) == 1
    assert "third" in recovered[0].title


def test_record_is_never_read_as_an_entry(tmp_path):
    journal = _open_onefile(tmp_path)
    third = next(e for e in journal if "third" in e.title)
    journal.save_deleted_entries([third])
    journal.delete_entries([third])
    journal.write()

    reopened = _reopen_onefile(tmp_path)
    assert len(reopened) == 2
    assert reopened.entries[0].date == datetime.datetime(2020, 8, 29, 11, 11)


def test_editor_deletion_uses_same_recovery_flow(tmp_path):
    journal = _open_onefile(tmp_path)
    original_count = len(journal)

    # user removes the third entry's block from the editor text
    edited = "\n".join(str(e) for e in journal if "third" not in e.title)
    journal.parse_editable_str(edited)
    journal.write()

    assert os.path.exists(journal.deleted_entries_filename())
    after_edit = _reopen_onefile(tmp_path)
    assert len(after_edit) == original_count - 1

    assert after_edit.restore_deleted_entries() == 1
    assert len(_reopen_onefile(tmp_path)) == original_count


def test_editor_modification_does_not_write_recovery_record(tmp_path):
    journal = _open_onefile(tmp_path)
    edited_entries = [str(e) for e in journal]
    # same timestamp, changed text -> modified, not deleted
    edited_entries[-1] = "[2020-09-24 09:14] Completely rewritten title.\n"
    journal.parse_editable_str("\n".join(edited_entries))

    assert not os.path.exists(journal.deleted_entries_filename())


def test_editor_replacing_sole_entry_with_new_date_is_modification(tmp_path):
    journal = _open_onefile(tmp_path)
    only_entry = "[2030-01-01 00:00] Replacement entry, old date gone.\n"
    journal.entries = [journal.entries[-1]]
    journal.parse_editable_str(only_entry)

    # one entry replaced by one entry -> modification, nothing recoverable
    assert not os.path.exists(journal.deleted_entries_filename())


def test_editor_whole_journal_replacement_records_surplus_entries(tmp_path):
    journal = _open_onefile(tmp_path)
    replacement = "[2021-11-13 09:00] Replacing my whole journal with this.\n"
    journal.parse_editable_str(replacement)

    record = journal._load_deleted_entries()
    # 3 old entries vs 1 new: one is a modification, the other two are deleted
    assert len(record) == 2
    restored_titles = " ".join(e.title for e in record)
    assert "first" not in restored_titles
    assert "second" in restored_titles
    assert "third" in restored_titles


def test_failed_record_write_leaves_journal_untouched(tmp_path):
    journal = _open_onefile(tmp_path)
    original_bytes = (tmp_path / "journal.txt").read_bytes()
    third = next(e for e in journal if "third" in e.title)

    with mock.patch(
        "jrnl.journals.Journal.atomic_write", side_effect=OSError("disk full")
    ):
        with pytest.raises(JrnlException) as exc:
            journal.save_deleted_entries([third])

    assert exc.value.has_message_text(MsgText.DeletedEntriesRecordWriteFailed)
    assert (tmp_path / "journal.txt").read_bytes() == original_bytes
    assert not os.path.exists(journal.deleted_entries_filename())
    assert _no_temp_files_left(str(tmp_path))


def test_controller_delete_aborts_before_touching_journal(tmp_path):
    journal = _open_onefile(tmp_path)
    original_bytes = (tmp_path / "journal.txt").read_bytes()
    third = next(e for e in journal if "third" in e.title)
    journal.prompt_action_entries = lambda message: [third]

    with mock.patch.object(
        journal,
        "save_deleted_entries",
        side_effect=JrnlException(),
    ):
        with pytest.raises(JrnlException):
            _delete_search_results(journal, old_entries=list(journal.entries))

    assert (tmp_path / "journal.txt").read_bytes() == original_bytes
    assert third in journal.entries
    assert _no_temp_files_left(str(tmp_path))


# --- folder journal --- #


def test_folder_restore_recreates_emptied_day_file(tmp_path):
    journal = _open_folder(tmp_path)
    solo_day_file = tmp_path / "journal" / "2020" / "01" / "01.txt"
    assert solo_day_file.exists()

    solo = next(e for e in journal if "Solo" in e.title)
    journal.save_deleted_entries([solo])
    journal.delete_entries([solo])
    journal.write()

    # the emptied date file is gone, its directories remain
    assert not solo_day_file.exists()
    assert solo_day_file.parent.is_dir()

    reopened = _reopen_folder(tmp_path)
    assert len(reopened) == 2
    assert reopened.restore_deleted_entries() == 1

    restored = _reopen_folder(tmp_path)
    assert solo_day_file.exists()
    assert len(restored) == 3
    restored_solo = next(e for e in restored if "Solo" in e.title)
    assert restored_solo.date.date() == datetime.date(2020, 1, 1)
    assert "@alone" in restored_solo.tags


def test_folder_restore_appends_to_existing_same_day_file(tmp_path):
    journal = _open_folder(tmp_path)
    morning = next(e for e in journal if "First of two" in e.title)

    journal.save_deleted_entries([morning])
    journal.delete_entries([morning])
    journal.write()

    day_file = tmp_path / "journal" / "2020" / "01" / "02.txt"
    assert "@evening" in day_file.read_text()
    assert "@morning" not in day_file.read_text()

    reopened = _reopen_folder(tmp_path)
    assert reopened.restore_deleted_entries() == 1

    restored = _reopen_folder(tmp_path)
    same_day = [e for e in restored if e.date.date() == datetime.date(2020, 1, 2)]
    assert len(same_day) == 2
    titles = " ".join(e.title for e in same_day)
    assert "First of two" in titles
    assert "Second of two" in titles
    # restored exactly once, no duplicates
    assert len(restored) == 3


def test_folder_record_is_not_inside_journal_tree(tmp_path):
    journal = _open_folder(tmp_path)
    solo = next(e for e in journal if "Solo" in e.title)
    journal.save_deleted_entries([solo])

    record_path = journal.deleted_entries_filename()
    # the record is a sibling of the folder root, never globbed as a day file
    assert record_path == str(tmp_path / ".journal.jrnl-deleted")
    assert not record_path.startswith(str(tmp_path / "journal") + os.sep)
    assert len(_reopen_folder(tmp_path)) == 3


def test_folder_editor_deletion_recovers(tmp_path):
    journal = _open_folder(tmp_path)
    edited = "\n".join(str(e) for e in journal if "Solo" not in e.title)
    journal.parse_editable_str(edited)
    journal.write()

    assert os.path.exists(journal.deleted_entries_filename())
    reopened = _reopen_folder(tmp_path)
    assert len(reopened) == 2
    assert reopened.restore_deleted_entries() == 1
    assert len(_reopen_folder(tmp_path)) == 3


# --- corrupt records --- #


@pytest.mark.parametrize(
    "corruption",
    [
        b"not a jrnl record",
        DELETED_ENTRIES_RECORD_MAGIC + b"{not json",
        DELETED_ENTRIES_RECORD_MAGIC + b'{"version": 99, "entries": []}',
        DELETED_ENTRIES_RECORD_MAGIC + b'{"version": 1, "entries": []}',
        DELETED_ENTRIES_RECORD_MAGIC
        + b'{"version": 1, "entries": [{"date": "nope", "starred": false, '
        + b'"text": "[2020-01-01 00:00] x\\n"}]}',
        DELETED_ENTRIES_RECORD_MAGIC
        + b'{"version": 1, "entries": [{"date": "2020-01-01T00:00:00", '
        + b'"starred": "yes", "text": "[2020-01-01 00:00] x\\n"}]}',
    ],
)
def test_corrupt_record_restores_nothing_and_leaves_journal_unchanged(
    tmp_path, corruption
):
    journal = _open_onefile(tmp_path)
    third = next(e for e in journal if "third" in e.title)
    journal.save_deleted_entries([third])
    journal.delete_entries([third])
    journal.write()
    journal_after_delete = (tmp_path / "journal.txt").read_bytes()

    record_path = journal.deleted_entries_filename()
    with open(record_path, "wb") as f:
        f.write(corruption)

    reopened = _reopen_onefile(tmp_path)
    with pytest.raises(JrnlException) as exc:
        reopened.restore_deleted_entries()

    assert exc.value.has_message_text(MsgText.DeletedEntriesRecordCorrupt)
    assert len(reopened) == 2
    assert (tmp_path / "journal.txt").read_bytes() == journal_after_delete
    # the corrupt record is kept for inspection
    assert os.path.exists(record_path)


# --- encrypted journals keep the record protected --- #


def test_record_for_encrypted_journal_uses_journal_encryption(tmp_path):
    journal = Journal("default", journal=str(tmp_path / "journal.txt"), encrypt=True)
    journal.entries = journal._parse(JOURNAL_TEXT)
    encrypt_spy = mock.Mock(
        side_effect=lambda text: b"ENCRYPTED:" + text.encode("utf-8")
    )
    decrypt_spy = mock.Mock(
        side_effect=lambda data: data[len(b"ENCRYPTED:") :].decode("utf-8")
    )
    journal._encrypt = encrypt_spy
    journal._decrypt = decrypt_spy

    third = next(e for e in journal if "third" in e.title)
    journal.save_deleted_entries([third])
    encrypt_spy.assert_called_once()

    raw = (tmp_path / ".journal.txt.jrnl-deleted").read_bytes()
    assert raw.startswith(DELETED_ENTRIES_RECORD_MAGIC)
    body = raw[len(DELETED_ENTRIES_RECORD_MAGIC) :]
    # the body went through the journal's encryption layer
    assert body.startswith(b"ENCRYPTED:")

    restoring = Journal("default", journal=str(tmp_path / "journal.txt"), encrypt=True)
    restoring._decrypt = decrypt_spy
    recovered = restoring._load_deleted_entries()
    decrypt_spy.assert_called_once()
    assert len(recovered) == 1
    assert "third" in recovered[0].title
