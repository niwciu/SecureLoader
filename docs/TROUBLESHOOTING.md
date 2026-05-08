# 🔍 Troubleshooting

This page covers common errors and how to fix them.

---

## 🔌 Serial Port Issues

### "No serial ports found" (GUI) / empty `sld list-ports` output

**Cause:** No USB-to-serial adapter is recognised by the OS, or the driver
is not installed.

**Steps:**
1. Plug in the adapter, then run `sld list-ports` again.
2. On Linux, check `dmesg | tail -20` for USB device events.
   The device typically appears as `/dev/ttyUSB0` (CP210x, CH340) or
   `/dev/ttyACM0` (CDC-ACM).
3. On Linux, ensure your user is in the `dialout` group:
   ```bash
   sudo usermod -aG dialout $USER
   # log out and back in for the change to take effect
   ```
4. On Windows, install the driver for your adapter (CP210x, FTDI, CH340, etc.)
   and look for `COMx` in Device Manager.

---

### "cannot open /dev/ttyUSB0: [Errno 13] Permission denied"

**Cause:** Your user does not have read/write access to the serial device.

**Fix:**
```bash
sudo usermod -aG dialout $USER
# or, as a one-off:
sudo chmod a+rw /dev/ttyUSB0
```

---

### "timed out waiting for device handshake"

**Cause:** The host sent `GET_VERSION` but the device did not respond within
the timeout period.

**Checks:**
- Verify the device is in **bootloader mode** (not the application). Most
  bootloaders activate on power-on or on a specific reset condition.
- Verify the **baud rate** matches the bootloader's configuration (default:
  115200). Try `--baudrate 9600` or other common rates if unsure.
- Verify the **parity** setting. Some bootloaders use odd or even parity.
  Use `--parity odd` / `--parity even` to match.
- Try a different USB cable or adapter — cheap adapters can have unreliable
  TX/RX lines.
- Increase the timeout: `sld flash --timeout 120 --file firmware.bin --port /dev/ttyUSB0`

---

### "serial write failed" / "serial read failed"

**Cause:** The serial port was disconnected or the device reset mid-transfer.

**Fix:** Reconnect the device, ensure it is in bootloader mode, and retry.

---

## ⚠️ Compatibility Errors

### "Device does not match firmware (product ID)"

**Cause:** The `productId` in the firmware header does not match the
`productId` reported by the bootloader.

This is a safety check to prevent flashing firmware intended for a different
product variant.

**Checks:**
- Confirm you are using the correct `.bin` file for the connected device.
- Use `sld info --file firmware.bin` to inspect the firmware's product ID.
- Use `sld info --port /dev/ttyUSB0` to read the device's product ID.

If you are certain the firmware is correct and want to override the check:
```bash
sld flash --file firmware.bin --port /dev/ttyUSB0 --force
```

!!! warning
    Using `--force` can brick the device if the firmware is genuinely
    incompatible (different flash layout, different MCU).

---

### "Device does not match firmware (bootloader protocol version)"

**Cause:** The `protocolVersion` in the firmware header does not equal the
`bootloaderVersion` reported by the device.

**Fix:** Ensure you are using firmware compiled for the bootloader version
currently installed on the device. The bootloader may need to be updated
separately before the application firmware can be flashed.

---

### "Device does not match firmware (flash page size)"

**Cause:** The `flashPageSize` reported by the bootloader does not match the
`flashPageSize` stored in the firmware header.

The bootloader transfers firmware in fixed-size pages. Both sides must agree on
the page size: the host slices the payload into chunks of exactly that many bytes,
and the bootloader expects chunks of that same size.

**Checks:**
- Use `sld info --file firmware.bin` and `sld info --port /dev/ttyUSB0` to compare
  the page size values on both sides.
- If the device reports a different value (e.g. `128`) than the firmware header
  (e.g. `2048`), the firmware was packaged with the wrong page size. Re-run the
  encryption/packaging tool with the correct `FLASH_PAGE_SIZE` value that matches
  the bootloader's `bl_hw_config.h` constant.
- If the bootloader constant is wrong, fix `FLASH_PAGE_SIZE` in the firmware source
  and rebuild and re-flash the bootloader first.

---

### Red highlighted fields in the GUI

- **Protocol** / **Bootloader Version** — protocol version mismatch.
- **Product ID** fields (device and file) — product ID mismatch.
- **Page Size** fields (device and file) — flash page size mismatch.

The **Update** button stays disabled until all three checks pass.

---

## ⬇️ Firmware Download Issues

### "plain HTTP is not permitted (http://...)"

**Cause:** `http.base_url` (or `--base-url`) starts with `http://` instead of `https://`.
Plain HTTP is rejected by default to prevent credentials and firmware from being transmitted
in cleartext.

**Fix (preferred):** Update your server to use HTTPS and change the configured URL:
```bash
sld config set http.base_url https://myserver/update
```

**Fix (controlled environments only):** If HTTPS is not available and you accept the risk,
pass `--allow-insecure` explicitly on each `fetch` call:
```bash
sld fetch --license AB --unique C0FE --output firmware.bin --allow-insecure
```

> ⚠️ Never use `--allow-insecure` on a network where credentials or firmware could be
> intercepted. The flag is intended for isolated lab environments only.

---

### "TLS certificate verification cannot be disabled"

**Cause:** `HttpFirmwareSource` was constructed with `tls_verify=False` without also
passing `allow_insecure=True`. This combination is rejected by default.

**Fix (testing only):** Pass `allow_insecure=True` when constructing the source programmatically,
or use `--allow-insecure` from the CLI. Never disable TLS verification in production.

---

### "cannot fetch http://...info.txt: ..."

**Cause:** The HTTP firmware server is unreachable or returned an error.

**Checks:**
- Verify `http.base_url` is set correctly: `sld config show`.
- Test the URL in a browser or with `curl`.
- If the server requires authentication, set credentials:
  ```bash
  sld config set http.login <user>
  sld config set http.password <pass>
  ```
- If the server uses HTTPS, ensure the URL starts with `https://`.
- Verify your server layout matches the required path structure:
  `{base_url}/{license_id}/{unique_id}/info.txt` and
  `{base_url}/{license_id}/{unique_id}/{version}.bin`.
  See [User Guide — HTTP server requirements](USER_GUIDE.md#-http-server-requirements)
  for details.

---

### "cannot download http://...{version}.bin: ..."

**Cause:** The `info.txt` file was fetched successfully but the firmware
binary could not be downloaded.

**Checks:**
- Verify the `.bin` file exists at the path returned by `info.txt`.
- Ensure the version string in `info.txt` exactly matches the `.bin`
  filename (without the `.bin` extension).

---

## ⚙️ Configuration Issues

### Config file location

```bash
sld config path     # print the path
sld config show     # show current values
```

Default locations:

| OS | Path |
|----|------|
| Linux | `~/.config/secureloader/config.ini` |
| Windows | `%APPDATA%\secureloader\config.ini` |
| macOS | `~/Library/Application Support/secureloader/config.ini` |

The file is INI format and can be edited by hand. It is written atomically
(`.tmp` + rename) and with `0600` permissions on Unix.

### Supported config keys

| Key | Description |
|-----|-------------|
| `http.base_url` | Base URL for the firmware HTTP server |
| `http.login` | HTTP Basic Auth username (leave empty if not required) |
| `http.password` | HTTP Basic Auth password (leave empty if not required) |
| `ui.language` | Display language: `auto`, `en`, `de`, `fr`, `es`, `it`, `pl` |
| `ui.instruction_url` | URL opened by GUI _Update instruction…_ menu item (hidden when empty) |

---

## 📦 Installation Issues

### "PySide6 not found" when launching `sld-gui`

**Cause:** The GUI extra was not installed.

**Fix:**
```bash
pip install -e ".[gui]"
```

---

### mypy / ruff errors after editing

Ensure you are using the project's configured tools:
```bash
pip install -e ".[dev]"
ruff check .
mypy src
bandit -r src/ -ll -x src/secure_loader/gui/resources
```

Mypy runs in `--strict` mode. All public functions and methods must be fully
typed.

---

## 🔎 Getting More Information

### CLI

Enable verbose logging for more detail:

```bash
sld -v flash ...     # INFO level
sld -vv flash ...    # DEBUG level (verbose output from serial and HTTP libraries)
```

### GUI

By default `sld-gui` produces no console output. Pass `--debug` to enable
full DEBUG-level logging from the `secure_loader` package:

```bash
sld-gui --debug
```

The debug trace includes:
- every call to `_update_download_button` with all gate conditions (useful for diagnosing a
  locked Update button)
- compatibility check results with exact hex values for bootloader version, product ID, and
  page size on both sides
- HTTP fetch progress (URL, HTTP status, Content-Length, bytes received)
- firmware download worker lifecycle events

> **Note:** Debug logging has a measurable performance cost — the GUI polls every 500 ms and
> writes multiple log lines per cycle. Use `--debug` only when diagnosing a problem, not
> during normal operation.
