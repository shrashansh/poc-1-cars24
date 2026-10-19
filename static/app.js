"use strict";

const SLOT_NAMES = {
  front: "Front", rear: "Rear + badge", left: "Left side", right: "Right side", dash: "Odometer",
  interior: "Dashboard", seats: "Seats", tyre: "Tyre close-up", rc: "RC", service: "Service record",
};
const STEPS = [
  "Capture QA: checking each photo",
  "Identity agent: plate, colour, same car",
  "Variant agent: badges, wheels, cabin, RC",
  "Odometer agent: reading the cluster",
  "Damage agent: panels, non-original parts, tyres",
  "Document agent: RC and service record",
  "Cross-check: reconciling the findings",
  "Pricing: narrowing the real reference",
  "Explainer: seller message and inspector checklist",
];

const $ = (s) => document.querySelector(s);
const state = { catalog: null, samples: [], slots: {}, activeSample: null };

function el(tag, attrs = {}, ...kids) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "class") e.className = v;
    else if (k === "text") e.textContent = v;
    else e.setAttribute(k, v);
  }
  for (const k of kids) if (k !== null && k !== undefined) e.append(k);
  return e;
}
const inr = (n) => "₹" + Math.round(n).toLocaleString("en-IN");
const pct = (c) => Math.round(c * 100) + "%";

// ---------------- setup ----------------
async function init() {
  const [health, catalog, samples] = await Promise.all(
    ["/api/health", "/api/catalog", "/api/samples"].map((u) => fetch(u).then((r) => r.json())));
  state.catalog = catalog;
  state.samples = samples.cars;

  const pill = $("#modePill");
  if (health.openai_ready) { pill.textContent = `OpenAI · ${health.openai_model}`; pill.className = "pill good"; }
  else { pill.textContent = "OpenAI key missing"; pill.className = "pill bad"; $("#keyNotice").hidden = false; $("#run").disabled = true; }

  const model = $("#model");
  for (const [id, m] of Object.entries(catalog.models)) model.append(el("option", { value: id, text: m.label }));
  model.addEventListener("change", fillModelFields);
  catalog.km_bands.forEach(([a, b], i) =>
    $("#kmband").append(el("option", { value: String(i), text: `${a.toLocaleString("en-IN")} – ${b.toLocaleString("en-IN")} km` })));
  fillModelFields();

  catalog.slots.forEach((slot) => (state.slots[slot] = null));
  renderSlots();
  renderSamples();
  if (state.samples.length) loadSample(state.samples[0]);

  $("#form").addEventListener("submit", run);
}

function fillModelFields() {
  const m = state.catalog.models[$("#model").value];
  const year = $("#year"), variant = $("#variant");
  year.replaceChildren(...m.years.map((y) => el("option", { value: String(y), text: String(y) })));
  variant.replaceChildren(...m.variants.map((v) => el("option", { value: v, text: v })));
}

function renderSamples() {
  const box = $("#samples");
  box.replaceChildren();
  for (const car of state.samples) {
    const b = el("button", { type: "button", class: "sample" + (state.activeSample === car.id ? " active" : "") },
      el("b", { text: car.title }), el("span", { text: car.story }));
    b.addEventListener("click", () => loadSample(car));
    box.append(b);
  }
}

function loadSample(car) {
  state.activeSample = car.id;
  const d = car.declared;
  $("#rc").value = d.rc_number;
  $("#model").value = d.model_id; fillModelFields();
  $("#year").value = String(d.year);
  $("#variant").value = d.variant;
  $("#kmband").value = String(d.km_band_index);
  for (const slot of Object.keys(state.slots)) {
    const url = car.photos[slot];
    state.slots[slot] = url ? { kind: "sample", url, ref: url.replace(/^\/samples\//, ""), alt: car.alternates[slot] } : null;
  }
  renderSamples();
  renderSlots();
}

function renderSlots() {
  const box = $("#slots");
  box.replaceChildren();
  for (const slot of Object.keys(state.slots)) {
    const node = $("#slotTpl").content.firstElementChild.cloneNode(true);
    const s = state.slots[slot];
    node.querySelector(".slot-name").textContent = SLOT_NAMES[slot] || slot;
    const input = node.querySelector("input");
    input.id = "slot-" + slot;
    input.setAttribute("aria-label", "Photo: " + (SLOT_NAMES[slot] || slot));
    if (s) {
      node.classList.add("filled");
      node.querySelector("img").src = s.url;
      node.querySelector("img").alt = SLOT_NAMES[slot];
      node.querySelector(".slot-src").textContent = s.kind === "sample" ? "sample" : "yours";
    }
    input.addEventListener("change", () => {
      const f = input.files[0];
      if (!f) return;
      state.slots[slot] = { kind: "upload", file: f, url: URL.createObjectURL(f) };
      renderSlots();
    });
    node.querySelector(".slot-clear").addEventListener("click", () => { state.slots[slot] = null; renderSlots(); });
    box.append(node);
  }
}

// ---------------- run ----------------
async function run(ev) {
  ev.preventDefault();
  const err = $("#formError");
  err.hidden = true;
  const fd = new FormData($("#form"));
  let count = 0;
  for (const [slot, s] of Object.entries(state.slots)) {
    if (!s) continue;
    count++;
    if (s.kind === "upload") fd.append("photo_" + slot, s.file, s.file.name);
    else fd.append("sample_" + slot, s.ref);
  }
  if (!count) { err.textContent = "Add at least one photo, or load the sample car."; err.hidden = false; return; }

  $("#run").disabled = true;
  $("#empty").hidden = true; $("#report").hidden = true; $("#running").hidden = false;
  const stop = animateProgress();
  try {
    const res = await fetch("/api/inspect", { method: "POST", body: fd });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "The server could not run the inspection.");
    renderReport(data);
  } catch (e) {
    err.textContent = e.message; err.hidden = false;
    $("#empty").hidden = false;
  } finally {
    stop();
    $("#running").hidden = true;
    $("#run").disabled = false;
  }
}

function animateProgress() {
  const list = $("#progress");
  list.replaceChildren(...STEPS.map((t) => el("li", {}, el("span", { class: "dot" }), el("span", { text: t }))));
  let i = 0;
  const tick = () => {
    [...list.children].forEach((li, j) => {
      li.className = j === i ? "active" : "";
      li.firstChild.className = j === i ? "spinner" : "dot";
    });
    i = i === 0 ? 1 : Math.min(i + 1, STEPS.length - 1);
  };
  tick();
  const id = setInterval(tick, 2600);
  return () => clearInterval(id);
}

// ---------------- report ----------------
function section(title, ...kids) {
  return el("div", { class: "section" }, el("h3", { text: title }), ...kids);
}

function statusPill(status) {
  const map = { ok: ["good", "Done"], skipped: ["na", "Skipped"], error: ["bad", "Error"] };
  const [cls, txt] = map[status] || ["na", status];
  return el("span", { class: "pill " + cls, text: txt });
}

function renderReport(r) {
  const a = r.agents;
  const pricing = a["Pricing"].data || {};
  const cross = a["Cross-check"].data || {};
  const ex = a["Explainer"].data || {};
  const out = $("#report");
  out.replaceChildren();

  // 1. Price
  const ref = pricing.reference, vb = pricing.verified_band;
  if (ref && vb) {
    const lo = Math.min(ref.low, vb.low) * 0.98, hi = Math.max(ref.high, vb.high) * 1.02;
    const pos = (v) => ((v - lo) / (hi - lo)) * 100;
    const bar = (l, h, color) => {
      const b = el("div", { class: "bar" }); const s = el("span");
      s.style.left = pos(l) + "%"; s.style.width = (pos(h) - pos(l)) + "%"; s.style.background = color;
      b.append(s); return b;
    };
    const card = (cls, label, low, high, color, rows) => el("div", { class: "price " + cls },
      el("span", { class: "label", text: label }),
      el("span", { class: "band num", text: `${inr(low)} – ${inr(high)}` }),
      bar(low, high, color),
      el("dl", { class: "kv" }, ...rows.flatMap(([k, v]) => [el("dt", { text: k }), el("dd", { class: "num", text: v })])));
    out.append(section("Price range",
      el("div", { class: "cards2" },
        card("", "Reference today", ref.low, ref.high, "#94A3B8", [["Width", inr(ref.high - ref.low)], ["Variant priced", ref.variant]]),
        card("new", "After photo checks", vb.low, vb.high, "#4736FE", [
          ["Width", `${inr(vb.high - vb.low)} (${pricing.band_width_change_pct}% ${pricing.band_width_change_pct >= 0 ? "narrower" : "wider"})`],
          ["Facts verified", String(pricing.verified_facts.length)]])),
      el("p", { class: "note", text: "Reference: " + ref.source }),
      pricing.km_note ? el("p", { class: "note", text: pricing.km_note }) : null,
      ...(pricing.notes || []).map((n) => el("p", { class: "note", text: n }))));
  } else {
    out.append(section("Price range", el("p", { class: "callout bad",
      text: "No real price reference exists for this model, year and variant, so no rupee range is shown. The findings below are what Cars24's pricing engine would receive." })));
  }

  // 2. Issues
  const issues = cross.issues || [];
  const sev = { critical: "bad", warning: "warn", info: "na" };
  out.append(section("What needs attention",
    issues.length ? el("ul", { class: "issues" }, ...issues.map((i) =>
      el("li", {}, el("span", { class: "pill " + (sev[i.severity] || "na"), text: i.severity }), el("span", { text: i.message }))))
      : el("p", { class: "callout good", text: "No conflicts between the photos, the RC and the declared details." })));

  // 3. Findings
  out.append(section("Findings", el("div", { class: "findings" }, ...findingCards(a))));

  // 4. Items for the deduction table
  const pend = pricing.pending_price_items || [];
  if (pend.length) {
    out.append(section("For Cars24's deduction table",
      el("div", { class: "table-wrap" }, el("table", {},
        el("thead", {}, el("tr", {}, el("th", { text: "Finding" }), el("th", { text: "Effect" }), el("th", { text: "Why" }))),
        el("tbody", {}, ...pend.map((p) => el("tr", {}, el("td", { text: p.item }), el("td", { text: p.effect }), el("td", { text: p.why }))))))));
  }

  // 5. Agent trace
  out.append(section(`Agent trace · ${(r.elapsed_ms / 1000).toFixed(1)} s · ${r.job.model_used || ""}`,
    el("ol", { class: "trace" }, ...r.trace.map((t) => el("li", {},
      el("div", {}, el("span", { class: "name", text: t.agent }), el("span", { class: "eng", text: t.engine })),
      el("div", { class: "sum", text: t.error ? `${t.summary} (${t.error})` : t.summary }),
      el("div", { class: "meta" }, statusPill(t.status), el("span", { class: "num", text: `${t.ms} ms` })))))));

  // 6. Seller view
  out.append(section("What the seller sees",
    el("div", { class: "msg" }, ...ex.seller_message.map((m) => el("p", { text: m }))),
    ex.seller_message_hi ? el("div", { class: "msg", style: "margin-top:8px" }, el("p", { text: ex.seller_message_hi })) : null,
    ex.seller_tips && ex.seller_tips.length ? el("ul", { class: "note" }, ...ex.seller_tips.map((t) => el("li", { text: t }))) : null));

  // 7. Inspector checklist
  const typeLabel = { resolve: "Resolve", verify: "Verify", confirm: "Confirm", always: "Always" };
  out.append(section("Inspector checklist",
    el("ul", { class: "checklist" }, ...ex.inspector_checklist.map((c, i) => {
      const id = "chk" + i;
      return el("li", {}, el("input", { type: "checkbox", id }),
        el("label", { for: id, style: "flex-direction:row;gap:8px;color:inherit;font-size:14px" },
          el("span", { class: "pill " + ({ critical: "bad", warning: "warn", flag: "warn", ai_finding: "", routine: "na" }[c.severity] ?? ""), text: typeLabel[c.type] }),
          el("span", { text: c.item })));
    }))));

  // 8. Raw output
  const json = JSON.stringify(r, null, 2);
  const dl = el("button", { type: "button", class: "btn ghost", text: "Download JSON" });
  dl.addEventListener("click", () => {
    const blob = new Blob([json], { type: "application/json" });
    const link = el("a", { href: URL.createObjectURL(blob), download: `preinspection-${Date.now()}.json` });
    link.click();
  });
  out.append(section("Full report", el("div", { class: "row" }, dl),
    el("details", {}, el("summary", { text: "Show raw JSON" }), el("pre", { text: json }))));

  out.hidden = false;
  out.scrollIntoView({ behavior: "smooth", block: "start" });
}

function findingCards(a) {
  const cards = [];
  const card = (title, pill, ...body) => el("div", { class: "finding" }, el("h4", {}, el("span", { text: title }), pill), ...body);

  const id = a["Identity"];
  if (id) {
    const c = (id.data && id.data.checks) || {};
    const read = (id.data && id.data.read) || {};
    const ok = c.plate_matches_rc === true && c.same_car !== false;
    cards.push(card("Identity", el("span", { class: "pill " + (ok ? "good" : c.plate_matches_rc === false ? "bad" : "na"), text: ok ? "Matches RC" : "Check" }),
      el("p", { text: `Plate read: ${read.plate || "not readable"} (${pct(read.plate_confidence || 0)})` }),
      el("p", { text: `Colour: ${read.colour || "unknown"}` + (c.colour_matches_rc === true ? " · matches RC" : "") }),
      el("p", { text: read.notes || "" })));
  }
  const v = a["Variant"];
  if (v && v.data) {
    const d = v.data;
    const ok = d.detected !== "unknown" && d.confidence >= 0.6;
    cards.push(card("Variant", el("span", { class: "pill " + (!ok ? "na" : d.detected === d.declared ? "good" : "warn"),
      text: !ok ? "Unconfirmed" : d.detected === d.declared ? "Confirmed" : "Mismatch" }),
      el("p", { text: `Declared ${d.declared}; photos show ${d.detected} (${pct(d.confidence)})` }),
      d.evidence && d.evidence.length ? el("ul", {}, ...d.evidence.map((e) => el("li", { text: e }))) : null));
  }
  const o = a["Odometer"];
  if (o && o.data) {
    const d = o.data;
    cards.push(card("Odometer", el("span", { class: "pill " + (d.reading_km == null ? "na" : d.in_declared_band ? "good" : "warn"),
      text: d.reading_km == null ? "Not read" : d.in_declared_band ? "In band" : "Outside band" }),
      el("p", { text: d.reading_km == null ? "No legible reading." : `${d.reading_km.toLocaleString("en-IN")} km (${pct(d.confidence)})` }),
      el("p", { text: d.evidence || "" })));
  }
  const dm = a["Damage"];
  if (dm && dm.data) {
    const d = dm.data;
    cards.push(card("Body and wheels", el("span", { class: "pill " + ((d.damages || []).length || (d.observations || []).length ? "warn" : "good"),
      text: `${(d.damages || []).length} defect(s)` }),
      el("ul", {}, ...(d.damages || []).map((x) => el("li", { text: `${x.panel.replaceAll("_", " ")}: ${x.issue} (${x.severity}, ${pct(x.confidence)})` })),
        ...(d.observations || []).map((x) => el("li", { text: `Non-original: ${x.item} (${pct(x.confidence)})` }))),
      el("p", { text: `Tyres: ${d.tyres.notes || "not assessed"}` })));
  }
  const doc = a["Document"];
  if (doc && doc.data) {
    const d = doc.data, rc = d.rc;
    cards.push(card("Documents", el("span", { class: "pill " + (rc && rc.found ? "good" : "na"), text: rc && rc.found ? "RC read" : "No RC" }),
      rc && rc.found ? el("p", { text: `${rc.maker_classification || ""} · ${rc.colour || ""} · registered ${rc.registration_date || "?"}` + (rc.hypothecation ? " · hypothecated" : "") }) : null,
      el("p", { text: d.documents_found ? `${d.entries.length} service entries read` : "No service record provided: history check skipped." })));
  }
  return cards;
}

init().catch((e) => {
  const err = $("#formError");
  err.textContent = "Could not start: " + e.message;
  err.hidden = false;
});
