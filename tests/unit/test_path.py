# Copyright © 2012-2023 jrnl contributors
# License: https://www.gnu.org/licenses/gpl-3.0.html

import os
import random
import stat
import string
from os import getenv
from unittest.mock import patch

import pytest

from jrnl.exception import JrnlException
from jrnl.messages import MsgText
from jrnl.path import absolute_path
from jrnl.path import atomic_write
from jrnl.path import expand_path
from jrnl.path import home_dir


@pytest.fixture
def home_dir_str(monkeypatch):
    username = "username"
    monkeypatch.setenv("USERPROFILE", username)  # for windows
    monkeypatch.setenv("HOME", username)  # for *nix
    return username


@pytest.fixture
def random_test_var(monkeypatch):
    name = f"JRNL_TEST_{''.join(random.sample(string.ascii_uppercase, 10))}"
    val = "".join(random.sample(string.ascii_lowercase, 25))
    monkeypatch.setenv(name, val)
    return (name, val)


def test_home_dir(home_dir_str):
    assert home_dir() == home_dir_str


@pytest.mark.on_posix
@pytest.mark.parametrize(
    "path",
    ["~"],
)
def test_expand_path_actually_expands_mac_linux(path):
    # makes sure that path isn't being returns as-is
    assert expand_path(path) != path


@pytest.mark.on_win
@pytest.mark.parametrize(
    "path",
    ["~", "%USERPROFILE%"],
)
def test_expand_path_actually_expands_windows(path):
    # makes sure that path isn't being returns as-is
    assert expand_path(path) != path


@pytest.mark.on_posix
@pytest.mark.parametrize(
    "paths",
    [
        ["~", "HOME"],
    ],
)
def test_expand_path_expands_into_correct_value_mac_linux(paths):
    input_path, expected_path = paths[0], paths[1]
    assert expand_path(input_path) == getenv(expected_path)


@pytest.mark.on_win
@pytest.mark.parametrize(
    "paths",
    [
        ["~", "USERPROFILE"],
        ["%USERPROFILE%", "USERPROFILE"],
    ],
)
def test_expand_path_expands_into_correct_value_windows(paths):
    input_path, expected_path = paths[0], paths[1]
    assert expand_path(input_path) == getenv(expected_path)


@pytest.mark.on_posix
@pytest.mark.parametrize("_", range(25))
def test_expand_path_expands_into_random_env_value_mac_linux(_, random_test_var):
    var_name, var_value = random_test_var[0], random_test_var[1]
    assert expand_path(var_name) == var_name
    assert expand_path(f"${var_name}") == var_value  # mac & linux
    assert expand_path(f"${var_name}") == getenv(var_name)


@pytest.mark.on_win
@pytest.mark.parametrize("_", range(25))
def test_expand_path_expands_into_random_env_value_windows(_, random_test_var):
    var_name, var_value = random_test_var[0], random_test_var[1]
    assert expand_path(var_name) == var_name
    assert expand_path(f"%{var_name}%") == var_value  # windows
    assert expand_path(f"%{var_name}%") == getenv(var_name)


@patch("jrnl.path.expand_path")
@patch("os.path.abspath")
def test_absolute_path(mock_abspath, mock_expand_path):
    test_val = "test_value"

    assert absolute_path(test_val) == mock_abspath.return_value
    mock_expand_path.assert_called_with(test_val)
    mock_abspath.assert_called_with(mock_expand_path.return_value)


def test_atomic_write_creates_new_file(tmp_path):
    filename = str(tmp_path / "journal.txt")

    atomic_write(filename, b"hello world")

    with open(filename, "rb") as f:
        assert f.read() == b"hello world"
    # no leftover temp file
    assert os.listdir(tmp_path) == ["journal.txt"]


def test_atomic_write_replaces_existing_file(tmp_path):
    filename = str(tmp_path / "journal.txt")
    with open(filename, "wb") as f:
        f.write(b"old content")

    atomic_write(filename, b"new content")

    with open(filename, "rb") as f:
        assert f.read() == b"new content"
    assert os.listdir(tmp_path) == ["journal.txt"]


def test_atomic_write_leaves_original_untouched_on_failure(tmp_path, monkeypatch):
    filename = str(tmp_path / "journal.txt")
    with open(filename, "wb") as f:
        f.write(b"original content")

    def broken_replace(*args, **kwargs):
        msg = "simulated failure"
        raise OSError(msg)

    monkeypatch.setattr(os, "replace", broken_replace)

    with pytest.raises(OSError):
        atomic_write(filename, b"new content")

    with open(filename, "rb") as f:
        assert f.read() == b"original content"
    # the temp file should have been cleaned up, leaving just the original
    assert os.listdir(tmp_path) == ["journal.txt"]


def test_atomic_write_new_file_uses_default_permissions(tmp_path):
    filename = str(tmp_path / "brand_new.txt")

    atomic_write(filename, b"content")

    # mkstemp creates files readable and writable only by the owner
    assert stat.S_IMODE(os.stat(filename).st_mode) == 0o600
    assert os.listdir(tmp_path) == ["brand_new.txt"]


@pytest.mark.on_posix
@pytest.mark.parametrize("mode", [0o600, 0o640, 0o644, 0o604])
def test_atomic_write_preserves_existing_permissions(tmp_path, mode):
    filename = str(tmp_path / "journal.txt")
    with open(filename, "wb") as f:
        f.write(b"old content")
    os.chmod(filename, mode)

    atomic_write(filename, b"new content")

    assert stat.S_IMODE(os.stat(filename).st_mode) == mode


@pytest.mark.on_posix
def test_atomic_write_follows_symlink_and_keeps_link(tmp_path):
    link_dir = tmp_path / "synced_folder"
    real_dir = tmp_path / "elsewhere"
    link_dir.mkdir()
    real_dir.mkdir()
    real_file = real_dir / "real.journal"
    link_file = link_dir / "journal.txt"
    real_file.write_bytes(b"old content")
    os.chmod(real_file, 0o640)
    os.symlink(real_file, link_file)

    atomic_write(str(link_file), b"new content")

    # the link is still a link pointing at the same target
    assert os.path.islink(link_file)
    assert os.path.realpath(link_file) == str(real_file)
    assert real_file.read_bytes() == b"new content"
    # no temp file lingers in either directory
    assert os.listdir(link_dir) == ["journal.txt"]
    assert os.listdir(real_dir) == ["real.journal"]
    # the target keeps its original permission bits
    assert stat.S_IMODE(real_file.stat().st_mode) == 0o640


@pytest.mark.on_posix
def test_atomic_write_follows_relative_symlink(tmp_path):
    real_file = tmp_path / "real.journal"
    link_file = tmp_path / "link.journal"
    real_file.write_bytes(b"old")
    os.symlink("real.journal", link_file)

    atomic_write(str(link_file), b"new content")

    assert os.path.islink(link_file)
    assert os.readlink(link_file) == "real.journal"
    assert real_file.read_bytes() == b"new content"


@pytest.mark.on_posix
def test_atomic_write_reject_dangling_symlink(tmp_path):
    link_file = tmp_path / "journal.txt"
    missing_target = tmp_path / "missing.journal"
    os.symlink(missing_target, link_file)

    with pytest.raises(JrnlException) as exc_info:
        atomic_write(str(link_file), b"new content")

    assert exc_info.value.has_message_text(MsgText.JournalWriteBrokenSymlink)
    # nothing was created and no temp file lingers
    assert os.path.islink(link_file)
    assert not missing_target.exists()
    assert os.listdir(tmp_path) == ["journal.txt"]


@pytest.mark.on_posix
def test_atomic_write_rejects_symlink_to_directory(tmp_path):
    target_dir = tmp_path / "a_directory"
    target_dir.mkdir()
    link_file = tmp_path / "journal.txt"
    os.symlink(target_dir, link_file)

    with pytest.raises(JrnlException) as exc_info:
        atomic_write(str(link_file), b"new content")

    assert exc_info.value.has_message_text(MsgText.JournalWriteTargetIsDirectory)
    assert os.path.islink(link_file)
    assert os.listdir(target_dir) == []
    assert not [n for n in os.listdir(tmp_path) if n.startswith(".jrnl-")]


@pytest.mark.on_posix
def test_atomic_write_rejects_plain_directory(tmp_path):
    target_dir = tmp_path / "journal.d"
    target_dir.mkdir()

    with pytest.raises(JrnlException) as exc_info:
        atomic_write(str(target_dir), b"new content")

    assert exc_info.value.has_message_text(MsgText.JournalWriteTargetIsDirectory)
    assert os.path.isdir(target_dir)


@pytest.mark.on_posix
def test_atomic_write_rejects_unwritable_directory(tmp_path):
    filename = tmp_path / "journal.txt"
    filename.write_bytes(b"original content")
    os.chmod(tmp_path, 0o555)

    try:
        with pytest.raises(JrnlException) as exc_info:
            atomic_write(str(filename), b"new content")
    finally:
        os.chmod(tmp_path, 0o755)

    assert exc_info.value.has_message_text(MsgText.JournalWriteDirectoryNotWritable)
    # the write never started: original content and no temp file
    assert filename.read_bytes() == b"original content"
    assert os.listdir(tmp_path) == ["journal.txt"]


@pytest.mark.on_posix
def test_atomic_write_keeps_hard_links_pointing_at_new_content(tmp_path):
    first_name = tmp_path / "a.journal"
    other_name = tmp_path / "b.journal"
    first_name.write_bytes(b"old content")
    os.link(first_name, other_name)
    original_inode = first_name.stat().st_ino
    os.chmod(first_name, 0o640)

    atomic_write(str(first_name), b"new and possibly shorter")

    # same inode, still two names, both reading the new content
    assert first_name.stat().st_ino == original_inode
    assert first_name.stat().st_nlink == 2
    assert os.path.samefile(first_name, other_name)
    assert other_name.read_bytes() == b"new and possibly shorter"
    # inode is reused, so permission bits and directory contents are untouched
    assert stat.S_IMODE(first_name.stat().st_mode) == 0o640
    assert sorted(os.listdir(tmp_path)) == ["a.journal", "b.journal"]


@pytest.mark.on_posix
def test_atomic_write_hard_link_via_symlink_updates_every_name(tmp_path):
    real_dir = tmp_path / "elsewhere"
    real_dir.mkdir()
    real_file = real_dir / "real.journal"
    other_name = real_dir / "second.name"
    real_file.write_bytes(b"old content")
    os.link(real_file, other_name)
    link_file = tmp_path / "journal.txt"
    os.symlink(real_file, link_file)

    atomic_write(str(link_file), b"new content")

    assert os.path.islink(link_file)
    assert real_file.stat().st_nlink == 2
    assert other_name.read_bytes() == b"new content"
    assert sorted(os.listdir(real_dir)) == ["real.journal", "second.name"]


@pytest.mark.on_posix
def test_atomic_write_refuses_when_hard_links_cannot_be_kept(tmp_path):
    first_name = tmp_path / "a.journal"
    other_name = tmp_path / "b.journal"
    first_name.write_bytes(b"old content")
    os.link(first_name, other_name)
    os.chmod(first_name, 0o444)

    try:
        with pytest.raises(JrnlException) as exc_info:
            atomic_write(str(first_name), b"new content")
    finally:
        os.chmod(first_name, 0o644)

    assert exc_info.value.has_message_text(MsgText.JournalWriteHardLinksNotWritable)
    # nothing changed: both names keep the old content and the inode
    assert first_name.read_bytes() == b"old content"
    assert other_name.read_bytes() == b"old content"
    assert os.path.samefile(first_name, other_name)
    assert sorted(os.listdir(tmp_path)) == ["a.journal", "b.journal"]


@pytest.mark.on_posix
def test_atomic_write_in_place_failure_restores_original(tmp_path, monkeypatch):
    first_name = tmp_path / "a.journal"
    other_name = tmp_path / "b.journal"
    first_name.write_bytes(b"original content")
    os.link(first_name, other_name)

    real_write = os.write
    call_count = {"n": 0}

    def fail_first_write(fd, data):
        call_count["n"] += 1
        if call_count["n"] == 1:
            msg = "simulated in-place write failure"
            raise OSError(msg)
        return real_write(fd, data)

    monkeypatch.setattr(os, "write", fail_first_write)

    with pytest.raises(OSError):
        atomic_write(str(first_name), b"new content")

    # rollback restored the original bytes through the same shared inode
    assert first_name.read_bytes() == b"original content"
    assert other_name.read_bytes() == b"original content"
    assert os.path.samefile(first_name, other_name)
    assert sorted(os.listdir(tmp_path)) == ["a.journal", "b.journal"]


@pytest.mark.on_posix
def test_atomic_write_replace_failure_through_symlink_is_safe(tmp_path, monkeypatch):
    link_dir = tmp_path / "synced_folder"
    real_dir = tmp_path / "elsewhere"
    link_dir.mkdir()
    real_dir.mkdir()
    real_file = real_dir / "real.journal"
    link_file = link_dir / "journal.txt"
    real_file.write_bytes(b"original content")
    os.chmod(real_file, 0o604)
    os.symlink(real_file, link_file)

    def broken_replace(*args, **kwargs):
        msg = "simulated failure"
        raise OSError(msg)

    monkeypatch.setattr(os, "replace", broken_replace)

    with pytest.raises(OSError):
        atomic_write(str(link_file), b"new content")

    assert os.path.islink(link_file)
    assert real_file.read_bytes() == b"original content"
    assert stat.S_IMODE(real_file.stat().st_mode) == 0o604
    assert os.listdir(link_dir) == ["journal.txt"]
    assert os.listdir(real_dir) == ["real.journal"]
