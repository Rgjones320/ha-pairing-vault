// All URLs are relative so the page works under Home Assistant's Ingress path.
const API = "api/devices";
const TYPE_LABEL = { matter: "Matter", zwave: "Z-Wave", insteon: "Insteon", other: "Other" };
// The code shown in the list and under a full-screen QR code, per type.
const CODE_FIELD = { matter: "manual_code", zwave: "dsk", insteon: "insteon_id", other: "manual_code" };
const CODE_NAME = { manual_code: "Matter pairing code", dsk: "DSK", insteon_id: "Insteon ID" };
const QR_HINT = {
  matter: "The text inside the QR code. Matter codes start with MT:",
  zwave: "The text inside the QR code. Z-Wave SmartStart codes start with 90 and are all digits.",
  insteon: "The text inside the QR code. On Insteon labels it is the device ID without the dots.",
  other: "The text inside the QR code, if there is one.",
};

const $ = (sel) => document.querySelector(sel);
const listEl = $("#list");
const dialog = $("#dialog");
const form = $("#form");
let devices = [];
let editingId = null;

async function request(url, options = {}) {
  const res = await fetch(url, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (res.status === 204) return null;
  const body = await res.json().catch(() => ({}));
  if (!res.ok) {
    const err = new Error(
      body.fields
        ? Object.entries(body.fields).map(([k, v]) => {
            const label = k.replaceAll("_", " ");
            return `${label[0].toUpperCase()}${label.slice(1)} ${v}`;
          }).join(", ")
        : body.error || `Request failed (${res.status})`
    );
    throw err;
  }
  return body;
}

async function load() {
  try {
    devices = await request(API);
    $("#error").hidden = true;
  } catch (e) {
    $("#error").textContent = e.message;
    $("#error").hidden = false;
  }
  render();
}

function render() {
  const q = $("#search").value.trim().toLowerCase();
  const type = $("#filter").value;
  const shown = devices.filter((d) => {
    if (type && d.protocol !== type) return false;
    if (!q) return true;
    return [d.name, d.location, d.serial_number, d.manufacturer, d.model,
            d.qr_payload, d.manual_code, d.dsk, d.insteon_id, d.notes]
      .some((v) => v && v.toLowerCase().includes(q));
  });

  listEl.replaceChildren(...shown.map(renderItem));
  $("#empty").hidden = devices.length !== 0;

  const locations = [...new Set(devices.map((d) => d.location).filter(Boolean))].sort();
  $("#locations").replaceChildren(...locations.map((l) => new Option(l)));
}

function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  Object.assign(node, attrs);
  node.append(...children.filter((c) => c != null && c !== ""));
  return node;
}

function renderItem(d) {
  const code = d[CODE_FIELD[d.protocol]] || (d.protocol === "other" ? d.dsk : "");
  const meta = [
    d.location && el("span", {}, d.location),
    [d.manufacturer, d.model].filter(Boolean).join(" ") && el("span", {}, [d.manufacturer, d.model].filter(Boolean).join(" ")),
    d.serial_number && el("span", {}, "S/N ", el("span", { className: "mono" }, d.serial_number)),
    code && el("span", { className: "mono" }, code),
  ].filter(Boolean);
  const li = el("li", { className: "item", tabIndex: 0 },
    el("div", { className: "top" },
      el("span", { className: "name" }, d.name),
      el("span", { className: `badge ${d.protocol}` }, TYPE_LABEL[d.protocol] || d.protocol),
      d.qr_payload
        ? el("button", {
            type: "button", className: "show-qr", textContent: "Show QR",
            onclick: (e) => { e.stopPropagation(); showQr(d); },
            onkeydown: (e) => e.stopPropagation(),
          })
        : el("span", { className: "badge other", title: "No QR payload stored" }, "No QR"),
    ),
    meta.length ? el("div", { className: "meta" }, ...meta) : null,
  );
  li.addEventListener("click", () => openForm(d));
  li.addEventListener("keydown", (e) => { if (e.key === "Enter") openForm(d); });
  return li;
}

function currentProtocol() {
  return form.elements.protocol.value || "matter";
}

function applyProtocol() {
  const p = currentProtocol();
  form.querySelectorAll("[data-for]").forEach((node) => {
    node.hidden = !node.dataset.for.split(" ").includes(p);
  });
  form.querySelector('[data-hint="qr"]').textContent = QR_HINT[p];
}

function openForm(device = null) {
  form.reset();
  editingId = device ? device.id : null;
  $("#form-title").textContent = device ? "Edit device" : "Add device";
  $("#delete").hidden = !device;
  $("#form-error").hidden = true;
  if (device) {
    for (const [key, value] of Object.entries(device)) {
      const field = form.elements[key];
      if (field && key !== "protocol") field.value = value ?? "";
    }
    form.elements.protocol.value = device.protocol;
  }
  applyProtocol();
  resetQrFeedback();
  if (device?.qr_payload) interpret(device.qr_payload, { fill: false });
  dialog.showModal();
  form.elements.name.focus();
}

form.addEventListener("input", (e) => {
  $("#form-error").hidden = true;
  if (e.target.name === "qr_payload") $("#show-qr").hidden = !e.target.value.trim();
});

form.addEventListener("change", (e) => {
  if (e.target.name === "protocol") applyProtocol();
  if (e.target.name === "qr_payload") {
    resetQrFeedback();
    if (e.target.value.trim()) interpret(e.target.value, { fill: true });
  }
});

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  const data = Object.fromEntries(new FormData(form));
  // Clear code fields that don't apply to this type so stale values aren't kept.
  form.querySelectorAll("[data-for]").forEach((node) => {
    if (node.hidden) node.querySelectorAll("input").forEach((input) => { data[input.name] = ""; });
  });
  try {
    await request(editingId ? `${API}/${editingId}` : API, {
      method: editingId ? "PUT" : "POST",
      body: JSON.stringify(data),
    });
    dialog.close();
    await load();
  } catch (err) {
    $("#form-error").textContent = err.message;
    $("#form-error").hidden = false;
  }
});

$("#delete").addEventListener("click", async () => {
  const name = form.elements.name.value || "this device";
  if (!confirm(`Delete ${name}? Its stored codes will be gone.`)) return;
  try {
    await request(`${API}/${editingId}`, { method: "DELETE" });
    dialog.close();
    await load();
  } catch (err) {
    $("#form-error").textContent = err.message;
    $("#form-error").hidden = false;
  }
});

$("#cancel").addEventListener("click", () => dialog.close());
dialog.addEventListener("close", stopCamera);
$("#add").addEventListener("click", () => openForm());
$("#search").addEventListener("input", render);
$("#filter").addEventListener("change", render);

// --- QR codes ---------------------------------------------------------------
// Decoding happens in the browser, so the photo never leaves the device. The
// payload text is then sent to the add-on to work out the pairing codes.

const qrStatus = $("#qr-status");
const qrDetails = $("#qr-details");
const cameraDialog = $("#camera");
const video = $("#camera-video");
let cameraStream = null;
let interpretSeq = 0;

// Live video needs a secure context (https or localhost). Photo upload doesn't.
const cameraAvailable = window.isSecureContext && !!navigator.mediaDevices?.getUserMedia;
$("#qr-camera").hidden = !cameraAvailable;
$("#camera-note").hidden = window.isSecureContext;

function setQrStatus(text, isError = false) {
  qrStatus.textContent = text;
  qrStatus.classList.toggle("error", isError);
  qrStatus.hidden = !text;
}

function resetQrFeedback() {
  interpretSeq++;
  setQrStatus("");
  qrDetails.hidden = true;
  qrDetails.replaceChildren();
  $("#show-qr").hidden = !form.elements.qr_payload.value.trim();
}

// Ask the add-on what the payload means. With fill, copy the pairing code
// and type into the form, since the QR code is the source of truth for them.
async function interpret(payload, { fill, scanned = false } = {}) {
  const seq = ++interpretSeq;
  let result;
  try {
    result = await request("api/decode", { method: "POST", body: JSON.stringify({ payload }) });
  } catch (err) {
    if (seq === interpretSeq) setQrStatus(err.message, true);
    return;
  }
  if (seq !== interpretSeq) return;
  const label = TYPE_LABEL[result.protocol];
  if (result.protocol === "other") {
    if (scanned) setQrStatus("QR code read. It isn't a Matter, Z-Wave or Insteon code, so it's kept as text.");
    return;
  }
  if (fill) {
    form.elements.protocol.value = result.protocol;
    applyProtocol();
    for (const [key, value] of Object.entries(result.fields)) form.elements[key].value = value;
    const filled = CODE_NAME[CODE_FIELD[result.protocol]];
    const article = /^[AEIOU]/.test(label) ? "an" : "a";
    setQrStatus(`${scanned ? "Read" : "Recognised"} ${article} ${label} code and filled in the ${filled}.`);
  }
  qrDetails.replaceChildren(...result.details.flatMap(([k, v]) => [el("dt", {}, k), el("dd", {}, v)]));
  qrDetails.hidden = !result.details.length;
}

function useScanned(text) {
  form.elements.qr_payload.value = text.trim();
  resetQrFeedback();
  interpret(text, { fill: true, scanned: true });
}

let detector;
function barcodeDetector() {
  // Native decoder where the browser has one (Chrome on Android, macOS).
  if (detector === undefined) {
    try {
      detector = "BarcodeDetector" in window ? new BarcodeDetector({ formats: ["qr_code"] }) : null;
    } catch {
      detector = null;
    }
  }
  return detector;
}

async function detectNative(source) {
  const d = barcodeDetector();
  if (!d) return null;
  try {
    const found = await d.detect(source);
    return found[0]?.rawValue || null;
  } catch {
    return null;
  }
}

const scratch = document.createElement("canvas");
function detectJs(source, width, height, maxSide, inversionAttempts) {
  const scale = Math.min(1, maxSide / Math.max(width, height));
  scratch.width = Math.round(width * scale);
  scratch.height = Math.round(height * scale);
  const ctx = scratch.getContext("2d", { willReadFrequently: true });
  ctx.drawImage(source, 0, 0, scratch.width, scratch.height);
  const img = ctx.getImageData(0, 0, scratch.width, scratch.height);
  return jsQR(img.data, img.width, img.height, { inversionAttempts })?.data || null;
}

async function loadImage(file) {
  if (window.createImageBitmap) {
    try {
      return await createImageBitmap(file);
    } catch { /* fall back to <img>, which some browsers decode more formats with */ }
  }
  const url = URL.createObjectURL(file);
  try {
    const img = new Image();
    img.src = url;
    await img.decode();
    return img;
  } finally {
    URL.revokeObjectURL(url);
  }
}

async function decodeImageFile(file) {
  let image;
  try {
    image = await loadImage(file);
  } catch {
    throw new Error("This browser couldn't open that image. If it's a HEIC photo, save it as JPEG or PNG and try again.");
  }
  const width = image.naturalWidth || image.width;
  const height = image.naturalHeight || image.height;
  const text = await detectNative(image);
  if (text) return text;
  // Big photos with a small code decode better at a few different sizes.
  for (const size of [1600, 1000, 640, 2400]) {
    const found = detectJs(image, width, height, size, "attemptBoth");
    if (found) return found;
    if (size >= Math.max(width, height)) break;
  }
  return null;
}

$("#qr-photo").addEventListener("click", () => $("#qr-file").click());

$("#qr-file").addEventListener("change", async (e) => {
  const file = e.target.files[0];
  e.target.value = "";
  if (!file) return;
  resetQrFeedback();
  setQrStatus("Reading the photo…");
  try {
    const text = await decodeImageFile(file);
    if (text) useScanned(text);
    else setQrStatus("No QR code found in that photo. Try a closer, sharper shot with the whole code in view.", true);
  } catch (err) {
    setQrStatus(err.message, true);
  }
});

async function startCamera() {
  resetQrFeedback();
  try {
    cameraStream = await navigator.mediaDevices.getUserMedia({
      video: { facingMode: { ideal: "environment" }, width: { ideal: 1280 } },
      audio: false,
    });
  } catch (err) {
    const why = {
      NotAllowedError: "Camera access was blocked. Allow it in the browser's site settings, or use Scan a photo.",
      NotFoundError: "No camera was found. Use Scan a photo instead.",
    }[err.name] || `Couldn't start the camera (${err.message}).`;
    setQrStatus(why, true);
    return;
  }
  video.srcObject = cameraStream;
  $("#camera-status").textContent = "Point the camera at the QR code.";
  cameraDialog.showModal();
  try {
    await video.play();
  } catch { /* autoplay of a muted inline video is allowed; ignore odd failures */ }
  scanFrame();
}

async function scanFrame() {
  if (!cameraStream) return;
  if (video.readyState >= video.HAVE_CURRENT_DATA) {
    const text = (await detectNative(video))
      || detectJs(video, video.videoWidth, video.videoHeight, 800, "dontInvert");
    if (text && cameraStream) {
      cameraDialog.close();
      useScanned(text);
      return;
    }
  }
  setTimeout(() => requestAnimationFrame(scanFrame), 120);
}

function stopCamera() {
  if (!cameraStream) return;
  cameraStream.getTracks().forEach((t) => t.stop());
  cameraStream = null;
  video.srcObject = null;
  if (cameraDialog.open) cameraDialog.close();
}

$("#qr-camera").addEventListener("click", startCamera);
$("#camera-cancel").addEventListener("click", () => cameraDialog.close());
cameraDialog.addEventListener("close", stopCamera);

// Full-screen display, so a phone app can scan the stored code from this screen.
const viewer = $("#viewer");
let wakeLock = null;

function qrSvg(text) {
  const mode = /^[0-9]+$/.test(text) ? "Numeric"
    : /^[0-9A-Z $%*+\-./:]+$/.test(text) ? "Alphanumeric" : "Byte";
  const qr = qrcode(0, "M");
  qr.addData(text, mode);
  qr.make();
  return qr.createSvgTag({ cellSize: 8, margin: 32, scalable: true }); // 4-module quiet zone
}

async function showQr(device) {
  const payload = (device.qr_payload || "").trim();
  if (!payload) return;
  try {
    $("#viewer-qr").innerHTML = qrSvg(payload);
  } catch {
    $("#viewer-qr").textContent = "This payload is too long to show as a QR code.";
  }
  $("#viewer-name").textContent = device.name || "";
  const viewerCode = $("#viewer-code");
  viewerCode.replaceChildren();
  if (device.protocol === "zwave" && device.dsk) {
    // The first five digits are the PIN Z-Wave controllers ask for.
    const [pin, ...rest] = device.dsk.split("-");
    viewerCode.append("DSK ", el("strong", {}, pin), rest.length ? "-" + rest.join("-") : "");
  } else if (device.protocol === "insteon" && device.insteon_id) {
    viewerCode.append(`ID ${device.insteon_id}`);
  } else if (device.manual_code) {
    viewerCode.append(device.manual_code);
  }
  viewer.showModal();
  try { await viewer.requestFullscreen?.(); } catch { /* not allowed in this frame; the dialog still fills it */ }
  try { wakeLock = await navigator.wakeLock?.request("screen"); } catch { /* optional */ }
}

viewer.addEventListener("close", () => {
  if (document.fullscreenElement) document.exitFullscreen().catch(() => {});
  wakeLock?.release().catch(() => {});
  wakeLock = null;
});
viewer.addEventListener("click", () => viewer.close());
$("#show-qr").addEventListener("click", () => {
  const data = Object.fromEntries(new FormData(form));
  showQr(data);
});

load();
