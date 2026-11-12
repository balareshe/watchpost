<script setup>
import { ref, onMounted } from "vue";
import { get, post, patch, del, fmt, STATUS_LABEL, TEMPLATES, SEVERITY_OPTIONS, severityLabel } from "../api";
import { canWrite } from "../store";

const BUILTIN = []; // 组件列表全部来自 Gatus 与节点配置
const list = ref([]);
const components = ref(BUILTIN);
const msg = ref("");
const msgOk = ref(false);

const form = ref({
  title: "",
  titleEn: "",
  severity: "minor",
  status: "investigating",
  owner: "",
  summary: "",
  summaryEn: "",
  firstUpdate: "",
  affected: []
});

function note(text, ok) {
  msg.value = text || "";
  msgOk.value = !!ok;
}

function toggleAffected(name) {
  const i = form.value.affected.indexOf(name);
  if (i >= 0) form.value.affected.splice(i, 1);
  else form.value.affected.push(name);
}

async function load() {
  try {
    const [inc, gatus, nodes] = await Promise.all([
      get("/api/incidents"),
      get("/api/v1/endpoints/statuses").catch(() => []),
      get("/api/nodes").catch(() => ({ nodes: [] }))
    ]);
    list.value = inc.incidents || [];
    ensureDrafts();
    const names = (Array.isArray(gatus) ? gatus : []).map((e) => e.name);
    const custom = (nodes.nodes || []).filter((n) => !n.builtin).map((n) => n.name);
    components.value = [...new Set([...BUILTIN, ...names, ...custom])];
  } catch (e) {
    note("加载失败：" + e.message, false);
  }
}

async function create() {
  if (!canWrite()) return;
  try {
    await post("/api/incidents", form.value);
    note("创建成功", true);
    form.value = {
      title: "",
      titleEn: "",
      severity: "warn",
      status: "investigating",
      owner: "",
      summary: "",
      summaryEn: "",
      firstUpdate: "",
      affected: []
    };
    load();
  } catch (e) {
    note("失败：" + e.message, false);
  }
}

async function applyState(id, status) {
  try {
    await patch(`/api/incidents/${id}`, { status });
    load();
  } catch (e) {
    alert(e.message);
  }
}

async function remove(id) {
  if (!confirm("确定删除这条事件？")) return;
  try {
    await del(`/api/incidents/${id}`);
    load();
  } catch (e) {
    alert(e.message);
  }
}

const upd = ref({});

function ensureDrafts() {
  list.value.forEach((inc) => {
    if (!upd.value[inc.id]) {
      upd.value[inc.id] = { text: "", author: inc.owner || "", status: "monitoring" };
    }
  });
}

function fillTemplate(id, status) {
  if (!status) return;
  const draft = upd.value[id];
  if (!draft) return;
  draft.text = TEMPLATES[status] || "";
  draft.status = status;
}

async function publish(id) {
  const draft = upd.value[id];
  if (!draft || !draft.text) return;
  try {
    await post(`/api/incidents/${id}/updates`, {
      status: draft.status || "monitoring",
      text: draft.text,
      author: draft.author || ""
    });
    draft.text = "";
    load();
  } catch (e) {
    alert(e.message);
  }
}

onMounted(load);
</script>

<template>
  <div class="page-head">
    <h1>事件</h1>
    <span>{{ list.length ? "共 " + list.length + " 条" : "" }}</span>
  </div>

  <div v-if="canWrite()" class="card">
    <h2>新建事件</h2>
    <div class="row2">
      <div><label>标题（中文）</label><input v-model="form.title" type="text" placeholder="网页/API 部分中断" /></div>
      <div><label>标题（英文，可空）</label><input v-model="form.titleEn" type="text" /></div>
    </div>

    <label>受影响组件</label>
    <div class="chips">
      <span
        v-for="name in components"
        :key="name"
        class="chip"
        :class="{ on: form.affected.includes(name) }"
        @click="toggleAffected(name)"
      >{{ name }}</span>
    </div>

    <div class="row2">
      <div>
        <label>严重程度</label>
        <select v-model="form.severity">
          <option v-for="o in SEVERITY_OPTIONS" :key="o.value" :value="o.value">{{ o.label }}</option>
        </select>
      </div>
      <div><label>处理人（可空）</label><input v-model="form.owner" type="text" /></div>
    </div>

    <label>状态</label>
    <select v-model="form.status">
      <option v-for="(label, key) in STATUS_LABEL" :key="key" :value="key">{{ label }}</option>
    </select>

    <label>概要（中文）</label>
    <textarea v-model="form.summary"></textarea>
    <label>概要（英文，可空）</label>
    <textarea v-model="form.summaryEn"></textarea>
    <label>首条进度说明（可空）</label>
    <textarea v-model="form.firstUpdate"></textarea>

    <div class="row-actions">
      <button class="primary" @click="create">创建事件</button>
      <span class="msg" :class="msgOk ? 'ok' : 'err'">{{ msg }}</span>
    </div>
  </div>

  <div class="card">
    <h2>全部事件</h2>
    <p v-if="!list.length" class="empty">还没有事件</p>

    <div v-for="inc in list" :key="inc.id" class="item">
      <div class="item-h">
        <span class="badge" :class="inc.status">{{ STATUS_LABEL[inc.status] || inc.status }}</span>
        {{ inc.title }}
        <span v-if="inc.auto" class="badge custom">自动</span>
      </div>
      <div class="item-s">
        {{ fmt(inc.startedAt) }}<template v-if="inc.resolvedAt"> → {{ fmt(inc.resolvedAt) }}</template>
        · {{ (inc.affected || []).join("、") }}
        <template v-if="inc.owner"> · {{ inc.owner }}</template>
        · 更新 {{ (inc.updates || []).length }} 条
      </div>

      <div v-if="canWrite()" class="row-actions">
        <select :value="inc.status" @change="applyState(inc.id, $event.target.value)">
          <option v-for="(label, key) in STATUS_LABEL" :key="key" :value="key">{{ label }}</option>
        </select>
        <button class="danger" @click="remove(inc.id)">删除</button>
      </div>

      <details v-if="canWrite()" class="upd-box">
        <summary>发布进度</summary>
        <label>模板</label>
        <select @change="fillTemplate(inc.id, $event.target.value)">
          <option value="">选择模板…</option>
          <option v-for="(tpl, key) in TEMPLATES" :key="key" :value="key">
            {{ STATUS_LABEL[key] }} — {{ tpl }}
          </option>
        </select>
        <label>说明</label>
        <textarea v-model="upd[inc.id].text" placeholder="填写进度说明"></textarea>
        <label>处理人</label>
        <input v-model="upd[inc.id].author" type="text" />
        <label>本次状态</label>
        <select v-model="upd[inc.id].status">
          <option v-for="(label, key) in STATUS_LABEL" :key="key" :value="key">{{ label }}</option>
        </select>
        <div class="row-actions">
          <button class="primary" @click="publish(inc.id)">发布进度</button>
        </div>
      </details>
    </div>
  </div>
</template>

<style scoped>
.upd-box {
  margin-top: 8px;
}
.upd-box summary {
  font-size: 12px;
  color: var(--ink-2);
  cursor: pointer;
}
</style>
