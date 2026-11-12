<script setup>
import { ref, onMounted } from "vue";
import { get, post } from "../api";

const msg = ref("");
const msgOk = ref(false);
const loading = ref(true);
const form = ref({
  siteName: "",
  pageTitle: "",
  subtitle: "",
  favicon: "",
  slowMs: 800,
  templates: {}
});

const DEFAULT_TPL = {
  downTitle: "{name} 无法访问（{time} 起）",
  downSummary: "自动监控发现「{name}」无法正常访问：连续 {fails} 次探测失败，立即重试 {retries} 次仍未恢复，异常始于 {startedAt}。已自动创建工单，等待值班确认。",
  downUpdate: "最近一次探测：{status}，{cost}。自动监控已创建工单。",
  slowTitle: "{name} 响应变慢（{time} 起）",
  slowSummary: "自动监控发现「{name}」响应变慢：连续 {streak} 次探测耗时超过 {threshold} ms，最近一次 {lastMs} ms。可用性未受影响，已记录以便观察。",
  slowUpdate: "最近一次探测 {lastMs} ms，超过阈值 {threshold} ms。"
};

const VARS_DOWN = ["{name}", "{time}", "{startedAt}", "{fails}", "{retries}", "{status}", "{cost}"];
const VARS_SLOW = ["{name}", "{time}", "{streak}", "{threshold}", "{lastMs}"];

const FAVICON_PRESETS = ["📊", "🟢", "🛰", "🌐", "⚡", "🔧", "📡", "🩺"];

function note(text, ok) {
  msg.value = text || "";
  msgOk.value = !!ok;
}

async function load() {
  loading.value = true;
  try {
    const data = await get("/api/settings/full");
    form.value = {
      siteName: data.siteName || "",
      pageTitle: data.pageTitle || "",
      subtitle: data.subtitle || "",
      favicon: data.favicon || "",
      slowMs: data.slowMs == null ? 800 : data.slowMs,
      templates: { ...DEFAULT_TPL, ...(data.templates || {}) }
    };
  } catch (e) {
    note("加载失败：" + e.message, false);
  } finally {
    loading.value = false;
  }
}

async function save() {
  try {
    await post("/api/settings", form.value);
    note("已保存，状态页刷新后生效", true);
  } catch (e) {
    note("保存失败：" + e.message, false);
  }
}

function useIcon(icon) {
  form.value.favicon = icon;
}

onMounted(load);
</script>

<template>
  <div class="page-head"><h1>系统设置</h1><span>站点对外展示的名称与标题</span></div>

  <div class="card">
    <h2>站点信息</h2>
    <p v-if="loading" class="empty">加载中…</p>
    <template v-else>
      <label>站点名称（页面左上角显示）</label>
      <input v-model="form.siteName" type="text" placeholder="站点状态" />

      <label>浏览器标题（标签页显示）</label>
      <input v-model="form.pageTitle" type="text" placeholder="站点状态" />

      <label>副标题（名称下方的说明文字）</label>
      <input v-model="form.subtitle" type="text" placeholder="数据每 30 秒刷新一次" />

      <label>慢响应阈值（毫秒，超过则显示黄色）</label>
      <input v-model.number="form.slowMs" type="number" min="100" step="50" placeholder="800" />
      <p class="muted" style="margin-top: 4px">节点仍可用但延迟 ≥ 该值时，状态会显示为黄色「部分服务响应较慢」；填 0 关闭。</p>

      <label>站点图标（emoji 或图片 URL）</label>
      <input v-model="form.favicon" type="text" placeholder="📊 或 https://example.com/icon.png" />
      <div class="chips" style="margin-top: 8px">
        <span v-for="icon in FAVICON_PRESETS" :key="icon" class="chip" @click="useIcon(icon)">{{ icon }}</span>
        <span class="chip" @click="useIcon('')">清空</span>
      </div>

      <h2 class="section-title">自动工单文案模板</h2>
      <p class="muted" style="margin: 0 0 8px">
        自动开工单时按模板生成文案。占位符会被替换成实际值，留空则使用默认模板。
      </p>

      <label>故障工单标题</label>
      <input v-model="form.templates.downTitle" type="text" />
      <div class="vars"><span v-for="v in VARS_DOWN" :key="v" class="var" @click="form.templates.downTitle += v">{{ v }}</span></div>

      <label>故障工单摘要</label>
      <textarea v-model="form.templates.downSummary" rows="3"></textarea>
      <div class="vars"><span v-for="v in VARS_DOWN" :key="v" class="var" @click="form.templates.downSummary += v">{{ v }}</span></div>

      <label>故障工单首条进度</label>
      <input v-model="form.templates.downUpdate" type="text" />
      <div class="vars"><span v-for="v in VARS_DOWN" :key="v" class="var" @click="form.templates.downUpdate += v">{{ v }}</span></div>

      <label>慢响应工单标题</label>
      <input v-model="form.templates.slowTitle" type="text" />
      <div class="vars"><span v-for="v in VARS_SLOW" :key="v" class="var" @click="form.templates.slowTitle += v">{{ v }}</span></div>

      <label>慢响应工单摘要</label>
      <textarea v-model="form.templates.slowSummary" rows="3"></textarea>
      <div class="vars"><span v-for="v in VARS_SLOW" :key="v" class="var" @click="form.templates.slowSummary += v">{{ v }}</span></div>

      <label>慢响应工单首条进度</label>
      <input v-model="form.templates.slowUpdate" type="text" />
      <div class="vars"><span v-for="v in VARS_SLOW" :key="v" class="var" @click="form.templates.slowUpdate += v">{{ v }}</span></div>

      <div class="row-actions">
        <button class="primary" @click="save">保存</button>
        <span class="msg" :class="msgOk ? 'ok' : 'err'">{{ msg }}</span>
      </div>
    </template>
  </div>

  <div class="card">
    <h2>预览</h2>
    <div class="preview">
      <div class="preview-brand">
        <span class="preview-icon">{{ form.favicon && !form.favicon.startsWith("http") ? form.favicon : "📄" }}</span>
        <div>
          <div class="preview-name">{{ form.siteName || "站点名称" }}</div>
          <div class="preview-sub">{{ form.subtitle || "副标题" }}</div>
        </div>
      </div>
      <div class="preview-tab">标签页：{{ form.pageTitle || "浏览器标题" }}</div>
    </div>
  </div>
</template>

<style scoped>
.vars {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 4px;
}

.var {
  font-size: 11px;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  border: 1px solid var(--line);
  border-radius: 5px;
  padding: 0 6px;
  cursor: pointer;
  color: var(--ink-2);
  background: #fafbfb;
}

.var:hover {
  border-color: #9aa4ae;
  color: var(--ink);
}

.section-title {
  margin-top: 22px;
  padding-top: 14px;
  border-top: 1px solid var(--line);
}

.preview {
  border: 1px dashed var(--line);
  border-radius: 8px;
  padding: 14px;
}

.preview-brand {
  display: flex;
  align-items: center;
  gap: 10px;
}

.preview-icon {
  font-size: 22px;
}

.preview-name {
  font-size: 15px;
  font-weight: 700;
}

.preview-sub {
  font-size: 12px;
  color: var(--ink-3);
  margin-top: 2px;
}

.preview-tab {
  margin-top: 12px;
  font-size: 12px;
  color: var(--ink-3);
  border-top: 1px solid var(--line);
  padding-top: 10px;
}
</style>
