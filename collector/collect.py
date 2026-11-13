#!/usr/bin/env python3
# Copyright (C) 2026 balareshe（摆烂人生） <https://github.com/balareshe/watchpost>. All rights reserved.
# Licensed under the Watchpost Non-Commercial Source License 1.0 (see LICENSE).
# 本项目禁止商业使用；分发须保留本声明与授权协议，并署名 Watchpost。
"""从 Gatus 的 SQLite 导出差错事件与每日可用率，供状态页静态读取。

用法（容器内）：python collect.py /data/data.db /out/status.json

数据来源：
  endpoint_events  —— Gatus 记录的状态变化（START / HEALTHY / UNHEALTHY ...）
  endpoint_uptimes —— Gatus 自己按小时聚合的执行次数，适合做长期可用率
输出：
  {"generatedAt","days":{"YYYY-MM-DD":{"up":n,"total":n}},"incidents":[...]}
"""
import datetime as dt
import json
import os
import re
import sqlite3
import sys

DB = sys.argv[1] if len(sys.argv) > 1 else "/data/data.db"
OUT = sys.argv[2] if len(sys.argv) > 2 else "/out/status.json"
TZ = dt.timezone(dt.timedelta(hours=8))  # Asia/Shanghai
# 「重大」的最小持续时间：Gatus 事件只记录状态翻转，单次探测失败也会产生一条
# UNHEALTHY 事件，持续时间最多等于一个探测间隔。默认 90 秒 ≈ 3 次连续失败，
# 低于它的按「一般」处理（黄色），避免把已自愈的抖动显示成重大。
CRITICAL_MIN_SEC = int(os.environ.get("CRITICAL_MIN_SEC") or 90)


def parse_ts(raw):
    """Gatus 存的是 '2026-11-12 11:31:07.189363581 +0000 UTC'，去掉纳秒再解析。"""
    s = re.sub(r"\.\d+", "", str(raw).replace(" UTC", "").strip())
    return dt.datetime.strptime(s, "%Y-%m-%d %H:%M:%S %z")


def iso(value):
    return value.astimezone(TZ).isoformat(timespec="seconds") if value else None


def main():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    # 让「按端点 + 时间窗」的查询走索引；已存在或无权写入时忽略
    try:
        con.execute(
            "CREATE INDEX IF NOT EXISTS idx_results_ep_ts ON endpoint_results(endpoint_id, timestamp)"
        )
        con.commit()
    except sqlite3.Error:
        pass

    names = {
        r["endpoint_id"]: r["endpoint_name"]
        for r in con.execute("SELECT endpoint_id, endpoint_name FROM endpoints")
    }

    # ---- 逐端点的状态机，拼出事故窗口 ----
    seq = {}
    for r in con.execute(
        "SELECT endpoint_id, event_type, event_timestamp FROM endpoint_events ORDER BY event_timestamp"
    ):
        try:
            ts = parse_ts(r["event_timestamp"])
        except ValueError:
            continue
        seq.setdefault(r["endpoint_id"], []).append((r["event_type"], ts))

    raw = []
    for eid, events in seq.items():
        opened_at = None
        severity = None
        for event_type, ts in events:
            is_bad = event_type not in ("HEALTHY", "START")
            if is_bad and opened_at is None:
                opened_at, severity = ts, ("down" if event_type == "UNHEALTHY" else "warn")
            elif not is_bad and opened_at is not None:
                raw.append(
                    {
                        "start": opened_at,
                        "end": ts,
                        "severity": severity,
                        "endpoint": names.get(eid, str(eid)),
                    }
                )
                opened_at = None
        if opened_at is not None:  # 仍在故障中
            raw.append(
                {
                    "start": opened_at,
                    "end": None,
                    "severity": severity,
                    "endpoint": names.get(eid, str(eid)),
                }
            )

    # ---- 时间重叠的事故合并成一条（多组件同时异常只报一条）----
    raw.sort(key=lambda i: i["start"])
    merged = []
    for inc in raw:
        if merged:
            last = merged[-1]
            last_end = last["end"]
            if last_end is None or inc["start"] <= last_end:
                if last["end"] is not None:
                    if inc["end"] is None or inc["end"] > last["end"]:
                        last["end"] = inc["end"]
                if inc["severity"] == "down":
                    last["severity"] = "down"
                last["endpoints"].add(inc["endpoint"])
                continue
        merged.append(
            {
                "start": inc["start"],
                "end": inc["end"],
                "severity": inc["severity"],
                "endpoints": {inc["endpoint"]},
            }
        )

    # ---- 每日可用率（来自 Gatus 的小时聚合）----
    days = {}
    for r in con.execute(
        "SELECT hour_unix_timestamp, total_executions, successful_executions FROM endpoint_uptimes"
    ):
        day = dt.datetime.fromtimestamp(r["hour_unix_timestamp"], TZ).strftime("%Y-%m-%d")
        bucket = days.setdefault(day, {"up": 0, "total": 0})
        bucket["up"] += int(r["successful_executions"] or 0)
        bucket["total"] += int(r["total_executions"] or 0)

    now = dt.datetime.now(TZ)
    incidents = []
    for item in merged[-100:]:
        end = item["end"] or now
        duration = max(0, int((end - item["start"]).total_seconds()))
        severity = item["severity"]
        if severity == "down" and duration < CRITICAL_MIN_SEC:
            # 单次/两次探测失败就自愈的，不算重大：Watcher 那边也是这么判的（重试成功不开单）
            severity = "warn"
        incidents.append(
            {
                "start": iso(item["start"]),
                "end": iso(item["end"]),
                "ongoing": item["end"] is None,
                "severity": severity,
                "endpoints": sorted(item["endpoints"]),
                "durationSec": duration,
            }
        )

    # ---- 最近 24 小时 × 96 格，逐格汇总（供页面时间轴）----
    # 每格 15 分钟；没有探测记录的格子留 null（页面显示为灰色）。
    BUCKETS = 96
    now_floor = now.replace(microsecond=0)
    window_start = now_floor - dt.timedelta(hours=24)
    step = 24 * 3600 / BUCKETS

    series = {}
    for name in names.values():
        series[name] = [None] * BUCKETS

    # Gatus 存的时间是 UTC 且格式固定（"YYYY-MM-DD HH:MM:SS.nnn +0000 UTC"），
    # 用同格式的前缀做字符串比较即可在 SQL 层过滤，避免每次全表扫描。
    cutoff = window_start.astimezone(dt.timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    for eid, name in names.items():
        rows = con.execute(
            "SELECT success, timestamp FROM endpoint_results "
            "WHERE endpoint_id = ? AND timestamp >= ?",
            (eid, cutoff),
        )
        for r in rows:
            try:
                ts = parse_ts(r["timestamp"])
            except ValueError:
                continue
            offset = (ts - window_start).total_seconds()
            if offset < 0:
                continue
            idx = min(int(offset // step), BUCKETS - 1)
            cell = series[name][idx]
            if cell is None:
                cell = {"ok": 0, "total": 0}
                series[name][idx] = cell
            cell["total"] += 1
            if r["success"]:
                cell["ok"] += 1

    # ---- 每天 × 每个组件的可用率（供日历点击后的明细）----
    day_endpoints = {}
    for r in con.execute(
        "SELECT endpoint_id, hour_unix_timestamp, total_executions, successful_executions FROM endpoint_uptimes"
    ):
        name = names.get(r["endpoint_id"])
        if name is None:
            continue
        day = dt.datetime.fromtimestamp(r["hour_unix_timestamp"], TZ).strftime("%Y-%m-%d")
        bucket = day_endpoints.setdefault(day, {}).setdefault(name, {"up": 0, "total": 0})
        bucket["up"] += int(r["successful_executions"] or 0)
        bucket["total"] += int(r["total_executions"] or 0)

    # ---- 演示数据层：web/data/demo.json 存在时合并进去（删掉文件即恢复真实数据）----
    demo_path = os.path.join(os.path.dirname(OUT), "demo.json")
    demo = False
    try:
        with open(demo_path, encoding="utf-8") as handle:
            demo_data = json.load(handle)
        extra = demo_data.get("incidents") or []
        if extra:
            incidents = sorted(incidents + extra, key=lambda i: i["start"])
            demo = True
        for day_key, bucket in (demo_data.get("days") or {}).items():
            days[day_key] = bucket
            demo = True
        for day_key, per in (demo_data.get("dayEndpoints") or {}).items():
            day_endpoints[day_key] = per
            demo = True
    except (OSError, ValueError):
        pass

    payload = {
        "generatedAt": now.isoformat(timespec="seconds"),
        "demo": demo,
        "days": days,
        "dayEndpoints": day_endpoints,
        "incidents": incidents,
        "series": series,
    }
    with open(OUT, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, separators=(",", ":"))
    print(f"wrote {OUT}: days={len(days)} incidents={len(incidents)}")


if __name__ == "__main__":
    main()
