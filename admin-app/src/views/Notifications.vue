<script setup>
import { ref, computed, onMounted } from "vue";
import { get, post } from "../api";

const msg = ref("");
const msgOk = ref(false);
const testMsg = ref("");
const testOk = ref(false);
const loading = ref(true);
const recipients = ref([]);

const VARS = ["{site}", "{title}", "{components}", "{severity}", "{summary}", "{status}", "{time}", "{url}"];

const form = ref({
  enabled: false,
  smtpHost: "",
  smtpPort: 465,
  smtpUser: "",
  smtpPass: "",
  smtpFrom: "",
  smtpSecure: true,
  subject: "[{site}] {title}",
  body: ""
});

const testEmail = ref("");

function note(text, ok) {
  msg.value = text || "";
  msgOk.value = !!ok;
}

function noteTest(text, ok) {
  testMsg.value = text || "";
  testOk.value = !!ok;
}

async function load() {
  loading.value = true;
  try {
    const data = await get("/api/settings/full");
    const n = data.notify || {};
    form.value = {
      enabled: !!n.enabled,
      smtpHost: n.smtpHost || "",
      smtpPort: n.smtpPort || 465,
      smtpUser: n.smtpUser || "",
      smtpPass: n.smtpPass || "",
      smtpFrom: n.smtpFrom || "",
      smtpSecure: n.smtpSecure !== false,
      subject: n.subject || "[{site}] {title}",
      body: n.body || ""
    };
    const users = await get("/api/users").catch(() => ({ users: [] }));
    recipients.value = (users.users || []).filter((u) => u.enabled !== false).map((u) => u.email);
    if (!testEmail.value && recipients.value.length) testEmail.value = recipients.value[0];
  } catch (e) {
    note("加载失败：" + e.message, false);
  } finally {
    loading.value = false;
  }
}

async function save() {
  try {
    await post("/api/settings", { notify: { ...form.value, smtpPort: Number(form.value.smtpPort) || 465 } });
    note("已保存", true);
  } catch (e) {
    note("保存失败：" + e.message, false);
  }
}

async function sendTest() {
  if (!testEmail.value) {
    noteTest("请填写测试收件邮箱", false);
    return;
  }
  try {
    const res = await post("/api/settings/test", { email: testEmail.value });
    noteTest(res.message || "已发送", true);
  } catch (e) {
    noteTest(e.message, false);
  }
}

function insertVar(target, v) {
  if (target === "subject") form.value.subject += v;
  else form.value.body += v;
}

const preview = computed(() => {
  const map = {
    "{site}": "站点状态",
    "{title}": "主站 无法访问",
    "{components}": "主站、应用",
    "{severity}": "不可用",
    "{summary}": "监控发现连续探测失败，已开始排查。",
    "{status}": "investigating",
    "{time}": "2026-11-12 22:10",
    "{url}": "https://status.example.com/incident.html?id=xxx"
  };
  let out = form.value.body || "";
  Object.keys(map).forEach((k) => {
    out = out.split(k).join(map[k]);
  });
  return out;
});

onMounted(load);
</script>

<template>
  <div class="page-head"><h1>通知</h1><span>发现异常时自动发邮件给所有启用账号</span></div>

  <div class="card">
    <h2>开关注释</h2>
    <label class="inline">
      <input v-model="form.enabled" type="checkbox" />
      <span>启用事件邮件通知（新建事件时自动发送）</span>
    </label>
    <p class="muted" style="margin-top: 8px">
      收件人：<strong>{{ recipients.length }} 个已启用账号</strong>
      <template v-if="recipients.length">（{{ recipients.join("、") }}）</template>
    </p>
  </div>

  <div class="card">
    <h2>邮件服务器</h2>
    <p v-if="loading" class="empty">加载中…</p>
    <template v-else>
      <div class="row2">
        <div><label>SMTP 服务器</label><input v-model="form.smtpHost" type="text" placeholder="smtp.example.com" /></div>
        <div><label>端口</label><input v-model="form.smtpPort" type="number" placeholder="465" /></div>
      </div>
      <div class="row2">
        <div><label>账号</label><input v-model="form.smtpUser" type="text" placeholder="noreply@example.com" /></div>
        <div><label>密码 / 授权码</label><input v-model="form.smtpPass" type="text" placeholder="留空则沿用服务器环境变量" /></div>
      </div>
      <div class="row2">
        <div><label>发件人（可空）</label><input v-model="form.smtpFrom" type="text" placeholder="默认与账号相同" /></div>
        <div>
          <label>加密方式</label>
          <select v-model="form.smtpSecure">
            <option :value="true">SSL（465，推荐）</option>
            <option :value="false">STARTTLS（587）</option>
          </select>
        </div>
      </div>
    </template>
  </div>

  <div class="card">
    <h2>邮件模板</h2>
    <label>主题</label>
    <input v-model="form.subject" type="text" />
    <div class="vars">
      <span v-for="v in VARS" :key="v" class="var" @click="insertVar('subject', v)">{{ v }}</span>
    </div>

    <label>正文</label>
    <textarea v-model="form.body" rows="8"></textarea>
    <div class="vars">
      <span v-for="v in VARS" :key="v" class="var" @click="insertVar('body', v)">{{ v }}</span>
    </div>

    <label>效果预览</label>
    <pre class="preview-body">{{ preview }}</pre>

    <div class="row-actions">
      <button class="primary" @click="save">保存</button>
      <span class="msg" :class="msgOk ? 'ok' : 'err'">{{ msg }}</span>
    </div>
  </div>

  <div class="card">
    <h2>测试发送</h2>
    <div class="row2">
      <div><label>收件邮箱</label><input v-model="testEmail" type="text" /></div>
      <div style="display: flex; align-items: flex-end; gap: 8px">
        <button @click="sendTest">发送测试邮件</button>
        <span class="msg" :class="testOk ? 'ok' : 'err'">{{ testMsg }}</span>
      </div>
    </div>
    <p class="muted" style="margin-top: 10px">测试发送使用「已保存」的配置，改完记得先保存。</p>
  </div>
</template>

<style scoped>
.vars {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 6px;
}

.var {
  font-size: 11.5px;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  border: 1px solid var(--line);
  border-radius: 5px;
  padding: 1px 6px;
  cursor: pointer;
  color: var(--ink-2);
  background: #fafbfb;
}

.var:hover {
  border-color: #9aa4ae;
  color: var(--ink);
}

.preview-body {
  margin: 6px 0 0;
  padding: 10px 12px;
  background: #f7f8f9;
  border: 1px solid var(--line);
  border-radius: 8px;
  font-size: 12.5px;
  line-height: 1.65;
  color: var(--ink-2);
  white-space: pre-wrap;
  font-family: inherit;
}
</style>
