# Copyright © 2012-2023 jrnl contributors
# License: https://www.gnu.org/licenses/gpl-3.0.html

import argparse
import logging
import os
import re
from typing import TYPE_CHECKING
from typing import Any
from typing import Callable

from rich.pretty import pretty_repr
from ruamel.yaml import YAML
from ruamel.yaml import constructor

from jrnl import __version__
from jrnl.color import is_valid_color
from jrnl.exception import JrnlException
from jrnl.messages import Message
from jrnl.messages import MsgStyle
from jrnl.messages import MsgText
from jrnl.output import list_journals
from jrnl.output import print_msg
from jrnl.path import get_config_path
from jrnl.path import get_default_journal_path

if TYPE_CHECKING:
    from jrnl.journals import Journal

# Constants
DEFAULT_JOURNAL_KEY = "default"

YAML_SEPARATOR = ": "
YAML_FILE_ENCODING = "utf-8"

# Version handling. jrnl releases look like "4.6" or "4.6.1", and pre-release
# builds look like "4.6-beta2"; the first beta in a series is published as
# "<baseline>-beta". A leading "v" is accepted for historical config files
# (e.g. "v2.4.5"). Release numbers compare numerically and beta numbers compare
# numerically (beta2 < beta10), never as strings.
ParsedVersion = tuple[tuple[int, ...], int | None]

_VERSION_RE = re.compile(
    r"^v?(?P<release>\d+(?:\.\d+)*)(?:-beta(?P<beta>\d*))?$",
    re.IGNORECASE,
)


def parse_jrnl_version(value: Any) -> "ParsedVersion | None":
    """Parse a jrnl version into ``(release_numbers, beta_number)``.

    ``beta_number`` is ``None`` for a release, otherwise the beta sequence
    number (a bare ``-beta`` tag is the first beta). Returns ``None`` when the
    value cannot be recognized, so callers can apply the conservative policy
    of refusing to touch the config.
    """
    if isinstance(value, bool) or value is None:
        return None

    # YAML can hand a bare version such as 4.6 back as a number.
    if isinstance(value, (int, float)):
        text = str(value)
    elif isinstance(value, str):
        text = value.strip()
    else:
        return None

    match = _VERSION_RE.match(text)
    if not match:
        return None

    release = tuple(int(part) for part in match.group("release").split("."))
    beta_number_text = match.group("beta")
    if beta_number_text is None:
        # No "-beta" tag at all: this is a release.
        beta_number = None
    else:
        # The first beta in a series ships with a bare "-beta" tag.
        beta_number = int(beta_number_text) if beta_number_text else 1
    return release, beta_number


def compare_jrnl_versions(
    config_version: "ParsedVersion", current_version: "ParsedVersion"
) -> int:
    """Compare parsed versions, returning -1, 0, or 1.

    On the same release baseline, any beta sorts below the release. Beta
    sequence numbers are compared numerically rather than lexicographically.
    """
    config_release, config_beta = config_version
    current_release, current_beta = current_version

    if config_release < current_release:
        return -1
    if config_release > current_release:
        return 1

    if config_beta == current_beta:
        return 0
    if config_beta is None:
        return 1
    if current_beta is None:
        return -1

    return (config_beta > current_beta) - (config_beta < current_beta)


def ensure_config_version_compatible(config_version: Any, config_path: str) -> None:
    """Refuse to touch a config whose version is unparseable or newer than
    this jrnl installation.

    Raises ``JrnlException`` before any file is opened for writing. A config
    without a version field is not checked here; callers keep routing those
    through the existing missing-key fill-in flow.
    """
    parsed_config_version = parse_jrnl_version(config_version)
    if parsed_config_version is None:
        raise JrnlException(
            Message(
                MsgText.ConfigVersionUnparseable,
                MsgStyle.ERROR,
                {
                    "config_path": config_path,
                    "config_version": config_version,
                    "current_version": __version__,
                },
            )
        )

    parsed_current_version = parse_jrnl_version(__version__)
    # The running program's own version always has to be parseable.
    assert parsed_current_version is not None

    if compare_jrnl_versions(parsed_config_version, parsed_current_version) > 0:
        raise JrnlException(
            Message(
                MsgText.ConfigVersionNewer,
                MsgStyle.ERROR,
                {
                    "config_path": config_path,
                    "config_version": config_version,
                    "current_version": __version__,
                },
            )
        )


def make_yaml_valid_dict(input: list) -> dict:
    """

    Convert a two-element list of configuration key-value pair into a flat dict.

    The dict is created through the yaml loader, with the assumption that
    "input[0]: input[1]" is valid yaml.

    :param input: list of configuration keys in dot-notation and their respective values
    :type input: list
    :return: A single level dict of the configuration keys in dot-notation and their
        respective desired values
    :rtype: dict
    """

    assert len(input) == 2

    # yaml compatible strings are of the form Key:Value
    yamlstr = YAML_SEPARATOR.join(input)

    runtime_modifications = YAML(typ="safe").load(yamlstr)

    return runtime_modifications


def save_config(config: dict, alt_config_path: str | None = None) -> None:
    """Supply alt_config_path if using an alternate config through --config-file."""
    config_path = alt_config_path if alt_config_path else get_config_path()

    # Every config write-back goes through here: a config stamped with a
    # newer or unparseable version must never be rewritten, no matter which
    # entry point (fill-in, in-place encrypt/decrypt, pending updates) asked
    # for the write.
    if "version" in config:
        ensure_config_version_compatible(config["version"], config_path)

    config["version"] = __version__

    yaml = YAML(typ="safe")
    yaml.default_flow_style = False  # prevents collapsing of tree structure

    with open(
        config_path,
        "w",
        encoding=YAML_FILE_ENCODING,
    ) as f:
        yaml.dump(config, f)


def get_default_config() -> dict[str, Any]:
    return {
        "version": __version__,
        "journals": {"default": {"journal": get_default_journal_path()}},
        "editor": os.getenv("VISUAL") or os.getenv("EDITOR") or "",
        "encrypt": False,
        "template": False,
        "default_hour": 9,
        "default_minute": 0,
        "timeformat": "%F %r",
        "tagsymbols": "#@",
        "highlight": True,
        "linewrap": 79,
        "indent_character": "|",
        "colors": {
            "body": "none",
            "date": "none",
            "tags": "none",
            "title": "none",
        },
    }


def get_default_colors() -> dict[str, Any]:
    return {
        "body": "none",
        "date": "black",
        "tags": "yellow",
        "title": "cyan",
    }


def scope_config(config: dict, journal_name: str) -> dict:
    if journal_name not in config["journals"]:
        return config
    config = config.copy()
    journal_conf = config["journals"].get(journal_name)
    if isinstance(journal_conf, dict):
        # We can override the default config on a by-journal basis
        logging.debug(
            "Updating configuration with specific journal overrides:\n%s",
            pretty_repr(journal_conf),
        )
        config.update(journal_conf)
    else:
        # But also just give them a string to point to the journal file
        config["journal"] = journal_conf

    logging.debug("Scoped config:\n%s", pretty_repr(config))
    return config


def verify_config_colors(config: dict) -> bool:
    """
    Ensures the keys set for colors are valid colorama.Fore attributes, or "None"
    :return: True if all keys are set correctly, False otherwise
    """
    all_valid_colors = True
    for key, color in config["colors"].items():
        if isinstance(color, str) and color.upper() == "NONE":
            continue
        if not is_valid_color(color):
            print_msg(
                Message(
                    MsgText.InvalidColor,
                    MsgStyle.NORMAL,
                    {
                        "key": key,
                        "color": color,
                    },
                )
            )
            all_valid_colors = False
    return all_valid_colors


def load_config(config_path: str) -> dict:
    """Tries to load a config file from YAML."""
    try:
        with open(config_path, encoding=YAML_FILE_ENCODING) as f:
            yaml = YAML(typ="safe")
            yaml.allow_duplicate_keys = False
            return yaml.load(f)
    except constructor.DuplicateKeyError as e:
        print_msg(
            Message(
                MsgText.ConfigDoubleKeys,
                MsgStyle.WARNING,
                {
                    "error_message": e,
                },
            )
        )
        with open(config_path, encoding=YAML_FILE_ENCODING) as f:
            yaml = YAML(typ="safe")
            yaml.allow_duplicate_keys = True
            return yaml.load(f)


def is_config_json(config_path: str) -> bool:
    with open(config_path, "r", encoding="utf-8") as f:
        config_file = f.read()
    return config_file.strip().startswith("{")


def update_config(
    config: dict, new_config: dict, scope: str | None, force_local: bool = False
) -> None:
    """Updates a config dict with new values - either global if scope is None
    or config['journals'][scope] is just a string pointing to a journal file,
    or within the scope"""
    if scope and isinstance(config["journals"][scope], dict):
        config["journals"][scope].update(new_config)
    elif scope and force_local:  # Convert to dict
        config["journals"][scope] = {"journal": config["journals"][scope]}
        config["journals"][scope].update(new_config)
    else:
        config.update(new_config)


def apply_config_updates_in_place(
    config: dict, updates: dict, journal_name: str
) -> None:
    """Apply config updates at whichever level each key originally lived.

    For each key in updates: if the journal has a journal-level override for
    that key, update it there; otherwise update the top-level key. This
    preserves the original config scope rather than silently moving settings.
    """
    journal_conf = config.get("journals", {}).get(journal_name)
    for key, value in updates.items():
        if isinstance(journal_conf, dict) and key in journal_conf:
            journal_conf[key] = value
        else:
            config[key] = value


def flush_pending_config_updates(
    journal: "Journal",
    original_config: dict,
    journal_name: str,
    alt_config_path: str | None = None,
) -> None:
    """Persist any config changes accumulated on the journal (e.g. a legacy
    encryption upgrade triggered by a write) back to the on-disk config.
    Supply alt_config_path if using an alternate config through --config-file."""
    if not journal._pending_config_updates:
        return

    # Refuse before accumulating anything onto a config we are not allowed
    # to rewrite, so no partial update can reach the disk write below.
    if "version" in original_config:
        ensure_config_version_compatible(
            original_config["version"],
            alt_config_path if alt_config_path else get_config_path(),
        )

    apply_config_updates_in_place(
        original_config, journal._pending_config_updates, journal_name
    )
    journal._pending_config_updates.clear()
    save_config(original_config, alt_config_path)


def get_journal_name(args: argparse.Namespace, config: dict) -> argparse.Namespace:
    args.journal_name = DEFAULT_JOURNAL_KEY

    # The first arg might be a journal name
    if args.text:
        potential_journal_name = args.text[0]
        if potential_journal_name[-1] == ":":
            potential_journal_name = potential_journal_name[0:-1]

        if potential_journal_name in config["journals"]:
            args.journal_name = potential_journal_name
            args.text = args.text[1:]

    logging.debug("Using journal name: %s", args.journal_name)
    return args


def cmd_requires_valid_journal_name(func: Callable) -> Callable:
    def wrapper(args: argparse.Namespace, config: dict, original_config: dict):
        validate_journal_name(args.journal_name, config)
        func(args=args, config=config, original_config=original_config)

    return wrapper


def validate_journal_name(journal_name: str, config: dict) -> None:
    if journal_name not in config["journals"]:
        raise JrnlException(
            Message(
                MsgText.NoNamedJournal,
                MsgStyle.ERROR,
                {
                    "journal_name": journal_name,
                    "journals": list_journals(config),
                },
            ),
        )
