<script setup>
import { ref, onMounted, computed } from "vue";
import { get, fmt, STATUS_LABEL } from "../api";

const loading = ref(true);
const updatedAt = ref("");
const rows = ref([]);
const incidents = ref([]);
const announcements = ref([]);
const maintenance = ref([]);
const todayRate = ref(null);
const todayCount = ref("");

const down = computed(() => rows.value.filter((r) => !r.ok));
const open = computed(() => incidents.value.filter((i) => i.status !== "resolved"));
const activeMt = computed(() => {
  const now = Date.now();
  return maintenance.value.filter(
    (m) => new Date(m.startAt).getTime() <= now && now <= new Date(m.endAt).getTime()
  );
});
const pinned = computed(() => announcements.value.filter((a) => a.pinned).length);
const recent = computed(() =>
  [...incidents.value]
    .sort((a, b) => new Date(b.startedAt) - new Date(a.startedAt))
    .slice(0, 5)
);

async function load() {
  loading.value = true;
  const safe = (p) => p.catch(() => ({}));
  const [gatus, inc, ann, mt, status, nodesLive, nodesCfg] = await Promise.all([
    safe(get("/api/v1/endpoints/statuses")),
    safe(get("/api/incidents")),
    safe(get("/api/announcements")),
    safe(get("/api/maintenance")),
    safe(get("/data/status.json?v=4")),
    safe(get("/data/nodes.json?v=4")),
    safe(get("/api/nodes"))
  ]);

  const list = (Array.isArray(gatus) ? gatus : []).map((e) => {
    const results = e.results || [];
    const last = results[results.length - 1];
    return { name: e.name, ok: !!(last && last.success), ms: last ? Math.round(last.duration / 1e6) : null };
  });

  const custom = ((nodesLive || {}).nodes || []).map((n) => ({
    name: n.name,
    ok: !!n.ok,
    ms: n.ms,
    custom: true
  }));

  const orderMap = {};
  ((nodesCfg || {}).nodes || []).forEach((n) => {
    orderMap[n.name] = n.order || 0;
  });

  rows.value = list.concat(custom).sort((a, b) => {
    const oa = orderMap[a.name] == null ? 1000 : orderMap[a.name];
    const ob = orderMap[b.name] == null ? 1000 : orderMap[b.name];
    if (oa !== ob) return oa - ob;
    return String(a.name).localeCompare(String(b.name), "zh");
  });

  incidents.value = (inc || {}).incidents || [];
  announcements.value = (ann || {}).announcements || [];
  maintenance.value = (mt || {}).maintenance || [];

  const today = new Date().toLocaleDateString("sv-SE");
  const bucket = ((status || {}).days || {})[today];
  todayRate.value = bucket && bucket.total ? bucket.up / bucket.total : null;
  todayCount.value = bucket && bucket.total ? `${bucket.up}/${bucket.total} 次成功` : "暂无数据";

  updatedAt.value = new Date().toLocaleTimeString("zh-CN", { hour12: false });
  loading.value = false;
}

onMounted(load);
</script>

<template>
  <div class="page-head">
    <h1>概览</h1>
    <span v-if="updatedAt">更新于 {{ updatedAt }}</span>
  </div>

  <div class="stats">
    <div class="stat">
      <div class="k">当前状态</div>
      <div class="v" :class="down.length ? 'bad' : 'ok'">{{ down.length ? "异常" : "正常" }}</div>
      <div class="s">{{ down.length ? down.length + " 个节点异常" : "全部节点正常" }}</div>
    </div>
    <div class="stat">
      <div class="k">监控节点</div>
      <div class="v">{{ rows.length }}</div>
    </div>
    <div class="stat">
      <div class="k">今日可用率</div>
      <div class="v" :class="todayRate != null && todayRate < 0.995 ? 'bad' : ''">
        {{ todayRate == null ? "—" : (todayRate * 100).toFixed(2) + "%" }}
      </div>
      <div class="s">{{ todayCount }}</div>
    </div>
    <div class="stat">
      <div class="k">未恢复事件</div>
      <div class="v" :class="open.length ? 'bad' : ''">{{ open.length }}</div>
      <div class="s">{{ open.length ? "需要跟进" : "无" }}</div>
    </div>
    <div class="stat">
      <div class="k">公告</div>
      <div class="v">{{ announcements.length }}</div>
      <div class="s">{{ pinned }} 条置顶</div>
    </div>
    <div class="stat">
      <div class="k">维护窗口</div>
      <div class="v" :class="activeMt.length ? 'bad' : ''">{{ maintenance.length }}</div>
      <div class="s">{{ activeMt.length ? "进行中 " + activeMt.length + " 个" : "无进行中" }}</div>
    </div>
  </div>

  <div class="card">
    <h2>节点状态</h2>
    <p v-if="loading" class="empty">加载中…</p>
    <p v-else-if="!rows.length" class="empty">暂无节点</p>
    <div v-for="r in rows" :key="r.name" class="item">
      <div class="item-h">
        <i class="dot" :class="{ bad: !r.ok }"></i>
        {{ r.name }}
        <span v-if="r.custom" class="badge custom">自定义</span>
        <span class="muted ms">{{ r.ms == null ? "—" : r.ms + " ms" }}</span>
      </div>
    </div>
  </div>

  <div class="card">
    <h2>最近事件</h2>
    <p v-if="!recent.length" class="empty">还没有事件</p>
    <div v-for="i in recent" :key="i.id" class="item">
      <div class="item-h">
        <span class="badge" :class="i.status">{{ STATUS_LABEL[i.status] || i.status }}</span>
        {{ i.title }}
      </div>
      <div class="item-s">{{ fmt(i.startedAt) }} · {{ (i.affected || []).join("、") || "—" }}</div>
    </div>
  </div>
</template>
