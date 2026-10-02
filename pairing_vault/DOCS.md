# Pairing Vault

Matter and Z-Wave devices come with a setup QR code printed on the device and on the box or manual. Once a device is installed the label is usually hard to reach, and slips of paper get lost. Pairing Vault stores those codes in Home Assistant so they are there when you need to set a device up again.

## What it stores

For each device:

- **Name** and **type** (Matter, Z-Wave, or other)
- **QR code payload**: the text inside the QR code (Matter codes start with `MT:`, Z-Wave SmartStart codes start with `90`)
- **Manual pairing code** (Matter, 11 or 21 digits) or **DSK** (Z-Wave, eight groups of five digits)
- **Serial number**, **manufacturer**, **model**
- **Location** and **notes**

## Using it

Open **Pairing Vault** from the sidebar. Use **Add device** to store a new entry, click an entry to edit it, and use the search box to filter by name, location, serial number or code.

## Backups

Everything is stored in a single SQLite database in the add-on's `/data` folder, which Home Assistant includes in its backups automatically.
