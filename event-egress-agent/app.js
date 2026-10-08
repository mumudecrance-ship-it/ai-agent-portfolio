(() => {
  "use strict";

  const state = {
    project: null,
    mode: "fixed",
    liveConfig: null,
    currentDigest: null,
    currentScope: "fixed",
    exits: [],
    replayToken: 0,
    busy: false,
    confirmable: false,
  };
  const $ = (selector) => document.querySelector(selector);
  const $$ = (selector) => [...document.querySelectorAll(selector)];
  const directionLabels = {
    north: "北侧", northeast: "东北侧", east: "东侧", southeast: "东南侧",
    south: "南侧", southwest: "西南侧", west: "西侧", northwest: "西北侧",
  };
  const directionPositions = {
    north: [50, 10], northeast: [79, 21], east: [90, 50], southeast: [79, 79],
    south: [50, 90], southwest: [21, 79], west: [10, 50], northwest: [21, 21],
  };

  async function api(path, options = {}) {
    const response = await fetch(path, {
      cache: "no-store",
      headers: { "Content-Type": "application/json", ...(options.headers || {}) },
      ...options,
    });
    const payload = await response.json().catch(() => ({ ok: false, error: { code: "RESPONSE_INVALID", message: "本地服务返回无法解析。" } }));
    if (!response.ok || payload.ok === false) {
      const error = payload.error || { code: `HTTP_${response.status}`, message: "操作没有完成。" };
      const exception = new Error(error.message || String(error));
      exception.payload = error;
      throw exception;
    }
    return payload;
  }

  function escapeHtml(value) {
    return String(value).replace(/[&<>'"]/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;" }[char]));
  }

  function safeText(value) {
    if (value == null || value === "") return "—";
    if (typeof value === "boolean") return value ? "是" : "否";
    if (typeof value === "object") return JSON.stringify(value, null, 2);
    return String(value);
  }

  function toast(message, isError = false) {
    const node = $("#toast");
    node.textContent = message;
    node.className = isError ? "show error" : "show";
    clearTimeout(toast.timer);
    toast.timer = setTimeout(() => { node.className = ""; }, 4200);
  }

  function setStatus(status, reason = "") {
    const labels = {
      READY_TO_REPLAY: "可以开始固定回放",
      LIVE_READY: "可以开始我的推演",
      API_KEY_REQUIRED: "需要连接 API",
      FIXED_REPLAY_RUNNING: "正在回放固定方案",
      LIVE_API_RUNNING: "AI 正在整理变化",
      INPUT_REQUIRED: "需要补充输入",
      PENDING_HUMAN_CONFIRMATION: "等待本人确认",
      SIGNABLE_CANDIDATE: "候选可以进入确认",
      HUMAN_CONFIRMED: "本轮候选已确认",
      REPLAN_REQUIRED: "需要重新规划"
    };
    const node = $("#current-status");
    node.textContent = labels[status] || "本轮已停止";
    node.dataset.statusCode = status;
    node.title = `状态码：${status}`;
    $("#status-reason").textContent = reason;
  }

  function updateControls() {
    $$(".mode").forEach((button) => { button.disabled = state.busy; });
    $$("[data-outcome]").forEach((button) => { button.disabled = state.busy || state.mode !== "fixed"; });
    $("#run-live").disabled = state.busy || state.mode !== "live";
    const canConfirm = state.confirmable && !state.busy;
    $("#reviewer").disabled = !canConfirm;
    $("#reviewer").placeholder = canConfirm ? "填写姓名" : "先运行可确认候选";
    $("#confirm-form .confirm-button").disabled = !canConfirm;
  }

  function setBusy(busy) {
    state.busy = busy;
    updateControls();
  }

  function setConfirmable(decision, digest = null) {
    state.confirmable = decision === "PENDING_HUMAN_CONFIRMATION" && Boolean(digest);
    state.currentDigest = state.confirmable ? digest : null;
    updateControls();
  }

  function renderProject(project) {
    document.title = project.title;
    document.body.dataset.theme = project.theme;
    $("#product-name").textContent = project.title;
    $("#product-subtitle").textContent = project.product_line;
    $("#user-moment").textContent = project.user_moment;
    $("#mission-title").textContent = project.mission_title;
    $("#mission-copy").textContent = project.mission_copy;
    $("#case-kicker").textContent = project.fixed_case.case_id;
    $("#case-title").textContent = project.fixed_case.title;
    $("#case-summary").textContent = project.fixed_case.summary;
    $("#skill-name").textContent = project.skill.name;
    $("#gate-copy").textContent = project.human_gate.copy;
    $("#boundary-copy").textContent = project.boundaries.stop_at;
    $("#live-title").textContent = project.live.title;
    $("#live-description").textContent = project.live.description;
    renderAgents(project.agents);
    renderOutcomes(project.fixed_case.outcomes);
    renderVenueBlueprint($("#case-visual"), {
      name: project.fixed_case.title.replace(/\s*12,000\s*人散场$/, ""),
      audience_count: 12000,
      exits: project.visual.exits.map((item) => ({ ...item, capacity_per_tick: item.capacity })),
    }, false);
    loadDefaultVenue(project.live.default_venue);
    $("#event-description").value = project.live.default_event;
  }

  function renderAgents(agents) {
    $("#agent-list").innerHTML = agents.map((agent, index) => `
      <li data-index="${index + 1}"><strong>${escapeHtml(agent.name)}</strong><span>${escapeHtml(agent.task)}</span><span class="contract">读：${escapeHtml(agent.input)}<br>交：${escapeHtml(agent.output)}<br>停：${escapeHtml(agent.stop)}</span></li>
    `).join("");
  }

  function renderOutcomes(outcomes) {
    $("#outcome-controls").innerHTML = outcomes.map((item) => `
      <button class="outcome-button ${item.role === "target" ? "target" : ""}" type="button" data-outcome="${escapeHtml(item.id)}">
        <strong>${escapeHtml(item.label)}</strong><small>${escapeHtml(item.short)}</small>
      </button>
    `).join("");
  }

  function loadDefaultVenue(venue) {
    $("#venue-name").value = venue.name;
    $("#audience-count").value = venue.audience_count;
    $("#zone-notes").value = venue.zone_notes || "";
    state.exits = venue.exits.map((item) => ({ ...item }));
    renderExitRows();
  }

  function renderExitRows() {
    $("#exit-rows").innerHTML = state.exits.map((item) => `
      <div class="exit-row" data-exit="${escapeHtml(item.id)}">
        <span class="exit-id">${escapeHtml(item.id)}</span>
        <label>出口名称<input data-field="name" maxlength="40" value="${escapeHtml(item.name)}" required></label>
        <label>方位<select data-field="direction">${Object.entries(directionLabels).map(([value, label]) => `<option value="${value}" ${item.direction === value ? "selected" : ""}>${label}</option>`).join("")}</select></label>
        <label>每轮容量<input data-field="capacity_per_tick" type="number" min="20" max="20000" step="20" value="${Number(item.capacity_per_tick)}" required></label>
        <button class="remove-exit" type="button" aria-label="删除 ${escapeHtml(item.id)}" ${state.exits.length <= 2 ? "disabled" : ""}>删除</button>
      </div>
    `).join("");
    $("#exit-count").textContent = `${state.exits.length} / 8 个出口`;
    $("#add-exit").disabled = state.exits.length >= 8;
    updateLivePreview();
  }

  function syncExitState() {
    state.exits = $$(".exit-row").map((row) => ({
      id: row.dataset.exit,
      name: row.querySelector('[data-field="name"]').value.trim(),
      direction: row.querySelector('[data-field="direction"]').value,
      capacity_per_tick: Number(row.querySelector('[data-field="capacity_per_tick"]').value),
    }));
  }

  function addExit() {
    syncExitState();
    if (state.exits.length >= 8) return;
    const used = new Set(state.exits.map((item) => item.id));
    const number = Array.from({ length: 8 }, (_, index) => index + 1).find((item) => !used.has(`E${item}`));
    const directions = Object.keys(directionLabels);
    state.exits.push({ id: `E${number}`, name: `新出口 ${number}`, direction: directions[(number - 1) % directions.length], capacity_per_tick: 400 });
    renderExitRows();
    $("#exit-rows .exit-row:last-child input").focus();
  }

  function removeExit(button) {
    syncExitState();
    if (state.exits.length <= 2) {
      toast("至少保留 2 个出口。", true);
      return;
    }
    const id = button.closest(".exit-row").dataset.exit;
    state.exits = state.exits.filter((item) => item.id !== id);
    renderExitRows();
  }

  function collectVenueConfig() {
    syncExitState();
    const venue = {
      name: $("#venue-name").value.trim(),
      audience_count: Number($("#audience-count").value),
      zone_notes: $("#zone-notes").value.trim(),
      exits: state.exits.map((item) => ({ ...item })),
    };
    if (!venue.name) throw new Error("请填写场馆名称。");
    if (!Number.isInteger(venue.audience_count) || venue.audience_count < 100 || venue.audience_count > 200000) throw new Error("总人数需在 100—200,000 之间。");
    if (venue.exits.length < 2 || venue.exits.length > 8) throw new Error("请配置 2—8 个出口。");
    venue.exits.forEach((item) => {
      if (!item.name) throw new Error(`${item.id} 还没有出口名称。`);
      if (!Number.isInteger(item.capacity_per_tick) || item.capacity_per_tick < 20 || item.capacity_per_tick > 20000) throw new Error(`${item.id} 的每轮容量需在 20—20,000 之间。`);
    });
    const groupCount = Math.min(4, venue.exits.length);
    const basePeople = Math.floor(venue.audience_count / groupCount);
    const remainder = venue.audience_count % groupCount;
    venue.groups = Array.from({ length: groupCount }, (_, index) => ({
      id: `G${index + 1}`,
      name: `分区客群 ${index + 1}`,
      people: basePeople + (index < remainder ? 1 : 0),
      preferred_exit_ids: [venue.exits[index % venue.exits.length].id],
    }));
    return venue;
  }

  function updateLivePreview() {
    const venue = {
      name: $("#venue-name").value.trim() || "未命名场馆",
      audience_count: Number($("#audience-count").value) || 0,
      exits: state.exits,
    };
    renderVenueBlueprint($("#live-venue-preview"), venue, true);
  }

  function renderVenueBlueprint(target, venue, compact) {
    const exits = Array.isArray(venue.exits) ? venue.exits : [];
    const lines = exits.map((item, index) => {
      const [x, y] = directionPositions[item.direction] || directionPositions[Object.keys(directionPositions)[index % 8]];
      return `<line x1="50" y1="50" x2="${x}" y2="${y}" vector-effect="non-scaling-stroke"></line>`;
    }).join("");
    const markers = exits.map((item, index) => {
      const [x, y] = directionPositions[item.direction] || directionPositions[Object.keys(directionPositions)[index % 8]];
      return `<div class="blueprint-exit" style="--x:${x}%;--y:${y}%"><strong>${escapeHtml(item.id)}</strong><span>${escapeHtml(item.name)}</span><small>${Number(item.capacity_per_tick || item.capacity || 0).toLocaleString()} 人/轮</small></div>`;
    }).join("");
    target.className = `venue-blueprint${compact ? " compact" : ""}`;
    target.innerHTML = `
      <svg class="route-lines" viewBox="0 0 100 100" aria-hidden="true">${lines}</svg>
      <div class="venue-core"><span>${escapeHtml(venue.name || "场馆")}</span><strong>${Number(venue.audience_count || 0).toLocaleString()} 人</strong><small>12 轮 · 2 分钟/轮</small></div>
      ${markers}
    `;
  }

  function switchMode(mode) {
    if (state.busy) return;
    state.replayToken += 1;
    state.mode = mode;
    state.currentScope = mode;
    $$(".mode").forEach((button) => {
      const active = button.dataset.mode === mode;
      button.classList.toggle("active", active);
      button.setAttribute("aria-pressed", active ? "true" : "false");
    });
    $("#fixed-panel").classList.toggle("active", mode === "fixed");
    $("#live-panel").classList.toggle("active", mode === "live");
    $("#source-badge").textContent = mode === "fixed" ? "固定回归" : "API 实时";
    $("#source-badge").className = `source-badge ${mode}`;
    $("#case-kicker").textContent = mode === "fixed" ? state.project.fixed_case.case_id : "PERSONAL VENUE PROFILE";
    $("#case-title").textContent = mode === "fixed" ? state.project.fixed_case.title : state.project.live.title;
    $("#case-summary").textContent = mode === "fixed" ? state.project.fixed_case.summary : state.project.live.description;
    setConfirmable(null);
    resetFlow();
    setStatus(mode === "fixed" ? "READY_TO_REPLAY" : (state.liveConfig?.configured ? "LIVE_READY" : "API_KEY_REQUIRED"), mode === "fixed" ? "选择一种固定方案" : "配置场馆并描述事件");
  }

  function resetFlow() {
    $$("#flow-track li").forEach((node) => {
      node.dataset.state = "idle";
      node.querySelector("em").textContent = node.dataset.flow === "human" ? "未到达" : "待开始";
    });
    $("#flow-caption").textContent = "尚未运行；流程状态会按真实交接结果回放。";
  }

  function setFlow(flow, status, label) {
    const node = $(`#flow-track [data-flow="${flow}"]`);
    if (!node) return;
    node.dataset.state = status;
    node.querySelector("em").textContent = label;
  }

  function wait(ms) {
    return new Promise((resolve) => setTimeout(resolve, ms));
  }

  async function replayTrace(trace, token, mode) {
    const roleMap = { AGENT: "agent", SKILL: "skill", RULE: "rule", ENGINE: "engine", HUMAN: "human" };
    resetFlow();
    for (const item of trace || []) {
      if (token !== state.replayToken) return false;
      const flow = roleMap[item.role];
      if (!flow) continue;
      setFlow(flow, "active", "正在交接");
      $("#flow-caption").textContent = item.label;
      await wait(260);
      if (token !== state.replayToken) return false;
      setFlow(flow, flow === "human" ? "waiting" : "done", flow === "human" ? "等待确认" : "已交出");
    }
    $("#flow-caption").textContent = mode === "fixed" ? "固定数据已完成确定性回放；本轮没有调用模型。" : "真实 API 草案已通过本地规则，A/B/C 已由确定性引擎复算。";
    return true;
  }

  function summarizeValue(value) {
    if (Array.isArray(value)) return value.slice(0, 8).map((item) => typeof item === "object" ? JSON.stringify(item, null, 2) : safeText(item));
    if (value && typeof value === "object") return Object.entries(value).slice(0, 10).map(([key, child]) => `${key}: ${typeof child === "object" ? JSON.stringify(child, null, 2) : safeText(child)}`);
    return [safeText(value)];
  }

  function renderResult(target, result, metadata = null, title = "运行结果") {
    const decision = result.decision || result.status || "PENDING_HUMAN_CONFIRMATION";
    const summary = result.summary || result.reason || "结果已生成，等待查看。";
    const visibleKeys = ["changes", "local_intents", "findings", "rule_checks", "handoff_boundary"].filter((key) => key in result);
    target.className = "result-board";
    target.innerHTML = `
      <div class="result-lead"><div><h3>${escapeHtml(title)}</h3><p>${escapeHtml(summary)}</p></div><span class="decision">${escapeHtml(decision)}</span></div>
      <div class="result-sections">${visibleKeys.map((key) => {
        const lines = summarizeValue(result[key]);
        return `<section class="result-section"><h4>${({ changes: "AI 整理的变化", local_intents: "AI 提议的局部意图", findings: "主要发现", rule_checks: "规则门禁", handoff_boundary: "交付边界" })[key]}</h4><ul>${lines.map((line) => `<li><pre>${escapeHtml(line)}</pre></li>`).join("")}</ul></section>`;
      }).join("")}</div>
      ${metadata ? `<div class="metadata-line"><span>真实 API</span><span>${escapeHtml(metadata.provider)}</span><span>${escapeHtml(metadata.model)}</span><span>${escapeHtml(metadata.request_id)}</span><span>Key：${escapeHtml(metadata.key_persistence)}</span></div>` : `<div class="metadata-line"><span>固定回归</span><span>本轮不调用模型</span></div>`}
    `;
    if (window.ProjectUI?.afterResult) window.ProjectUI.afterResult(target, result, metadata);
    setStatus(decision, summary);
  }

  async function runFixed(mode) {
    const token = ++state.replayToken;
    setConfirmable(null);
    setBusy(true);
    resetFlow();
    setFlow("agent", "active", "准备固定输入");
    $("#flow-caption").textContent = "正在读取固定场馆与事件。";
    setStatus("FIXED_REPLAY_RUNNING", "同一份数据正在通过确定性引擎");
    $("#fixed-result").className = "result-board empty running";
    $("#fixed-result").innerHTML = "<p>Agent 意图、Skill 门禁、规则校验与 12 轮仿真正在回放…</p>";
    try {
      const payload = await api("/api/fixed/run", { method: "POST", body: JSON.stringify({ mode }) });
      const completed = await replayTrace(payload.result.agent_trace, token, "fixed");
      if (!completed) return;
      renderResult($("#fixed-result"), payload.result, null, payload.result.label);
      state.currentScope = "fixed";
      setConfirmable(payload.result.decision, payload.result.candidate_digest);
      toast("固定回归已完成，本轮没有调用模型。");
    } catch (error) {
      if (token === state.replayToken) handleError(error, $("#fixed-result"));
    } finally {
      if (token === state.replayToken) setBusy(false);
    }
  }

  function collectLiveInput() {
    const venue = collectVenueConfig();
    const eventDescription = $("#event-description").value.trim();
    if (eventDescription.length < 8) throw new Error("请用至少 8 个字描述本轮事件或明确说明‘无突发事件’。");
    const source = $("#event-source").value.trim();
    const modelInput = [
      "【场馆档案；只能引用其中的出口 ID】",
      JSON.stringify(venue, null, 2),
      "【自然语言事件】",
      eventDescription,
      "【来源或备注】",
      source || "未提供",
    ].join("\n\n");
    return { input: modelInput, venue_config: venue, event_description: eventDescription, source, images: [], allow_web_search: false };
  }

  async function runLive(event) {
    event.preventDefault();
    let payloadInput;
    try {
      payloadInput = collectLiveInput();
    } catch (error) {
      setStatus("INPUT_REQUIRED", error.message);
      toast(error.message, true);
      return;
    }
    const token = ++state.replayToken;
    const button = $("#run-live");
    setConfirmable(null);
    setBusy(true);
    button.textContent = "AI 正在整理变化…";
    resetFlow();
    setFlow("agent", "active", "等待真实 API");
    $("#flow-caption").textContent = "变化理解 Agent 正在处理当前场馆与事件；后续规则和仿真还未开始。";
    setStatus("LIVE_API_RUNNING", "正在调用已配置模型；失败时不会切回 Mock");
    $("#live-result").className = "result-board empty running";
    $("#live-result").innerHTML = "<p>真实 API 正在整理变化草案。只有 API 成功且草案通过规则后，确定性仿真才会返回。</p>";
    try {
      const payload = await api("/api/live/run", { method: "POST", body: JSON.stringify(payloadInput) });
      if (token !== state.replayToken) return;
      const completed = await replayTrace(payload.data.result.agent_trace, token, "live");
      if (!completed) return;
      renderResult($("#live-result"), payload.data.result, payload.data.metadata, "本轮个人推演候选");
      state.currentScope = "live";
      setConfirmable(payload.data.result.decision, payload.data.candidate_digest);
      toast("真实 API 草案与确定性仿真均已完成；当前仍待人工确认。");
    } catch (error) {
      if (token === state.replayToken) {
        setFlow("agent", "failed", "本轮已停止");
        $("#flow-caption").textContent = "真实 API 或本地规则拒绝了本轮；没有切回固定结果。";
        handleError(error, $("#live-result"));
      }
    } finally {
      if (token === state.replayToken) {
        setBusy(false);
        button.textContent = "整理变化并运行 A/B/C";
      }
    }
  }

  function handleError(error, target = null) {
    const details = error.payload || { code: "INPUT_INVALID", message: error.message, recovery: "检查输入后重试。" };
    setStatus(details.code, details.message);
    if (target) {
      target.className = "result-board error-board";
      target.innerHTML = `<div class="result-lead"><div><h3>本轮已停止</h3><p>${escapeHtml(details.message)}</p></div><span class="decision">${escapeHtml(details.code)}</span></div><div class="recovery-grid"><div><strong>怎样继续</strong><p>${escapeHtml(details.recovery || "检查输入后重试。")}</p></div><div><strong>数据边界</strong><p>没有切回固定案例，也没有沿用上一次成功结果。</p></div></div>`;
    }
    toast(`${details.code}：${details.message}`, true);
  }

  async function configure(event) {
    event.preventDefault();
    const message = $("#config-message");
    message.className = "config-message";
    message.textContent = "正在保存到本机进程内存…";
    try {
      const payload = await api("/api/live/configure", {
        method: "POST",
        body: JSON.stringify({ api_key: $("#api-key").value, model: $("#api-model").value, base_url: $("#api-base-url").value }),
      });
      state.liveConfig = payload.live_config;
      $("#api-key").value = "";
      updateConfigStatus();
      message.textContent = `已配置 ${state.liveConfig.provider} / ${state.liveConfig.model}，${state.liveConfig.key_mask} 只保存在进程内存。`;
      toast("API 配置已保存到本机进程内存。");
    } catch (error) {
      message.className = "config-message error";
      message.textContent = `${error.payload?.code || "ERROR"}：${error.message}`;
    }
  }

  function updateConfigStatus() {
    const chip = $("#api-status");
    if (state.liveConfig?.configured) {
      chip.textContent = `${state.liveConfig.model} · ${state.liveConfig.key_mask}`;
      chip.className = "api-chip ready";
    } else {
      chip.textContent = "未连接";
      chip.className = "api-chip";
    }
  }

  async function clearConfig() {
    try {
      const payload = await api("/api/live/clear-config", { method: "POST", body: "{}" });
      state.liveConfig = payload.live_config;
      updateConfigStatus();
      $("#config-message").textContent = "内存 Key 已清除；项目文件没有变化。";
      toast("内存 Key 已清除。");
    } catch (error) { handleError(error); }
  }

  async function confirm(event) {
    event.preventDefault();
    if (state.busy || !state.confirmable || !state.currentDigest) {
      toast("先运行并查看可以确认的最新候选。", true);
      return;
    }
    try {
      const payload = await api("/api/confirm", { method: "POST", body: JSON.stringify({ reviewer: $("#reviewer").value, scope: state.currentScope, expected_digest: state.currentDigest }) });
      setStatus(payload.confirmation.status, `${payload.confirmation.reviewer} 已确认；${payload.confirmation.next_boundary}`);
      setFlow("human", "done", "已本地确认");
      setConfirmable(null);
      toast(`${payload.confirmation.reviewer} 已完成本地人工确认。`);
    } catch (error) { handleError(error); }
  }

  async function reset() {
    state.replayToken += 1;
    const token = state.replayToken;
    setConfirmable(null);
    setBusy(true);
    $("#reset").disabled = true;
    try {
      await api("/api/reset", { method: "POST", body: JSON.stringify({ scope: state.mode }) });
      const target = state.mode === "fixed" ? $("#fixed-result") : $("#live-result");
      target.className = "result-board empty";
      target.innerHTML = `<p>${state.mode === "fixed" ? "固定回归已回到开场状态。" : "本轮实时结果与确认已清除；场馆输入仍保留。"}</p>`;
      $("#reviewer").value = "";
      $("#run-live").textContent = "整理变化并运行 A/B/C";
      resetFlow();
      setStatus(state.mode === "fixed" ? "READY_TO_REPLAY" : (state.liveConfig?.configured ? "LIVE_READY" : "API_KEY_REQUIRED"), "当前模式已复位");
      toast("复位完成，另一模式没有被修改。");
    } catch (error) { handleError(error); }
    finally {
      if (token === state.replayToken) {
        setBusy(false);
        $("#reset").disabled = false;
      }
    }
  }

  async function externalAction() {
    try { await api("/api/external-action", { method: "POST", body: "{}" }); }
    catch (error) { handleError(error); }
  }

  function bindEvents() {
    $$(".mode").forEach((button) => button.addEventListener("click", () => switchMode(button.dataset.mode)));
    $("#outcome-controls").addEventListener("click", (event) => { const button = event.target.closest("[data-outcome]"); if (button) runFixed(button.dataset.outcome); });
    $("#live-form").addEventListener("submit", runLive);
    $("#add-exit").addEventListener("click", addExit);
    $("#exit-rows").addEventListener("click", (event) => { const button = event.target.closest(".remove-exit"); if (button) removeExit(button); });
    $("#exit-rows").addEventListener("input", () => { syncExitState(); updateLivePreview(); });
    $("#exit-rows").addEventListener("change", () => { syncExitState(); updateLivePreview(); });
    $("#venue-name").addEventListener("input", updateLivePreview);
    $("#audience-count").addEventListener("input", updateLivePreview);
    $("#config-form").addEventListener("submit", configure);
    $("#clear-config").addEventListener("click", clearConfig);
    $("#open-config").addEventListener("click", () => $("#config-dialog").showModal());
    $("#close-config").addEventListener("click", () => $("#config-dialog").close());
    $("#confirm-form").addEventListener("submit", confirm);
    $("#reset").addEventListener("click", reset);
    $("#external-action").addEventListener("click", externalAction);
    $("#toggle-agents").addEventListener("click", () => {
      $(".agent-map").classList.toggle("expanded");
      const expanded = $(".agent-map").classList.contains("expanded");
      $("#toggle-agents").textContent = expanded ? "收起输入输出" : "展开输入输出";
      $("#toggle-agents").setAttribute("aria-expanded", expanded ? "true" : "false");
    });
  }

  async function init() {
    try {
      const payload = await api("/api/bootstrap");
      state.project = payload.project;
      state.liveConfig = payload.live_config;
      renderProject(state.project);
      updateConfigStatus();
      bindEvents();
      resetFlow();
      setStatus("READY_TO_REPLAY", "选择一种固定方案开始");
      updateControls();
    } catch (error) { handleError(error); }
  }

  init();
})();
