// All URLs are relative so the page works under Home Assistant's Ingress path.
const API = "api/devices";
const TYPE_LABEL = { matter: "Matter", zwave: "Z-Wave", other: "Other" };
const QR_HINT = {
  matter: "The text inside the QR code. Matter codes start with MT:",
  zwave: "The text inside the QR code. Z-Wave SmartStart codes start with 90 and are all digits.",
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
            d.qr_payload, d.manual_code, d.dsk, d.notes]
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
  const code = d.protocol === "zwave" ? d.dsk : d.manual_code;
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
      !d.qr_payload ? el("span", { className: "badge other", title: "No QR payload stored" }, "No QR") : null,
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
  dialog.showModal();
  form.elements.name.focus();
}

form.addEventListener("input", () => { $("#form-error").hidden = true; });

form.addEventListener("change", (e) => {
  if (e.target.name === "protocol") applyProtocol();
});

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  const data = Object.fromEntries(new FormData(form));
  // Clear the code field that doesn't apply so stale values aren't kept.
  if (data.protocol === "matter") data.dsk = "";
  if (data.protocol === "zwave") data.manual_code = "";
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
$("#add").addEventListener("click", () => openForm());
$("#search").addEventListener("input", render);
$("#filter").addEventListener("change", render);

load();
