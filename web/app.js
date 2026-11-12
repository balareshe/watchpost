// Copyright (C) 2026 balareshe（摆烂人生） <https://github.com/balareshe/vigil-status>. All rights reserved.
// Licensed under the Vigil Non-Commercial Source License 1.0 (see LICENSE).
// 本项目禁止商业使用；分发须保留本声明与授权协议，并署名 Vigil。
/* 站点状态页前端
 * 数据来源：
 *   GET /api/v1/endpoints/statuses            最近探测结果（当前状态 / 延迟 / 详情表）
 *   GET /api/v1/endpoints/{key}/uptimes/30d   30 天可用率（0~1）
 *   GET /data/status.json                     采集器导出：每日可用率 / 按组件每日可用率 / 事故记录 / 24h×96 格
 * 安全：只渲染组件名称，不读取也不展示任何 URL / 主机名。
 */
(function () {
  "use strict";

  // 组件顺序由后台「节点」页配置的 order 决定
  function orderIndexOf(name) {
    var o = STORE.nodeOrder && STORE.nodeOrder[name];
    return o == null ? 9999 : o;
  }
  var BARS = 96;
  var REFRESH_MS = 30000;
  var DATA_V = "4";
  var DETAIL_ROWS = 5;

  var listEl = document.getElementById("list");
  var headEl = document.getElementById("headline");
  var subEl = document.getElementById("subline");
  var updEl = document.getElementById("updated");
  var calEl = document.getElementById("calendar");
  var calMonthEl = document.getElementById("calMonth");
  var incEl = document.getElementById("incidents");

  var expanded = {};
  var onlyFail = {};
  var resultCache = {};
  var STORE = { days: {}, dayEnds: {}, incidents: [], manual: [], demo: false, slowMs: 800, slowStreak: 3, nodeSlow: {} };
  var STATUS_LABEL = { investigating: "排查中", identified: "已定位", in_progress: "修复中", monitoring: "监控中", resolved: "已恢复" };
  var SEVERITY_LABEL = { critical: "重大", major: "严重", minor: "一般", info: "提示", maintenance: "维护", down: "重大", warn: "一般" };

  function severityClass(sev) {
    if (sev === "critical" || sev === "major" || sev === "down") return "down";
    if (sev === "maintenance") return "maint";
    if (sev === "info") return "info";
    return "warn";
  }
  var selectedDay = null;

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  function getJSON(url) {
    return fetch(url, { cache: "no-store" }).then(function (r) {
      if (!r.ok) throw new Error("HTTP " + r.status);
      return r.json();
    });
  }

  function getText(url) {
    return fetch(url, { cache: "no-store" }).then(function (r) {
      if (!r.ok) throw new Error("HTTP " + r.status);
      return r.text();
    });
  }

  function seriesBars(series) {
    if (!series || !series.length) return null;
    var out = [];
    for (var i = 0; i < BARS; i++) {
      var cell = series[i];
      out.push(cell && cell.total ? cell : null);
    }
    return out;
  }

  function fallbackBars(results, now) {
    var bars = [];
    for (var i = 0; i < BARS; i++) bars.push(null);
    var asc = (results || []).slice().sort(function (a, b) {
      return new Date(a.timestamp) - new Date(b.timestamp);
    });
    if (!asc.length) return bars;
    var start = now - 24 * 3600e3;
    var step = (24 * 3600e3) / BARS;
    for (var j = 0; j < asc.length; j++) {
      var t = new Date(asc[j].timestamp).getTime();
      var idx = Math.floor((t - start) / step);
      if (idx < 0) continue;
      if (idx >= BARS) idx = BARS - 1;
      var cell = bars[idx] || { ok: 0, total: 0 };
      cell.total++;
      if (asc[j].success) cell.ok++;
      bars[idx] = cell;
    }
    return bars;
  }

  function barClass(cell) {
    if (!cell) return "";
    var ratio = cell.ok / cell.total;
    if (ratio >= 1) return "up";
    if (ratio >= 0.9) return "soft";
    if (ratio >= 0.5) return "warn";
    return "down";
  }

  function uptimeClass(ratio) {
    if (ratio == null) return "";
    if (ratio >= 0.999) return "good";
    if (ratio >= 0.99) return "mid";
    return "bad";
  }

  function fmtUptime(ratio) {
    if (ratio == null) return "—";
    return (ratio * 100).toFixed(2) + "%";
  }

  function fmtMs(ns) {
    if (ns == null) return "—";
    var ms = ns / 1e6;
    if (ms < 10) return ms.toFixed(1) + " ms";
    return Math.round(ms) + " ms";
  }

  function fmtDuration(sec) {
    if (sec == null) return "—";
    if (sec < 60) return sec + " 秒";
    var m = Math.floor(sec / 60);
    if (m < 60) return m + " 分钟";
    var h = Math.floor(m / 60);
    return h + " 小时 " + String(m % 60).padStart(2, "0") + " 分";
  }

    // 日历配色按「当天出现过什么级别的问题」：
    // 红色级事件 → 红；只有黄色级（慢响应等）→ 黄；无异常 → 绿；无数据 → 灰
    function dayState(dateKey) {
      var bucket = STORE.days[dateKey];
      var incs = incidentsOn(dateKey);
      if (!incs.length && (!bucket || !bucket.total)) return "none";
      var level = "up";
      incs.forEach(function (inc) {
        var cls = severityClass(inc.severity);
        if (cls === "down") level = "down";
        else if ((cls === "warn" || cls === "maint") && level !== "down") level = "warn";
      });
      return level;
    }

  function sortEndpoints(eps) {
    var idx = function (n) {
      var i = orderIndexOf(n);
      return i === -1 ? 999 : i;
    };
    return eps.slice().sort(function (a, b) {
      var d = idx(a.name) - idx(b.name);
      return d !== 0 ? d : String(a.name).localeCompare(String(b.name), "zh");
    });
  }

  // ---------------- 组件行 ----------------

  function sparkline(results) {
    var chrono = (results || []).slice().reverse();
    var pts = chrono.map(function (r) { return (r.duration || 0) / 1e6; });
    if (pts.length < 2) return "";

    var w = 560, h = 56, pad = 4;
    var max = Math.max.apply(null, pts);
    var min = Math.min.apply(null, pts);
    var span = Math.max(max - min, 1);

    var path = pts.map(function (v, i) {
      var x = pad + (i * (w - pad * 2)) / (pts.length - 1);
      var y = h - pad - ((v - min) / span) * (h - pad * 2);
      return (i ? "L" : "M") + x.toFixed(1) + " " + y.toFixed(1);
    }).join(" ");

    return '<div class="spark-wrap">' +
      '<svg class="spark" viewBox="0 0 ' + w + ' ' + h + '" preserveAspectRatio="none" aria-label="延迟曲线">' +
        '<path d="' + path + '" fill="none" stroke="#22c55e" stroke-width="1.6" stroke-linejoin="round" stroke-linecap="round"/>' +
      '</svg>' +
      '<span class="spark-meta">延迟 ' + Math.round(min) + '–' + Math.round(max) + ' ms</span>' +
    '</div>';
  }

  function detailTable(name) {
    var all = resultCache[name] || [];
    var list = onlyFail[name] ? all.filter(function (r) { return !r.success; }) : all;
    list = list.slice(-DETAIL_ROWS).reverse();

    var total = all.length;
    var okCount = all.filter(function (r) { return r.success; }).length;
    var failCount = total - okCount;

    var tools = '<div class="detail-tools">' +
      '<span class="detail-meta">共 ' + total + ' 次探测：成功 ' + okCount + ' / 失败 ' + failCount +
        '（下表展示最近 ' + Math.min(total, DETAIL_ROWS) + ' 条）</span>' +
      '<button class="only-fail' + (onlyFail[name] ? " active" : "") + '" type="button">只看失败</button>' +
    '</div>';

    if (!list.length) {
      return tools + '<p class="empty">' +
        (onlyFail[name] ? "这段时间没有失败记录" : "暂无探测记录") + '</p>';
    }

    var rows = list.map(function (r) {
      var t = new Date(r.timestamp).toLocaleTimeString("zh-CN", { hour12: false });
      var status = r.status != null && r.status !== 0 ? r.status : "—";
      var reasons = (!r.success && r.errors && r.errors.length) ? r.errors.join("；") : "";
      return '<tr>' +
        '<td>' + esc(t) + '</td>' +
        '<td class="' + (r.success ? "c-ok" : "c-bad") + '">' + (r.success ? "成功" : "失败") + '</td>' +
        '<td>' + esc(fmtMs(r.duration)) + '</td>' +
        '<td>' + esc(status) + '</td>' +
        '<td class="c-reason">' + (reasons ? esc(reasons) : "") + '</td>' +
      '</tr>';
    }).join("");

    return tools + sparkline(all) +
      '<table class="detail-table">' +
        '<thead><tr><th>时间</th><th>结果</th><th>延迟</th><th>状态</th><th>失败原因</th></tr></thead>' +
        '<tbody>' + rows + '</tbody></table>';
  }

  function renderRows(rows, now) {
    var down = 0, warn = 0;
    rows.forEach(function (r) {
      if (r.state === "down") down++;
      else if (r.state === "warn") warn++;
    });
    if (down) {
      headEl.textContent = "部分服务异常";
      headEl.className = "bad";
      subEl.textContent = down + " 项服务不可用，正在持续探测";
    } else if (warn) {
      headEl.textContent = "部分服务响应较慢";
      headEl.className = "";
      subEl.textContent = "所有服务均按预期运行";
    } else {
      headEl.textContent = "一切运行正常";
      headEl.className = "ok";
      subEl.textContent = "所有服务均按预期运行";
    }

    listEl.innerHTML = rows.map(function (r) {
      var bars = r.bars.map(function (cell) {
        return '<i class="bar ' + barClass(cell) + '"></i>';
      }).join("");

      var isOpen = !!expanded[r.name];
      var lat = r.latency != null

        ? '<span class="lat' + (r.slow ? " slow" : "") + '">~' + r.latency + ' ms</span>'

        : "";

      return '<section class="row' + (isOpen ? " open" : "") + '" data-name="' + esc(r.name) + '">' +
        '<div class="row-head">' +
          '<span class="dot ' + r.state + '"></span>' +
          '<span class="name">' + esc(r.name) + '</span>' +
          lat +
          '<span class="uptime ' + uptimeClass(r.uptime) + '"><b>' + fmtUptime(r.uptime) + '</b><span class="uptime-label"> 可用性</span></span>' +
          '<button class="more" type="button" aria-expanded="' + (isOpen ? "true" : "false") + '">' +
            (isOpen ? "收起" : "详情") + '</button>' +
        '</div>' +
        '<div class="bars">' + bars + '</div>' +
        '<div class="detail"' + (isOpen ? "" : " hidden") + '>' + detailTable(r.name) + '</div>' +
      '</section>';
    }).join("");

    updEl.textContent = "更新于 " + new Date(now).toLocaleTimeString("zh-CN", { hour12: false });
  }

  // ---------------- 事件日历 ----------------

  var calPop = null;

  function ensurePop() {
    if (calPop) return calPop;
    calPop = document.createElement("div");
    calPop.className = "cal-pop";
    calPop.setAttribute("hidden", "");
    document.body.appendChild(calPop);
    return calPop;
  }

  // 工单（后台创建）→ 列表展示用的统一结构
  function manualAsIncident(inc) {
    var start = new Date(inc.startedAt).getTime();
    var end = inc.resolvedAt ? new Date(inc.resolvedAt).getTime() : null;
    return {
      id: inc.id,
      title: inc.title,
      start: inc.startedAt,
      end: inc.resolvedAt,
      severity: inc.severity,
      endpoints: inc.affected || [],
      ongoing: !inc.resolvedAt,
      status: inc.status,
      durationSec: Math.max(0, Math.round(((end || Date.now()) - start) / 1000))
    };
  }

  function allIncidents() {
    var manual = (STORE.manual || []).map(manualAsIncident);
    var auto = (STORE.incidents || []).filter(function (i) { return !i.id || String(i.id).indexOf("demo") !== 0; });
    return manual.concat(auto).sort(function (a, b) {
      return new Date(b.start) - new Date(a.start);
    });
  }

  function incidentsOn(dateKey) {
    var start = new Date(dateKey + "T00:00:00").getTime();
    var end = start + 86400000;
    return allIncidents().filter(function (inc) {
      var s = new Date(inc.start).getTime();
      var e = inc.end ? new Date(inc.end).getTime() : Date.now();
      return s < end && e > start;
    });
  }

  function daySummary(dateKey) {
    var bucket = STORE.days[dateKey];
    var ends = STORE.dayEnds[dateKey] || {};
    var incs = incidentsOn(dateKey);
    return { bucket: bucket, ends: ends, incs: incs };
  }

  function incTimeRange(inc) {
    var st = new Date(inc.start);
    var en = inc.end ? new Date(inc.end) : null;
    var f = function (d) {
      return d.toLocaleTimeString("zh-CN", { hour12: false, hour: "2-digit", minute: "2-digit" });
    };
    return f(st) + (en ? "–" + f(en) : " 起");
  }

  function popContent(dateKey) {
    var s = daySummary(dateKey);
    var label = dateKey.slice(5).replace("-", " 月 ") + " 日";
    var ratio = s.bucket && s.bucket.total ? s.bucket.up / s.bucket.total : null;

    var html = '<div class="cal-pop-title">' + esc(label) + '</div>';
    html += '<div class="cal-pop-line">可用率 <b>' + (ratio == null ? "无数据" : fmtUptime(ratio)) + '</b>';
    if (s.bucket && s.bucket.total) html += "（" + s.bucket.up + "/" + s.bucket.total + "）";
    html += '</div>';

    if (!s.incs.length) {
      html += '<div class="cal-pop-line">当天没有异常</div>';
    } else {
      html += '<div class="cal-pop-line">' + s.incs.length + ' 起异常</div>';
      s.incs.slice(0, 3).forEach(function (inc) {
        var names = (inc.endpoints || []).join("、") || "未知";
        html += '<div class="cal-pop-inc ' + (severityClass(inc.severity) === "down" ? "bad" : (severityClass(inc.severity) === "maint" ? "maint" : "")) + '">' +
          '<i></i><span>' + esc(incTimeRange(inc)) + '</span>' + esc(names) + '</div>';
      });
      if (s.incs.length > 3) {
        html += '<div class="cal-pop-more">还有 ' + (s.incs.length - 3) + ' 起…</div>';
      }
    }

    html += '<div class="cal-pop-hint">点击查看当天明细</div>';
    return html;
  }

  function showPop(cell, dateKey) {
    var pop = ensurePop();
    pop.innerHTML = popContent(dateKey);
    pop.removeAttribute("hidden");

    var r = cell.getBoundingClientRect();
    var pw = pop.offsetWidth, ph = pop.offsetHeight;
    var left = Math.min(Math.max(8, r.left + r.width / 2 - pw / 2), window.innerWidth - pw - 8);
    var top = r.top - ph - 8;
    if (top < 8) top = r.bottom + 8;
    pop.style.left = left + "px";
    pop.style.top = top + "px";
  }

  function hidePop() {
    if (calPop) calPop.setAttribute("hidden", "");
  }

  function renderDayDetail(dateKey) {
    var s = daySummary(dateKey);
    var label = dateKey.slice(5).replace("-", " 月 ") + " 日";
    var ratio = s.bucket && s.bucket.total ? s.bucket.up / s.bucket.total : null;

    var rows = Object.keys(s.ends).sort(function (a, b) {
      var i = orderIndexOf(a), j = orderIndexOf(b);
      return (i === -1 ? 999 : i) - (j === -1 ? 999 : j);
    }).map(function (name) {
      var e = s.ends[name];
      var r = e.total ? e.up / e.total : 0;
      return '<tr><td>' + esc(name) + '</td>' +
        '<td class="' + (r >= 0.995 ? "c-ok" : (r >= 0.98 ? "" : "c-bad")) + '">' +
          (e.total ? fmtUptime(r) : "—") + '</td>' +
        '<td>' + e.up + ' / ' + e.total + '</td></tr>';
    }).join("");

    var incHtml = s.incs.length
      ? s.incs.map(function (inc) {
          var st = new Date(inc.start).toLocaleTimeString("zh-CN", { hour12: false });
          var en = inc.end ? new Date(inc.end).toLocaleTimeString("zh-CN", { hour12: false }) : "进行中";
          return '<div class="inc ' + inc.severity + '"><i class="inc-dot"></i><div class="inc-main">' +
            '<div class="inc-title">' + esc((inc.endpoints || []).join("、") || "未知服务") + '</div>' +
            '<div class="inc-meta">' + esc(st + " — " + en) + ' · 持续 ' + fmtDuration(inc.durationSec) + '</div>' +
          '</div></div>';
        }).join("")
      : '<p class="empty">当天没有异常记录</p>';

    return '<div class="cal-detail-head">' + esc(label) +
        '　可用率 <b class="' + (ratio != null && ratio < 0.995 ? "c-bad" : "") + '">' +
        (ratio == null ? "无数据" : fmtUptime(ratio)) + '</b>' +
        (s.bucket && s.bucket.total ? '（' + s.bucket.up + '/' + s.bucket.total + '）' : '') +
      '</div>' +
      (rows ? '<table class="detail-table cal-table"><thead><tr><th>组件</th><th>可用率</th><th>成功/总次数</th></tr></thead><tbody>' + rows + '</tbody></table>' : '') +
      '<div class="cal-detail-inc">' + incHtml + '</div>';
  }

  function renderCalendar() {
    var now = new Date();
    var today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
    var dow = (today.getDay() + 6) % 7;
    var thisMonday = new Date(today.getTime() - dow * 86400000);
    var start = new Date(thisMonday.getTime() - 21 * 86400000);

    function key(d) {
      return d.getFullYear() + "-" + String(d.getMonth() + 1).padStart(2, "0") + "-" + String(d.getDate()).padStart(2, "0");
    }

    calMonthEl.textContent = (start.getMonth() + 1) + " 月 " + start.getDate() + " 日 – " +
      (today.getMonth() + 1) + " 月 " + today.getDate() + " 日";

    var heads = ["一", "二", "三", "四", "五", "六", "日"]
      .map(function (d) { return '<div class="cal-head">' + d + '</div>'; }).join("");

    var cells = "";
    for (var i = 0; i < 28; i++) {
      var d = new Date(start.getTime() + i * 86400000);
      if (d.getTime() > today.getTime()) {
        cells += '<div class="cal-cell empty"></div>';
        continue;
      }
      var k = key(d);
      var state = dayState(k);
      var sel = selectedDay === k ? " selected" : "";
      var hasInc = incidentsOn(k).length ? " has-inc" : "";
      cells += '<div class="cal-cell ' + state + sel + hasInc + '" data-date="' + k + '" tabindex="0"><span>' +
        d.getDate() + '</span></div>';
    }

    calEl.innerHTML = '<div class="cal-grid">' + heads + cells + '</div>';

    var detail = document.getElementById("calDetail");
    if (detail) {
      if (selectedDay) {
        detail.innerHTML = renderDayDetail(selectedDay);
        detail.removeAttribute("hidden");
      } else {
        detail.innerHTML = "";
        detail.setAttribute("hidden", "");
      }
    }
  }

  // ---------------- 最近事件 ----------------

  var INC_LIMIT = 5;
  var incExpanded = false;

  function incCard(inc) {
    var href = inc.id ? "/incident.html?id=" + encodeURIComponent(inc.id) : "";
    var start = new Date(inc.start);
    var end = inc.end ? new Date(inc.end) : null;
    var dateLabel = String(start.getMonth() + 1).padStart(2, "0") + "-" + String(start.getDate()).padStart(2, "0");
    var startT = start.toLocaleTimeString("zh-CN", { hour12: false, hour: "2-digit", minute: "2-digit" });
    var endT = end ? end.toLocaleTimeString("zh-CN", { hour12: false, hour: "2-digit", minute: "2-digit" }) : "进行中";
    var names = inc.endpoints && inc.endpoints.length ? inc.endpoints.join("、") : "未知服务";

    return '<div class="inc ' + severityClass(inc.severity) + '"' +
      (href ? ' data-href="' + href + '"' : '') + '>' +
      '<div class="inc-date">' + esc(dateLabel) + '</div>' +
      '<i class="inc-dot"></i>' +
      '<div class="inc-main">' +
        '<div class="inc-title">' + esc(inc.title || names) + ' <span class="sev-tag ' + severityClass(inc.severity) + '">' + (SEVERITY_LABEL[inc.severity] || "一般") + '</span>' + (inc.ongoing ? ' <b>处理中</b>' : '') + '</div>' +
        '<div class="inc-meta">' + esc(startT + " — " + endT) + ' · 持续 ' + fmtDuration(inc.durationSec) + '</div>' +
      '</div>' +
    '</div>';
  }

  function renderBanner(list) {
    var box = document.getElementById("banner");
    if (!box) return;
    // 横幅只提示「红色级」问题；慢响应只进事件列表，不弹横幅
    var active = (list || []).filter(function (i) {
      return i.status && i.status !== "resolved" && severityClass(i.severity) === "down";
    });
    if (!active.length) { box.style.display = "none"; box.innerHTML = ""; return; }
    var top = active[0];
    var names = (top.affected || []).join("、") || "部分服务";
    box.style.display = "block";
    box.innerHTML = '<span class="banner-dot"></span>' +
      '<b>' + esc(names) + '</b> 出现异常' +
      '<a class="banner-link" href="/incident.html?id=' + encodeURIComponent(top.id) + '">查看处理进展 ›</a>';
  }

  function renderIncidents(list) {
    if (!list || !list.length) {
      incEl.innerHTML = '<p class="empty">近期没有异常记录</p>';
      return;
    }
    var all = list.slice().sort(function (a, b) {
      return new Date(b.start) - new Date(a.start);   // 显式按开始时间倒序（新→旧）
    });
    var shown = incExpanded ? all : all.slice(0, INC_LIMIT);

    var html = shown.map(incCard).join("");

    if (all.length > INC_LIMIT) {
      html += '<div class="inc-more-wrap">' +
        '<button class="inc-more" type="button">' +
          (incExpanded ? "收起" : "查看更多（共 " + all.length + " 条）") +
        '</button></div>';
    }
    incEl.innerHTML = html;
  }

  // ---------------- 加载 ----------------

  function renderMaintenance(list) {
    var box = document.getElementById("maint");
    if (!box) return;
    var now = Date.now();
    var win = (list || []).filter(function (w) {
      var s = new Date(w.startAt).getTime(), e = new Date(w.endAt).getTime();
      return s <= now && now <= e;
    })[0];
    if (!win) { box.style.display = "none"; box.innerHTML = ""; return; }
    var end = new Date(win.endAt).toLocaleString("zh-CN", { hour12: false, month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" });
    var names = (win.affected || []).join("、") || "站点";
    box.style.display = "flex";
    box.innerHTML = '<span class="banner-dot maintenance-dot"></span>' +
      '<b>' + esc(names) + '</b> 维护中，预计 ' + esc(end) + ' 完成' +
      (win.note ? ' · ' + esc(win.note) : '');
  }

  function renderAnnouncements(list) {
    var box = document.getElementById("annList");
    var wrap = document.getElementById("announcements");
    if (!box || !wrap) return;
    if (!list || !list.length) { wrap.setAttribute("hidden", ""); box.innerHTML = ""; return; }
    wrap.removeAttribute("hidden");
    var sorted = list.slice().sort(function (a, b) {
      if (!!b.pinned !== !!a.pinned) return b.pinned ? 1 : -1;
      return new Date(b.createdAt) - new Date(a.createdAt);
    });
    box.innerHTML = sorted.map(function (a) {
      var when = new Date(a.createdAt).toLocaleString("zh-CN", {
        hour12: false, month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit"
      });
        return '<div class="ann ' + (a.level === "warning" ? "warning" : "") + '" data-id="' + esc(a.id) + '">' +
        '<div class="ann-head">' +
          (a.pinned ? '<span class="ann-pin">置顶</span>' : '') +
          '<span class="ann-title">' + esc(a.title) + '</span>' +
          '<span class="ann-time">' + esc(when) + '</span>' +
        '</div>' +
        (a.body ? '<div class="ann-body">' + esc(a.body) + '</div>' : '') +
      '</div>';
    }).join("");
  }

  // 公告：点击整块跳转详情页
  function bindAnnClicks() {
    var box = document.getElementById("annList");
    if (!box || box.dataset.bound) return;
    box.dataset.bound = "1";
    box.addEventListener("click", function (ev) {
      var card = ev.target.closest(".ann[data-id]");
      if (card) location.href = "/announcement.html?id=" + encodeURIComponent(card.getAttribute("data-id"));
    });
  }

  // 站点名称 / 标题 / 副标题 / 图标
  function applySiteSettings(site) {
    if (!site) return;
    if (site.slowMs != null) STORE.slowMs = Number(site.slowMs) || 0;
    if (site.siteName) {
      var brandName = document.getElementById("brandName") || document.querySelector(".brand");
      if (brandName) brandName.textContent = site.siteName;
    }
    if (site.pageTitle) document.title = site.pageTitle;
    if (site.subtitle) {
      var brandSub = document.getElementById("brandSub");
      if (brandSub) brandSub.textContent = site.subtitle;
    }
    if (site.favicon) {
      var link = document.querySelector("link[rel='icon']");
      if (!link) {
        link = document.createElement("link");
        link.rel = "icon";
        document.head.appendChild(link);
      }
      if (/^https?:\/\//i.test(site.favicon) || site.favicon.indexOf("data:") === 0) {
        link.href = site.favicon;
      } else {
        var svg = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">' +
          '<text y=".9em" font-size="90">' + site.favicon.replace(/[<>&]/g, "") + '</text></svg>';
        link.href = "data:image/svg+xml," + encodeURIComponent(svg);
      }
    }
  }

  function load() {    var now = Date.now();
    var pStatus = getJSON("/api/v1/endpoints/statuses");
    var pIncidents = getJSON("/api/incidents").catch(function () { return { incidents: [] }; });
    var pAnn = getJSON("/api/announcements").catch(function () { return { announcements: [] }; });
    var pMaint = getJSON("/api/maintenance").catch(function () { return { maintenance: [] }; });
    var pNodesCfg = getJSON("/api/nodes").catch(function () { return { nodes: [] }; });
    var pNodesLive = getJSON("/data/nodes.json?v=" + DATA_V).catch(function () { return { nodes: [] }; });
    var pSite = getJSON("/api/settings").catch(function () { return {}; });
    var pData = getJSON("/data/status.json?v=" + DATA_V).catch(function () { return null; });

    Promise.all([pStatus, pData, pIncidents, pAnn, pMaint, pNodesCfg, pNodesLive, pSite]).then(function (result) {
      var eps = result[0] || [];
      var data = result[1] || {};
      var manualData = result[2] || {};
      var annData = result[3] || {};
      var maintData = result[4] || {};
      var nodesCfg = result[5] || {};
      var nodesLive = result[6] || {};
      var site = result[7] || {};
      applySiteSettings(site);
      STORE.manual = manualData.incidents || [];
      STORE.announcements = annData.announcements || [];
      STORE.maintenance = maintData.maintenance || [];
      STORE.nodeOrder = {};
      STORE.nodeSlow = {};
      (nodesCfg.nodes || []).forEach(function (n) {
        STORE.nodeOrder[n.name] = n.order || 0;
        if (typeof n.slowMs === "number" && n.slowMs > 0) STORE.nodeSlow[n.name] = n.slowMs;
      });
      STORE.customNodes = (nodesLive.nodes || []).map(function (n) {
        // 逐次探测灌进 resultCache，让「详情」按钮和内置节点一致
        resultCache[n.name] = (n.recent || []).map(function (s) {
          return {
            timestamp: s[0] * 1000,
            success: !!s[1],
            duration: (s[2] || 0) * 1e6,
            status: s[3] || 0,
            errors: s[1] ? [] : [s[3] ? "HTTP " + s[3] : "连接失败或超时"]
          };
        });
        return {
          name: n.name,
          custom: true,
          state: n.ok ? "up" : "down",
          uptime: n.uptime,
          latency: n.ms,
          bars: n.bars || []
        };
      });
      STORE.days = data.days || {};
      STORE.dayEnds = data.dayEndpoints || {};
      STORE.incidents = data.incidents || [];
      STORE.demo = !!data.demo;
      var badge = document.getElementById("demoBadge");
      if (badge) { if (STORE.demo) badge.removeAttribute("hidden"); else badge.setAttribute("hidden", ""); }

      var series = data.series || {};
      var sorted = sortEndpoints(eps);
      var jobs = sorted.map(function (ep) {
        return getText("/api/v1/endpoints/" + encodeURIComponent(ep.key) + "/uptimes/30d")
          .then(function (txt) {
            var n = Number(String(txt).trim());
            return isNaN(n) ? null : n;
          })
          .catch(function () { return null; });
      });

      return Promise.all(jobs).then(function (uptimes) {
        var rows = sorted.map(function (ep, i) {
          var results = ep.results || [];
          var latest = results.length ? results[results.length - 1] : null;
          resultCache[ep.name] = results;
          return {
            name: ep.name,
            state: latest ? (latest.success ? "up" : "down") : "none",
            uptime: uptimes[i],
            bars: seriesBars(series[ep.name]) || fallbackBars(results, now),
            latency: latest && latest.duration != null ? Math.round(latest.duration / 1e6) : null
          };
        });
        rows = rows.concat(STORE.customNodes);
        // 延迟：连续 N 次超过阈值才标黄（避免单次抖动闪黄）
        function trailingSlow(name, thresholdMs) {
          var list = resultCache[name] || [];
          var streak = 0;
          for (var i = list.length - 1; i >= 0; i -= 1) {
            var item = list[i];
            if (!item.success) break;
            if ((item.duration || 0) / 1e6 < thresholdMs) break;
            streak += 1;
          }
          return streak;
        }

        rows.forEach(function (r) {
          var threshold = STORE.nodeSlow[r.name] || STORE.slowMs;
          if (r.state !== "up" || r.latency == null || !threshold) return;
          var streak = trailingSlow(r.name, threshold);
          if (streak >= STORE.slowStreak) {
            r.state = "warn";
            r.slow = true;
            r.slowStreak = streak;
          }
        });
        rows.sort(function (a, b) {
          var oa = STORE.nodeOrder[a.name];
          var ob = STORE.nodeOrder[b.name];
          oa = oa == null ? 1000 : oa;
          ob = ob == null ? 1000 : ob;
          if (oa !== ob) return oa - ob;
          return String(a.name).localeCompare(String(b.name), "zh");
        });
        renderRows(rows, now);
        renderCalendar();
        var merged = allIncidents();
        renderIncidents(merged);
        renderBanner(STORE.manual);
        renderMaintenance(STORE.maintenance);
        renderAnnouncements(STORE.announcements);
        bindAnnClicks();
      });
    }).catch(function (err) {
      headEl.textContent = "无法获取状态数据";
      headEl.className = "bad";
      subEl.textContent = "请稍后刷新（" + err.message + "）";
    });
  }

  // 组件详情交互
  listEl.addEventListener("click", function (ev) {
    var row = ev.target.closest(".row");
    if (!row) return;
    var name = row.getAttribute("data-name");

    if (ev.target.closest(".only-fail")) {
      onlyFail[name] = !onlyFail[name];
      var detail = row.querySelector(".detail");
      if (detail) detail.innerHTML = detailTable(name);
      return;
    }
    var btn = ev.target.closest(".more");
    if (!btn) return;

    var panel = row.querySelector(".detail");
    var open = panel.hasAttribute("hidden");
    if (open) {
      panel.removeAttribute("hidden");
      row.classList.add("open");
      btn.textContent = "收起";
      btn.setAttribute("aria-expanded", "true");
      expanded[name] = true;
    } else {
      panel.setAttribute("hidden", "");
      row.classList.remove("open");
      btn.textContent = "详情";
      btn.setAttribute("aria-expanded", "false");
      delete expanded[name];
    }
  });

  // 日历：悬停浮层 / 点击明细
  calEl.addEventListener("mouseover", function (ev) {
    var cell = ev.target.closest(".cal-cell[data-date]");
    if (!cell) return;
    var k = cell.getAttribute("data-date");
    if (selectedDay === k) { hidePop(); return; }   // 已选中的那一天不再弹浮层
    showPop(cell, k);
  });
  calEl.addEventListener("mouseout", function (ev) {
    var cell = ev.target.closest(".cal-cell[data-date]");
    if (!cell) return;
    if (cell.contains(ev.relatedTarget)) return;
    hidePop();
  });
  window.addEventListener("scroll", hidePop, { passive: true });

  calEl.addEventListener("click", function (ev) {
    var cell = ev.target.closest(".cal-cell[data-date]");
    if (!cell) return;
    var k = cell.getAttribute("data-date");
    selectedDay = (selectedDay === k) ? null : k;
    hidePop();
    renderCalendar();
  });

  // 最近事件：点击整行跳到事件详情
  incEl.addEventListener("click", function (ev) {
    var row = ev.target.closest(".inc[data-href]");
    if (row && !ev.target.closest(".inc-more")) location.href = row.getAttribute("data-href");
  });

  // 最近事件：查看更多 / 收起
  incEl.addEventListener("click", function (ev) {
    if (!ev.target.closest(".inc-more")) return;
    incExpanded = !incExpanded;
    renderIncidents(STORE.incidents);
  });

  load();  setInterval(load, REFRESH_MS);
})();