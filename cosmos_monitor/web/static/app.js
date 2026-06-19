/* cosmos-monitor web — frontend.
   No build step, no framework: a single file is enough for a dashboard
   this size, and it keeps the "clone repo, run, open browser" promise
   of the original TUI intact. */

(() => {
  "use strict";

  const CHAIN_COLORS = {
    bright_green: "#3fb950", bright_cyan: "#56d4dd", bright_yellow: "#e3b341",
    bright_magenta: "#e066d6", bright_red: "#f85149", bright_blue: "#58a6ff",
    cyan: "#2bb3ad", yellow: "#d29922", green: "#2ea043", magenta: "#bf5af2",
    blue: "#4078c0", red: "#da3633", bright_white: "#f0f3f6",
  };
  const colorFor = (name) => CHAIN_COLORS[name] || "#8b949e";

  const PAGE_SIZE = 15;

  /** @type {Record<string, any>} chain_id -> { cfg, els, validators, sort, search, page } */
  const chains = {};
  let activeChainId = null;

  const $ = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

  const tabsEl = $("#tabs");
  const contentEl = $("#content");
  const constellationEl = $("#constellation");
  const connStatusEl = $("#connStatus");
  const emptyStateEl = $("#emptyState");
  const pageTemplate = $("#chainPageTemplate");
  const toastEl = $("#toast");

  // ── Helpers ───────────────────────────────────────────────────────────

  function fmtUptime(sec) {
    sec = Math.max(0, sec | 0);
    if (sec < 60) return `${sec}s`;
    if (sec < 3600) return `${Math.floor(sec / 60)}m`;
    if (sec < 86400) return `${Math.floor(sec / 3600)}h ${Math.floor((sec % 3600) / 60)}m`;
    return `${Math.floor(sec / 86400)}d ${Math.floor((sec % 86400) / 3600)}h`;
  }

  function esc(s) {
    return String(s ?? "").replace(/[&<>"']/g, (c) => (
      { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]
    ));
  }

  function toast(msg) {
    toastEl.textContent = msg;
    toastEl.classList.remove("hidden");
    clearTimeout(toastEl._t);
    toastEl._t = setTimeout(() => toastEl.classList.add("hidden"), 3200);
  }

  function statusClass(status) {
    if (status === "BONDED") return "ok";
    if (status === "UNBONDING") return "warn";
    if (status === "UNBONDED") return "bad";
    return "dim";
  }

  // ── Tabs / chain page scaffolding ───────────────────────────────────────

  function tabId(chainId) {
    return "c-" + chainId.replace(/[^a-zA-Z0-9_-]/g, "-");
  }

  function buildChainPage(cfg) {
    const frag = pageTemplate.content.cloneNode(true);
    const section = frag.querySelector(".chain-page");
    const color = colorFor(cfg.color);
    section.style.setProperty("--chain-color", color);
    section.id = tabId(cfg.chain_id) + "-page";
    section.setAttribute("aria-labelledby", tabId(cfg.chain_id) + "-tab");

    $$(".panel", section).forEach((p) => p.style.setProperty("--chain-color", color));

    const hideBtn = section.querySelector('[data-action="hide-chain"]');
    hideBtn.classList.remove("hidden");
    hideBtn.addEventListener("click", () => hideChain(cfg));

    const searchInput = section.querySelector('[data-field="val-search"]');
    searchInput.addEventListener("input", () => {
      chains[cfg.chain_id].search = searchInput.value.trim().toLowerCase();
      chains[cfg.chain_id].page = 0;
      renderValTable(cfg.chain_id);
    });

    $$("th[data-sort]", section).forEach((th) => {
      th.addEventListener("click", () => {
        const key = th.dataset.sort;
        const st = chains[cfg.chain_id];
        st.sortDir = st.sortKey === key ? -st.sortDir : 1;
        st.sortKey = key;
        renderValTable(cfg.chain_id);
      });
    });

    section.querySelector('[data-action="prev-page"]').addEventListener("click", () => {
      const st = chains[cfg.chain_id];
      if (st.page > 0) { st.page--; renderValTable(cfg.chain_id); }
    });
    section.querySelector('[data-action="next-page"]').addEventListener("click", () => {
      const st = chains[cfg.chain_id];
      const max = Math.max(0, Math.ceil(st.filtered().length / PAGE_SIZE) - 1);
      if (st.page < max) { st.page++; renderValTable(cfg.chain_id); }
    });

    contentEl.appendChild(section);
    return section;
  }

  function buildTab(cfg) {
    const btn = document.createElement("button");
    btn.className = "tab";
    btn.id = tabId(cfg.chain_id) + "-tab";
    btn.setAttribute("role", "tab");
    btn.setAttribute("aria-selected", "false");
    btn.style.setProperty("--tab-color", colorFor(cfg.color));
    btn.textContent = cfg.name;
    btn.addEventListener("click", () => activateChain(cfg.chain_id));
    tabsEl.appendChild(btn);
    return btn;
  }

  function buildStar(cfg) {
    const b = document.createElement("button");
    b.className = "star";
    b.title = cfg.name;
    b.style.setProperty("--star-color", colorFor(cfg.color));
    b.dataset.running = "false";
    b.addEventListener("click", () => activateChain(cfg.chain_id));
    constellationEl.appendChild(b);
    return b;
  }

  function activateChain(chainId) {
    activeChainId = chainId;
    Object.values(chains).forEach((st) => {
      const isActive = st.cfg.chain_id === chainId;
      st.els.tab.setAttribute("aria-selected", String(isActive));
      st.els.page.classList.toggle("active", isActive);
      st.els.star.setAttribute("data-active", String(isActive));
    });
  }

  function hideChain(cfg) {
    if (!confirm(`${cfg.name} bu listeden gizlensin mi? (Tekrar görmek için sunucuda ~/.cosmos-monitor.json dosyasını düzenleyebilirsin.)`)) return;
    fetch("/api/nodes/hide", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ target: cfg.chain_id }),
    }).then(() => toast(`${cfg.name} gizlendi.`));
  }

  // ── Sync chain list from server ─────────────────────────────────────────

  function syncChains(list) {
    const seen = new Set();
    list.forEach((cfg) => {
      seen.add(cfg.chain_id);
      if (chains[cfg.chain_id]) {
        chains[cfg.chain_id].cfg = cfg;
        return;
      }
      const tab = buildTab(cfg);
      const page = buildChainPage(cfg);
      const star = buildStar(cfg);
      chains[cfg.chain_id] = {
        cfg,
        els: {
          tab, page, star,
          node: page.querySelector('[data-field="node"]'),
          myval: page.querySelector('[data-field="myval"]'),
          chainBox: page.querySelector('[data-field="chain"]'),
          network: page.querySelector('[data-field="network"]'),
          valCount: page.querySelector('[data-field="val-count"]'),
          valRows: page.querySelector('[data-field="val-rows"]'),
          pageInfo: page.querySelector('[data-field="page-info"]'),
          log: page.querySelector('[data-field="log"]'),
        },
        validators: [],
        sortKey: null,
        sortDir: 1,
        search: "",
        page: 0,
        filtered() {
          let v = this.validators;
          if (this.search) v = v.filter((x) => x.moniker.toLowerCase().includes(this.search));
          if (this.sortKey) {
            const k = this.sortKey, dir = this.sortDir;
            v = [...v].sort((a, b) => String(a[k]).localeCompare(String(b[k]), undefined, { numeric: true }) * dir);
          }
          return v;
        },
      };
    });

    // Remove tabs/pages for chains the server no longer reports (hidden).
    Object.keys(chains).forEach((id) => {
      if (!seen.has(id)) {
        chains[id].els.tab.remove();
        chains[id].els.page.remove();
        chains[id].els.star.remove();
        delete chains[id];
      }
    });

    emptyStateEl.classList.toggle("hidden", list.length > 0);

    if (!activeChainId || !chains[activeChainId]) {
      const first = list[0];
      if (first) activateChain(first.chain_id);
    }
  }

  // ── Rendering per status update ──────────────────────────────────────────

  function renderNode(st, d) {
    const ok = d.running;
    st.els.node.innerHTML = `
      <dt>Süreç</dt><dd class="${ok ? "ok" : "bad"}">${ok ? "✓ Çalışıyor (pid " + d.pid + ")" : "✗ Çalışmıyor"}</dd>
      <dt>RPC</dt><dd class="${ok ? "ok" : "bad"}">${ok ? "✓ Dinleniyor" : "✗ Kapalı"}</dd>
      <dt>Çalışma süresi</dt><dd>${fmtUptime(d.uptime_sec)}</dd>
      <dt>Bellek</dt><dd>${d.mem_pct.toFixed(2)}%</dd>
      <dt>Disk</dt><dd>${d.disk_pct.toFixed(2)}%</dd>
      <dt>Versiyon</dt><dd>${esc(d.version) || "—"}</dd>`;
  }

  function renderChain(st, d) {
    const syncing = d.syncing;
    st.els.chainBox.innerHTML = `
      <div class="sync-row">
        <span class="sync-label ${syncing ? "warn" : "ok"}">${syncing ? "■ Senkronize ediliyor" : "■ Senkron"}</span>
      </div>
      <div class="sync-row">
        <div class="bar-track"><div class="bar-fill ${syncing ? "syncing" : ""}" style="width:${Math.min(100, d.sync_pct)}%"></div></div>
        <span class="sync-meta">${d.sync_pct.toFixed(2)}%</span>
      </div>
      <div class="sync-meta">${Number(d.latest_block).toLocaleString("tr-TR")} blok</div>`;
  }

  function renderNetwork(st, d, cfg) {
    st.els.network.innerHTML = `
      <dt>Peer</dt><dd class="ok">${d.peers}</dd>
      <dt>Node ID</dt><dd class="dim" title="${esc(d.node_id)}">${esc((d.node_id || "—").slice(0, 16))}${d.node_id ? "…" : ""}</dd>
      <dt>Gecikme</dt><dd>${d.latency_ms}ms</dd>
      <dt>Zincir</dt><dd>${esc(d.chain_id || cfg.chain_id)}</dd>
      <dt>İsim</dt><dd>${esc(d.moniker || cfg.moniker || "—")}</dd>
      <dt>Portlar</dt><dd class="dim">RPC ${cfg.ports.rpc} · P2P ${cfg.ports.p2p} · REST ${cfg.ports.rest}</dd>`;
  }

  function renderMyVal(st, d, cfg) {
    const v = d.validator || {};
    const sc = statusClass(v.status);
    const hasRewards = (parseFloat(v.comm_rewards) > 0) || (parseFloat(v.outstanding) > 0);
    st.els.myval.innerHTML = `
      <dt>Moniker</dt><dd>${esc(v.moniker || d.moniker || "—")}${v.jailed ? ' <span class="bad">JAILED</span>' : ""}</dd>
      <dt>Durum</dt><dd class="${sc}">${esc(v.status || "—")}</dd>
      <dt>Güç</dt><dd>${esc(v.voting_power || "0")}</dd>
      <dt>Komisyon</dt><dd>${esc(v.commission || "0%")}</dd>
      <dt>Kom. Ödülü</dt><dd class="${hasRewards ? "warn" : ""}">${esc(v.comm_rewards || "0")} ${esc(cfg.denom)}</dd>
      <dt>Bekleyen</dt><dd class="${hasRewards ? "warn" : ""}">${esc(v.outstanding || "0")} ${esc(cfg.denom)}</dd>`;
  }

  function renderValTable(chainId) {
    const st = chains[chainId];
    if (!st) return;
    const all = st.filtered();
    const total = all.length;
    const maxPage = Math.max(0, Math.ceil(total / PAGE_SIZE) - 1);
    st.page = Math.min(st.page, maxPage);
    const slice = all.slice(st.page * PAGE_SIZE, st.page * PAGE_SIZE + PAGE_SIZE);
    const myMoniker = (st.lastStatus && st.lastStatus.validator && st.lastStatus.validator.moniker) || "";

    st.els.valCount.textContent = `AĞ VALİDATÖRLERİ (${total})`;
    st.els.pageInfo.textContent = total ? `sayfa ${st.page + 1} / ${maxPage + 1}` : "—";

    st.els.valRows.innerHTML = slice.map((v) => {
      const mine = myMoniker && v.moniker === myMoniker;
      const cr = v.comm_rewards && v.comm_rewards !== "—" && v.comm_rewards !== "0";
      const os = v.outstanding && v.outstanding !== "—" && v.outstanding !== "0";
      return `<tr class="${mine ? "is-mine" : ""}">
        <td>${mine ? "★ " : ""}${esc(v.moniker)}</td>
        <td class="${statusClass(v.status)}">${esc(v.status)}</td>
        <td>${esc(v.tokens)}</td>
        <td>${esc(v.commission)}</td>
        <td class="${cr ? "warn" : "dim"}">${esc(v.comm_rewards)}</td>
        <td class="${os ? "warn" : "dim"}">${esc(v.outstanding)}</td>
      </tr>`;
    }).join("") || `<tr><td colspan="6" class="dim">Validator listesi henüz alınamadı.</td></tr>`;
  }

  const LOG_PATTERNS = [
    [/(\b(?:\d{1,3}\.){3}\d{1,3}\b)/g, '<span class="log-ip">$1</span>'],
    [/(\b[0-9A-Fa-f]{40,64}\b)/g, '<span class="log-hash">$1</span>'],
    [/(module=[a-zA-Z0-9_-]+)/g, '<span class="log-mod">$1</span>'],
    [/(height=\d+)/g, '<span class="log-height">$1</span>'],
  ];

  function renderLogLine(line) {
    let cls = "log-line";
    if (/ INF /.test(line)) cls += " log-inf";
    else if (/ ERR(O)?\b/.test(line)) cls += " log-err";
    else if (/ WRN | WARN/.test(line)) cls += " log-wrn";
    let html = esc(line);
    for (const [re, rep] of LOG_PATTERNS) html = html.replace(re, rep);
    return `<div class="${cls}">${html}</div>`;
  }

  function renderLog(st, d) {
    const wasAtBottom = st.els.log.scrollTop + st.els.log.clientHeight >= st.els.log.scrollHeight - 12;
    if (!d.log_lines || !d.log_lines.length) {
      st.els.log.innerHTML = `<div class="log-empty">log bulunamadı.</div>`;
      return;
    }
    st.els.log.innerHTML = d.log_lines.map(renderLogLine).join("");
    if (wasAtBottom) st.els.log.scrollTop = st.els.log.scrollHeight;
  }

  function applyStatus(chainId, d) {
    const st = chains[chainId];
    if (!st) return;
    st.lastStatus = d;
    if (Array.isArray(d.validators) && d.validators.length) st.validators = d.validators;

    renderNode(st, d);
    renderChain(st, d);
    renderNetwork(st, d, st.cfg);
    renderMyVal(st, d, st.cfg);
    renderValTable(chainId);
    renderLog(st, d);

    st.els.star.dataset.running = String(!!d.running);
  }

  // ── WebSocket plumbing ───────────────────────────────────────────────────

  let ws = null;
  let backoff = 1000;

  function connect() {
    const proto = location.protocol === "https:" ? "wss" : "ws";
    ws = new WebSocket(`${proto}://${location.host}/ws`);

    ws.onopen = () => {
      connStatusEl.textContent = "bağlı";
      connStatusEl.className = "conn-status conn-connected";
      backoff = 1000;
    };

    ws.onmessage = (ev) => {
      let msg;
      try { msg = JSON.parse(ev.data); } catch { return; }
      if (msg.type === "chains") {
        syncChains(msg.data || []);
      } else if (msg.type === "status") {
        applyStatus(msg.chain_id, msg.data);
      }
    };

    ws.onclose = () => {
      connStatusEl.textContent = "bağlantı kesildi, yeniden bağlanılıyor…";
      connStatusEl.className = "conn-status conn-down";
      setTimeout(connect, backoff);
      backoff = Math.min(backoff * 1.6, 15000);
    };

    ws.onerror = () => ws.close();
  }

  // ── UI wiring ─────────────────────────────────────────────────────────

  $("#refreshBtn").addEventListener("click", () => {
    fetch("/api/refresh", { method: "POST" }).then(() => toast("Yenilendi"));
  });

  const dialog = $("#addNodeDialog");
  $("#addNodeBtn").addEventListener("click", () => {
    $("#homeInput").value = "";
    dialog.showModal();
    $("#homeInput").focus();
  });
  $("#cancelAddNode").addEventListener("click", () => dialog.close());
  $("#addNodeForm").addEventListener("submit", (ev) => {
    ev.preventDefault();
    const homeDir = $("#homeInput").value.trim();
    if (!homeDir) return;
    fetch("/api/nodes/add", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ home_dir: homeDir }),
    }).then((r) => r.json()).then(() => {
      dialog.close();
      toast("Node eklendi.");
    }).catch(() => toast("Eklenemedi — sunucu loglarına bak."));
  });

  document.addEventListener("keydown", (ev) => {
    const tag = (ev.target.tagName || "").toLowerCase();
    if (tag === "input" || tag === "textarea" || dialog.open) return;
    if (ev.key === "r") $("#refreshBtn").click();
    else if (ev.key === "a") $("#addNodeBtn").click();
    else if ((ev.key === "n" || ev.key === "p") && activeChainId) {
      const st = chains[activeChainId];
      const max = Math.max(0, Math.ceil(st.filtered().length / PAGE_SIZE) - 1);
      if (ev.key === "n" && st.page < max) st.page++;
      if (ev.key === "p" && st.page > 0) st.page--;
      renderValTable(activeChainId);
    }
  });

  connect();
})();
