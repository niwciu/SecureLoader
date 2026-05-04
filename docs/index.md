# 🔐 SecureLoader


<table style="width: 100%; border: none;">
  <tr>
    <td style="width: 260px; vertical-align: top;">
      <img src="SecureLoader.png" alt="SecureLoader logo">
    </td>
    <td style="vertical-align: top; font-size: 0.9rem; font-family: system-ui, sans-serif; position: relative;">
      <div style="margin-bottom: 1.5em;">
          <strong>SecureLoader</strong> is a cross-platform tool for uploading encrypted firmware binaries
          to embedded devices over a serial link.
          It ships with a scriptable CLI (`sld`) and an optional Qt6 GUI (`sld-gui`).
      </div>
      <div style="text-align: right;">
        <a href="https://github.com/niwciu/SecureLoader/releases">
          <img src="https://img.shields.io/badge/Download-EXE-blue?style=for-the-badge&logo=python" alt="Download SecureLoader">
        </a>
      </div>
    </td>
  </tr>
</table>
---

## 🧩 Companion tool — EncryptBIN

Firmware files flashed by SecureLoader are produced by
[**EncryptBIN**](https://github.com/niwciu/EncryptBIN) — a companion tool that takes
a raw binary and outputs an AES-128 CBC encrypted `.bin` with the 48-byte header
SecureLoader expects.

```mermaid
flowchart LR
    A[Factory / Initial provisioning] --> SB[SecureBootloader flashing] --> D[(Device)]

    A2[EncryptBIN] -->|produces| B([encrypted .bin])
    B -->|input| C[SecureLoader]
    C -->|flashes| D

    classDef tool fill:#3f51b5,stroke:#1a237e,color:#fff,stroke-width:2px
    classDef file fill:#009688,stroke:#004d40,color:#fff
    classDef device fill:#455a64,stroke:#263238,color:#fff

    class A,A2,C tool
    class B file
    class D,SB device

    click SB "https://github.com/niwciu/SECURE_BOOTLOADER" "SecureBootloader repository"
    click A2 "https://github.com/niwciu/EncryptBIN" "EncryptBIN repository"
```

---

## ✨ Key Features

- **🔒 Encrypted firmware format** — 48-byte little-endian header (protocol version,
  product ID, app version, previous app version, page count, page size, IV, CRC32)
  followed by an AES-128 CBC encrypted payload
  created by [EncryptBIN](https://github.com/niwciu/EncryptBIN).
- **📡 Custom serial bootloader protocol** — byte-stream, XOR-based ACK/NAK handshake,
  automatic reconnect on timeout, configurable baud rate, parity, and stop-bits.
- **📂 Three firmware sources** — local `.bin` file, HTTP server download (`sld fetch` /
  GUI _Fetch from server_), and a GitHub Releases source (scaffold — not yet wired to
  CLI or GUI; see [Roadmap](GITHUB_SOURCE_MIGRATION.md)).
  The HTTP source supports optional Basic Auth and derives the server URL from the
  device's Product ID automatically.
- **⚡ Full-featured CLI** — every capability available from the terminal and scriptable
  in CI pipelines.
- **🖥️ Qt6 GUI** — graphical frontend covering all CLI features with live compatibility
  indicators and progress bars.
- **🌍 Cross-platform** — Linux, Windows, macOS (Python 3.10+, pyserial, PySide6).
- **🗣️ Runtime i18n** — language switch without restart (English, German, French,
  Spanish, Italian, Polish).

---

## 🏗️ Architecture at a Glance

```mermaid
graph TB
    subgraph Frontends
        CLI["CLI — sld<br/><i>click-based</i>"]
        GUI["GUI — sld-gui<br/><i>PySide6 / Qt6</i>"]
    end

    subgraph Core["Core (pure Python — no UI dependency)"]
        direction LR
        firmware["firmware.py<br/>header parser"]
        protocol["protocol.py<br/>serial state machine"]
        sources["sources/<br/>FirmwareSource ABC"]
        updater["updater.py<br/>compatibility check"]
    end

    CLI --> Core
    GUI --> Core
```

The strict layering rule — **core never imports from CLI or GUI** — keeps the
protocol and firmware logic independently testable and reusable.

---

## 🚀 Quick Start

```bash
# Install CLI + GUI
pip install -e ".[gui]"

# Verify
sld --version
sld-gui &
```

Flash a firmware file:

```bash
sld flash --file firmware.bin --port /dev/ttyUSB0
```

See the [User Guide](USER_GUIDE.md) for full installation options and a
step-by-step walkthrough.

---

## 📚 Documentation Map

| Page | Contents |
|------|----------|
| [User Guide](USER_GUIDE.md) | Installation, CLI reference, GUI walkthrough, configuration |
| [Firmware Format](FIRMWARE_FORMAT.md) | Binary header layout, field semantics, wire vs. disk format |
| [Serial Protocol](PROTOCOL.md) | Command set, timing, state machine, bootloader requirements |
| [Architecture](ARCHITECTURE.md) | Layer design, module responsibilities, threading model |
| [Contributing](CONTRIBUTING.md) | Dev setup, testing, code style, adding sources / languages |
| [Troubleshooting](TROUBLESHOOTING.md) | Common errors and fixes |
| [Roadmap](GITHUB_SOURCE_MIGRATION.md) | GitHub Releases migration plan |

---

## 📄 License

MIT — see [LICENSE](https://github.com/niwciu/SecureLoader/blob/main/LICENSE).
