# Copyright © 2012-2023 jrnl contributors
# License: https://www.gnu.org/licenses/gpl-3.0.html

"""
Read-only probing of the journals configured in the config file.

The functions here answer, without ever creating or modifying anything and
without ever prompting for a password:

* whether the configured journal path is reachable -- readable, missing, or
  present but unreadable (encrypted journals are reported as locked);
* which journal type the path holds -- a single file, a directory of per-day
  files, or a Day One directory.

The type decision deliberately uses the same rules as ``open_journal``:

* a directory whose name ends in ``.dayone`` or which contains an ``entries``
  member is a Day One journal;
* any other directory that contains per-day files (the ``YYYY/MM/DD.txt``
  layout recognized by ``FolderJournal``) is a folder journal;
* everything else that exists is treated as a single file.

Unlike ``open_journal`` (and ``Journal.open`` in particular), probing never
creates a missing file or directory and never writes, so listing and the
installation self-check are safe to run against broken configurations.
"""

import logging
import os
import stat

from jrnl.config import scope_config
from jrnl.path import expand_path

# Reachability values reported for every configured journal.
READABLE = "readable"
MISSING = "missing"
UNREADABLE = "unreadable"
LOCKED = "locked"

# Journal type values. ``None`` means the type cannot be determined (e.g. the
# path is missing or an ordinary directory that is not a journal).
FILE_TYPE = "file"
FOLDER_TYPE = "folder"
DAYONE_TYPE = "dayone"


def is_dayone_directory(journal_path: str, directory_entries: list[str]) -> bool:
    """The same Day One detection rule ``open_journal`` uses.

    ``journal_path`` is the configured (path-expanded) journal path and
    ``directory_entries`` is the result of ``os.listdir(journal_path)``.
    """
    return journal_path.strip("/").endswith(".dayone") or (
        "entries" in directory_entries
    )


def probe_all_journals(config: dict) -> dict:
    """Probe every journal configured in ``config``.

    Returns a mapping with three keys:

    * ``journals`` -- an ordered dict of journal name to a per-journal report;
    * ``problems`` -- a list of ``{"journal", "path", "reason"}`` mappings for
      the journals that need the user's attention (missing, unreadable, or not
      actually a journal);
    * ``summary`` -- counts keyed by reachability plus a ``problems`` count.

    A failure while probing one journal never prevents the remaining journals
    from being probed.
    """
    reports: dict[str, dict] = {}
    problems: list[dict] = []

    for journal_name in config.get("journals", {}):
        report = probe_journal(journal_name, config)
        reports[journal_name] = report
        if report.get("reason"):
            problems.append(
                {
                    "journal": journal_name,
                    "path": report["path"],
                    "reason": report["reason"],
                }
            )

    summary = {
        "total": len(reports),
        READABLE: 0,
        LOCKED: 0,
        MISSING: 0,
        UNREADABLE: 0,
        "problems": len(problems),
    }
    for report in reports.values():
        summary[report["status"]] += 1

    return {"journals": reports, "problems": problems, "summary": summary}


def probe_journal(journal_name: str, config: dict) -> dict:
    """Probe a single configured journal without opening (or creating) it.

    The report always contains ``path``, ``status`` and ``type``. Readable
    plaintext journals additionally contain ``entry_count`` and, when they have
    at least one entry, ``last_entry_time``. Journals with a problem carry a
    ``reason`` string.
    """
    report: dict = {}

    try:
        scoped = scope_config(config, journal_name).copy()
        scoped["journal"] = expand_path(scoped["journal"])
        path = scoped["journal"]
        report["path"] = path

        try:
            path_stat = os.stat(path)
        except FileNotFoundError:
            # Same rule open_journal applies to a path that does not exist: a
            # trailing separator means a folder journal, anything else a file.
            prospective_type = FOLDER_TYPE if path.endswith(os.sep) else FILE_TYPE
            return _finalize(
                report,
                status=MISSING,
                journal_type=prospective_type,
                reason="Journal path does not exist",
            )
        except PermissionError as e:
            return _finalize(
                report,
                status=UNREADABLE,
                journal_type=None,
                reason=os.strerror(e.errno) or "Permission denied",
            )
        except OSError as e:
            return _finalize(
                report,
                status=UNREADABLE,
                journal_type=None,
                reason=str(e),
            )

        if stat.S_ISDIR(path_stat.st_mode):
            return _probe_directory(journal_name, scoped, path, report)

        if stat.S_ISREG(path_stat.st_mode):
            return _probe_file(journal_name, scoped, path, report)

        # Exists, but is neither a file nor a directory (socket, device, ...)
        return _finalize(
            report,
            status=UNREADABLE,
            journal_type=None,
            reason="Path is neither a file nor a directory",
        )

    except Exception as e:  # one broken journal must not break the whole list
        logging.debug("Failed to probe journal '%s'", journal_name, exc_info=True)
        report.setdefault("path", "")
        return _finalize(
            report,
            status=UNREADABLE,
            journal_type=report.get("type"),
            reason=f"{type(e).__name__}: {e}",
        )


def _probe_directory(journal_name: str, scoped: dict, path: str, report: dict) -> dict:
    try:
        directory_entries = os.listdir(path)
    except PermissionError as e:
        journal_type = DAYONE_TYPE if path.strip("/").endswith(".dayone") else None
        return _finalize(
            report,
            status=UNREADABLE,
            journal_type=journal_type,
            reason=os.strerror(e.errno) or "Permission denied",
        )
    except OSError as e:
        return _finalize(report, status=UNREADABLE, journal_type=None, reason=str(e))

    if is_dayone_directory(path, directory_entries):
        return _probe_dayone(journal_name, scoped, path, report)

    return _probe_folder(journal_name, scoped, path, report)


def _probe_dayone(journal_name: str, scoped: dict, path: str, report: dict) -> dict:
    # Directory journals cannot be encrypted; open_journal warns about this
    # config mistake but still opens the journal, so report the same way.
    reason = _encryption_configured_for_directory(journal_name, scoped)

    from jrnl.journals.DayOneJournal import DayOne

    journal = DayOne(**scoped).open()
    _add_entry_stats(report, journal)
    return _finalize(
        report,
        status=READABLE,
        journal_type=DAYONE_TYPE,
        reason=reason,
    )


def _probe_folder(journal_name: str, scoped: dict, path: str, report: dict) -> dict:
    from jrnl.journals.FolderJournal import Folder

    # Only a directory holding the YYYY/MM/DD.txt layout is a folder journal;
    # an ordinary directory (empty, or containing unrelated files) is not
    # reported as a journal. This uses the exact globbing Folder.open() uses.
    if not next(Folder._get_files(path), None):
        return _finalize(
            report,
            status=READABLE,
            journal_type=None,
            reason=(
                "Directory is not a Day One journal and contains no per-day entry files"
            ),
        )

    reason = _encryption_configured_for_directory(journal_name, scoped)

    journal = Folder(journal_name, **scoped).open()
    _add_entry_stats(report, journal)
    return _finalize(
        report,
        status=READABLE,
        journal_type=FOLDER_TYPE,
        reason=reason,
    )


def _probe_file(journal_name: str, scoped: dict, path: str, report: dict) -> dict:
    try:
        with open(path, "rb") as f:
            data = f.read()
    except PermissionError as e:
        return _finalize(
            report,
            status=UNREADABLE,
            journal_type=FILE_TYPE,
            reason=os.strerror(e.errno) or "Permission denied",
        )
    except OSError as e:
        return _finalize(
            report,
            status=UNREADABLE,
            journal_type=FILE_TYPE,
            reason=str(e),
        )

    if _is_locked(data, scoped):
        # Never prompt for a password and never decrypt; just report locked.
        return _finalize(report, status=LOCKED, journal_type=FILE_TYPE)

    try:
        text = data.decode("utf-8")
        # Same parsing a plain open() performs, minus the file creation and
        # the (non-existent, as the journal is not encrypted) decryption.
        from jrnl.journals.Journal import Journal

        journal = Journal(journal_name, **scoped)
        journal.entries = journal._parse(text)
    except UnicodeDecodeError as e:
        return _finalize(
            report,
            status=UNREADABLE,
            journal_type=FILE_TYPE,
            reason=f"Journal is not valid UTF-8: {e}",
        )
    except Exception as e:
        logging.debug("Failed to parse journal '%s'", journal_name, exc_info=True)
        return _finalize(
            report,
            status=UNREADABLE,
            journal_type=FILE_TYPE,
            reason=f"{type(e).__name__}: {e}",
        )

    _add_entry_stats(report, journal)
    return _finalize(report, status=READABLE, journal_type=FILE_TYPE)


def _is_locked(data: bytes, scoped: dict) -> bool:
    """A journal is locked when the config says it is encrypted, or when the
    on-disk content carries an encrypted format header. Only magic-byte
    detection is used, so no password prompt or decryption is needed."""
    if scoped.get("encrypt"):
        return True

    from jrnl.encryption.Jrnlv2Encryption import is_v2_encrypted
    from jrnl.encryption.Jrnlv3Encryption import is_v3_encrypted

    return is_v3_encrypted(data) or is_v2_encrypted(data)


def _encryption_configured_for_directory(journal_name: str, scoped: dict):
    if scoped.get("encrypt"):
        return (
            f"Config for journal '{journal_name}' has 'encrypt' set to true, "
            "but directory journals cannot be encrypted"
        )
    return None


def _add_entry_stats(report: dict, journal) -> None:
    report["entry_count"] = len(journal)
    if journal.entries:
        report["last_entry_time"] = max(
            entry.date for entry in journal.entries
        ).isoformat()


def _finalize(
    report: dict, status: str, journal_type: str | None, reason: str | None = None
) -> dict:
    finalized = {
        "path": report.get("path", ""),
        "status": status,
        "type": journal_type,
    }
    if "entry_count" in report:
        finalized["entry_count"] = report["entry_count"]
    if "last_entry_time" in report:
        finalized["last_entry_time"] = report["last_entry_time"]
    if reason:
        finalized["reason"] = reason
    report.clear()
    report.update(finalized)
    return report
