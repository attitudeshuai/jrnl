# Copyright © 2012-2023 jrnl contributors
# License: https://www.gnu.org/licenses/gpl-3.0.html

import contextlib
import logging
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Callable

from jrnl.exception import JrnlException
from jrnl.messages import Message
from jrnl.messages import MsgStyle
from jrnl.messages import MsgText
from jrnl.os_compat import decode_bytes
from jrnl.os_compat import get_preferred_encoding
from jrnl.os_compat import on_windows
from jrnl.os_compat import split_args
from jrnl.output import print_msg
from jrnl.path import absolute_path
from jrnl.path import get_templates_path

RECOVERY_SUFFIX = ".recovery"
ENCRYPTED_RECOVERY_SUFFIX = ".recovery.encrypted"


def get_text_from_editor(
    config: dict,
    template: str = "",
    *,
    recovery_encrypt: Callable[[bytes], bytes] | None = None,
) -> str:
    suffix = ".jrnl"
    if config["template"]:
        template_filename = Path(config["template"]).name
        suffix = "-" + template_filename
    filehandle, tmpfile = tempfile.mkstemp(prefix="jrnl", text=True, suffix=suffix)
    os.close(filehandle)
    logging.debug(f"Editor: created tempfile {tmpfile}")

    try:
        with open(tmpfile, "wb") as f:
            if template:
                f.write(template.encode("utf-8"))

        try:
            logging.debug(f"Editor: invoking editor with command {config['editor']}")
            subprocess.call(split_args(config["editor"]) + [tmpfile])
        except FileNotFoundError:
            logging.error(f"Editor: misconfigured editor {config['editor']}")
            raise JrnlException(
                Message(
                    MsgText.EditorMisconfigured,
                    MsgStyle.ERROR,
                    {"editor_key": config["editor"]},
                )
            )

        with open(tmpfile, "rb") as f:
            raw_bytes = f.read()
    except BaseException:
        # The editor output is preserved separately when it cannot be decoded;
        # every other failure just cleans the temp file up.
        with contextlib.suppress(OSError):
            os.remove(tmpfile)
        raise

    try:
        raw = decode_bytes(raw_bytes)
    except UnicodeDecodeError:
        preserved_path, encrypted = _preserve_editor_output(
            tmpfile, raw_bytes, config, recovery_encrypt
        )
        messages = [
            Message(
                MsgText.EditorContentNotDecodable,
                MsgStyle.ERROR,
                {
                    "encoding": get_preferred_encoding(),
                    "preserved_path": preserved_path,
                },
            )
        ]
        if encrypted:
            messages.append(
                Message(MsgText.EditorPreservedContentEncrypted, MsgStyle.NORMAL)
            )
        raise JrnlException(*messages)

    os.remove(tmpfile)
    logging.debug(f"Editor: removed tempfile {tmpfile}")

    # A byte order mark on its own decodes to an empty file; whitespace-only
    # content is left for the caller to judge against an unchanged template.
    if not raw:
        raise JrnlException(Message(MsgText.NoTextReceived, MsgStyle.NORMAL))

    return raw


def _preserve_editor_output(
    tmpfile: str,
    raw_bytes: bytes,
    config: dict,
    recovery_encrypt: Callable[[bytes], bytes] | None,
) -> tuple[str, bool]:
    """Keeps the bytes the editor wrote so they can be recovered.

    Returns (preserved_path, encrypted). Encrypted journals never leave
    plain text behind: when ``recovery_encrypt`` is supplied, the preserved
    bytes are encrypted with the journal's password instead.
    """
    if config.get("encrypt") and recovery_encrypt is not None:
        preserved_path = tmpfile + ENCRYPTED_RECOVERY_SUFFIX
        try:
            protected_bytes = recovery_encrypt(raw_bytes)
            with open(preserved_path, "wb") as f:
                f.write(protected_bytes)
            with contextlib.suppress(OSError):
                os.chmod(preserved_path, 0o600)
        except BaseException:
            # Never leave plaintext editor content behind for an encrypted
            # journal; if protecting it fails, remove everything and surface
            # the original error.
            with contextlib.suppress(OSError):
                os.remove(tmpfile)
            with contextlib.suppress(OSError):
                os.remove(preserved_path)
            raise
        os.remove(tmpfile)
        logging.debug(f"Editor: kept encrypted editor output at {preserved_path}")
        return preserved_path, True

    preserved_path = tmpfile + RECOVERY_SUFFIX
    os.replace(tmpfile, preserved_path)
    logging.debug(f"Editor: kept editor output at {preserved_path}")
    return preserved_path, False


def read_stdin_text() -> str:
    # It's possible to get invalid UTF-8 here, so we replace on error to
    # avoid crashing and losing the whole journal entry.
    try:
        sys.stdin.reconfigure(errors="replace")
    except AttributeError:
        pass
    return sys.stdin.read()


def get_text_from_stdin() -> str:
    print_msg(
        Message(
            MsgText.WritingEntryStart,
            MsgStyle.TITLE,
            {
                "how_to_quit": (
                    MsgText.HowToQuitWindows if on_windows() else MsgText.HowToQuitLinux
                )
            },
        )
    )

    try:
        raw = read_stdin_text()
    except KeyboardInterrupt:
        logging.error("Append mode: keyboard interrupt")
        raise JrnlException(
            Message(MsgText.KeyboardInterruptMsg, MsgStyle.ERROR_ON_NEW_LINE),
            Message(MsgText.JournalNotSaved, MsgStyle.WARNING),
        )

    return raw


def get_template_path(template_path: str, jrnl_template_dir: str) -> str:
    actual_template_path = os.path.join(jrnl_template_dir, template_path)
    if not os.path.exists(actual_template_path):
        logging.debug(
            f"Couldn't open {actual_template_path}. "
            "Treating template path like a local / abs path."
        )
        actual_template_path = absolute_path(template_path)

    return actual_template_path


def read_template_file(template_path: str) -> str:
    """
    Reads the template file given a template path in this order:

        * Check $XDG_DATA_HOME/jrnl/templates/template_path.
        * Check template_arg as an absolute / relative path.

    If a file is found, its contents are returned as a string.
    If not, a JrnlException is raised.
    """

    jrnl_template_dir = get_templates_path()
    actual_template_path = get_template_path(template_path, jrnl_template_dir)

    try:
        with open(actual_template_path, encoding="utf-8") as f:
            template_data = f.read()
            return template_data
    except FileNotFoundError:
        logging.debug(f"Couldn't read template file {actual_template_path}")
        raise JrnlException(
            Message(
                MsgText.CantReadTemplate,
                MsgStyle.ERROR,
                {
                    "template_path": template_path,
                    "actual_template_path": actual_template_path,
                    "jrnl_template_dir": str(jrnl_template_dir) + os.sep,
                },
            )
        )
