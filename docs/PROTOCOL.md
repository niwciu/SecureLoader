# 📡 Serial Protocol Specification

Reference document for **bootloader authors** and device integrators.
Describes the protocol that the host application implements — the device
must behave according to this document to be updatable with SecureLoader.

Host implementation: [`src/secure_loader/core/protocol.py`](https://github.com/niwciu/SecureLoader/blob/main/src/secure_loader/core/protocol.py).

---

## 📋 Table of Contents

1. [Line Parameters](#️-line-parameters)
2. [Framing and Commands](#-framing-and-commands)
3. [Commands — Details](#-commands--details)
4. [Update Sequence](#-update-sequence)
5. [Timing](#️-timing)
6. [Error Handling](#️-error-handling)
7. [Host State Machine](#-host-state-machine)
8. [Device State Machine](#-device-state-machine)
9. [Bootloader Requirements](#-bootloader-requirements)
10. [Compatibility and Versioning](#-compatibility-and-versioning)

---

## ⚙️ Line Parameters

| Parameter | Value |
|-----------|-------|
| Baud rate | `115200` (default, configurable) |
| Data bits | `8` |
| Stop bits | `1` (default, configurable) |
| Parity | `None` (default), `Odd`, `Even` — configurable |
| Flow control | none |
| Endianness | little-endian (all multi-byte fields) |

The host sets parity and stop bits according to the `--parity` / `--stopbits`
CLI arguments or the GUI dropdowns. The device must support at least one parity
mode (typically `None`).

---

## 🔤 Framing and Commands

Communication is **frameless** (byte-stream). Each command is a single byte;
additional data follows in agreed-upon fixed sizes — no length prefix, no
delimiter.

### Command Codes (host → device)

| Name | Code | Payload | Meaning |
|------|------|---------|---------|
| `GET_VERSION` | `0x01` | — | Request device info |
| `START` | `0x02` | 44 B wire header | Begin firmware transfer |
| `NEXT_PAGE` | `0x03` | `flashPageSize` B | One payload page |
| `RESET` | `0x04` | — | Soft-reset the device |
| `NONE` | `0x00` | — | Reserved, unused |

### ACK / NAK Encoding (device → host)

The device responds with a single byte derived from the command code by XOR:

| Type | Rule | Examples |
|------|------|---------|
| ✅ ACK (success) | `cmd XOR 0x40` | `0x01` → `0x41` · `0x02` → `0x42` · `0x03` → `0x43` |
| ❌ NAK (error) | `cmd XOR 0x80` | `0x01` → `0x81` · `0x02` → `0x82` · `0x03` → `0x83` |

One rule covers all commands — no translation table needed on either side.

---

## 📖 Commands — Details

### `GET_VERSION` (`0x01`)

**Host sends:** `0x01` — polled every 500 ms until the device responds.

**Device responds:** `0x41` (ACK), then a **16-byte device info block**
(little-endian):

| Offset | Size | Type | Field |
|-------:|-----:|------|-------|
| 0 | 4 | u32 | `bootloaderVersion` |
| 4 | 8 | u64 | `productId` |
| 12 | 4 | u32 | `flashPageSize` |

**Field meanings:**

- `bootloaderVersion` — must equal `protocolVersion` in the firmware header;
  mismatch prevents flashing (no backward compatibility).
- `productId` — 64-bit identifier. Characters `hex[4:6]` of its 16-digit hex
  representation form `licenseId`; characters `hex[12:16]` form `uniqueId`
  (see [Firmware Format — productId Derived Fields](FIRMWARE_FORMAT.md#-productid-derived-fields)).
- `flashPageSize` — size of one flash page in bytes. The host uses this value
  to segment the payload. When `0`, the host falls back to `1024`.

> **Note:** the host never sends NAK (`0x81`) for `GET_VERSION` in the current implementation.

---

### `START` (`0x02`)

**Host sends:** `0x02`, then the **44-byte wire header**
(see [Firmware Format — Wire Header](FIRMWARE_FORMAT.md#-wire-header-44-b)).

**Device responds:**

- `0x42` ✅ ACK — ready for `NEXT_PAGE`. The device has erased the required
  flash sectors and initialised decryption / CRC state.
- `0x82` ❌ NAK — error (e.g. mismatched `productId`, flash erase failed,
  invalid IV). The host reports the error and returns to `CONNECTING`.

---

### `NEXT_PAGE` (`0x03`)

**Host sends:** `0x03`, then exactly `flashPageSize` bytes of the current page.

**Device responds:**

- `0x43` ✅ ACK — page decrypted and written; host sends next page (or stops
  when payload is exhausted).
- `0x83` ❌ NAK — write / decryption error. The host aborts the transfer.

The host ends the transfer **implicitly**: after the last page is ACKed, the
host transitions back to `CONNECTED` without sending any "end" command. The
device detects the end when it has received `pageCount` pages (from the wire
header), then verifies the CRC and applies the firmware.

---

### `RESET` (`0x04`)

**Host sends:** `0x04`.

**Device responds:** `0x44` ✅ ACK, then immediately resets.

> **Note:** the current host implementation **does not issue** `RESET`. The
> command is reserved in the enum for future use (e.g. force-reboot after
> an update). Bootloaders should implement it defensively.

---

## 🔄 Update Sequence

Full message exchange during a successful firmware update (retransmitted polls omitted):

```mermaid
sequenceDiagram
    participant H as Host
    participant D as Device

    loop every 500 ms until response
        H->>D: 0x01  GET_VERSION
        D->>H: 0x41  ACK + 16 B info (bootloaderVersion, productId, flashPageSize)
    end

    Note over H: validates compatibility<br/>(bootloaderVersion == protocolVersion, productId match)

    H->>D: 0x02  START + 44 B wire header
    D->>H: 0x42  ACK  (flash erased, decryption ready)

    loop pageCount pages
        H->>D: 0x03  NEXT_PAGE + flashPageSize B
        D->>H: 0x43  ACK  (page written)
    end

    Note over D: verify CRC32 · apply firmware

    loop poll resumes after transfer
        H->>D: 0x01  GET_VERSION
    end
```

---

## ⏱️ Timing

| Parameter | Value | Source |
|-----------|-------|--------|
| `GET_VERSION` poll interval | 500 ms | `POLL_INTERVAL_S = 0.5` |
| CONNECTED missed-poll limit | 3 polls (~1.5 s) | `CONNECTED_MISSED_POLLS = 3` |
| Flash erase timeout (STARTING) | 30 000 ms | `ERASE_TIMEOUT_S = 30.0` |
| Page ACK margin (SENDING) | 2 000 ms | `ALIVE_TIMEOUT_S = 2.0` |
| Host write timeout | 2 000 ms | `Serial(write_timeout=2.0)` |
| Host read timeout | 50 ms | `Serial(timeout=0.05)` |
| Default `flashPageSize` fallback | 1 024 B | `DEFAULT_PAGE_SIZE = 1024` |

**CONNECTED alive check (count-based):** the host increments a missed-poll counter
each time it sends `GET_VERSION` while in `CONNECTED`. The counter resets to zero
when a `GET_VERSION` ACK arrives. If the counter reaches `CONNECTED_MISSED_POLLS`
(3 consecutive unanswered polls, ~1.5 s), the host drops back to `CONNECTING`.

**STARTING erase timeout:** flash erase duration is unknown and can be several
seconds. The clock starts when `START` is sent (not from the last `GET_VERSION`
ACK). If `ERASE_TIMEOUT_S` (30 s) elapses without a `START` ACK, the host drops
back to `CONNECTING`.

**SENDING page ACK timeout (dynamic):** the host calculates the expected page
transmission time from the baud rate and page size
(`page_size × 10 bits / baudrate`), then adds `ALIVE_TIMEOUT_S` (2 s) as a
write-and-response margin. This ensures the timeout scales correctly at low baud
rates or with large pages. Example: 9600 baud, 2048-byte page → 2.13 s tx +
2 s margin = 4.1 s total.

**Write timeout:** if the device does not consume data fast enough (UART
backpressure), `pyserial` raises an exception after 2 s and the host disconnects.

---

## ⚠️ Error Handling

### Host side

| Situation | Host action |
|-----------|-------------|
| Unknown / stray byte in stream | Ignored — framing is state-driven, no resync needed |
| NAK on `START` or `NEXT_PAGE` | Logs error, emits `on_error` callback, returns to `CONNECTING` |
| CONNECTED: 3 missed polls | Returns to `CONNECTING`, restarts polling |
| STARTING/SENDING: alive timeout (2 s) | Returns to `CONNECTING`, restarts polling |
| Serial write exception | Stops loop, reports error, disconnects |

### Device side (recommendations)

- On transfer error (bad CRC, flash write refused): send NAK and **return to
  bootloader state**, ready for a new `START`. Do not reboot — the host will
  perform a fresh handshake.
- On unexpected bytes: respond with the NAK matching the expected command in
  the current state, or remain silent.

---

## 🤖 Host State Machine

```mermaid
stateDiagram-v2
    direction TB

    [*] --> IDLE
    IDLE --> CONNECTING : connect()

    CONNECTING --> CONNECTED : ACK(GET_VERSION) + 16 B info
    CONNECTING --> CONNECTING : timeout — retry GET_VERSION poll

    CONNECTED --> STARTING : start_download()
    CONNECTED --> CONNECTING : 3 consecutive missed polls (~1.5 s)

    STARTING --> SENDING : ACK(START)
    STARTING --> CONNECTING : NAK(START) / alive timeout (2 s)

    SENDING --> CONNECTED : payload exhausted (transfer done)
    SENDING --> CONNECTING : NAK(NEXT_PAGE) / alive timeout (2 s)

    CONNECTED --> IDLE : disconnect()
    STARTING --> IDLE : disconnect()
    SENDING --> IDLE : disconnect()
    CONNECTING --> IDLE : disconnect()
```

> `STARTING` and `SENDING` both show as **"Download"** in the GUI status field.

---

## 🔧 Device State Machine

Recommended state machine for a compatible bootloader:

```mermaid
stateDiagram-v2
    direction TB

    [*] --> WAIT_CMD : power on / reset

    WAIT_CMD --> WAIT_CMD : 0x01 GET_VERSION → reply 0x41 + 16 B info
    WAIT_CMD --> READ_HEADER : 0x02 START → read 44 B wire header
    WAIT_CMD --> [*] : 0x04 RESET → reply 0x44 · reset

    READ_HEADER --> WAIT_CMD : header invalid → 0x82 NAK
    READ_HEADER --> RECEIVE_PAGES : header valid → 0x42 ACK\n(erase flash, init decryption)

    RECEIVE_PAGES --> RECEIVE_PAGES : 0x03 NEXT_PAGE ok → 0x43 ACK
    RECEIVE_PAGES --> WAIT_CMD : 0x03 NEXT_PAGE error → 0x83 NAK

    RECEIVE_PAGES --> VERIFY : pageCount pages received

    VERIFY --> WAIT_CMD : CRC fail — stay in bootloader
    VERIFY --> [*] : CRC ok → jump to application
```

The bootloader maintains a received-page counter. After `pageCount` pages
(from the wire header) are received, it verifies the overall CRC32, then
typically jumps to the new application. At that point the host should see a
new `bootloaderVersion` / `productId` on the next `GET_VERSION` (if the
bootloader still listens after reset).

---

## ✅ Bootloader Requirements

Minimum requirements for a compatible device:

1. **UART:** 115200 8N1 (optionally configurable parity / stop bits).
2. **Commands:** responds to `0x01`, `0x02`, `0x03`, `0x04`.
3. **Responses:** single byte via `cmd XOR 0x40` (ACK) / `cmd XOR 0x80` (NAK).
4. **Polling:** responds to `GET_VERSION` while idle within one poll interval (500 ms).
5. **Device info:** after ACK for `GET_VERSION`, sends exactly 16 B
   (`bootloaderVersion u32` + `productId u64` + `flashPageSize u32`, little-endian).
6. **Transfer capability:**
    - erases flash for the application area,
    - decrypts each page (algorithm defined by the firmware build toolchain),
    - writes each page to flash,
    - verifies the CRC32 after all pages,
    - jumps to the new application on success, or stays in bootloader on failure.
7. **Silent:** does not send unsolicited bytes (the host ignores them, but they
   pollute debug output).

**Optional (recommended):**

- Watchdog reset of the bootloader after > 30 s with no command (safety for
  devices left in bootloader mode).

---

## 🔢 Compatibility and Versioning

The `protocolVersion` field in the firmware header must **equal**
`bootloaderVersion` from the device info response. The host compares them
for strict equality before starting the transfer:

- No semver — numbers must match exactly.
- A breaking protocol change requires bumping `protocolVersion` in both the
  bootloader and the firmware build toolchain.
- If soft compatibility is needed (e.g. minor version ignored), modify
  `check_device_matches_firmware` in
  [`core/updater.py`](https://github.com/niwciu/SecureLoader/blob/main/src/secure_loader/core/updater.py).

> **Recommendation:** treat `protocolVersion` as a monotonically increasing
> integer that changes only when the wire header format or command semantics
> change. Track the application version separately in `appVersion`.
