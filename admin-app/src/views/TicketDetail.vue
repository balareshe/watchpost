<script setup>
import { ref, computed, onMounted, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import {
  get, post, patch, del, fmt,
  STATUS_LABEL, TEMPLATES, SEVERITY_OPTIONS, severityClass, severityLabel
} from "../api";

const route = useRoute();
const router = useRouter();

const loading = ref(true);
const notFound = ref(false);
const inc = ref(null);
const msg = ref("");
const msgOk = ref(false);
const draft = ref({ text: "", author: "", status: "monitoring" });

const updList = computed(() =>
  [...(inc.value?.updates || [])].sort((a, b) => new Date(b.at) - new Date(a.at))
);

function note(text, ok) {
  msg.value = text || "";
  msgOk.value = !!ok;
}

async function load() {
  loading.value = true;
  notFound.value = false;
  try {
    const data = await get("/api/incidents");
    const found = (data.incidents || []).find((i) => i.id === route.params.id);
    if (!found) {
      notFound.value = true;
      inc.value = null;
    } else {
      inc.value = found;
      draft.value.author = found.owner || "";
    }
  } catch (e) {
    note("加载失败：" + e.message, false);
  } finally {
    loading.value = false;
  }
}

async function changeStatus(status) {
  try {
    await patch(`/api/incidents/${inc.value.id}`, { status });
    await load();
    note("状态已更新", true);
  } catch (e) {
    note("更新失败：" + e.message, false);
  }
}

async function changeSeverity(severity) {
  try {
    await patch(`/api/incidents/${inc.value.id}`, { severity });
    await load();
    note("严重程度已更新", true);
  } catch (e) {
    note("更新失败：" + e.message, false);
  }
}

async function changeOwner() {
  try {
    await patch(`/api/incidents/${inc.value.id}`, { owner: draft.value.author || inc.value.owner });
    await load();
    note("处理人已更新", true);
  } catch (e) {
    note("更新失败：" + e.message, false);
  }
}

function fillTemplate(status) {
  draft.value.status = status;
  draft.value.text = TEMPLATES[status] || "";
}

async function publish() {
  if (!draft.value.text.trim()) {
    note("请填写进度说明", false);
    return;
  }
  try {
    await post(`/api/incidents/${inc.value.id}/updates`, {
      status: draft.value.status,
      text: draft.value.text,
      author: draft.value.author || ""
    });
    draft.value.text = "";
    await load();
    note("已发布", true);
  } catch (e) {
    note("发布失败：" + e.message, false);
  }
}

async function remove() {
  if (!confirm("确定删除这个工单？删除后不可恢复。")) return;
  try {
    await del(`/api/incidents/${inc.value.id}`);
    router.push({ name: "tickets" });
  } catch (e) {
    alert(e.message);
  }
}

function duration() {
  if (!inc.value) return "";
  const start = new Date(inc.value.startedAt).getTime();
  const end = inc.value.resolvedAt ? new Date(inc.value.resolvedAt).getTime() : Date.now();
  const mins = Math.max(0, Math.round((end - start) / 60000));
  if (mins < 60) return mins + " 分钟";
  const h = Math.floor(mins / 60);
  const m = mins % 60;
  return m ? `${h} 小时 ${m} 分` : `${h} 小时`;
}

onMounted(load);
watch(() => route.params.id, load);
</script>

<template>
  <div class="page-head">
    <a class="back" @click="router.push({ name: 'tickets' })">‹ 返回工单列表</a>
  </div>

  <p v-if="loading" class="empty">加载中…</p>
  <p v-else-if="notFound" class="empty">没有找到这个工单（可能已被删除）。</p>

  <template v-else-if="inc">
    <div class="card">
      <div class="t-title-row">
        <span class="badge" :class="inc.status">{{ STATUS_LABEL[inc.status] || inc.status }}</span>
        <span class="sev-tag" :class="severityClass(inc.severity)">{{ severityLabel(inc.severity) }}</span>
        <h2 class="t-title">{{ inc.title }}</h2>
      </div>
      <p v-if="inc.titleEn" class="sub">{{ inc.titleEn }}</p>

      <div class="t-meta">
        {{ fmt(inc.startedAt) }}
        <template v-if="inc.resolvedAt"> → {{ fmt(inc.resolvedAt) }}</template>
        · 持续 {{ duration() }} · 更新 {{ (inc.updates || []).length }} 条
        <template v-if="inc.auto"> · 自动创建</template>
      </div>

      <p v-if="inc.summary" class="summary">{{ inc.summary }}</p>

      <div class="chips" style="margin-top: 10px">
        <span v-for="name in inc.affected || []" :key="name" class="chip on">{{ name }}</span>
        <span v-if="!(inc.affected || []).length" class="muted">未指定受影响组件</span>
      </div>
    </div>

    <div class="card">
      <h2>基础操作</h2>
      <div class="ops">
        <div>
          <label>状态</label>
          <select :value="inc.status" @change="changeStatus($event.target.value)">
            <option v-for="(label, key) in STATUS_LABEL" :key="key" :value="key">{{ label }}</option>
          </select>
        </div>
        <div>
          <label>严重程度</label>
          <select :value="inc.severity" @change="changeSeverity($event.target.value)">
            <option v-for="o in SEVERITY_OPTIONS" :key="o.value" :value="o.value">{{ o.label }}</option>
          </select>
        </div>
        <div>
          <label>处理人</label>
          <div class="inline">
            <input v-model="draft.author" type="text" placeholder="值班人" />
            <button @click="changeOwner">保存</button>
          </div>
        </div>
      </div>
      <div class="row-actions" style="margin-top: 12px">
        <button class="danger" @click="remove">删除工单</button>
        <span class="msg" :class="msgOk ? 'ok' : 'err'">{{ msg }}</span>
      </div>
    </div>

    <div class="card">
      <h2>发布进度</h2>
      <div class="ops">
        <div>
          <label>状态</label>
          <select v-model="draft.status" @change="fillTemplate(draft.status)">
            <option v-for="(label, key) in STATUS_LABEL" :key="key" :value="key">{{ label }}</option>
          </select>
        </div>
      </div>
      <label>说明</label>
      <textarea v-model="draft.text" rows="4" placeholder="填写本次进度说明"></textarea>
      <div class="row-actions">
        <button class="primary" @click="publish">发布</button>
        <button v-for="(tpl, key) in TEMPLATES" :key="key" class="tpl-btn" @click="fillTemplate(key)">
          {{ STATUS_LABEL[key] }}
        </button>
      </div>
    </div>

    <div class="card">
      <h2>更新记录</h2>
      <p v-if="!updList.length" class="empty">还没有更新</p>
      <div v-for="(u, i) in updList" :key="i" class="upd">
        <div class="upd-h">
          <span class="badge" :class="u.status || inc.status">{{ STATUS_LABEL[u.status] || STATUS_LABEL[inc.status] }}</span>
          <span class="muted">{{ fmt(u.at) }}<template v-if="u.author"> · {{ u.author }}</template></span>
        </div>
        <div class="upd-text">{{ u.text }}</div>
        <div v-if="u.textEn" class="upd-text muted">{{ u.textEn }}</div>
      </div>
    </div>
  </template>
</template>

<style scoped>
.back {
  font-size: 12.5px;
  color: var(--ink-3);
  cursor: pointer;
}

.back:hover {
  color: var(--ink);
}

.t-title-row {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.t-title {
  margin: 0;
  font-size: 17px;
  font-weight: 700;
}

.sub {
  margin: 4px 0 0;
  font-size: 12.5px;
  color: var(--ink-2);
}

.t-meta {
  font-size: 11.5px;
  color: var(--ink-3);
  margin-top: 8px;
}

.summary {
  font-size: 13px;
  line-height: 1.7;
  margin: 10px 0 0;
}

.ops {
  display: flex;
  gap: 14px;
  flex-wrap: wrap;
}

.ops > div {
  flex: 1 1 180px;
  min-width: 160px;
}

.inline {
  display: flex;
  gap: 6px;
}

.inline button {
  flex: 0 0 auto;
}

.tpl-btn {
  font-size: 12px;
  padding: 4px 10px;
  border-radius: 999px;
  color: var(--ink-2);
}

.upd {
  border-bottom: 1px solid var(--line);
  padding: 10px 0;
}

.upd:last-child {
  border-bottom: none;
}

.upd-h {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
}

.upd-text {
  font-size: 12.5px;
  margin-top: 5px;
  line-height: 1.65;
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
