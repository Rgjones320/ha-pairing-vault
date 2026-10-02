import hashlib

import pytest

from app.payloads import PayloadError, decode, matter_manual_code
from app.server import create_app

# Example from the Matter specification / connectedhomeip test vectors.
MATTER_QR = "MT:Y.K9042C00KA0648G00"
# Example from the Z-Wave node provisioning QR code specification.
ZWAVE_QR = "900132782003515253545541424344453132333435212223242500100435301537022065520001000000300578"


def zwave_qr(body: str) -> str:
    """Build a Z-Wave QR string with a valid checksum around ``body``."""
    checksum = int.from_bytes(hashlib.sha1(body.encode()).digest()[:2], "big")
    return f"9001{checksum:05d}{body}"


def test_matter():
    res = decode(MATTER_QR)
    assert res["protocol"] == "matter"
    assert res["fields"] == {"qr_payload": MATTER_QR, "manual_code": "3497-011-2332"}
    details = dict(res["details"])
    assert details["Vendor ID"] == "0xFFF1"
    assert details["Product ID"] == "0x8000"
    assert details["Discriminator"] == "3840"
    assert details["Discovery"] == "Bluetooth"


def test_matter_lowercase_prefix_and_multiple_devices():
    both = MATTER_QR + "*" + MATTER_QR[3:]
    res = decode("  mt:" + both[3:] + " ")
    assert res["fields"] == {"qr_payload": both, "manual_code": "3497-011-2332"}
    assert "2 devices" in dict(res["details"])["Note"]


def test_matter_long_manual_code_for_custom_flow():
    code = matter_manual_code(3840, 20202021, 0xFFF1, 0x8000, flow=2)
    assert len(code.replace("-", "")) == 21
    assert code.startswith("7")  # VID/PID-present bit set in the first digit


@pytest.mark.parametrize("bad", ["MT:", "MT:Y.K9042C00KA0648G0", "MT:Y.K9042C00KA0648G0!"])
def test_matter_invalid(bad):
    with pytest.raises(PayloadError):
        decode(bad)


def test_zwave():
    res = decode(ZWAVE_QR)
    assert res["protocol"] == "zwave"
    assert res["fields"] == {"qr_payload": ZWAVE_QR, "dsk": "51525-35455-41424-34445-31323-33435-21222-32425"}
    details = dict(res["details"])
    assert details["Inclusion"] == "SmartStart"
    assert details["Security"] == "S2 Unauthenticated, S2 Authenticated"
    assert details["Manufacturer ID"] == "0xFFF0"
    assert details["Firmware"] == "2.66"


def test_zwave_minimal():
    dsk = "34028236692093846346337460743156821145530"[:40]
    res = decode(zwave_qr("002" + dsk))
    assert res["fields"]["dsk"] == "-".join(dsk[i:i + 5] for i in range(0, 40, 5))
    assert dict(res["details"])["Security"] == "S2 Authenticated"


def test_zwave_spaces_removed():
    spaced = " ".join(ZWAVE_QR[i:i + 10] for i in range(0, len(ZWAVE_QR), 10))
    assert decode(spaced)["fields"]["qr_payload"] == ZWAVE_QR


def test_zwave_bad_checksum():
    bad = ZWAVE_QR[:20] + ("1" if ZWAVE_QR[20] != "1" else "2") + ZWAVE_QR[21:]
    with pytest.raises(PayloadError, match="checksum"):
        decode(bad)


@pytest.mark.parametrize("text", ["1A2B3C", "1a.2b.3c", " 1A 2B 3C "])
def test_insteon(text):
    assert decode(text) == {"protocol": "insteon", "fields": {"insteon_id": "1A.2B.3C"}, "details": []}


def test_other_text():
    assert decode("https://example.com/device/123") == {"protocol": "other", "fields": {}, "details": []}


@pytest.fixture
def client(tmp_path):
    return create_app(str(tmp_path)).test_client()


def test_decode_endpoint(client):
    res = client.post("/api/decode", json={"payload": MATTER_QR})
    assert res.status_code == 200
    assert res.get_json()["fields"]["manual_code"] == "3497-011-2332"

    res = client.post("/api/decode", json={"payload": "MT:!!"})
    assert res.status_code == 400 and res.get_json()["error"]

    assert client.post("/api/decode", json={}).status_code == 400
