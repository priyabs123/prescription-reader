// Frontend logic. It talks to the FastAPI backend with fetch():
//   GET  /api/config   -> what the server can do
//   POST /api/upload   -> image in, extracted text out
//   POST /api/explain  -> confirmed text in, explanation out
// All text coming from the server is inserted with textContent (never innerHTML),
// so nothing in a prescription can inject HTML into the page.

(function () {
  "use strict";

  const $ = (id) => document.getElementById(id);
  const MAX_TEXT = 5000;
  const SAMPLE_TEXT = [
    "Tab Paracetamol 500mg 1-0-1 after food x 5 days",
    "Cap Omeprazole 20 mg OD before breakfast",
    "Syp Cough syrup 5ml TDS",
    "Tab [?Pantop?] 40mg OD",
  ].join("\n");

  const state = {
    file: null,
    rotation: 0,
    objectUrl: null,
    maxMb: 5,
    lastResult: null,
  };

  // ---------- small helpers ----------
  function el(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  }

  function showError(message) {
    const box = $("error-box");
    box.textContent = message;
    box.hidden = false;
    box.scrollIntoView({ behavior: "smooth", block: "center" });
  }

  function clearError() {
    $("error-box").hidden = true;
    $("error-box").textContent = "";
  }

  function setLoading(on, text) {
    $("loading").hidden = !on;
    if (text) $("loading-text").textContent = text;
  }

  async function api(path, options) {
    let response;
    try {
      response = await fetch(path, options);
    } catch (e) {
      throw new Error("Could not reach the server. Is it running? Check your connection and try again.");
    }
    let data = null;
    try {
      data = await response.json();
    } catch (e) {
      /* not JSON */
    }
    if (!response.ok) {
      const message = data && data.error && data.error.message
        ? data.error.message
        : "Something went wrong (error " + response.status + "). Please try again.";
      throw new Error(message);
    }
    return data;
  }

  // ---------- setup ----------
  async function loadConfig() {
    try {
      const cfg = await api("/api/config");
      state.maxMb = cfg.max_upload_mb;
      $("dz-sub").textContent = "JPG, JPEG or PNG, up to " + cfg.max_upload_mb + " MB";
      const select = $("language");
      select.textContent = "";
      Object.entries(cfg.languages).forEach(([code, name]) => {
        const opt = el("option", "", name);
        opt.value = code;
        select.appendChild(opt);
      });
      const status = $("status-line");
      if (cfg.ocr_available) {
        status.textContent = "Reader ready: " +
          (cfg.ocr_provider === "vision" ? "Google Cloud Vision" : "Gemini vision model") + ".";
      } else {
        status.textContent = "No OCR service is configured. You can still type or paste the prescription text in step 2.";
      }
    } catch (e) {
      showError(e.message);
    }
  }

  function showReview() {
    $("review-card").hidden = false;
  }

  // ---------- step 1: choose + preview ----------
  function handleFile(file) {
    clearError();
    if (!file) return;
    const name = file.name.toLowerCase();
    if (!/\.(jpe?g|png)$/.test(name) || !/^image\/(jpeg|png)$/.test(file.type)) {
      showError("Only JPG, JPEG and PNG images are allowed.");
      return;
    }
    if (file.size > state.maxMb * 1024 * 1024) {
      showError("The image is too large. Please choose a file smaller than " + state.maxMb + " MB.");
      return;
    }
    if (file.size === 0) {
      showError("The file is empty. Please choose another image.");
      return;
    }
    if (state.objectUrl) URL.revokeObjectURL(state.objectUrl);
    state.file = file;
    state.rotation = 0;
    state.objectUrl = URL.createObjectURL(file);
    $("preview-img").src = state.objectUrl;
    $("preview-img").style.transform = "";
    $("preview-area").hidden = false;
    $("quality-warnings").hidden = true;
    $("ocr-notes").hidden = true;
  }

  function rotate(delta) {
    state.rotation = (state.rotation + delta + 360) % 360;
    $("preview-img").style.transform = "rotate(" + state.rotation + "deg)";
  }

  function fillList(listId, items) {
    const list = $(listId);
    list.textContent = "";
    items.forEach((text) => list.appendChild(el("li", "", text)));
    list.hidden = items.length === 0;
  }

  async function readPrescription() {
    clearError();
    if (!state.file) {
      showError("Please choose a prescription image first.");
      return;
    }
    const form = new FormData();
    form.append("file", state.file);
    form.append("rotate", String(state.rotation));
    setLoading(true, "Reading your prescription... this can take up to a minute.");
    try {
      const data = await api("/api/upload", { method: "POST", body: form });
      showReview();
      $("transcript").value = data.text;
      $("confirm-check").checked = false;
      fillList("quality-warnings", data.quality_warnings);
      fillList("ocr-notes", data.notes);
      onTranscriptChange();
      $("transcript").scrollIntoView({ behavior: "smooth", block: "center" });
    } catch (e) {
      showError(e.message);
    } finally {
      setLoading(false);
    }
  }

  // ---------- step 2: review ----------
  function renderHighlight() {
    const box = $("highlight");
    const text = $("transcript").value;
    box.textContent = "";
    box.hidden = !/\[\?.*?\?\]/.test(text);
    if (box.hidden) return;
    text.split(/(\[\?.*?\?\])/).forEach((part) => {
      if (/^\[\?.*\?\]$/.test(part)) box.appendChild(el("mark", "", part));
      else box.appendChild(document.createTextNode(part));
    });
  }

  function updateExplainButton() {
    $("explain-btn").disabled = !($("transcript").value.trim() && $("confirm-check").checked);
  }

  function onTranscriptChange() {
    renderHighlight();
    updateExplainButton();
  }

  // ---------- step 3: explain ----------
  async function explain() {
    clearError();
    const text = $("transcript").value.trim();
    if (!text) {
      showError("Please enter or load the prescription text first.");
      return;
    }
    if (text.length > MAX_TEXT) {
      showError("The text is too long. Please keep it under " + MAX_TEXT + " characters.");
      return;
    }
    setLoading(true, "Preparing the explanation...");
    try {
      const data = await api("/api/explain", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          text: text,
          language: $("language").value,
          user_confirmed: $("confirm-check").checked,
        }),
      });
      state.lastResult = data;
      renderResults(data);
    } catch (e) {
      showError(e.message);
    } finally {
      setLoading(false);
    }
  }

  function renderResults(data) {
    const L = data.labels;
    $("results").hidden = false;
    $("results").lang = data.language;

    // warnings
    const warnBox = $("result-warnings");
    $("lbl-warnings").textContent = L.lbl_warnings;
    fillList("warnings-list", data.warnings);
    warnBox.hidden = data.warnings.length === 0;

    // transcription (kept separate from the explanation)
    $("lbl-transcription").textContent = L.lbl_transcription;
    $("res-transcription").textContent = data.transcription;

    // medicines
    $("lbl-medicines").textContent = L.lbl_medicines;
    const itemsBox = $("res-items");
    itemsBox.textContent = "";
    data.items.forEach((item) => {
      const card = el("div", item.status === "needs_confirmation" ? "med needs" : "med");
      card.appendChild(el("div", "med-source", item.source_text));
      card.appendChild(el("span", "badge", item.status_label));
      if (item.explanation.length) {
        const ul = el("ul");
        item.explanation.forEach((line) => ul.appendChild(el("li", "", line)));
        card.appendChild(ul);
      }
      if (item.flags.length) {
        const ul = el("ul");
        item.flags.forEach((flag) => ul.appendChild(el("li", "flag", "⚠ " + flag)));
        card.appendChild(ul);
      }
      itemsBox.appendChild(card);
    });

    // other lines
    $("other-wrap").hidden = data.other_text.length === 0;
    $("lbl-other").textContent = L.lbl_other;
    $("res-other").textContent = data.other_text.join("\n");

    // AI general information (clearly separated)
    const names = Object.keys(data.general_info);
    $("general-wrap").hidden = names.length === 0;
    $("lbl-general").textContent = L.lbl_general_info;
    $("general-caption").textContent = L.lbl_general_info_caption;
    const gl = $("general-list");
    gl.textContent = "";
    names.forEach((name) => gl.appendChild(el("li", "", name + ": " + data.general_info[name])));

    // notes + disclaimer
    $("lbl-notes").textContent = L.lbl_notes;
    fillList("res-notes", data.notes);
    $("res-disclaimer").textContent = data.disclaimer;

    $("results").scrollIntoView({ behavior: "smooth", block: "start" });
  }

  // ---------- step 4: copy / download ----------
  function resultsAsText() {
    const d = state.lastResult;
    if (!d) return "";
    const L = d.labels;
    const out = [];
    out.push("=== " + L.lbl_transcription + " ===", d.transcription, "");
    out.push("=== " + L.lbl_medicines + " ===");
    d.items.forEach((item) => {
      out.push("* " + item.source_text + "  [" + item.status_label + "]");
      item.explanation.forEach((line) => out.push("    - " + line));
      item.flags.forEach((flag) => out.push("    ! " + flag));
    });
    out.push("");
    if (d.other_text.length) out.push("=== " + L.lbl_other + " ===", d.other_text.join("\n"), "");
    if (d.warnings.length) out.push("=== " + L.lbl_warnings + " ===", ...d.warnings.map((w) => "! " + w), "");
    const names = Object.keys(d.general_info);
    if (names.length) {
      out.push("=== " + L.lbl_general_info + " ===", L.lbl_general_info_caption);
      names.forEach((n) => out.push("- " + n + ": " + d.general_info[n]));
      out.push("");
    }
    out.push("=== " + L.lbl_notes + " ===", ...d.notes.map((n) => "- " + n), "", d.disclaimer);
    return out.join("\n");
  }

  async function copyResults() {
    const text = resultsAsText();
    if (!text) return;
    try {
      await navigator.clipboard.writeText(text);
    } catch (e) {
      const area = document.createElement("textarea");
      area.value = text;
      document.body.appendChild(area);
      area.select();
      try { document.execCommand("copy"); } catch (e2) { /* ignore */ }
      document.body.removeChild(area);
    }
    $("copy-btn").textContent = "Copied!";
    setTimeout(() => { $("copy-btn").textContent = "Copy results"; }, 1800);
  }

  function downloadResults() {
    const text = resultsAsText();
    if (!text) return;
    const blob = new Blob(["﻿" + text], { type: "text/plain;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = "prescription-explanation.txt";
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  }

  // ---------- clear everything (privacy) ----------
  function clearAll() {
    if (state.objectUrl) URL.revokeObjectURL(state.objectUrl);
    state.file = null;
    state.rotation = 0;
    state.objectUrl = null;
    state.lastResult = null;
    $("file-input").value = "";
    $("preview-img").removeAttribute("src");
    $("preview-area").hidden = true;
    $("quality-warnings").hidden = true;
    $("ocr-notes").hidden = true;
    $("transcript").value = "";
    $("confirm-check").checked = false;
    $("results").hidden = true;
    $("review-card").hidden = true;
    clearError();
    onTranscriptChange();
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  // ---------- wire up events ----------
  function init() {
    $("file-input").addEventListener("change", (e) => handleFile(e.target.files[0]));
    const zone = $("dropzone");
    ["dragenter", "dragover"].forEach((ev) =>
      zone.addEventListener(ev, (e) => { e.preventDefault(); zone.classList.add("drag"); })
    );
    ["dragleave", "drop"].forEach((ev) =>
      zone.addEventListener(ev, (e) => { e.preventDefault(); zone.classList.remove("drag"); })
    );
    zone.addEventListener("drop", (e) => handleFile(e.dataTransfer.files[0]));

    $("rotate-left").addEventListener("click", () => rotate(-90));
    $("rotate-right").addEventListener("click", () => rotate(90));
    $("read-btn").addEventListener("click", readPrescription);
    $("type-btn").addEventListener("click", () => {
      showReview();
      $("transcript").focus();
      $("review-card").scrollIntoView({ behavior: "smooth", block: "center" });
    });
    // changing the language re-explains straight away if results are already showing
    $("language").addEventListener("change", () => {
      if (state.lastResult && !$("explain-btn").disabled) explain();
    });
    $("sample-btn").addEventListener("click", () => {
      $("transcript").value = SAMPLE_TEXT;
      $("confirm-check").checked = false;
      onTranscriptChange();
    });
    // Safety: if the text changes, the earlier "I have compared this text" tick no longer
    // applies to the new text, and any old explanation no longer matches it.
    $("transcript").addEventListener("input", () => {
      $("confirm-check").checked = false;
      $("results").hidden = true;
      state.lastResult = null;
      onTranscriptChange();
    });
    $("confirm-check").addEventListener("change", updateExplainButton);
    $("explain-btn").addEventListener("click", explain);
    $("copy-btn").addEventListener("click", copyResults);
    $("download-btn").addEventListener("click", downloadResults);
    $("clear-btn").addEventListener("click", clearAll);

    loadConfig();
    onTranscriptChange();
  }

  init();
})();
