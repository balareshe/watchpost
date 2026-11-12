<script setup>
import { ref, computed, onMounted } from "vue";
import { get, post, del, fmt } from "../api";
import { canWrite } from "../store";
import DatePicker from "../components/DatePicker.vue";

const BUILTIN = []; // 组件列表全部来自 Gatus 与节点配置
const list = ref([]);
const components = ref(BUILTIN);
const msg = ref("");
const msgOk = ref(false);

const form = ref({ title: "", startAt: "", endAt: "", note: "", affected: [] });

function note(text, ok) {
  msg.value = text || "";
  msgOk.value = !!ok;
}

function toggle(name) {
  const i = form.value.affected.indexOf(name);
  if (i >= 0) form.value.affected.splice(i, 1);
  else form.value.affected.push(name);
}

const pad = (n) => String(n).padStart(2, "0");
const local = (d) =>
  `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;

const summary = computed(() => {
  if (!form.value.startAt || !form.value.endAt) return "";
  const start = new Date(form.value.startAt);
  const end = new Date(form.value.endAt);
  if (Number.isNaN(start.getTime()) || Number.isNaN(end.getTime())) return "";
  const mins = Math.round((end - start) / 60000);
  if (mins <= 0) return "结束时间必须晚于开始时间";
  const h = Math.floor(mins / 60);
  const m = mins % 60;
  const dur = h && m ? `${h} 小时 ${m} 分钟` : h ? `${h} 小时` : `${m} 分钟`;
  const short = (d) => `${pad(d.getMonth() + 1)}/${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
  return `${short(start)} → ${short(end)} · 共 ${dur}`;
});

function preset(kind) {
  const now = new Date();
  let start;
  let end;
  if (kind === "tonight") {
    start = new Date(now);
    start.setHours(0, 0, 0, 0);
    end = new Date(start.getTime() + 6 * 3600 * 1000);
  } else if (kind === "sunday") {
    start = new Date(now);
    const diff = (7 - start.getDay()) % 7;
    start.setDate(start.getDate() + diff);
    start.setHours(2, 0, 0, 0);
    end = new Date(start.getTime() + 2 * 3600 * 1000);
  } else {
    const hours = kind === "1h" ? 1 : 2;
    start = new Date(now);
    start.setSeconds(0, 0);
    const rem = start.getMinutes() % 5;
    if (rem) start.setMinutes(start.getMinutes() + (5 - rem));
    end = new Date(start.getTime() + hours * 3600 * 1000);
  }
  form.value.startAt = local(start);
  form.value.endAt = local(end);
}

async function load() {
  try {
    const [mt, gatus] = await Promise.all([
      get("/api/maintenance"),
      get("/api/v1/endpoints/statuses").catch(() => [])
    ]);
    list.value = mt.maintenance || [];
    const names = (Array.isArray(gatus) ? gatus : []).map((e) => e.name);
    components.value = [...new Set([...BUILTIN, ...names])];
  } catch (e) {
    note("加载失败：" + e.message, false);
  }
}

async function create() {
  if (!canWrite()) return;
  if (!form.value.startAt || !form.value.endAt) {
    note("请填写开始与结束时间", false);
    return;
  }
  if (summary.value.startsWith("结束时间必须晚于")) {
    note("结束时间必须晚于开始时间", false);
    return;
  }
  try {
    await post("/api/maintenance", {
      ...form.value,
      startAt: new Date(form.value.startAt).toISOString(),
      endAt: new Date(form.value.endAt).toISOString()
    });
    note("已创建", true);
    form.value = { title: "", startAt: "", endAt: "", note: "", affected: [] };
    load();
  } catch (e) {
    note("失败：" + e.message, false);
  }
}

async function remove(id) {
  if (!confirm("删除这个维护窗口？")) return;
  try {
    await del(`/api/maintenance/${id}`);
    load();
  } catch (e) {
    alert(e.message);
  }
}

onMounted(load);
</script>

<template>
  <div class="page-head">
    <h1>维护窗口</h1>
    <span>{{ list.length ? "共 " + list.length + " 条" : "" }}</span>
  </div>

  <div v-if="canWrite()" class="card">
    <h2>创建维护窗口</h2>
    <label>标题</label>
    <input v-model="form.title" type="text" placeholder="例行维护" />

    <label>开始时间</label>
    <DatePicker v-model="form.startAt" placeholder="选择开始时间" />

    <label>结束时间</label>
    <DatePicker v-model="form.endAt" placeholder="选择结束时间" :min="form.startAt" />

    <div class="presets">
      <span class="presets-label">快捷：</span>
      <button type="button" @click="preset('1h')">现在起 1 小时</button>
      <button type="button" @click="preset('2h')">现在起 2 小时</button>
      <button type="button" @click="preset('tonight')">今天 00:00–06:00</button>
      <button type="button" @click="preset('sunday')">本周日 02:00–04:00</button>
    </div>

    <p v-if="summary" class="dt-summary" :class="{ bad: summary.startsWith('结束时间必须晚于') }">
      {{ summary }}
    </p>

    <label>影响组件</label>
    <div class="chips">
      <span
        v-for="name in components"
        :key="name"
        class="chip"
        :class="{ on: form.affected.includes(name) }"
        @click="toggle(name)"
      >{{ name }}</span>
    </div>

    <label>说明（可空）</label>
    <input v-model="form.note" type="text" placeholder="维护期间可能短暂不可用" />

    <div class="row-actions">
      <button class="primary" @click="create">创建</button>
      <span class="msg" :class="msgOk ? 'ok' : 'err'">{{ msg }}</span>
    </div>
  </div>

  <div class="card">
    <h2>已登记</h2>
    <p v-if="!list.length" class="empty">还没有维护窗口</p>
    <div v-for="w in list" :key="w.id" class="item">
      <div class="item-h">{{ w.title }}</div>
      <div class="item-s">
        {{ fmt(w.startAt) }} → {{ fmt(w.endAt) }} · {{ (w.affected || []).join("、") }}
        <template v-if="w.note"> · {{ w.note }}</template>
      </div>
      <div v-if="canWrite()" class="row-actions">
        <button class="danger" @click="remove(w.id)">删除</button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.presets {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  margin-top: 10px;
}

.presets-label {
  font-size: 12px;
  color: var(--ink-3);
}

.presets button {
  font-size: 12px;
  padding: 4px 10px;
  border-radius: 999px;
  color: var(--ink-2);
}

.presets button:hover {
  border-color: #9aa4ae;
  color: var(--ink);
}

.dt-summary {
  margin: 10px 0 0;
  font-size: 12.5px;
  color: var(--ink-2);
  font-variant-numeric: tabular-nums;
}

.dt-summary.bad {
  color: #b42318;
}
</style>
