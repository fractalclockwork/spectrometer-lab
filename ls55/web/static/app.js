/* LS 55 operator console front-end — Setup / Acquire / Results */
(() => {
  const $ = (id) => document.getElementById(id);
  const logEl = $("logdrawer");
  const state = {
    mode: "setup",
    connected: false,
    fixturesRoot: "",
    busy: false,
    live: { dark: { x: [], y: [] }, sample: { x: [], y: [] } },
    review: null,
    spectrum: null,
    lastPortCount: -1,
    lastAutoProbeMs: 0,
    runsCache: [],
    selectedRunId: null,
    lastStatus: null,
  };

  const presets = {
    freepath: { ex: 350, emLo: 400, emHi: 550, sx: 5, sm: 5, ss: 120, si: 2, guide: 450 },
    "water-raman": { ex: 350, emLo: 380, emHi: 420, sx: 10, sm: 10, ss: 120, si: 2, guide: 397 },
    tonic: { ex: 350, emLo: 400, emHi: 550, sx: 5, sm: 5, ss: 120, si: 2, guide: 450 },
    riboflavin: { ex: 445, emLo: 480, emHi: 620, sx: 5, sm: 5, ss: 120, si: 2, guide: 525 },
  };

  function log(line) {
    const ts = new Date().toISOString().slice(11, 23);
    logEl.textContent = `${ts} ${line}\n` + logEl.textContent.slice(0, 12000);
  }

  function errMsg(err) {
    if (err == null) return "unknown error";
    if (typeof err === "string") return err;
    if (Array.isArray(err)) return err.map((e) => e.msg || JSON.stringify(e)).join("; ");
    if (typeof err === "object" && err.detail != null) return errMsg(err.detail);
    return String(err.message || err);
  }

  async function api(path, opts = {}) {
    const res = await fetch(path, {
      headers: { "Content-Type": "application/json", ...(opts.headers || {}) },
      ...opts,
    });
    const text = await res.text();
    let data;
    try { data = text ? JSON.parse(text) : {}; }
    catch { data = { detail: text }; }
    if (!res.ok) throw new Error(errMsg(data.detail || data) || res.statusText);
    return data;
  }

  function setSlot(id, text, kind) {
    const el = $(id);
    if (!el) return;
    el.textContent = text;
    el.className = `slot ${kind || "idle"}`;
  }

  function setChip(id, text, kind) {
    const el = $(id);
    if (!el) return;
    el.textContent = text;
    el.className = `chip ${kind || "idle"}`;
  }

  function fmtNum(v, digits = 1) {
    if (v == null || Number.isNaN(Number(v))) return "—";
    return Number(v).toFixed(digits);
  }

  function near(a, b, tol = 0.6) {
    if (a == null || b == null) return true;
    return Math.abs(Number(a) - Number(b)) <= tol;
  }

  function setMode(mode) {
    if (!["setup", "acquire", "results"].includes(mode)) return;
    state.mode = mode;
    const ws = $("workspace");
    if (ws) ws.dataset.mode = mode;
    document.querySelectorAll(".mode-tab").forEach((btn) => {
      const on = btn.dataset.mode === mode;
      btn.classList.toggle("active", on);
      btn.setAttribute("aria-selected", on ? "true" : "false");
    });
    document.querySelectorAll(".tab-panel").forEach((panel) => {
      panel.hidden = panel.dataset.for !== mode;
    });
    const setupMain = $("setup-main");
    const plot = $("plot");
    if (mode === "setup") {
      if (setupMain) setupMain.hidden = false;
      if (plot) plot.hidden = true;
    } else {
      if (setupMain) setupMain.hidden = true;
      if (plot) plot.hidden = false;
      // Plotly needs a visible container to size correctly.
      requestAnimationFrame(() => {
        try { Plotly.Plots.resize("plot"); } catch (_) { /* ignore */ }
        renderPlot();
      });
    }
    updateDurationHint();
  }

  function setActiveStep(n) {
    document.querySelectorAll(".step").forEach((el) => {
      el.classList.toggle("active", Number(el.dataset.step) === n);
    });
  }

  function looksLikeLinkLoss(msg) {
    const t = String(msg || "").toLowerCase();
    return [
      "timeout",
      "input/output",
      "errno 5",
      "device disconnected",
      "no such file",
      "not open",
      "protocol",
      "inter-byte",
      "empty read",
      "usb",
      "serial",
    ].some((k) => t.includes(k));
  }

  async function resumeAfterLinkFailure(msg, opts = {}) {
    const keep = opts.keepBanner != null ? opts.keepBanner : msg;
    if (looksLikeLinkLoss(msg)) {
      await refreshState({ keepBanner: keep }).catch(() => {});
    } else if (opts.skipAutoProbe) {
      await refreshState({ skipAutoProbe: true, keepBanner: keep }).catch(() => {});
    } else {
      await refreshState({ keepBanner: keep }).catch(() => {});
    }
  }

  function renderSynoptic(s) {
    const st = (s.status && s.status.status) || {};
    const link = s.link || {};
    const cmdEx = Number($("ex").value);
    const cmdEm = Number($("em-lo").value);
    const cmdSx = Number($("sx").value);
    const cmdSm = Number($("sm").value);
    const rbEx = st.ex_nm != null ? Number(st.ex_nm) : null;
    const rbEm = st.em_nm != null ? Number(st.em_nm) : null;
    const rbSx = st.ex_slit != null ? Number(st.ex_slit) : (st.sx != null ? Number(st.sx) : null);
    const rbSm = st.em_slit != null ? Number(st.em_slit) : (st.sm != null ? Number(st.sm) : null);

    let esPos = s.es_position;
    if (esPos == null && link.es_position != null) esPos = link.es_position;
    let srcText = "Xe ?";
    let srcKind = "idle";
    if (Number(esPos) === 1) { srcText = "Xe OFF"; srcKind = "ok"; }
    else if (Number(esPos) === 0) { srcText = "Xe ON"; srcKind = "warn"; }
    $("syn-src-val").textContent = srcText;
    $("syn-src").className = `syn-node ${srcKind}`;

    const exMatch = rbEx == null || near(cmdEx, rbEx);
    const emMatch = rbEm == null || near(cmdEm, rbEm);
    $("syn-ex-val").textContent = `cmd ${fmtNum(cmdEx)} / rb ${fmtNum(rbEx)}`;
    $("syn-ex-slit").textContent = `slit cmd ${fmtNum(cmdSx)} / rb ${fmtNum(rbSx)}`;
    $("syn-ex").className = `syn-node ${rbEx == null ? "idle" : (exMatch ? "ok" : "warn")}`;

    $("syn-em-val").textContent = `cmd ${fmtNum(cmdEm)} / rb ${fmtNum(rbEm)}`;
    $("syn-em-slit").textContent = `slit cmd ${fmtNum(cmdSm)} / rb ${fmtNum(rbSm)}`;
    $("syn-em").className = `syn-node ${rbEm == null ? "idle" : (emMatch ? "ok" : "warn")}`;

    const me = (s.status && s.status.me_code) != null ? s.status.me_code : null;
    const meText = me != null ? `ME ${me}` : (link.job_running || link.state === "busy" ? "BUSY" : "ME —");
    $("syn-det-val").textContent = meText;
    $("syn-det").className = `syn-node ${
      link.job_running || link.state === "busy" ? "warn" : (s.state === "idle_safe" ? "ok" : "idle")
    }`;

    // Setup center card
    const setupStatus = $("setup-status");
    const setupSession = $("setup-session");
    if (setupStatus) {
      if (s.state === "idle_safe") {
        setupStatus.textContent =
          `idle_safe · Ex ${fmtNum(rbEx)} / Em ${fmtNum(rbEm)} · ${srcText}`;
      } else if (s.state === "fault") {
        setupStatus.textContent = `FAULT — ${s.last_error || "see banner"}`;
      } else if (s.state === "disconnected") {
        setupStatus.textContent = link.state
          ? `Disconnected · link ${link.state}`
          : "Disconnected — Probe or Connect when USB is up.";
      } else {
        setupStatus.textContent = `State ${s.state || "—"}`;
      }
    }
    if (setupSession) {
      const port = s.port || (link.port) || "—";
      setupSession.textContent =
        `state ${s.state || "—"}\nport ${port}\nsettled ${!!s.link_settled} · recovering ${!!s.recovering}`;
    }
  }

  function renderHealth(s) {
    const ports = s.ports || [];
    const link = s.link || {};
    const offline = $("source-mode").value === "fixture";
    const settled = !!s.link_settled;
    let linkAgeMs = Infinity;
    if (link.probed_at) {
      const t = Date.parse(link.probed_at);
      if (!Number.isNaN(t)) linkAgeMs = Date.now() - t;
    }
    const linkFresh = settled || linkAgeMs < 12000;

    let usbText = "USB --";
    let usbKind = "idle";
    if (offline) {
      usbText = "USB n/a";
      usbKind = "warn";
    } else if (!ports.length || link.state === "no_device" || link.state === "adapter_lost") {
      usbText = "USB --";
      usbKind = "bad";
    } else {
      usbText = "USB OK";
      usbKind = "ok";
    }

    let dutText = "DUT --";
    let dutKind = "idle";
    if (offline && s.state === "idle_safe") {
      dutText = "DUT FIX";
      dutKind = "warn";
    } else if (s.state === "fault") {
      dutText = "FAULT";
      dutKind = "bad";
    } else if (!ports.length || link.state === "no_device" || link.state === "adapter_lost") {
      dutText = "DUT --";
      dutKind = usbKind === "bad" ? "idle" : "warn";
    } else if (link.state === "powered_off") {
      dutText = "DUT OFF";
      dutKind = "warn";
    } else if (link.state === "busy" || link.job_running) {
      dutText = "BUSY";
      dutKind = "bad";
    } else if (link.state === "booting") {
      dutText = "BOOT";
      dutKind = "warn";
    } else if (settled || (link.state === "ready" && linkFresh)) {
      dutText = "DUT OK";
      dutKind = "ok";
    } else if (s.state === "idle_safe") {
      dutText = "DUT OK";
      dutKind = "ok";
    } else if (link.state === "adapter_present" || ports.length) {
      dutText = "DUT ..";
      dutKind = "warn";
    }

    const esUntrusted =
      !!link.job_running ||
      ["busy", "booting", "powered_off", "no_device", "adapter_lost", "adapter_present", "error"].includes(
        link.state,
      );
    let esPos = null;
    if (!esUntrusted) {
      if (linkFresh && link.es_position != null) esPos = Number(link.es_position);
      else if (settled && s.es_position != null) esPos = Number(s.es_position);
      else if (s.state === "idle_safe" && s.es_position != null) esPos = Number(s.es_position);
    }
    let xeText = "Xe ?";
    let xeKind = "idle";
    if (esPos === 1) {
      xeText = "Xe OFF";
      xeKind = "ok";
    } else if (esPos === 0) {
      xeText = "Xe ON";
      xeKind = "warn";
    }

    setSlot("slot-usb", usbText, usbKind);
    setSlot("slot-dut", dutText, dutKind);
    setSlot("slot-xe", xeText, xeKind);

    const nominal = usbKind === "ok" && dutKind === "ok" && xeKind === "ok";
    let level = "idle";
    if (nominal) level = "ok";
    else if (usbKind === "bad" || dutKind === "bad" || xeKind === "bad") level = "bad";
    else if (usbKind === "warn" || dutKind === "warn" || xeKind === "warn") level = "warn";
    const health = $("health");
    if (health) health.dataset.level = level;

    let sess = s.state || "—";
    let sessKind = s.state === "idle_safe" ? "ok" : s.state === "fault" ? "bad" : "idle";
    if (s.state === "disconnected") {
      sess = ports.length ? "no sess" : "disc";
      sessKind = "idle";
    }
    setChip("badge-session", `sess ${sess}`, sessKind);

    const st = s.status && s.status.status;
    if (st) {
      setChip(
        "badge-id",
        `55.${st.revision || "?"} Ex${st.ex_nm ?? "—"}/Em${st.em_nm ?? "—"}`,
        "ok",
      );
    } else if (s.port && String(s.port).startsWith("fixture:")) {
      setChip("badge-id", "id fixture", "warn");
    } else {
      setChip("badge-id", "id —", "idle");
    }

    let detail = "Nominal: DUT on · USB up · Xe OFF";
    if (offline) {
      detail = "Offline fixture mode — no live USB/DUT";
    } else if (!ports.length || link.state === "no_device" || link.state === "adapter_lost") {
      detail = "USB–serial unplugged — plug adapter when ready";
    } else if (link.state === "powered_off" || dutText === "DUT OFF") {
      detail = "DUT off (normal when quieting fan/Xe) — power on to resume; Xe OFF on restore";
    } else if (dutText === "BUSY") {
      detail = "DUT busy after power-on — waiting for idle, then Xe OFF";
    } else if (dutText === "BOOT") {
      detail = "DUT booting / homing — wait for DUT OK";
    } else if (s.xe_kill_pending) {
      detail = "Xe kill pending after link loss — Probe/Connect will force OFF";
    } else if (s.recovering && !settled) {
      detail = "Recovering — probing until ready and Xe OFF";
    } else if (settled && xeText === "Xe OFF") {
      detail = "Settled — Xe OFF (no poll until a command fails)";
    } else if (xeText === "Xe ON") {
      detail = "Xe ON — press Xe OFF (resting default)";
    } else if (nominal) {
      detail = "Nominal health — DUT on · USB up · Xe OFF";
    } else if (link.first_power_on) {
      detail = "Power-on seen — Xe forced OFF for safe idle";
    }
    const detailEl = $("health-detail");
    if (detailEl) detailEl.textContent = detail;

    renderSynoptic(s);
  }

  function setErrorBanner(msg) {
    const el = $("error-banner");
    if (!msg) {
      el.hidden = true;
      el.textContent = "";
      return;
    }
    el.hidden = false;
    el.textContent = msg;
  }

  function setBusy(on) {
    state.busy = on;
    [
      "btn-connect",
      "btn-setup",
      "btn-scout",
      "btn-scan",
      "btn-blank",
      "btn-recompute",
      "btn-xe-off",
      "btn-abort",
      "btn-refresh",
    ].forEach((id) => {
      const el = $(id);
      if (el) el.disabled = on;
    });
  }

  function updateDurationHint() {
    const lo = Number($("em-lo").value);
    const hi = Number($("em-hi").value);
    const ss = Number($("ss").value) || 120;
    const si = Number($("si").value) || 2;
    const span = Math.abs(hi - lo);
    const pts = Math.round(span / si) + 1;
    const sec = (span / ss) * 60;
    const text = `~${pts} pts · ~${sec.toFixed(0)} s per arm @ ${ss} nm/min`;
    const el = $("duration-hint");
    if (el) el.textContent = text;
    const acq = $("acquire-duration");
    if (acq) acq.textContent = text;
  }

  function applyPreset(name) {
    const p = presets[name];
    if (!p) return;
    $("ex").value = p.ex;
    $("em-lo").value = p.emLo;
    $("em-hi").value = p.emHi;
    $("sx").value = p.sx;
    $("sm").value = p.sm;
    $("ss").value = p.ss;
    $("si").value = p.si;
    $("guide").value = p.guide;
    if (name === "water-raman") {
      $("noise-lo").value = 410;
      $("noise-hi").value = 420;
      $("half-window").value = 8;
      $("wing-ll").value = 380;
      $("wing-lh").value = 386;
      $("wing-rl").value = 410;
      $("wing-rh").value = 420;
    } else if (name === "tonic") {
      $("noise-lo").value = 520;
      $("noise-hi").value = 548;
      $("half-window").value = 25;
      $("wing-ll").value = 400;
      $("wing-lh").value = 410;
      $("wing-rl").value = 520;
      $("wing-rh").value = 548;
    }
    updateDurationHint();
    setActiveStep(2);
    if (state.lastStatus) renderSynoptic(state.lastStatus);
  }

  function initPlot() {
    const layout = {
      paper_bgcolor: "#0f1419",
      plot_bgcolor: "#152033",
      font: { color: "#e7ecf3", size: 11 },
      margin: { t: 36, r: 48, b: 48, l: 56 },
      xaxis: { title: "Wavelength (nm)", gridcolor: "#334155" },
      yaxis: { title: "Intensity", gridcolor: "#334155" },
      legend: { orientation: "h", y: 1.12 },
      shapes: [],
    };
    Plotly.newPlot("plot", [], layout, { responsive: true, displayModeBar: true });
  }

  function shapesFromControls() {
    const guide = Number($("guide").value);
    const half = Number($("half-window").value);
    const nlo = Number($("noise-lo").value);
    const nhi = Number($("noise-hi").value);
    const wll = Number($("wing-ll").value);
    const wlh = Number($("wing-lh").value);
    const wrl = Number($("wing-rl").value);
    const wrh = Number($("wing-rh").value);
    return [
      { type: "line", x0: guide, x1: guide, y0: 0, y1: 1, yref: "paper",
        line: { color: "#94a3b8", dash: "dash", width: 1 } },
      { type: "rect", x0: guide - half, x1: guide + half, y0: 0, y1: 1, yref: "paper",
        fillcolor: "rgba(56,189,248,0.12)", line: { width: 0 } },
      { type: "rect", x0: nlo, x1: nhi, y0: 0, y1: 1, yref: "paper",
        fillcolor: "rgba(245,158,11,0.10)", line: { width: 0 } },
      { type: "rect", x0: wll, x1: wlh, y0: 0, y1: 1, yref: "paper",
        fillcolor: "rgba(34,197,94,0.10)", line: { width: 0 } },
      { type: "rect", x0: wrl, x1: wrh, y0: 0, y1: 1, yref: "paper",
        fillcolor: "rgba(34,197,94,0.10)", line: { width: 0 } },
    ];
  }

  function renderPlot() {
    if ($("plot") && $("plot").hidden) return;
    const traces = [];
    if (state.live.dark.x.length) {
      traces.push({
        x: state.live.dark.x, y: state.live.dark.y, name: "Dark",
        mode: "lines", line: { color: "#64748b", width: 1.4 },
      });
    }
    if (state.live.sample.x.length) {
      traces.push({
        x: state.live.sample.x, y: state.live.sample.y, name: "Sample ON",
        mode: "lines", line: { color: "#38bdf8", width: 1.6 },
      });
    }
    const rev = state.review;
    if (rev && state.mode === "results") {
      if (rev.blank && rev.blank.length) {
        traces.push({
          x: rev.wavelength_nm, y: rev.blank, name: "Blank",
          mode: "lines", line: { color: "#f59e0b", width: 1.2, dash: "dot" },
        });
      }
      traces.push({
        x: rev.wavelength_nm, y: rev.corrected, name: "Corrected",
        mode: "lines", line: { color: "#22c55e", width: 1.8 },
      });
      if (rev.continuum_fit && rev.continuum_fit.length) {
        traces.push({
          x: rev.wavelength_nm, y: rev.continuum_fit, name: "Wing fit",
          mode: "lines", line: { color: "#a78bfa", width: 1.2, dash: "dash" },
        });
      }
      if (rev.residual && rev.residual.length) {
        traces.push({
          x: rev.wavelength_nm, y: rev.residual, name: "Residual ΔI",
          mode: "lines", line: { color: "#fb7185", width: 1.3 }, yaxis: "y2",
        });
      }
    }
    const layoutUpdate = {
      shapes: shapesFromControls(),
      yaxis2: {
        overlaying: "y", side: "right", showgrid: false,
        title: "Residual", color: "#fb7185",
      },
    };
    const base = document.getElementById("plot").layout || {};
    Plotly.react("plot", traces, Object.assign({}, base, layoutUpdate));
  }

  function ingestSeries(series, bucket) {
    if (!series || !series.wavelength_nm || !series.intensity) return;
    bucket.x = series.wavelength_nm.slice();
    bucket.y = series.intensity.slice();
  }

  function applyScanResult(r) {
    if (r.dark) ingestSeries(r.dark, state.live.dark);
    if (r.sample) ingestSeries(r.sample, state.live.sample);
    if (r.clipped) {
      setChip("badge-clip", "CLIP", "bad");
      const ac = $("acquire-clip");
      if (ac) ac.textContent = "CLIPPED ≥900k";
    } else {
      setChip("badge-clip", "clip ok", "idle");
      const ac = $("acquire-clip");
      if (ac) ac.textContent = "Clip ok";
    }
    renderPlot();
  }

  function updateMetrics(rev) {
    if (!rev) {
      $("metrics").innerHTML = "Peak —<br />Δλ —<br />Abs SNR —<br />Contrast SNR —";
      return;
    }
    const peak = rev.peak_nm != null
      ? `${rev.peak_nm.toFixed(1)} nm  I=${Number(rev.peak_intensity).toFixed(0)}`
      : "—";
    const d = rev.delta_nm != null
      ? `${rev.delta_nm >= 0 ? "+" : ""}${rev.delta_nm.toFixed(1)} nm`
      : "—";
    const a = rev.absolute_snr != null ? rev.absolute_snr.toFixed(1) : "—";
    const c = rev.contrast_snr != null ? rev.contrast_snr.toFixed(1) : "—";
    const clip = rev.clipped ? "<br /><span style='color:#ef4444'>CLIPPED</span>" : "";
    $("metrics").innerHTML =
      `Peak ${peak}<br />Δλ ${d}<br />Abs SNR ${a}<br />Contrast SNR ${c}${clip}`;
  }

  function setGauge(intensity) {
    const max = 999999;
    const pct = Math.max(0, Math.min(100, (Math.abs(intensity) / max) * 100));
    $("gauge-fill").style.width = `${pct}%`;
    const kind = Math.abs(intensity) >= 900000
      ? "bad"
      : Math.abs(intensity) >= 500000
        ? "warn"
        : "ok";
    setChip(
      "badge-clip",
      Math.abs(intensity) >= 900000 ? "CLIP" : "clip ok",
      kind === "ok" ? "idle" : kind,
    );
  }

  function syncSourceMode() {
    const offline = $("source-mode").value === "fixture";
    $("port-field").hidden = offline;
    $("fixture-field").hidden = !offline;
  }

  async function autoProbeIfNeeded(s) {
    const ports = s.ports || [];
    const offline = $("source-mode").value === "fixture";
    if (offline || state.busy || state.connected) return;
    if (s.link_settled) return;
    if (!ports.length) {
      state.lastPortCount = 0;
      return;
    }
    const link = s.link || {};
    const prevCount = state.lastPortCount;
    const portsAppeared = (prevCount === 0 || prevCount < 0) && ports.length > 0;
    state.lastPortCount = ports.length;
    const due = Date.now() - state.lastAutoProbeMs > 5000;
    const needsRecover = [
      "adapter_present",
      "adapter_lost",
      "powered_off",
      "no_device",
      "booting",
      "busy",
      "error",
    ].includes(link.state) || !link.state || !!s.recovering;
    const dueBusy =
      (link.state === "busy" || link.job_running || link.state === "booting") &&
      Date.now() - state.lastAutoProbeMs > 3000;
    if (!(portsAppeared || dueBusy || (due && needsRecover))) return;
    state.lastAutoProbeMs = Date.now();
    setBusy(true);
    try {
      const body = {
        port: $("port").value || ports[0] || null,
        boot_wait_s: 5,
        clear_busy: $("clear-busy").checked,
      };
      const probe = await api("/api/probe", { method: "POST", body: JSON.stringify(body) });
      log(
        `auto-probe ${probe.state || "?"} ready=${!!probe.ready} ` +
          `busy=${!!probe.job_running} es=${probe.es_position} ` +
          `settled=${!!probe.link_settled} ` +
          `${(probe.errors || []).join("; ")}`,
      );
      if (probe.ready) setErrorBanner("");
      await refreshState({ skipAutoProbe: true });
    } catch (e) {
      log(`auto-probe FAIL ${errMsg(e)}`);
    } finally {
      setBusy(false);
    }
  }

  async function refreshState(opts = {}) {
    const s = await api("/api/state");
    state.lastStatus = s;
    const ports = s.ports || [];
    renderHealth(s);

    if (opts.keepBanner) {
      setErrorBanner(opts.keepBanner);
    } else {
      const link = s.link || {};
      const quietOff =
        link.state === "powered_off" ||
        (!ports.length && s.state === "disconnected");
      if (s.state === "idle_safe") {
        setErrorBanner("");
      } else if (quietOff) {
        setErrorBanner("");
      } else if (s.last_error && s.state === "fault") {
        setErrorBanner(s.last_error);
      } else if (s.last_error && link.state === "busy") {
        setErrorBanner("");
      } else if (s.last_error && link.state === "adapter_lost") {
        setErrorBanner(s.last_error);
      }
    }

    const sel = $("port");
    const current = sel.value;
    sel.innerHTML = "";
    ports.forEach((p) => {
      const opt = document.createElement("option");
      opt.value = p;
      opt.textContent = p.replace(/^.*\//, "");
      opt.title = p;
      sel.appendChild(opt);
    });
    if (!ports.length) {
      const opt = document.createElement("option");
      opt.value = "";
      opt.textContent = "(no adapter — plug USB–RS232)";
      sel.appendChild(opt);
    } else if (current && ports.includes(current)) {
      sel.value = current;
    }

    const fsel = $("fixture");
    const fcur = fsel.value;
    fsel.innerHTML = "";
    const fixtures = s.fixtures || [];
    fixtures.forEach((name) => {
      const opt = document.createElement("option");
      opt.value = name;
      opt.textContent = name;
      fsel.appendChild(opt);
    });
    if (!fixtures.length) {
      const opt = document.createElement("option");
      opt.value = "";
      opt.textContent = "(no fixtures)";
      fsel.appendChild(opt);
    } else if (fcur && fixtures.includes(fcur)) {
      fsel.value = fcur;
    } else if (fixtures.includes("demo_session")) {
      fsel.value = "demo_session";
    }
    state.fixturesRoot = s.fixtures_root || "";
    state.connected = s.state !== "disconnected" && s.state !== "fault";
    if (s.state === "disconnected" || s.state === "fault") setActiveStep(1);
    else if (s.state === "idle_safe") setActiveStep(2);
    syncSourceMode();
    if (!opts.skipAutoProbe) {
      autoProbeIfNeeded(s).then(() => {}).catch(() => {});
    }
    return s;
  }

  function paintRunList() {
    const list = $("run-list");
    if (!list) return;
    const q = (($("run-filter") && $("run-filter").value) || "").trim().toLowerCase();
    list.innerHTML = "";
    const rows = (state.runsCache || []).filter((r) => {
      if (!q) return true;
      const blob = `${r.run_id || ""} ${r.experiment || ""} ${r.replicate_kind || ""} ${r.sample_id || ""}`.toLowerCase();
      return blob.includes(q);
    });
    rows.slice(0, 80).forEach((r) => {
      const div = document.createElement("div");
      div.className = "run-item" + (r.run_id === state.selectedRunId ? " active" : "");
      div.textContent = `${r.run_id}  ${r.experiment || ""}  ${r.replicate_kind || ""}`;
      div.title = r.path || r.run_id;
      div.onclick = () => loadRun(r.run_id);
      list.appendChild(div);
    });
    if (!rows.length) {
      const empty = document.createElement("div");
      empty.className = "run-item";
      empty.textContent = "(no runs)";
      empty.style.cursor = "default";
      list.appendChild(empty);
    }
  }

  async function refreshBlanksAndRuns() {
    const blanks = await api("/api/blanks");
    const sel = $("blank");
    const cur = sel.value;
    sel.innerHTML = '<option value="">(none)</option>';
    (blanks.blanks || []).forEach((b) => {
      const opt = document.createElement("option");
      opt.value = b.path;
      opt.textContent = b.name;
      sel.appendChild(opt);
    });
    if (cur) sel.value = cur;

    const runs = await api("/api/runs");
    state.runsCache = (runs.runs || []).slice().reverse();
    paintRunList();
  }

  async function loadRun(runId) {
    setBusy(true);
    try {
      setMode("results");
      const detail = await api(`/api/runs/${encodeURIComponent(runId)}`);
      state.selectedRunId = runId;
      paintRunList();
      if (detail.spectrum) {
        state.spectrum = detail.spectrum;
        state.live.sample = {
          x: detail.spectrum.wavelength_nm.slice(),
          y: detail.spectrum.intensity.slice(),
        };
        state.live.dark = { x: [], y: [] };
      }
      setActiveStep(3);
      await recompute();
      log(`loaded run ${runId}`);
    } catch (e) {
      log(`load FAIL ${errMsg(e)}`);
    } finally {
      setBusy(false);
    }
  }

  async function recompute() {
    const payload = {
      guide_nm: Number($("guide").value),
      half_window_nm: Number($("half-window").value),
      noise_lo_nm: Number($("noise-lo").value),
      noise_hi_nm: Number($("noise-hi").value),
      wing_left: [Number($("wing-ll").value), Number($("wing-lh").value)],
      wing_right: [Number($("wing-rl").value), Number($("wing-rh").value)],
      mode: $("review-mode").value || "fluorescence",
      sample_settings: {
        ex_nm: Number($("ex").value),
        slit_nm: Number($("sx").value),
        speed: Number($("ss").value),
        interval_nm: Number($("si").value),
      },
    };
    if ($("blank").value) payload.blank_csv = $("blank").value;
    if (state.live.sample.x.length) {
      payload.wavelength_nm = state.live.sample.x;
      payload.sample_on = state.live.sample.y;
    } else if (state.spectrum) {
      payload.wavelength_nm = state.spectrum.wavelength_nm;
      payload.sample_on = state.spectrum.intensity;
    } else {
      log("no spectrum to review");
      return;
    }
    const rev = await api("/api/review/recompute", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    state.review = rev;
    if (rev.blank_settings_match === false) {
      $("blank-match").textContent =
        "Blank settings MISMATCH: " + (rev.blank_match_notes || []).join("; ");
    } else if (rev.blank_settings_match === true) {
      $("blank-match").textContent = "Blank settings match staged optics";
    } else if ($("blank").value) {
      $("blank-match").textContent = "Blank selected (settings unknown)";
    }
    updateMetrics(rev);
    renderPlot();
  }

  function wireWs() {
    const proto = location.protocol === "https:" ? "wss" : "ws";
    let ws;
    try {
      ws = new WebSocket(`${proto}://${location.host}/ws/telemetry`);
    } catch (e) {
      log(`ws open FAIL ${e}`);
      setTimeout(wireWs, 2000);
      return;
    }
    ws.onopen = () => log("telemetry connected");
    ws.onmessage = (ev) => {
      let msg;
      try { msg = JSON.parse(ev.data); } catch { return; }
      const { event, payload } = msg;
      if (event === "state_changed") {
        refreshState({ skipAutoProbe: true }).catch(() => {});
      }
      if (event === "scan_point") {
        if (state.mode !== "acquire") setMode("acquire");
        const arm = payload.arm || "";
        const bucket = arm.startsWith("dark") ? state.live.dark : state.live.sample;
        bucket.x.push(payload.wavelength_nm);
        bucket.y.push(payload.intensity);
        if (Math.abs(payload.intensity) >= 900000) {
          setChip("badge-clip", "CLIP", "bad");
          const ac = $("acquire-clip");
          if (ac) ac.textContent = "CLIPPED ≥900k";
        }
        if (bucket.x.length % 2 === 0) renderPlot();
      }
      if (event === "scan_phase") {
        log(`phase ${payload.phase}`);
        const ph = $("acquire-phase");
        if (ph) ph.textContent = `Phase ${payload.phase || "—"}`;
      }
      if (event === "scan_completed") {
        applyScanResult(payload);
        log(`scan done passed=${payload.passed} clipped=${payload.clipped}`);
        const ph = $("acquire-phase");
        if (ph) ph.textContent = `Phase done · passed=${!!payload.passed}`;
        recompute().catch((e) => log(String(e)));
        refreshBlanksAndRuns()
          .then(() => {
            const art = payload.artifacts || {};
            const rid = art.run_id || (state.runsCache[0] && state.runsCache[0].run_id);
            if (rid) {
              state.selectedRunId = rid;
              paintRunList();
            }
            setMode("results");
          })
          .catch(() => {});
        setActiveStep(5);
      }
      if (event === "single_read_done") {
        const i = payload.corrected ?? payload.intensity;
        $("scout-readout").textContent =
          `I = ${i != null ? Number(i).toFixed(0) : "—"}` + (payload.clipped ? "  CLIPPED" : "");
        if (i != null) setGauge(i);
      }
      if (event === "shutter_off") {
        refreshState({ skipAutoProbe: true }).catch(() => {});
      }
      if (event === "link_settled") {
        refreshState({ skipAutoProbe: true }).catch(() => {});
      }
      if (event === "link_unsettled") {
        refreshState().catch(() => {});
      }
      if (event === "link_probe") {
        refreshState().catch(() => {});
        if (payload && payload.state === "powered_off") {
          log("link: DUT powered off / silent (quiet bench OK)");
        }
      }
      if (event === "disconnected") {
        refreshState().catch(() => {});
      }
    };
    ws.onclose = () => setTimeout(wireWs, 1500);
  }

  document.querySelectorAll(".mode-tab").forEach((btn) => {
    btn.addEventListener("click", () => setMode(btn.dataset.mode));
  });

  $("btn-log-toggle").onclick = () => {
    const shell = $("log-shell");
    const open = shell.dataset.open === "true";
    shell.dataset.open = open ? "false" : "true";
  };

  $("source-mode").onchange = syncSourceMode;
  if ($("run-filter")) {
    $("run-filter").addEventListener("input", () => paintRunList());
  }

  $("btn-connect").onclick = async () => {
    setBusy(true);
    setErrorBanner("");
    try {
      const offline = $("source-mode").value === "fixture";
      const body = {
        gate_a_pass: $("gate-a").checked,
        compartment_closed: $("compartment").checked,
        clear_busy: $("clear-busy").checked,
        boot_wait_s: 90,
      };
      if (offline) {
        const name = $("fixture").value;
        if (!name) throw new Error("select an offline fixture");
        body.fixture_dir = `${state.fixturesRoot}/${name}`;
        body.port = null;
      } else {
        body.port = $("port").value || null;
        if (!body.port) throw new Error("no USB–serial adapter — plug in and Refresh");
      }
      log("connecting… (power/USB may still be settling)");
      const r = await api("/api/connect", { method: "POST", body: JSON.stringify(body) });
      log(`connected ${r.port}`);
      if (r.discover && r.discover.first_power_on) {
        log("power-on: Xe was ON at probe — forced OFF for safe idle");
      }
      setErrorBanner("");
      setActiveStep(2);
      setMode("setup");
      await refreshState();
      await refreshBlanksAndRuns();
    } catch (e) {
      const msg = errMsg(e);
      setErrorBanner(msg);
      log(`connect FAIL ${msg}`);
      await resumeAfterLinkFailure(msg);
    } finally {
      setBusy(false);
    }
  };

  $("btn-disconnect").onclick = async () => {
    setBusy(true);
    try {
      await api("/api/disconnect", { method: "POST", body: "{}" });
      await refreshState();
      setActiveStep(1);
      setMode("setup");
    } catch (e) {
      log(errMsg(e));
    } finally {
      setBusy(false);
    }
  };

  $("btn-refresh").onclick = async () => {
    setBusy(true);
    try {
      const cur = await api("/api/state");
      if (cur.state !== "disconnected") {
        const st = await api("/api/status/refresh", { method: "POST", body: "{}" });
        const ok = st && (st.ok !== false);
        log(`status refresh ok=${!!ok} state→ check UI`);
        if (!ok && (st.errors || []).length) {
          setErrorBanner((st.errors || []).join("; "));
        } else {
          setErrorBanner("");
        }
      } else {
        const offline = $("source-mode").value === "fixture";
        const body = {
          boot_wait_s: 5,
          clear_busy: $("clear-busy").checked,
        };
        if (offline) {
          const name = $("fixture").value;
          if (name) body.fixture_dir = `${state.fixturesRoot}/${name}`;
        } else {
          body.port = $("port").value || null;
        }
        const probe = await api("/api/probe", { method: "POST", body: JSON.stringify(body) });
        const pst = probe.state || "?";
        log(
          `probe state=${pst} ready=${!!probe.ready} ` +
            `busy=${!!probe.job_running} power_on=${!!probe.first_power_on} ` +
            `${(probe.errors || []).join("; ")}`,
        );
        if (!probe.ready && (probe.errors || []).length) {
          setErrorBanner((probe.errors || []).join("; "));
        } else if (probe.ready) {
          setErrorBanner("");
          if (probe.first_power_on) {
            log("power-on detected: Xe was ON — forced OFF on ready probe");
          }
        }
      }
      await refreshState();
    } catch (e) {
      const msg = errMsg(e);
      setErrorBanner(msg);
      log(`refresh FAIL ${msg}`);
      await resumeAfterLinkFailure(msg, { keepBanner: msg });
    } finally {
      setBusy(false);
    }
  };

  $("btn-xe-off").onclick = async () => {
    setBusy(true);
    setErrorBanner("");
    let keep = null;
    try {
      log("Xe OFF…");
      let off = await api("/api/shutter/off", { method: "POST", body: "{}" });
      let errs = off.errors || [];
      let ok = !!off.ok || !!(off.shutter && off.shutter.ok);
      if (!ok) {
        log(`Xe OFF direct fail: ${errs.join("; ") || "not ok"} — retry via Abort`);
        const ab = await api("/api/abort", { method: "POST", body: "{}" });
        off = ab;
        errs = ab.errors || (ab.shutter && ab.shutter.errors) || errs;
        ok = !!ab.ok || !!(ab.shutter && ab.shutter.ok);
      }
      log(`Xe OFF ok=${ok} ${(errs || []).join("; ")}`);
      if (!ok) {
        keep = (errs && errs.length) ? errs.join("; ") : "Xe OFF failed — check USB/DUT power";
      }
      await refreshState({ skipAutoProbe: true, keepBanner: keep });
    } catch (e) {
      const msg = errMsg(e);
      keep = msg;
      setErrorBanner(msg);
      log(`Xe OFF FAIL ${msg}`);
      await resumeAfterLinkFailure(msg, { keepBanner: keep, skipAutoProbe: true });
    } finally {
      setBusy(false);
    }
  };

  $("btn-abort").onclick = async () => {
    setBusy(true);
    let keep = null;
    try {
      const ab = await api("/api/abort", { method: "POST", body: "{}" });
      log(
        `abort ok=${ab.ok} state=${ab.state || "?"} ephemeral=${!!ab.ephemeral} ` +
          `deferred=${!!ab.deferred} ${(ab.errors || []).join("; ")}`,
      );
      if (!ab.ephemeral && ab.deferred) {
        const off = await api("/api/shutter/off", { method: "POST", body: "{}" });
        log(`Xe OFF ok=${off.ok}`);
      } else if (ab.shutter && ab.shutter.ok != null) {
        log(`Xe OFF ok=${!!ab.shutter.ok}`);
      }
      if (!ab.ok && (ab.errors || []).length) {
        keep = (ab.errors || []).join("; ");
      }
      await refreshState({ skipAutoProbe: true, keepBanner: keep });
    } catch (e) {
      const msg = errMsg(e);
      keep = msg;
      setErrorBanner(msg);
      log(`abort FAIL ${msg}`);
      await resumeAfterLinkFailure(msg, { keepBanner: keep, skipAutoProbe: true });
    } finally {
      setBusy(false);
    }
  };

  $("btn-setup").onclick = async () => {
    setBusy(true);
    try {
      const body = {
        ex_nm: Number($("ex").value),
        em_nm: Number($("em-lo").value),
        ex_slit: Number($("sx").value),
        em_slit: Number($("sm").value),
      };
      const r = await api("/api/setup", { method: "POST", body: JSON.stringify(body) });
      log(`setup ok=${r.ok}`);
      setActiveStep(3);
      await refreshState();
    } catch (e) {
      const msg = errMsg(e);
      log(`setup FAIL ${msg}`);
      await resumeAfterLinkFailure(msg);
    } finally {
      setBusy(false);
    }
  };

  function buildScanBody({ role = "sample" } = {}) {
    const preset = $("preset").value || "custom";
    return {
      mx: 1,
      ex_nm: Number($("ex").value),
      em_lo: Number($("em-lo").value),
      em_hi: Number($("em-hi").value),
      interval_nm: Number($("si").value),
      speed: Number($("ss").value),
      ex_slit: Number($("sx").value),
      em_slit: Number($("sm").value),
      include_dark: $("include-dark").checked,
      n_accumulate: 1,
      experiment: role === "blank" ? "dashboard-blank" : `dashboard-${preset}`,
      method_name: preset,
      series_id: $("sample-id").value || null,
      replicate_kind: $("replicate").value || "sanity",
      sample_id: $("sample-id").value || null,
      dilution: $("dilution").value || null,
      geometry: $("geometry").value || "right_angle_4w",
      role,
      persist: true,
    };
  }

  $("btn-blank").onclick = async () => {
    setBusy(true);
    setMode("acquire");
    setActiveStep(3);
    try {
      state.live = { dark: { x: [], y: [] }, sample: { x: [], y: [] } };
      state.review = null;
      renderPlot();
      const body = buildScanBody({ role: "blank" });
      log("matched blank scan starting…");
      const ph = $("acquire-phase");
      if (ph) ph.textContent = "Phase blank scan…";
      const r = await api("/api/scan", { method: "POST", body: JSON.stringify(body) });
      applyScanResult(r);
      log(`blank scan passed=${r.passed} clipped=${!!r.clipped}`);
      await refreshState();
      await refreshBlanksAndRuns();
      if (r.artifacts && r.artifacts.csv) {
        $("blank").value = r.artifacts.csv;
        $("blank-match").textContent = "Acquired matched blank (select confirms path)";
      }
      setMode("results");
    } catch (e) {
      const msg = errMsg(e);
      log(`blank FAIL ${msg}`);
      await resumeAfterLinkFailure(msg);
    } finally {
      setBusy(false);
    }
  };

  $("btn-scout").onclick = async () => {
    setBusy(true);
    setMode("acquire");
    setActiveStep(4);
    try {
      const body = {
        ex_nm: Number($("ex").value),
        em_nm: Number($("guide").value),
        integration_s: 1.0,
        dark_correct: true,
      };
      const r = await api("/api/single-read", { method: "POST", body: JSON.stringify(body) });
      const i = r.corrected ?? r.intensity;
      $("scout-readout").textContent =
        `I = ${i != null ? Number(i).toFixed(0) : "—"}` + (r.clipped ? "  CLIPPED" : "");
      if (i != null) setGauge(i);
      log(`scout ok=${r.ok} I=${i}`);
      await refreshState();
    } catch (e) {
      const msg = errMsg(e);
      log(`scout FAIL ${msg}`);
      await resumeAfterLinkFailure(msg);
    } finally {
      setBusy(false);
    }
  };

  $("btn-scan").onclick = async () => {
    setBusy(true);
    setMode("acquire");
    setActiveStep(5);
    try {
      state.live = { dark: { x: [], y: [] }, sample: { x: [], y: [] } };
      state.review = null;
      renderPlot();
      const body = buildScanBody({ role: "sample" });
      log("scan starting…");
      const ph = $("acquire-phase");
      if (ph) ph.textContent = "Phase scanning…";
      const r = await api("/api/scan", { method: "POST", body: JSON.stringify(body) });
      applyScanResult(r);
      log(`scan returned passed=${r.passed} clipped=${!!r.clipped}`);
      if (r.passed || (r.sample && r.sample.intensity && r.sample.intensity.length)) {
        await recompute();
      }
      await refreshState();
      await refreshBlanksAndRuns();
      const art = r.artifacts || {};
      const rid = art.run_id || (state.runsCache[0] && state.runsCache[0].run_id);
      if (rid) {
        state.selectedRunId = rid;
        paintRunList();
      }
      setMode("results");
    } catch (e) {
      const msg = errMsg(e);
      log(`scan FAIL ${msg}`);
      await resumeAfterLinkFailure(msg);
    } finally {
      setBusy(false);
    }
  };

  $("btn-recompute").onclick = async () => {
    setBusy(true);
    try {
      await recompute();
    } catch (e) {
      log(`review FAIL ${errMsg(e)}`);
    } finally {
      setBusy(false);
    }
  };

  $("preset").onchange = (e) => applyPreset(e.target.value);
  ["em-lo", "em-hi", "ss", "si", "ex", "sx", "sm"].forEach((id) => {
    $(id).addEventListener("input", () => {
      updateDurationHint();
      if (state.lastStatus) renderSynoptic(state.lastStatus);
    });
  });
  $("blank").onchange = () => {
    if ($("blank").value) {
      $("blank-match").textContent = "Blank selected — recompute to verify";
      setActiveStep(3);
    } else {
      $("blank-match").textContent = "No blank selected";
    }
  };

  const params = new URLSearchParams(location.search);
  if (params.get("fixture")) {
    $("source-mode").value = "fixture";
  }

  initPlot();
  updateDurationHint();
  setMode("setup");
  setActiveStep(1);
  refreshState()
    .then(async (s) => {
      await refreshBlanksAndRuns();
      const want = params.get("fixture");
      if (want && (s.fixtures || []).includes(want)) {
        $("fixture").value = want;
        syncSourceMode();
        log(`offline fixture preselected: ${want}`);
      }
    })
    .catch((e) => log(errMsg(e)));
  wireWs();
  setInterval(() => {
    if (state.busy) return;
    refreshState().catch(() => {});
  }, 2500);
})();
