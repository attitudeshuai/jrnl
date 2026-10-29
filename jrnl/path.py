# Copyright © 2012-2023 jrnl contributors
# License: https://www.gnu.org/licenses/gpl-3.0.html

import contextlib
import os
import os.path
import stat
import tempfile
from pathlib import Path

import xdg.BaseDirectory

from jrnl.exception import JrnlException
from jrnl.messages import Message
from jrnl.messages import MsgStyle
from jrnl.messages import MsgText

# Constants
XDG_RESOURCE = "jrnl"
DEFAULT_CONFIG_NAME = "jrnl.yaml"
DEFAULT_JOURNAL_NAME = "journal.txt"


def home_dir() -> str:
    return os.path.expanduser("~")


def expand_path(path: str) -> str:
    return os.path.expanduser(os.path.expandvars(path))


def absolute_path(path: str) -> str:
    return os.path.abspath(expand_path(path))


def get_default_journal_path() -> str:
    journal_data_path = xdg.BaseDirectory.save_data_path(XDG_RESOURCE) or home_dir()
    return os.path.join(journal_data_path, DEFAULT_JOURNAL_NAME)


def get_templates_path() -> str:
    """
    Get the path to the XDG templates directory. Creates the directory if it
    doesn't exist.
    """
    # jrnl_xdg_resource_path is created by save_data_path if it does not exist
    jrnl_xdg_resource_path = Path(xdg.BaseDirectory.save_data_path(XDG_RESOURCE))
    jrnl_templates_path = jrnl_xdg_resource_path / "templates"
    # Create the directory if needed.
    jrnl_templates_path.mkdir(exist_ok=True)
    return str(jrnl_templates_path)


def get_config_directory() -> str:
    try:
        return xdg.BaseDirectory.save_config_path(XDG_RESOURCE)
    except FileExistsError:
        raise JrnlException(
            Message(
                MsgText.ConfigDirectoryIsFile,
                MsgStyle.ERROR,
                {
                    "config_directory_path": os.path.join(
                        xdg.BaseDirectory.xdg_config_home, XDG_RESOURCE
                    )
                },
            ),
        )


def get_config_path() -> str:
    try:
        config_directory_path = get_config_directory()
    except JrnlException:
        return os.path.join(home_dir(), DEFAULT_CONFIG_NAME)
    return os.path.join(config_directory_path, DEFAULT_CONFIG_NAME)


def atomic_write(filename: str, data: bytes) -> None:
    """Writes data to filename atomically, so a crash or kill mid-write can't
    leave the file truncated or corrupted. Writes to a temp file in the same
    directory, then replaces the target in a single filesystem operation.

    Symbolic links are followed: the temp file replaces the file the link
    points at, never the link itself, and the target's permission bits are
    preserved. Targets with several hard links are rewritten through their
    existing inode so every name keeps seeing the same content. Unwritable
    destinations are rejected with a JrnlException before anything is
    written."""
    target_path, target_stat = _resolve_write_target(filename)

    if target_stat is None:
        # Target doesn't exist (and isn't a dangling link): create it with
        # the process's default permissions via the temp file.
        replace_dir = os.path.dirname(filename) or "."
        _require_writable_directory(filename, replace_dir)
        _replace_atomic(filename, data, replace_dir, mode=None)
    elif target_stat.st_nlink > 1:
        # Replacing the path would leave the other names pointing at a stale
        # independent copy; write through the shared inode instead.
        _require_in_place_writable(filename, target_path, target_stat.st_nlink)
        _write_through_inode(target_path, data)
    else:
        replace_dir = os.path.dirname(target_path) or "."
        _require_writable_directory(filename, replace_dir)
        _replace_atomic(
            target_path, data, replace_dir, mode=stat.S_IMODE(target_stat.st_mode)
        )


def _resolve_write_target(filename: str) -> tuple[str, os.stat_result | None]:
    """Returns (path to actually write, stat result) for filename, following
    symbolic links. Raises JrnlException on targets that must never be
    written: dangling links, directories, and other non-regular files."""
    if os.path.islink(filename):
        target_path = os.path.realpath(filename)
        try:
            target_stat = os.stat(filename)
        except FileNotFoundError:
            raise JrnlException(
                Message(
                    MsgText.JournalWriteBrokenSymlink,
                    MsgStyle.ERROR,
                    {"filename": filename, "target": os.readlink(filename)},
                )
            )
        _assert_regular_file(filename, target_path, target_stat)
        return target_path, target_stat

    try:
        target_stat = os.lstat(filename)
    except FileNotFoundError:
        return filename, None

    _assert_regular_file(filename, filename, target_stat)
    return filename, target_stat


def _assert_regular_file(
    filename: str, target_path: str, target_stat: os.stat_result
) -> None:
    if stat.S_ISDIR(target_stat.st_mode):
        raise JrnlException(
            Message(
                MsgText.JournalWriteTargetIsDirectory,
                MsgStyle.ERROR,
                {"filename": filename, "target": target_path},
            )
        )
    if not stat.S_ISREG(target_stat.st_mode):
        raise JrnlException(
            Message(
                MsgText.JournalWriteTargetNotRegularFile,
                MsgStyle.ERROR,
                {"filename": filename, "target": target_path},
            )
        )


def _require_writable_directory(filename: str, directory: str) -> None:
    if os.path.isdir(directory) and not os.access(directory, os.W_OK):
        raise JrnlException(
            Message(
                MsgText.JournalWriteDirectoryNotWritable,
                MsgStyle.ERROR,
                {"filename": filename, "directory": directory},
            )
        )


def _require_in_place_writable(
    filename: str, target_path: str, link_count: int
) -> None:
    if not os.access(target_path, os.W_OK | os.R_OK):
        raise JrnlException(
            Message(
                MsgText.JournalWriteHardLinksNotWritable,
                MsgStyle.ERROR,
                {"filename": filename, "link_count": link_count},
            )
        )


def _write_all_fd(fd: int, data: bytes) -> None:
    view = memoryview(data)
    while view:
        written = os.write(fd, view)
        if written == 0:
            msg = "os.write wrote 0 bytes"
            raise OSError(msg)
        view = view[written:]


def _write_through_inode(target_path: str, data: bytes) -> None:
    """Rewrites the file at target_path without replacing its inode, so
    symbolic links and every hard-linked name keep pointing at the same file.
    The original content is restored if writing fails partway through."""
    fd = os.open(target_path, os.O_RDWR)
    try:
        original = b""
        while True:
            chunk = os.read(fd, 1024 * 1024)
            if not chunk:
                break
            original += chunk

        try:
            os.lseek(fd, 0, os.SEEK_SET)
            _write_all_fd(fd, data)
            os.ftruncate(fd, len(data))
        except BaseException:
            with contextlib.suppress(OSError):
                os.lseek(fd, 0, os.SEEK_SET)
                _write_all_fd(fd, original)
                os.ftruncate(fd, len(original))
            raise
    finally:
        os.close(fd)


def _replace_atomic(
    target_path: str, data: bytes, replace_dir: str, mode: int | None
) -> None:
    fd, tmp_path = tempfile.mkstemp(dir=replace_dir, prefix=".jrnl-", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        if mode is not None:
            os.chmod(tmp_path, mode)
        os.replace(tmp_path, target_path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.remove(tmp_path)
        raise
