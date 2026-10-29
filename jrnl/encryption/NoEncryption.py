# Copyright © 2012-2023 jrnl contributors
# License: https://www.gnu.org/licenses/gpl-3.0.html

import logging

from jrnl.encryption.BaseEncryption import BaseEncryption
from jrnl.exception import JrnlException
from jrnl.messages import Message
from jrnl.messages import MsgStyle
from jrnl.messages import MsgText
from jrnl.os_compat import decode_bytes
from jrnl.os_compat import get_preferred_encoding


class NoEncryption(BaseEncryption):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        logging.debug("start")

    @property
    def version(self) -> str | None:
        return None

    def _encrypt(self, text: str) -> bytes:
        logging.debug("encrypting")
        return text.encode(self._encoding)

    def _decrypt(self, text: bytes) -> str:
        logging.debug("decrypting")
        try:
            return decode_bytes(text)
        except UnicodeDecodeError:
            raise JrnlException(
                Message(
                    MsgText.JournalFileNotDecodable,
                    MsgStyle.ERROR,
                    {
                        "filename": self._journal_name,
                        "encoding": get_preferred_encoding(),
                    },
                )
            )
