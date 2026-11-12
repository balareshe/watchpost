<script setup>
import { ref, computed, onMounted } from "vue";
import { useRouter } from "vue-router";
import { get, fmt, STATUS_LABEL, severityClass, severityLabel } from "../api";

const SEVERITY_FILTERS = [
  { value: "down", label: "重大 / 严重" },
  { value: "warn", label: "一般" },
  { value: "maint", label: "维护" },
  { value: "info", label: "提示" }
];

const router = useRouter();
const list = ref([]);
const loading = ref(true);
const statusFilter = ref("all");
const severityFilter = ref("all");
const keyword = ref("");

async function load() {
  loading.value = true;
  try {
    const data = await get("/api/incidents");
    list.value = data.incidents || [];
  } catch (e) {
    list.value = [];
  } finally {
    loading.value = false;
  }
}

const filtered = computed(() =>
  list.value
    .filter((i) => (statusFilter.value === "all" ? true : i.status === statusFilter.value))
    .filter((i) => (severityFilter.value === "all" ? true : severityClass(i.severity) === severityFilter.value))
    .filter((i) => {
      const k = keyword.value.trim().toLowerCase();
      if (!k) return true;
      return (
        (i.title || "").toLowerCase().includes(k) ||
        (i.affected || []).join("、").toLowerCase().includes(k) ||
        (i.owner || "").toLowerCase().includes(k)
      );
    })
    .sort((a, b) => new Date(b.startedAt) - new Date(a.startedAt))
);

function open(inc) {
  router.push({ name: "ticket", params: { id: inc.id } });
}

function duration(inc) {
  const start = new Date(inc.startedAt).getTime();
  const end = inc.resolvedAt ? new Date(inc.resolvedAt).getTime() : Date.now();
  const mins = Math.max(0, Math.round((end - start) / 60000));
  if (mins < 60) return mins + " 分钟";
  const h = Math.floor(mins / 60);
  const m = mins % 60;
  return m ? `${h} 小时 ${m} 分` : `${h} 小时`;
}

onMounted(load);
</script>

<template>
  <div class="page-head">
    <h1>工单</h1>
    <span>{{ filtered.length }} / {{ list.length }} 条</span>
  </div>

  <div class="card">
    <div class="filters">
      <select v-model="statusFilter">
        <option value="all">全部状态</option>
        <option v-for="(label, key) in STATUS_LABEL" :key="key" :value="key">{{ label }}</option>
      </select>
      <select v-model="severityFilter">
        <option value="all">全部严重程度</option>
        <option v-for="o in SEVERITY_FILTERS" :key="o.value" :value="o.value">{{ o.label }}</option>
      </select>
      <input v-model="keyword" type="text" placeholder="搜索标题 / 组件 / 处理人" class="search" />
    </div>
  </div>

  <div class="card">
    <p v-if="loading" class="empty">加载中…</p>
    <p v-else-if="!filtered.length" class="empty">没有符合条件的工单</p>

    <div v-for="inc in filtered" :key="inc.id" class="ticket" @click="open(inc)">
      <div class="t-head">
        <span class="badge" :class="inc.status">{{ STATUS_LABEL[inc.status] || inc.status }}</span>
        <span class="sev-tag" :class="severityClass(inc.severity)">{{ severityLabel(inc.severity) }}</span>
        <span class="t-title">{{ inc.title }}</span>
        <span v-if="inc.auto" class="badge custom">自动</span>
        <span class="t-arrow">›</span>
      </div>
      <div class="t-meta">
        {{ fmt(inc.startedAt) }}
        <template v-if="inc.resolvedAt"> → {{ fmt(inc.resolvedAt) }}</template>
        · 持续 {{ duration(inc) }}
        · {{ (inc.affected || []).join("、") || "未指定组件" }}
        <template v-if="inc.owner"> · {{ inc.owner }}</template>
        · 更新 {{ (inc.updates || []).length }} 条
      </div>
    </div>
  </div>
</template>

<style scoped>
.filters {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.filters select {
  width: auto;
  min-width: 130px;
}

.filters .search {
  flex: 1;
  min-width: 180px;
}

.ticket {
  padding: 12px 10px;
  margin: 0 -10px;
  border-bottom: 1px solid var(--line);
  border-radius: 8px;
  cursor: pointer;
}

.ticket:last-child {
  border-bottom: none;
}

.ticket:hover {
  background: #fafbfb;
}

.t-head {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13.5px;
  font-weight: 600;
}

.t-title {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.t-arrow {
  margin-left: auto;
  color: var(--ink-3);
  font-size: 16px;
}

.t-meta {
  font-size: 11.5px;
  color: var(--ink-3);
  margin-top: 4px;
}

.sev-tag {
  display: inline-block;
  font-size: 10.5px;
  font-weight: 500;
  padding: 0 6px;
  border-radius: 4px;
  border: 1px solid transparent;
}

.sev-tag.down {
  color: #b42318;
  background: #fef3f2;
  border-color: #fecdca;
}

.sev-tag.warn {
  color: #b45309;
  background: #fff7ed;
  border-color: #f5c48a;
}

.sev-tag.maint {
  color: #1d4ed8;
  background: #eff6ff;
  border-color: #bfdbfe;
}

.sev-tag.info {
  color: #4b5563;
  background: #f3f4f6;
  border-color: #e5e7eb;
}
</style>
