"""Decode Matter, Z-Wave SmartStart and Insteon QR code payloads.

Insteon labels carry just the six-hex-digit device ID (3FD2BE for 3F.D2.BE).
Matter: Matter Core Specification, section 5.1.3 (QR code) and 5.1.4
(manual pairing code). Z-Wave: "Node Provisioning QR Code Format"
(Z-Wave Alliance SDS13937).
"""

from __future__ import annotations

import hashlib
import re

BASE38 = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ-."


class PayloadError(ValueError):
    pass


def decode(payload: str) -> dict:
    """Return {"protocol", "fields", "details"} for a recognised payload.

    ``fields`` holds values for device entry fields, including the payload
    itself tidied up (case, stray spaces); ``details`` is a list of
    [label, value] pairs worth showing but with no field of their own.
    Raises PayloadError if the text looks like one of these formats but is
    malformed, and returns protocol "other" for anything else.
    """
    text = payload.strip()
    if text.upper().startswith("MT:"):
        return decode_matter(text)
    digits = re.sub(r"\s", "", text)
    if digits.startswith("90") and digits.isdigit() and len(digits) >= 52:
        return decode_zwave(digits)
    insteon = re.fullmatch(r"([0-9a-f]{2})[.:\s-]?([0-9a-f]{2})[.:\s-]?([0-9a-f]{2})", text, re.I)
    if insteon:
        return {"protocol": "insteon",
                "fields": {"insteon_id": ".".join(insteon.groups()).upper()},
                "details": []}
    return {"protocol": "other", "fields": {}, "details": []}


# --- Matter ---------------------------------------------------------------

_RENDEZVOUS = ((0, "Wi-Fi access point"), (1, "Bluetooth"), (2, "network"), (4, "Wi-Fi PAF"))
_FLOWS = {0: "standard", 1: "user action needed", 2: "custom"}


def _base38_decode(text: str) -> bytes:
    out = bytearray()
    for start in range(0, len(text), 5):
        chunk = text[start:start + 5]
        n_bytes = {5: 3, 4: 2, 2: 1}.get(len(chunk))
        if n_bytes is None:
            raise PayloadError("Matter code has the wrong length")
        value = 0
        for char in reversed(chunk):
            idx = BASE38.find(char)
            if idx < 0:
                raise PayloadError(f"Matter code contains an invalid character: {char!r}")
            value = value * 38 + idx
        if value >= 1 << (8 * n_bytes):
            raise PayloadError("Matter code is not valid base-38")
        out += value.to_bytes(n_bytes, "little")
    return bytes(out)


def decode_matter(text: str) -> dict:
    body = text[3:].upper()
    # Several devices can share one QR code, separated by "*". Use the first.
    first, *others = body.split("*")
    data = _base38_decode(first)
    if len(data) < 11:
        raise PayloadError("Matter code is too short")
    bits = int.from_bytes(data[:11], "little")

    def take(offset: int, width: int) -> int:
        return (bits >> offset) & ((1 << width) - 1)

    version = take(0, 3)
    vendor_id = take(3, 16)
    product_id = take(19, 16)
    flow = take(35, 2)
    rendezvous = take(37, 8)
    discriminator = take(45, 12)
    passcode = take(57, 27)
    if version != 0:
        raise PayloadError(f"Unsupported Matter code version {version}")
    if not 1 <= passcode <= 99999998:
        raise PayloadError("Matter code has an invalid setup passcode")

    via = [name for bit, name in _RENDEZVOUS if rendezvous & (1 << bit)]
    details = [
        ["Vendor ID", f"0x{vendor_id:04X}"],
        ["Product ID", f"0x{product_id:04X}"],
        ["Discriminator", str(discriminator)],
    ]
    if via:
        details.append(["Discovery", ", ".join(via)])
    if flow:
        details.append(["Commissioning", _FLOWS.get(flow, str(flow))])
    if others:
        details.append(["Note", f"QR code holds {len(others) + 1} devices; showing the first"])
    return {
        "protocol": "matter",
        "fields": {"qr_payload": "MT:" + body,
                   "manual_code": matter_manual_code(discriminator, passcode, vendor_id, product_id, flow)},
        "details": details,
    }


def matter_manual_code(discriminator: int, passcode: int, vendor_id: int = 0,
                       product_id: int = 0, flow: int = 0) -> str:
    """The numeric code printed under a Matter QR code, formatted with dashes."""
    long_form = flow != 0
    short_disc = discriminator >> 8
    digits = (
        f"{(int(long_form) << 2) | (short_disc >> 2)}"
        f"{((short_disc & 0x3) << 14) | (passcode & 0x3FFF):05d}"
        f"{passcode >> 14:04d}"
    )
    if long_form:
        digits += f"{vendor_id:05d}{product_id:05d}"
    digits += str(verhoeff_check_digit(digits))
    groups = (4, 3, 4, 5, 5) if long_form else (4, 3, 4)
    parts, pos = [], 0
    for size in groups:
        parts.append(digits[pos:pos + size])
        pos += size
    return "-".join(parts)


_VERHOEFF_D = [
    [0, 1, 2, 3, 4, 5, 6, 7, 8, 9], [1, 2, 3, 4, 0, 6, 7, 8, 9, 5],
    [2, 3, 4, 0, 1, 7, 8, 9, 5, 6], [3, 4, 0, 1, 2, 8, 9, 5, 6, 7],
    [4, 0, 1, 2, 3, 9, 5, 6, 7, 8], [5, 9, 8, 7, 6, 0, 4, 3, 2, 1],
    [6, 5, 9, 8, 7, 1, 0, 4, 3, 2], [7, 6, 5, 9, 8, 2, 1, 0, 4, 3],
    [8, 7, 6, 5, 9, 3, 2, 1, 0, 4], [9, 8, 7, 6, 5, 4, 3, 2, 1, 0],
]
_VERHOEFF_P = [
    [0, 1, 2, 3, 4, 5, 6, 7, 8, 9], [1, 5, 7, 6, 2, 8, 3, 0, 9, 4],
    [5, 8, 0, 3, 7, 9, 6, 1, 4, 2], [8, 9, 1, 6, 0, 4, 3, 5, 2, 7],
    [9, 4, 5, 3, 1, 2, 6, 8, 7, 0], [4, 2, 8, 6, 5, 7, 3, 9, 0, 1],
    [2, 7, 9, 3, 8, 0, 6, 4, 1, 5], [7, 0, 4, 6, 9, 1, 3, 2, 5, 8],
]
_VERHOEFF_INV = [0, 4, 3, 2, 1, 5, 6, 7, 8, 9]


def verhoeff_check_digit(digits: str) -> int:
    c = 0
    for i, d in enumerate(reversed(digits)):
        c = _VERHOEFF_D[c][_VERHOEFF_P[(i + 1) % 8][int(d)]]
    return _VERHOEFF_INV[c]


# --- Z-Wave SmartStart ----------------------------------------------------

_KEYS = ((0, "S2 Unauthenticated"), (1, "S2 Authenticated"), (2, "S2 Access Control"), (7, "S0"))


def decode_zwave(digits: str) -> dict:
    version = int(digits[2:4])
    checksum = int(digits[4:9])
    expected = int.from_bytes(hashlib.sha1(digits[9:].encode()).digest()[:2], "big")
    if checksum != expected:
        raise PayloadError("Z-Wave code checksum doesn't match; check for a mistyped digit")
    keys = int(digits[9:12])
    dsk = "-".join(digits[i:i + 5] for i in range(12, 52, 5))

    details = []
    if version == 1:
        details.append(["Inclusion", "SmartStart"])
    elif version == 0:
        details.append(["Inclusion", "S2 only (not SmartStart)"])
    granted = [name for bit, name in _KEYS if keys & (1 << bit)]
    if granted:
        details.append(["Security", ", ".join(granted)])

    pos = 52
    while pos + 4 <= len(digits):
        tlv_type = int(digits[pos:pos + 2]) >> 1
        length = int(digits[pos + 2:pos + 4])
        value = digits[pos + 4:pos + 4 + length]
        pos += 4 + length
        if len(value) != length:
            raise PayloadError("Z-Wave code is cut short")
        if tlv_type == 1 and length == 20:
            manufacturer, product_type, product_id, app_version = (
                int(value[i:i + 5]) for i in range(0, 20, 5)
            )
            details += [
                ["Manufacturer ID", f"0x{manufacturer:04X}"],
                ["Product type", f"0x{product_type:04X}"],
                ["Product ID", f"0x{product_id:04X}"],
                ["Firmware", f"{app_version >> 8}.{app_version & 0xFF}"],
            ]
    return {"protocol": "zwave", "fields": {"qr_payload": digits, "dsk": dsk}, "details": details}
