(() => {
  "use strict";

  const escapeHtml = (value) => String(value ?? "—").replace(/[&<>'"]/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;" }[char]));
  const metric = (value, digits = 0) => Number.isFinite(Number(value)) ? Number(value).toLocaleString("zh-CN", { maximumFractionDigits: digits }) : "—";
  const labels = {
    north: "北", northeast: "东北", east: "东", southeast: "东南",
    south: "南", southwest: "西南", west: "西", northwest: "西北",
  };

  function candidateRows(candidates, recommended) {
    if (!Array.isArray(candidates) || !candidates.length) return "";
    return `
      <section class="candidate-comparison" aria-labelledby="candidate-title">
        <div class="sim-section-heading"><div><h4 id="candidate-title">A/B/C 同输入比较</h4><p>候选共用同一场馆、事件和 Skill 门禁。</p></div><span>推荐候选：${escapeHtml(recommended || "暂无")}</span></div>
        <div class="candidate-table" role="table" aria-label="三个候选方案指标">
          <div class="candidate-row candidate-head" role="row"><span>候选</span><span>仿真完成</span><span>用时</span><span>峰值队列比</span><span>溢出轮次</span><span>结果</span></div>
          ${candidates.map((item) => {
            const metrics = item.metrics || {};
            const id = item.candidate || "—";
            return `<div class="candidate-row ${id === recommended ? "recommended" : ""}" role="row">
              <span><b>${escapeHtml(id)}</b><small>${escapeHtml(item.name || "候选方案")}</small></span>
              <span>${metric(metrics.completed_people)} 人</span>
              <span>${metric(metrics.clearance_minutes)} 分钟</span>
              <span>${metric(metrics.max_queue_density_ratio ?? metrics.max_queue_density, 3)}</span>
              <span>${metric(metrics.overflow_ticks ?? metrics.overflow_events)} 轮</span>
              <span><em>${escapeHtml(item.decision)}</em></span>
            </div>`;
          }).join("")}
        </div>
      </section>`;
  }

  function buildExitMap(exits) {
    const lines = exits.map((item) => `<line x1="50" y1="50" x2="${Number(item.x) || 50}" y2="${Number(item.y) || 50}" vector-effect="non-scaling-stroke"></line>`).join("");
    const markers = exits.map((item) => `<div class="sim-exit" data-exit="${escapeHtml(item.id)}" style="--x:${Number(item.x) || 50}%;--y:${Number(item.y) || 50}%"><strong>${escapeHtml(item.id)}</strong><span>${escapeHtml(labels[item.direction] || item.direction || "")}</span><i></i></div>`).join("");
    return `<div class="sim-map" aria-label="当前轮次出口队列"><svg viewBox="0 0 100 100" aria-hidden="true">${lines}</svg><div class="sim-core"><strong>单写者</strong><span>World Simulator</span></div>${markers}</div>`;
  }

  function buildTickButtons(trace) {
    return trace.map((row, index) => {
      const hasEvent = Array.isArray(row.active_events) && row.active_events.length > 0;
      return `<button type="button" class="tick" data-index="${index}" aria-label="查看第 ${row.tick} 轮" aria-pressed="false"><b>${row.tick}</b><small>${hasEvent ? "事件" : "结算"}</small></button>`;
    }).join("");
  }

  function addTickInteraction(board, trace, exits) {
    const exitById = Object.fromEntries(exits.map((item) => [item.id, item]));
    const renderTick = (index) => {
      const row = trace[index];
      if (!row) return;
      board.querySelectorAll(".tick").forEach((button, buttonIndex) => {
        button.classList.toggle("active", buttonIndex === index);
        button.setAttribute("aria-pressed", buttonIndex === index ? "true" : "false");
        button.classList.toggle("passed", buttonIndex < index);
      });
      board.querySelector("[data-tick-label]").textContent = `第 ${row.tick} 轮 · ${row.minute} 分钟`;
      board.querySelector("[data-tick-events]").textContent = row.active_events?.length ? row.active_events.join(" + ") : "本轮无新的容量事件";
      board.querySelector("[data-completed]").textContent = `${metric(row.completed)} 人`;
      board.querySelector("[data-remaining]").textContent = `${metric(row.remaining)} 人`;
      const queues = row.queue || {};
      const densities = row.density || {};
      board.querySelector(".queue-ledger").innerHTML = exits.map((item) => {
        const queue = Number(queues[item.id] || 0);
        const density = Number(densities[item.id] || 0);
        const width = Math.min(100, density * 100);
        return `<div class="queue-row"><span><b>${escapeHtml(item.id)}</b>${escapeHtml(item.name)}</span><i><u style="width:${width}%"></u></i><strong>${metric(queue)} 人 <small>${metric(density, 3)}</small></strong></div>`;
      }).join("");
      board.querySelectorAll(".sim-exit").forEach((node) => {
        const exit = exitById[node.dataset.exit] || {};
        const density = Number(densities[node.dataset.exit] || 0);
        node.dataset.pressure = density >= 1 ? "overflow" : density >= 0.72 ? "busy" : "normal";
        node.querySelector("i").style.setProperty("--pressure", String(Math.max(.16, Math.min(1, density))));
        node.title = `${exit.name || node.dataset.exit}：队列 ${metric(queues[node.dataset.exit] || 0)} 人，密度比 ${metric(density, 3)}`;
      });
      const targets = Object.entries(row.targets || {});
      board.querySelector(".intent-stream").innerHTML = targets.map(([group, target]) => `<span><b>${escapeHtml(group)}</b><i></i><strong>${escapeHtml(target)}</strong></span>`).join("");
    };
    board.querySelector(".tick-track").addEventListener("click", (event) => {
      const button = event.target.closest(".tick");
      if (button) renderTick(Number(button.dataset.index));
    });
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      renderTick(trace.length - 1);
      return;
    }
    let cursor = 0;
    renderTick(0);
    const timer = setInterval(() => {
      cursor += 1;
      if (cursor >= trace.length) {
        clearInterval(timer);
        return;
      }
      renderTick(cursor);
    }, 210);
  }

  window.ProjectUI = {
    afterResult(target, result, metadata) {
      target.querySelector(".simulation-board")?.remove();
      const computed = result.computed || {};
      const trace = computed.trace || result.recommended_trace || [];
      const metrics = computed.metrics || result.metrics || {};
      const venue = result.venue_profile || {};
      const exits = Array.isArray(venue.exits) ? venue.exits : [];
      const candidates = result.candidate_results || [];
      const board = document.createElement("section");
      board.className = "simulation-board";
      if (!trace.length || !exits.length) {
        board.innerHTML = `<p class="board-empty">本轮没有可回放的仿真轨迹。</p>`;
        target.querySelector(".result-sections")?.before(board);
        return;
      }
      const sourceLabel = metadata ? "真实 API 草案 + 本地确定性引擎" : "固定回归 + 本地确定性引擎";
      board.innerHTML = `
        <div class="sim-header">
          <div><h3>12 轮队列传播回放</h3><p>${sourceLabel}；客群 Agent 只写意图，World Simulator 是唯一状态写入者。</p></div>
          <span class="proof-chip">evidence ${escapeHtml(String(result.evidence_digest || computed.evidence_digest || "").slice(0, 10))}</span>
        </div>
        <div class="sim-metrics" aria-label="推荐候选指标">
          <div><span>仿真完成</span><strong>${metric(metrics.completed_people)} 人</strong></div>
          <div><span>清空用时</span><strong>${metric(metrics.clearance_minutes)} 分钟</strong></div>
          <div><span>峰值队列比</span><strong>${metric(metrics.max_queue_density_ratio ?? metrics.max_queue_density, 3)}</strong></div>
          <div><span>局部重规划</span><strong>${metric(metrics.local_replans)} 次</strong></div>
        </div>
        ${candidateRows(candidates, result.recommended_candidate || (result.id === "target" ? "B" : null))}
        <section class="tick-explorer" aria-labelledby="tick-title">
          <div class="sim-section-heading"><div><h4 id="tick-title">仿真轮次</h4><p>点击任意一轮，查看出口队列和客群流向。</p></div><span data-tick-label>第 1 轮</span></div>
          <div class="tick-track">${buildTickButtons(trace)}</div>
          <div class="tick-stage">
            <div class="map-and-intents">${buildExitMap(exits)}<div class="intent-stream" aria-label="客群 Agent 当前意图"></div></div>
            <div class="tick-evidence">
              <div class="event-line"><span>当前事件</span><strong data-tick-events>—</strong></div>
              <div class="progress-pair"><div><span>已完成</span><strong data-completed>—</strong></div><div><span>剩余</span><strong data-remaining>—</strong></div></div>
              <div class="queue-ledger"></div>
            </div>
          </div>
        </section>
        <div class="simulation-boundary"><strong>这是仿真候选，不是现实安全承诺。</strong><span>系统没有读取现实轨迹，也不会执行封路、运力调度、闸机控制或公众引导。</span></div>
      `;
      target.querySelector(".result-sections")?.before(board);
      addTickInteraction(board, trace, exits);
    },
  };
})();
