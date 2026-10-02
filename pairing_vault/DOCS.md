# Pairing Vault

Matter, Z-Wave and Insteon devices come with a setup QR code or ID printed on the device and on the box or manual. Once a device is installed the label is usually hard to reach, and slips of paper get lost. Pairing Vault stores those codes in Home Assistant so they are there when you need to set a device up again.

## What it stores

For each device:

- **Name** and **type** (Matter, Z-Wave, Insteon, or other)
- **QR code payload**: the text inside the QR code (Matter codes start with `MT:`, Z-Wave SmartStart codes start with `90`, Insteon codes are the six-character device ID)
- **Matter pairing code** (11 or 21 digits), **Z-Wave device specific key (DSK)** (eight groups of five digits), or **Insteon ID** (six characters such as `1A.2B.3C`)
- **Serial number**, **manufacturer**, **model**
- **Location** and **notes**

## Using it

Open **Pairing Vault** from the sidebar. Use **Add device** to store a new entry, click an entry to edit it, and use the search box to filter by name, location, serial number or code.

## Reading a QR code

In the device form, **Scan a photo** reads the QR code from a picture. On a phone it offers to take a photo with the camera or pick one from your library; on a computer it opens a file picker. This works whether you reach Home Assistant over `http` or `https`. The photo is decoded in your browser and is not uploaded or stored.

**Use camera** scans live from the camera preview. Browsers only allow live camera access on secure pages, so this button appears only when Home Assistant is opened over `https` (for example through Nabu Casa or your own certificate). Over plain `http` on your network, use **Scan a photo** instead.

When the code is a Matter (`MT:`), Z-Wave SmartStart (`90…`) or Insteon code, Pairing Vault fills in the type and the Matter pairing code, DSK or Insteon ID, and shows what else the code contains, such as the vendor and product IDs. You can also paste or type the code's text into the **QR code payload** box and the same happens when you leave the box.

On an iPhone, photos picked with **Scan a photo** are handed over as JPEG automatically. A HEIC file copied to a computer may not open in Chrome or Firefox; export it as JPEG first.

## Showing a code for re-setup

**Show QR** on a device in the list (or **Show** next to the payload in the form) displays its QR code full screen, black on white, with the Matter pairing code, DSK or Insteon ID underneath. Point the Home Assistant app, or your Matter or Z-Wave controller app, at the screen to set the device up again. For Z-Wave the first five digits of the DSK, which controllers ask for as the PIN, are in bold. Tap anywhere to close it.

## Backups

Everything is stored in a single SQLite database in the add-on's `/data` folder, which Home Assistant includes in its backups automatically.
