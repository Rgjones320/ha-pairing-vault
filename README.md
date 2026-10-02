# Pairing Vault App Repository

A Home Assistant app (add-on) that stores Matter, Z-Wave and Insteon setup QR codes, pairing codes and serial numbers, so you can re-setup a device without having physical access to the device.

I got tired of my drawer full of paper copies of the codes included with many smart devices so had Claude build this for me.

## Install

1. In Home Assistant, go to **Settings → Add-ons → Add-on Store**, open the ⋮ menu and choose **Repositories**.
2. Add `https://github.com/Rgjones320/ha-pairing-vault`.
3. Install **Pairing Vault** and start it. Optionally, enable **Show in sidebar**.

## Development

The add-on lives in `pairing_vault/`. It is a small Flask app served by waitress, storing data in SQLite at `/data/pairing_vault.db`.

```sh
pip install -r pairing_vault/requirements.txt pytest
python -m pytest                       # API and storage tests
cd pairing_vault && DATA_DIR=./data python -m app   # http://localhost:8099
```

The add-on icon is the `qrcode` glyph from [Material Design Icons](https://pictogrammers.com/library/mdi/) (Apache-2.0).

Schema changes go in `MIGRATIONS` in `pairing_vault/app/db.py` as a new entry; the database's `PRAGMA user_version` tracks which have run.
