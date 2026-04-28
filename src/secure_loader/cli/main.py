"""CLI entry point.

The CLI mirrors the GUI's feature set in a headless form::

    sld list-ports
    sld info --file firmware.bin
    sld info --port /dev/ttyUSB0
    sld fetch --license 42 --unique C0FE --output firmware.bin
    sld flash --port /dev/ttyUSB0 --file firmware.bin
    sld config set http.login <value>

All output is intentionally plain (no colour by default, no progress bars
by default) to make it easy to embed in scripts. Pass ``--verbose`` to
enable INFO/DEBUG logging and ``--progress`` to render tqdm-style bars.
"""

from __future__ import annotations

import logging
import sys
import threading
from pathlib import Path

import click
from serial.tools import list_ports

from .. import __app_name__, __version__
from ..config import AppConfig, config_path, load_config, save_config
from ..core.firmware import FirmwareHeader, load_firmware, parse_header
from ..core.protocol import (
    DeviceInfo,
    Parity,
    Protocol,
    ProtocolCallbacks,
    ProtocolError,
    State,
)
from ..core.sources import FirmwareIdentifier, FirmwareSourceError
from ..core.sources.http import HttpFirmwareSource
from ..core.updater import check_device_matches_firmware
from ..i18n import _, available_languages, set_language

log = logging.getLogger(__name__)


def _setup_logging(verbose: int) -> None:
    level = logging.WARNING
    if verbose == 1:
        level = logging.INFO
    elif verbose >= 2:
        level = logging.DEBUG
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    )


def _format_header(header: FirmwareHeader) -> str:
    return (
        f"  protocolVersion  = {header.format_protocol_version()}\n"
        f"  productId        = {header.format_product_id()}\n"
        f"  appVersion       = {header.format_app_version()}\n"
        f"  prevAppVersion   = {header.format_prev_app_version()}\n"
        f"  pageCount        = {header.page_count}\n"
        f"  flashPageSize    = {header.flash_page_size} B\n"
        f"  payloadSize      = {header.payload_size} B\n"
        f"  licenseID        = {header.license_id}\n"
        f"  uniqueID         = {header.unique_id}"
    )


def _format_device(device: DeviceInfo) -> str:
    return (
        f"  bootloaderVersion = {device.format_bootloader_version()}\n"
        f"  productId         = {device.format_product_id()}\n"
        f"  flashPageSize     = {device.flash_page_size} B"
    )


@click.group(
    context_settings={"help_option_names": ["-h", "--help"]},
    help=f"{__app_name__} — CLI",
)
@click.version_option(__version__, prog_name=__app_name__)
@click.option(
    "-v", "--verbose", count=True, help="Increase logging verbosity (-v INFO, -vv DEBUG)."
)
@click.option(
    "--language",
    type=click.Choice(["auto", *available_languages()]),
    default=None,
    help="Override UI language.",
)
@click.pass_context
def cli(ctx: click.Context, verbose: int, language: str | None) -> None:
    _setup_logging(verbose)
    config = load_config()
    if language is not None:
        set_language(language)
    elif config.language != "auto":
        set_language(config.language)
    ctx.ensure_object(dict)
    ctx.obj["config"] = config


# ----------------------------------------------------------------- list-ports


@cli.command("list-ports", help="List available serial ports.")
@click.pass_context
def list_ports_cmd(ctx: click.Context) -> None:
    ports = sorted(list_ports.comports(), key=lambda p: p.device)
    if not ports:
        click.echo(_("No serial ports found."))
        return
    for p in ports:
        desc = p.description or ""
        manuf = p.manufacturer or ""
        click.echo(f"{p.device}\t{desc}\t{manuf}")


# ----------------------------------------------------------------------- info


@cli.command("info", help="Show information about a firmware file or connected device.")
@click.option("--file", "file_path", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("--port", help="Serial port; when set, queries the device.")
@click.option("--baudrate", type=int, default=115200, show_default=True)
@click.option(
    "--stopbits",
    type=click.Choice(["1", "1.5", "2"]),
    default="1",
    show_default=True,
)
@click.option(
    "--parity",
    type=click.Choice(["none", "odd", "even"], case_sensitive=False),
    default="none",
    show_default=True,
)
@click.option("--timeout", type=float, default=15.0, show_default=True)
@click.pass_context
def info_cmd(
    ctx: click.Context,
    file_path: Path | None,
    port: str | None,
    baudrate: int,
    stopbits: str,
    parity: str,
    timeout: float,
) -> None:
    if not file_path and not port:
        raise click.UsageError("Provide --file and/or --port.")

    fw_header: FirmwareHeader | None = None
    if file_path:
        fw_header, _data = load_firmware(file_path)
        click.echo(_("Firmware header:"))
        click.echo(_format_header(fw_header))

    if port:
        device = _query_device(port, Parity.from_label(parity), timeout, baudrate, float(stopbits))
        click.echo(_("Connected to device:"))
        click.echo(_format_device(device))

        if fw_header is not None:
            reason = check_device_matches_firmware(device, fw_header)
            if reason:
                click.echo(f"  compatibility: MISMATCH — {reason.describe()}")
            else:
                click.echo("  compatibility: OK")


def _query_device(
    port: str,
    parity: Parity,
    timeout: float,
    baudrate: int = 115200,
    stopbits: float = 1.0,
) -> DeviceInfo:
    result: dict[str, DeviceInfo] = {}
    connected = threading.Event()

    def on_device(dev: DeviceInfo) -> None:
        result["dev"] = dev
        connected.set()

    callbacks = ProtocolCallbacks(on_device_info=on_device)
    proto = Protocol(
        port=port, parity=parity, baudrate=baudrate, stopbits=stopbits, callbacks=callbacks
    )
    proto.connect()
    driver = threading.Thread(target=proto.run, daemon=True)
    driver.start()
    try:
        if not connected.wait(timeout=timeout):
            raise ProtocolError("timed out waiting for device response")
        return result["dev"]
    finally:
        proto.stop()
        proto.disconnect()
        driver.join(timeout=2.0)


# ---------------------------------------------------------------------- fetch


@cli.command("fetch", help="Download a firmware image from the HTTP source.")
@click.option("--license", "license_id", required=True, help="License ID.")
@click.option("--unique", "unique_id", required=True, help="Unique device ID.")
@click.option(
    "--previous",
    "prev_version",
    default=None,
    help="Fetch the previous version identified by this appVersion.",
)
@click.option(
    "--output",
    "out_path",
    type=click.Path(dir_okay=False, path_type=Path),
    required=True,
)
@click.option("--base-url", default=None, help="Override configured base URL.")
@click.pass_context
def fetch_cmd(
    ctx: click.Context,
    license_id: str,
    unique_id: str,
    prev_version: str | None,
    out_path: Path,
    base_url: str | None,
) -> None:
    config: AppConfig = ctx.obj["config"]
    source = HttpFirmwareSource(
        base_url=base_url or config.http_base_url,
        credentials=config.credentials(),
    )
    identifier = FirmwareIdentifier(
        license_id=license_id,
        unique_id=unique_id,
        app_version=prev_version,
    )

    def progress(received: int, total: int) -> None:
        if total:
            click.echo(f"\r{received}/{total} B", nl=False)

    try:
        data = (
            source.fetch_previous(identifier, progress)
            if prev_version
            else source.fetch_latest(identifier, progress)
        )
    except FirmwareSourceError as e:
        raise click.ClickException(str(e)) from e
    click.echo()  # newline after progress
    out_path.write_bytes(data)

    try:
        header = parse_header(data)
        click.echo(_("Firmware header:"))
        click.echo(_format_header(header))
    except Exception:
        log.exception("downloaded data does not parse as a firmware header")


# ---------------------------------------------------------------------- flash


@cli.command("flash", help="Flash a firmware file to a connected device.")
@click.option(
    "--file",
    "file_path",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    required=True,
)
@click.option("--port", required=True)
@click.option("--baudrate", type=int, default=115200, show_default=True)
@click.option(
    "--stopbits",
    type=click.Choice(["1", "1.5", "2"]),
    default="1",
    show_default=True,
)
@click.option(
    "--parity",
    type=click.Choice(["none", "odd", "even"], case_sensitive=False),
    default="none",
    show_default=True,
)
@click.option("--timeout", type=float, default=300.0, show_default=True)
@click.option(
    "--force",
    is_flag=True,
    help="Skip product ID / protocol version compatibility checks.",
)
@click.pass_context
def flash_cmd(
    ctx: click.Context,
    file_path: Path,
    port: str,
    baudrate: int,
    stopbits: str,
    parity: str,
    timeout: float,
    force: bool,
) -> None:
    header, firmware = load_firmware(file_path)
    click.echo(_("Firmware header:"))
    click.echo(_format_header(header))

    device_info: dict[str, DeviceInfo] = {}
    connected = threading.Event()
    error_box: dict[str, str] = {}
    last_state: dict[str, State] = {}

    def on_device(dev: DeviceInfo) -> None:
        device_info["dev"] = dev
        connected.set()

    def on_error(msg: str) -> None:
        error_box["msg"] = msg
        connected.set()

    def on_state(state: State) -> None:
        last_state["state"] = state
        log.info("state: %s", state.name)

    def on_page(sent: int, total: int) -> None:
        if total:
            click.echo(f"\r{_('Update progress')}: {sent}/{total}", nl=False)

    callbacks = ProtocolCallbacks(
        on_device_info=on_device,
        on_error=on_error,
        on_state_changed=on_state,
        on_page_sent=on_page,
    )
    proto = Protocol(
        port=port,
        parity=Parity.from_label(parity),
        baudrate=baudrate,
        stopbits=float(stopbits),
        callbacks=callbacks,
    )
    proto.connect()
    driver = threading.Thread(target=proto.run, daemon=True)
    driver.start()

    try:
        if not connected.wait(timeout=min(timeout, 30.0)):
            raise click.ClickException("timed out waiting for device handshake")
        if "msg" in error_box:
            raise click.ClickException(error_box["msg"])

        device = device_info["dev"]
        click.echo(_("Connected to device:"))
        click.echo(_format_device(device))

        reason = check_device_matches_firmware(device, header)
        if reason and not force:
            raise click.ClickException(
                _(
                    "Device does not match firmware ({reason}).",
                    reason=reason.describe(),
                )
            )

        click.echo(_("Starting transfer..."))
        proto.start_download(firmware)
        proto.wait_for_download(timeout=timeout)
        click.echo()  # newline after progress
        click.echo(_("Update finished."))
    finally:
        proto.stop()
        proto.disconnect()
        driver.join(timeout=2.0)


# --------------------------------------------------------------------- config


@cli.group("config", help="Read and modify stored configuration.")
def config_group() -> None:
    pass


@config_group.command("path", help="Print the path of the configuration file.")
def config_path_cmd() -> None:
    click.echo(str(config_path()))


@config_group.command("show", help="Show the current configuration.")
@click.pass_context
def config_show_cmd(ctx: click.Context) -> None:
    cfg: AppConfig = ctx.obj["config"]
    click.echo(f"http.base_url         = {cfg.http_base_url}")
    click.echo(f"http.login            = {cfg.http_login}")
    click.echo(f"http.password         = {'***' if cfg.http_password else ''}")
    click.echo(f"ui.language           = {cfg.language}")
    click.echo(f"ui.instruction_url    = {cfg.update_instruction_url}")
    for i, path in enumerate(cfg.last_firmware_paths):
        click.echo(f"recent.firmware_{i}    = {path}")


@config_group.command("set", help="Set a configuration value (key=value).")
@click.argument("key")
@click.argument("value")
@click.pass_context
def config_set_cmd(ctx: click.Context, key: str, value: str) -> None:
    cfg: AppConfig = ctx.obj["config"]
    mapping: dict[str, str] = {
        "http.base_url": "http_base_url",
        "http.login": "http_login",
        "http.password": "http_password",
        "ui.language": "language",
        "ui.instruction_url": "update_instruction_url",
    }
    attr = mapping.get(key)
    if attr is None:
        raise click.UsageError(f"unknown key: {key}")
    setattr(cfg, attr, value)
    save_config(cfg)
    click.echo(f"{key} saved.")


def main() -> int:
    try:
        cli(standalone_mode=False)
    except click.ClickException as e:
        e.show()
        return e.exit_code
    except click.Abort:
        click.echo("Aborted.", err=True)
        return 130
    except Exception as e:
        log.exception("unhandled exception")
        click.echo(f"error: {e}", err=True)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
