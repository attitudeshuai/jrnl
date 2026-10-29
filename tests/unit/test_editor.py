# Copyright © 2012-2023 jrnl contributors
# License: https://www.gnu.org/licenses/gpl-3.0.html

import io
import os
from unittest.mock import Mock
from unittest.mock import mock_open
from unittest.mock import patch

import pytest

from jrnl.editor import get_template_path
from jrnl.editor import get_text_from_editor
from jrnl.editor import read_stdin_text
from jrnl.editor import read_template_file
from jrnl.exception import JrnlException
from jrnl.messages import MsgText
from jrnl.os_compat import UTF8_BOM
from jrnl.os_compat import decode_bytes
from jrnl.os_compat import normalize_newlines


@patch(
    "os.getcwd", side_effect="/"
)  # prevent failures in CI if current directory has been deleted
@patch("builtins.open", side_effect=FileNotFoundError())
def test_read_template_file_with_no_file_raises_exception(mock_open, mock_getcwd):
    with pytest.raises(JrnlException) as ex:
        read_template_file("invalid_file.txt")
        assert isinstance(ex.value, JrnlException)


@patch(
    "os.getcwd", side_effect="/"
)  # prevent failures in CI if current directory has been deleted
@patch("builtins.open", new_callable=mock_open, read_data="template text")
def test_read_template_file_with_valid_file_returns_text(mock_file, mock_getcwd):
    assert read_template_file("valid_file.txt") == "template text"


def test_get_template_path_when_exists_returns_correct_path():
    with patch("os.path.exists", return_value=True):
        output = get_template_path("template", "templatepath")

    assert output == os.path.join("templatepath", "template")


@patch("jrnl.editor.absolute_path")
def test_get_template_path_when_doesnt_exist_returns_correct_path(mock_absolute_paths):
    with patch("os.path.exists", return_value=False):
        output = get_template_path("template", "templatepath")

    assert output == mock_absolute_paths.return_value


def test_read_stdin_text_with_invalid_utf8_does_not_raise():
    # Regression test for https://github.com/jrnl-org/jrnl/issues/2082
    # A backspace over a multi-byte character (e.g. ß) in a canonical-mode
    # terminal only erases one byte, leaving stray invalid UTF-8 like this.
    raw_bytes = b"I saw Elvis. " + bytes([0xC3]) + b"ss"
    stdin = io.TextIOWrapper(io.BytesIO(raw_bytes), encoding="utf-8")

    with patch("sys.stdin", stdin):
        read_stdin_text()  # should not raise UnicodeDecodeError


def test_read_stdin_text_replaces_invalid_utf8_with_replacement_character():
    raw_bytes = b"I saw Elvis. " + bytes([0xC3]) + b"ss"
    stdin = io.TextIOWrapper(io.BytesIO(raw_bytes), encoding="utf-8")

    with patch("sys.stdin", stdin):
        result = read_stdin_text()

    assert result == "I saw Elvis. \ufffdss"


def test_read_stdin_text_when_stdin_does_not_support_reconfigure():
    # Some stdin replacements (e.g. pytest-xdist's captured stdin) don't
    # support reconfigure(); reading should still work in that case.
    stdin = Mock(spec=["read"])
    stdin.read.return_value = "I saw Elvis."

    with patch("sys.stdin", stdin):
        result = read_stdin_text()

    assert result == "I saw Elvis."


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("line one\r\nline two", "line one\nline two"),
        ("line one\rline two", "line one\nline two"),
        ("line one\nline two", "line one\nline two"),
        ("\r\n\r\n", "\n\n"),
        ("no newlines", "no newlines"),
    ],
)
def test_normalize_newlines(text, expected):
    assert normalize_newlines(text) == expected


def test_decode_bytes_strips_leading_bom():
    assert decode_bytes(UTF8_BOM + b"[2020-01-01 09:00] Title") == (
        "[2020-01-01 09:00] Title"
    )


def test_decode_bytes_strips_bom_and_normalizes_crlf():
    assert decode_bytes(UTF8_BOM + b"Title\r\nbody line\r\n") == ("Title\nbody line\n")


def test_decode_bytes_does_not_strip_bom_later_in_content():
    # Only the leading byte order mark is a marker; any other BOM bytes are
    # content and must be preserved as the ZWNBSP character.
    assert decode_bytes(b"a" + UTF8_BOM + b"b") == "a\ufeffb"


def test_decode_bytes_falls_back_to_preferred_encoding(monkeypatch):
    # "e-acute" in Windows-1252; not valid UTF-8
    raw = b"caf\xe9"
    monkeypatch.setattr("jrnl.os_compat.get_preferred_encoding", lambda: "cp1252")

    assert decode_bytes(raw) == "caf\u00e9"


def test_decode_bytes_raises_when_neither_encoding_works(monkeypatch):
    raw = b"\xff\xfe\x80\x81"
    monkeypatch.setattr("jrnl.os_compat.get_preferred_encoding", lambda: "utf-8")

    with pytest.raises(UnicodeDecodeError):
        decode_bytes(raw)


def _editor_config(**overrides):
    config = {"editor": "fake-editor", "template": ""}
    config.update(overrides)
    return config


def _run_editor(file_bytes, config=None, recovery_encrypt=None):
    """Invoke get_text_from_editor with a fake editor that leaves exactly
    file_bytes in the temp file."""
    config = config or _editor_config()

    def _fake_editor(command):
        with open(command[-1], "wb") as f:
            f.write(file_bytes)

    with patch("jrnl.editor.subprocess.call", side_effect=_fake_editor):
        return get_text_from_editor(config, recovery_encrypt=recovery_encrypt)


def test_get_text_from_editor_strips_bom_from_new_entry():
    raw = _run_editor(UTF8_BOM + "my clean title\n".encode("utf-8"))

    assert raw == "my clean title\n"
    assert "\ufeff" not in raw


def test_get_text_from_editor_normalizes_crlf():
    raw = _run_editor(b"my title\r\nsecond line\r\n")

    assert raw == "my title\nsecond line\n"
    assert "\r" not in raw


def test_get_text_from_editor_bom_only_is_empty():
    with pytest.raises(JrnlException) as exc:
        _run_editor(UTF8_BOM)

    assert exc.value.has_message_text(MsgText.NoTextReceived)


def test_get_text_from_editor_whitespace_only_is_returned_for_caller_to_judge():
    # Append mode distinguishes "empty" from "unchanged template"; the editor
    # must not pre-empt that decision for whitespace-only text.
    raw = _run_editor(b"  \r\n \n")

    assert raw == "  \n \n"


def test_get_text_from_editor_empty_file_raises_no_text():
    with pytest.raises(JrnlException) as exc:
        _run_editor(b"")

    assert exc.value.has_message_text(MsgText.NoTextReceived)


def test_get_text_from_editor_misconfigured_editor_raises():
    config = _editor_config()
    with (
        patch("jrnl.editor.subprocess.call", side_effect=FileNotFoundError),
        pytest.raises(JrnlException) as exc,
    ):
        get_text_from_editor(config)

    assert exc.value.has_message_text(MsgText.EditorMisconfigured)


def test_get_text_from_editor_undecodable_preserves_content_and_reports_path():
    undecodable = b"\xff\xfe\x80my text \x80\x81\n"

    with pytest.raises(JrnlException) as exc:
        _run_editor(undecodable, config=_editor_config())

    assert exc.value.has_message_text(MsgText.EditorContentNotDecodable)
    message = exc.value.messages[0]
    preserved_path = message.params["preserved_path"]
    try:
        assert preserved_path.endswith(".recovery")
        assert os.path.exists(preserved_path)
        with open(preserved_path, "rb") as f:
            assert f.read() == undecodable
    finally:
        os.remove(preserved_path)


def test_get_text_from_editor_undecodable_temp_file_is_not_left_behind():
    created_files = []
    undecodable = b"\xff\xfe\x80bad\n"

    real_mkstemp = __import__("tempfile").mkstemp

    def _tracking_mkstemp(*args, **kwargs):
        result = real_mkstemp(*args, **kwargs)
        created_files.append(result[1])
        return result

    with patch("tempfile.mkstemp", side_effect=_tracking_mkstemp):
        with pytest.raises(JrnlException):
            _run_editor(undecodable)

    tmpfile = created_files[0]
    assert not os.path.exists(tmpfile)
    assert os.path.exists(tmpfile + ".recovery")
    os.remove(tmpfile + ".recovery")


def test_get_text_from_editor_undecodable_encrypted_journal_keeps_ciphertext():
    undecodable = b"\xff\xfemy encrypted editor text \x80\n"
    config = _editor_config(encrypt=True)

    def _encryptor(raw_bytes):
        assert raw_bytes == undecodable
        return b"JRNLv3-encrypted-blob"

    with pytest.raises(JrnlException) as exc:
        _run_editor(undecodable, config=config, recovery_encrypt=_encryptor)

    assert exc.value.has_message_text(MsgText.EditorContentNotDecodable)
    assert exc.value.has_message_text(MsgText.EditorPreservedContentEncrypted)
    preserved_path = exc.value.messages[0].params["preserved_path"]
    try:
        assert preserved_path.endswith(".recovery.encrypted")
        with open(preserved_path, "rb") as f:
            preserved = f.read()
        assert preserved == b"JRNLv3-encrypted-blob"
        assert b"my encrypted editor text" not in preserved
    finally:
        os.remove(preserved_path)


def test_get_text_from_editor_encrypted_recovery_failure_removes_plaintext():
    undecodable = b"\xff\xfesecret plaintext\n"
    config = _editor_config(encrypt=True)

    failure = RuntimeError("no password available")

    def _failing_encryptor(raw_bytes):
        raise failure

    created_files = []
    real_mkstemp = __import__("tempfile").mkstemp

    def _tracking_mkstemp(*args, **kwargs):
        result = real_mkstemp(*args, **kwargs)
        created_files.append(result[1])
        return result

    with patch("tempfile.mkstemp", side_effect=_tracking_mkstemp):
        with (
            patch(
                "jrnl.editor.subprocess.call",
                side_effect=lambda cmd: open(cmd[-1], "wb").write(undecodable),
            ),
            pytest.raises(RuntimeError),
        ):
            get_text_from_editor(config, recovery_encrypt=_failing_encryptor)

    tmpfile = created_files[0]
    assert not os.path.exists(tmpfile)
    assert not os.path.exists(tmpfile + ".recovery")
    assert not os.path.exists(tmpfile + ".recovery.encrypted")
