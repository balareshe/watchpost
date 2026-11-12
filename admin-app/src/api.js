// Copyright (C) 2026 balareshe（摆烂人生） <https://github.com/balareshe/vigil-status>. All rights reserved.
// Licensed under the Vigil Non-Commercial Source License 1.0 (see LICENSE).
// 本项目禁止商业使用；分发须保留本声明与授权协议，并署名 Vigil。
const BASE = "";

export async function api(method, path, body) {
  const res = await fetch(BASE + path, {
    method,
    credentials: "same-origin",
    headers: body ? { "Content-Type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined
  });
  let data = {};
  try {
    data = await res.json();
  } catch {
    data = {};
  }
  if (res.status === 401) {
    window.dispatchEvent(new CustomEvent("auth:expired"));
  }
  if (!res.ok) {
    throw new Error(data.error || `HTTP ${res.status}`);
  }
  return data;
}

export const get = (path) => api("GET", path);
export const post = (path, body) => api("POST", path, body);
export const patch = (path, body) => api("PATCH", path, body);
export const del = (path) => api("DELETE", path);

export function fmt(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleString("zh-CN", {
    hour12: false,
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit"
  });
}

export function fmtTime(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleTimeString("zh-CN", { hour12: false, hour: "2-digit", minute: "2-digit" });
}

export const STATUS_LABEL = {
  investigating: "排查中",
  identified: "已定位",
  in_progress: "修复中",
  monitoring: "监控中",
  resolved: "已恢复"
};

export const SEVERITY_LABEL = {
  critical: "重大",
  major: "严重",
  minor: "一般",
  info: "提示",
  maintenance: "维护",
  down: "重大",
  warn: "一般"
};

export const SEVERITY_OPTIONS = [
  { value: "critical", label: "重大（核心不可用）" },
  { value: "major", label: "严重（主要功能受影响）" },
  { value: "minor", label: "一般（部分异常）" },
  { value: "info", label: "提示（不影响使用）" },
  { value: "maintenance", label: "维护（计划内）" }
];

export function severityClass(sev) {
  if (sev === "critical" || sev === "major" || sev === "down") return "down";
  if (sev === "maintenance") return "maint";
  if (sev === "info") return "info";
  return "warn";
}

export function severityLabel(sev) {
  return SEVERITY_LABEL[sev] || "一般";
}

export const TEMPLATES = {
  investigating: "我们已收到异常报告，正在排查原因。",
  identified: "已定位问题原因，正在制定修复方案。",
  in_progress: "已开始实施修复。",
  monitoring: "已实施修复，正在监控结果。",
  resolved: "本次问题已解决，服务已恢复。"
};
