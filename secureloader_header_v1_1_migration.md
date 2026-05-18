# SecureLoader Migration: header_t v1.0 → v1.1

## Overview of the header flow

Understanding who owns which part of the header is essential before making any changes.

```
┌─────────────┐   48-byte header   ┌──────────────┐   44-byte header   ┌─────────────┐
│  EncryptBIN │ ─────────────────► │ SecureLoader │ ─────────────────► │  Bootloader │
│  (creates   │   (encrypted file) │  (host tool) │      (UART)        │  header_t   │
│   .bin pkg) │                    │              │                    │  44 bytes)  │
└─────────────┘                    └──────────────┘                    └─────────────┘
```

- **EncryptBIN** produces an encrypted firmware package containing a **48-byte header** that includes `prev_app_version`. This format does **not change**.
- **SecureLoader** reads the 48-byte header from the file, uses `prev_app_version` internally (e.g. to fetch a rollback image from a server), then **strips `prev_app_version`** and transmits only **44 bytes** over UART to the bootloader.
- **The bootloader** receives a **44-byte header** (`header_t`, no `prev_app_version` field). It never sees `prev_app_version`.

---

## What changed in the bootloader

`prev_app_version` was removed from `header_t` and the downgrade-version guard was removed from `do_start()`.

### `header_t` before (48 bytes — bootloader v1.0.0)

```c
typedef struct {
    uint32_t protocol_version;  // Must match PROTOCOL_VERSION
    uint32_t product_ID_MSB;    // Upper 32 bits of DEVICE_ID
    uint32_t product_ID_LSB;    // Lower 32 bits of DEVICE_ID
    uint32_t app_version;       // Informational; not validated
    uint32_t prev_app_version;  // Downgrade guard: app_version must be >= this
    uint32_t page_count;        // 1 … (APP_LAST_PAGE - APP_START_PAGE + 1)
    uint32_t flash_page_size;   // Must match FLASH_PAGE_SIZE
    uint8_t  iv[16];            // AES-CBC initialisation vector
    uint32_t crc;               // Expected CRC-32 of the plaintext image
} header_t;                     // total: 48 bytes
```

### `header_t` after (44 bytes — bootloader v1.1+)

```c
typedef struct {
    uint32_t protocol_version;  // Must match PROTOCOL_VERSION
    uint32_t product_ID_MSB;    // Upper 32 bits of DEVICE_ID
    uint32_t product_ID_LSB;    // Lower 32 bits of DEVICE_ID
    uint32_t app_version;       // Informational; not validated
    uint32_t page_count;        // 1 … (APP_LAST_PAGE - APP_START_PAGE + 1)
    uint32_t flash_page_size;   // Must match FLASH_PAGE_SIZE
    uint8_t  iv[16];            // AES-CBC initialisation vector
    uint32_t crc;               // Expected CRC-32 of the plaintext image
} header_t;                     // total: 44 bytes
```

---

## Required changes in SecureLoader

EncryptBIN requires **no changes** — it continues to produce 48-byte headers.

SecureLoader must transmit a 44-byte header over UART. The byte layout it sends must match the bootloader's 44-byte `header_t` exactly (all fields little-endian).

### UART transmission byte layout (44 bytes)

```
offset  0 : protocol_version   (uint32_t, 4 bytes, little-endian)
offset  4 : product_ID_MSB     (uint32_t, 4 bytes, little-endian)
offset  8 : product_ID_LSB     (uint32_t, 4 bytes, little-endian)
offset 12 : app_version        (uint32_t, 4 bytes, little-endian)
offset 16 : page_count         (uint32_t, 4 bytes, little-endian)
offset 20 : flash_page_size    (uint32_t, 4 bytes, little-endian)
offset 24 : iv[0..15]          (16 bytes)
offset 40 : crc                (uint32_t, 4 bytes, little-endian)
```

`prev_app_version` (which sits at offset 16 in the 48-byte file header) must **not** be included in the UART transmission. All fields after `app_version` shift down by 4 bytes compared to the file layout.

### File parsing byte layout (48 bytes — unchanged)

```
offset  0 : protocol_version   (uint32_t, 4 bytes, little-endian)
offset  4 : product_ID_MSB     (uint32_t, 4 bytes, little-endian)
offset  8 : product_ID_LSB     (uint32_t, 4 bytes, little-endian)
offset 12 : app_version        (uint32_t, 4 bytes, little-endian)
offset 16 : prev_app_version   (uint32_t, 4 bytes, little-endian)  ← read, use internally, do NOT forward to bootloader
offset 20 : page_count         (uint32_t, 4 bytes, little-endian)
offset 24 : flash_page_size    (uint32_t, 4 bytes, little-endian)
offset 28 : iv[0..15]          (16 bytes)
offset 44 : crc                (uint32_t, 4 bytes, little-endian)
```

### What SecureLoader must do

1. Parse the full 48-byte header from the encrypted file (layout unchanged).
2. Read and use `prev_app_version` as needed (e.g. rollback image fetch from server).
3. Build the 44-byte UART header by copying all fields **except** `prev_app_version`, in the order shown in the UART layout table above.
4. Send `CMD_START` (0x02) followed immediately by the 44-byte UART header.

### Compatibility note

The 44-byte UART header is only compatible with **bootloader v1.1+**. A bootloader built from v1.0.0 expects 48 bytes; sending 44 bytes will cause it to stall waiting for the remaining 4 bytes and then misparse the first page command. Ensure the target device runs the matching bootloader version before uploading.

---

## Summary checklist

- [ ] **EncryptBIN** — no changes required; 48-byte file header format is unchanged
- [ ] **SecureLoader file parsing** — no changes required; continue reading the full 48-byte header from file
- [ ] **SecureLoader UART transmission** — build and send a 44-byte header (omit `prev_app_version`, adjust field offsets accordingly)
- [ ] Update any SecureLoader integration tests that construct or compare the raw UART byte sequence
- [ ] Confirm the target device runs bootloader v1.1+ before deploying updated SecureLoader
