# Copyright © 2012-2023 jrnl contributors
# License: https://www.gnu.org/licenses/gpl-3.0.html

import os
from types import SimpleNamespace

import pytest
from ruamel.yaml import YAML

from jrnl import __version__
from jrnl.config import compare_jrnl_versions
from jrnl.config import ensure_config_version_compatible
from jrnl.config import flush_pending_config_updates
from jrnl.config import get_default_config
from jrnl.config import load_config
from jrnl.config import parse_jrnl_version
from jrnl.config import save_config
from jrnl.config import update_config
from jrnl.exception import JrnlException
from jrnl.install import find_alt_config
from jrnl.install import load_or_install_jrnl
from jrnl.messages import MsgText
from jrnl.output import format_msg_text


def test_find_alt_config(request):
    work_config_path = os.path.join(
        request.fspath.dirname, "..", "data", "configs", "basic_onefile.yaml"
    )
    found_alt_config = find_alt_config(work_config_path)
    assert found_alt_config == work_config_path


def test_find_alt_config_not_exist(request):
    bad_config_path = os.path.join(
        request.fspath.dirname, "..", "data", "configs", "does-not-exist.yaml"
    )
    with pytest.raises(JrnlException) as ex:
        found_alt_config = find_alt_config(bad_config_path)
        assert found_alt_config is not None
    assert isinstance(ex.value, JrnlException)


# --- Version parsing ------------------------------------------------------- #


@pytest.mark.parametrize(
    "raw,parsed",
    [
        ("4.6", ((4, 6), None)),
        ("4.6.1", ((4, 6, 1), None)),
        ("4", ((4,), None)),
        ("v2.4.5", ((2, 4, 5), None)),
        ("4.6-beta", ((4, 6), 1)),
        ("4.6-beta2", ((4, 6), 2)),
        ("4.0.1-beta", ((4, 0, 1), 1)),
        ("V4.6-BETA10", ((4, 6), 10)),
        ("  4.6  ", ((4, 6), None)),
        (4.6, ((4, 6), None)),  # YAML hands bare 4.6 back as a float
        (4, ((4,), None)),
    ],
)
def test_parse_recognized_versions(raw, parsed):
    assert parse_jrnl_version(raw) == parsed


@pytest.mark.parametrize(
    "raw",
    [
        None,
        "",
        "   ",
        "garbage",
        "4.6-alpha",
        "4.6-rc1",
        "4.6.snapshot",
        "beta",
        "4..6",
        True,
        ["4.6"],
        {"version": "4.6"},
    ],
)
def test_parse_unrecognized_versions(raw):
    assert parse_jrnl_version(raw) is None


# --- Version ordering ------------------------------------------------------ #


def _compare(config_version, current_version=__version__):
    return compare_jrnl_versions(
        parse_jrnl_version(config_version),
        parse_jrnl_version(current_version),
    )


@pytest.mark.parametrize(
    "config_version,current_version,expected",
    [
        ("4.6", "4.6", 0),
        ("4.5", "4.6", -1),
        ("4.6.1", "4.6", 1),
        ("v2.4.5", "4.6", -1),
        # a beta of the same baseline sorts below the release
        ("4.6-beta", "4.6", -1),
        ("4.6", "4.6-beta", 1),
        ("4.6-beta", "4.6-beta", 0),
        # beta sequence numbers compare numerically, not lexicographically
        ("4.6-beta", "4.6-beta2", -1),
        ("4.6-beta2", "4.6-beta10", -1),
        ("4.6-beta9", "4.6-beta10", -1),
        ("4.6-beta10", "4.6-beta2", 1),
        ("4.6-beta3", "4.6-beta2", 1),
        ("4.0.1-beta", "4.0.1", -1),
        # a beta on a newer baseline is still newer
        ("4.7-beta", "4.6", 1),
        (4.6, "4.6", 0),  # YAML float vs string
    ],
)
def test_version_ordering(config_version, current_version, expected):
    assert _compare(config_version, current_version) == expected


# --- Version gate ---------------------------------------------------------- #


def test_gate_rejects_newer_version():
    with pytest.raises(JrnlException) as exc:
        ensure_config_version_compatible("99.9", "/path/to/config.yaml")
    message = exc.value.messages[0]
    assert message.text == MsgText.ConfigVersionNewer
    assert message.params["config_version"] == "99.9"
    assert message.params["current_version"] == __version__
    rendered = format_msg_text(message).plain
    assert "99.9" in rendered
    assert __version__ in rendered
    assert "newer" in rendered


def test_gate_rejects_unparseable_version():
    with pytest.raises(JrnlException) as exc:
        ensure_config_version_compatible("garbage", "/path/to/config.yaml")
    message = exc.value.messages[0]
    assert message.text == MsgText.ConfigVersionUnparseable
    assert message.params["config_version"] == "garbage"
    assert "could not be" in format_msg_text(message).plain


def test_newer_and_unparseable_errors_are_distinguishable():
    with pytest.raises(JrnlException) as newer_exc:
        ensure_config_version_compatible("99.9", "/path/to/config.yaml")
    with pytest.raises(JrnlException) as unparseable_exc:
        ensure_config_version_compatible("garbage", "/path/to/config.yaml")
    assert newer_exc.value.messages[0].text != unparseable_exc.value.messages[0].text


@pytest.mark.parametrize("raw", ["4.6", "4.5", "v2.4.5", "4.6-beta2", 4.6])
def test_gate_allows_same_and_older_versions(raw):
    ensure_config_version_compatible(raw, "/path/to/config.yaml")


# --- On-disk behavior ------------------------------------------------------ #


def _write_config_file(path, *, version=__version__, include_version=True, extra=None):
    config = get_default_config()
    config["journals"]["default"]["journal"] = str(path.parent / "journal.txt")
    if include_version:
        config["version"] = version
    else:
        del config["version"]
    if extra:
        config.update(extra)
    with open(path, "w", encoding="utf-8") as f:
        YAML(typ="safe").dump(config, f)
    return config


def _files_in(directory):
    return {p.name for p in directory.rglob("*") if p.is_file()}


def test_newer_version_refuses_startup_without_touching_the_file(tmp_path):
    config_path = tmp_path / "jrnl.yaml"
    _write_config_file(
        config_path, version="99.9", extra={"unknown_future_key": "kept"}
    )
    original_bytes = config_path.read_bytes()

    with pytest.raises(JrnlException) as exc:
        load_or_install_jrnl(str(config_path))
    assert exc.value.messages[0].text == MsgText.ConfigVersionNewer

    # byte-for-byte unchanged, and no backup or temporary file was created
    assert config_path.read_bytes() == original_bytes
    assert _files_in(tmp_path) == {"jrnl.yaml"}


def test_unparseable_version_refuses_startup_without_touching_the_file(tmp_path):
    config_path = tmp_path / "jrnl.yaml"
    _write_config_file(config_path, version="not-a-version")
    original_bytes = config_path.read_bytes()

    with pytest.raises(JrnlException) as exc:
        load_or_install_jrnl(str(config_path))
    assert exc.value.messages[0].text == MsgText.ConfigVersionUnparseable

    assert config_path.read_bytes() == original_bytes
    assert _files_in(tmp_path) == {"jrnl.yaml"}


def test_main_run_returns_nonzero_for_newer_version(tmp_path, capsys):
    from jrnl.main import run

    config_path = tmp_path / "jrnl.yaml"
    _write_config_file(config_path, version="99.9")
    original_bytes = config_path.read_bytes()

    status = run(["--config-file", str(config_path), "-1"])

    assert status == 1
    assert "newer version" in capsys.readouterr().err
    assert config_path.read_bytes() == original_bytes
    assert _files_in(tmp_path) == {"jrnl.yaml"}


def test_same_version_runs_and_preserves_unknown_keys_and_bytes(tmp_path):
    config_path = tmp_path / "jrnl.yaml"
    _write_config_file(config_path, extra={"unknown_future_key": "kept"})
    original_bytes = config_path.read_bytes()

    config = load_or_install_jrnl(str(config_path))

    assert config["unknown_future_key"] == "kept"
    # nothing to fill in and the version already matches: no writeback at all
    assert config_path.read_bytes() == original_bytes


def test_older_version_runs_and_fills_in_as_before(tmp_path):
    config_path = tmp_path / "jrnl.yaml"
    _write_config_file(config_path, version="4.5", extra={"legacy_unknown_key": "kept"})

    config = load_or_install_jrnl(str(config_path))

    assert config["version"] == __version__
    reloaded = load_config(str(config_path))
    assert reloaded["version"] == __version__
    assert reloaded["legacy_unknown_key"] == "kept"


def test_missing_version_keeps_existing_fill_in_behavior(tmp_path):
    config_path = tmp_path / "jrnl.yaml"
    _write_config_file(config_path, include_version=False)

    config = load_or_install_jrnl(str(config_path))

    assert config["version"] == __version__
    reloaded = load_config(str(config_path))
    for key in get_default_config():
        assert key in reloaded


def test_same_baseline_beta_is_treated_as_older(tmp_path):
    config_path = tmp_path / "jrnl.yaml"
    _write_config_file(config_path, version="4.6-beta2")

    config = load_or_install_jrnl(str(config_path))

    assert config["version"] == __version__
    assert load_config(str(config_path))["version"] == __version__


def test_newer_baseline_beta_is_refused(tmp_path):
    config_path = tmp_path / "jrnl.yaml"
    _write_config_file(config_path, version="4.7-beta")
    original_bytes = config_path.read_bytes()

    with pytest.raises(JrnlException) as exc:
        load_or_install_jrnl(str(config_path))
    assert exc.value.messages[0].text == MsgText.ConfigVersionNewer
    assert config_path.read_bytes() == original_bytes


# --- All write-back entries share the same rule --------------------------- #


def test_save_config_refuses_newer_version_without_writing(tmp_path):
    config_path = tmp_path / "jrnl.yaml"
    config = get_default_config()
    config["version"] = "99.9"

    with pytest.raises(JrnlException) as exc:
        save_config(config, str(config_path))

    assert exc.value.messages[0].text == MsgText.ConfigVersionNewer
    assert not config_path.exists()
    assert config["version"] == "99.9"  # the dict is not rewritten either


def test_save_config_refuses_unparseable_version_without_writing(tmp_path):
    config_path = tmp_path / "jrnl.yaml"
    config = get_default_config()
    config["version"] = "garbage"

    with pytest.raises(JrnlException):
        save_config(config, str(config_path))

    assert not config_path.exists()


def test_encrypt_decrypt_style_writeback_is_guarded(tmp_path):
    # Mirrors the update_config()/save_config() sequence used by the
    # in-place --encrypt/--decrypt write-back in jrnl.commands.
    config_path = tmp_path / "jrnl.yaml"
    config = get_default_config()
    config["version"] = "99.9"
    update_config(config, {"encrypt": True}, "default", force_local=True)

    with pytest.raises(JrnlException):
        save_config(config, str(config_path))

    assert not config_path.exists()


def test_pending_config_updates_are_guarded_without_partial_update(tmp_path):
    config_path = tmp_path / "jrnl.yaml"
    _write_config_file(config_path, version="99.9")
    original_bytes = config_path.read_bytes()
    original_config = load_config(str(config_path))
    journal = SimpleNamespace(_pending_config_updates={"encrypt": True})

    with pytest.raises(JrnlException):
        flush_pending_config_updates(
            journal, original_config, "default", str(config_path)
        )

    assert config_path.read_bytes() == original_bytes
    # pending work is neither applied nor cleared on the refusal path
    assert journal._pending_config_updates == {"encrypt": True}
    assert original_config["encrypt"] is False


def test_empty_pending_updates_do_not_trigger_the_gate(tmp_path):
    config_path = tmp_path / "jrnl.yaml"
    _write_config_file(config_path, version="99.9")
    original_config = load_config(str(config_path))
    journal = SimpleNamespace(_pending_config_updates={})

    # nothing pending means nothing is written, so no refusal either
    flush_pending_config_updates(journal, original_config, "default", str(config_path))
