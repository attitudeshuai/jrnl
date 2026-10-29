# Copyright © 2012-2023 jrnl contributors
# License: https://www.gnu.org/licenses/gpl-3.0.html

import codecs
import locale
import shlex
from sys import platform

UTF8_BOM = codecs.BOM_UTF8


def on_windows() -> bool:
    return "win32" in platform


def on_posix() -> bool:
    return not on_windows()


def split_args(args: str) -> list[str]:
    """Split arguments and add escape characters as appropriate for the OS"""
    return shlex.split(args, posix=on_posix())


def get_preferred_encoding() -> str:
    """The machine's preferred text encoding (the locale encoding), used as a
    fallback when bytes aren't valid UTF-8."""
    return locale.getpreferredencoding(False)


def normalize_newlines(text: str) -> str:
    """Normalize Windows (CRLF) and classic Mac (CR) line endings to a single
    line feed (LF), so entries never carry carriage returns in memory, in
    exports, or when written back to disk."""
    return text.replace("\r\n", "\n").replace("\r", "\n")


def decode_bytes(raw: bytes) -> str:
    """Decode bytes coming from an external editor or a journal file.

    A leading UTF-8 byte order mark is stripped before decoding, so it never
    lands in an entry's title, body, or date header. The bytes are first
    decoded as strict UTF-8; if that fails, the machine's preferred (locale)
    encoding is tried. Line endings are normalized to LF.

    Raises UnicodeDecodeError when neither encoding can decode the bytes.
    """
    if raw.startswith(UTF8_BOM):
        raw = raw[len(UTF8_BOM) :]

    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as utf8_error:
        try:
            text = raw.decode(get_preferred_encoding())
        except (UnicodeDecodeError, LookupError):
            raise utf8_error from None

    return normalize_newlines(text)
