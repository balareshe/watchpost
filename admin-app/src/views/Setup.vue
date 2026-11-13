<script setup>
import { ref, onMounted } from "vue";
import { get, post } from "../api";

const emit = defineEmits(["done"]);

const token = ref("");
const email = ref("");
const smtpHost = ref("");
const smtpPort = ref(465);
const smtpUser = ref("");
const smtpPass = ref("");
const smtpFrom = ref("");
const smtpSecure = ref(true);
const msg = ref("");
const msgOk = ref(false);
const busy = ref(false);

function note(text, ok) {
  msg.value = text || "";
  msgOk.value = !!ok;
}

async function submit() {
  if (busy.value) return;
  if (!token.value.trim()) {
    note("请填写初始化令牌（见容器日志）", false);
    return;
  }
  if (!email.value.trim() || !email.value.includes("@")) {
    note("请填写有效的管理员邮箱", false);
    return;
  }
  busy.value = true;
  try {
    const body = {
      token: token.value.trim(),
      email: email.value.trim(),
      smtp: smtpHost.value.trim()
        ? {
            smtpHost: smtpHost.value.trim(),
            smtpPort: Number(smtpPort.value) || 465,
            smtpUser: smtpUser.value.trim(),
            smtpPass: smtpPass.value,
            smtpFrom: smtpFrom.value.trim(),
            smtpSecure: smtpSecure.value
          }
        : null
    };
    const res = await post("/api/setup", body);
    note("初始化完成，正在进入后台…", true);
    emit("done", res);
  } catch (e) {
    note(e.message, false);
  } finally {
    busy.value = false;
  }
}

onMounted(async () => {
  try {
    const res = await get("/api/setup");
    if (!res.needed) emit("done", null);
  } catch {
    /* 探测失败时保持安装页，提交时后端会再次校验 */
  }
});
</script>

<template>
  <div class="login-wrap">
    <div class="login-card setup-card">
      <h1>首次安装</h1>
      <p class="sub">创建第一个管理员账号，并可选配置邮件服务</p>

      <div class="setup-hint">
        初始化令牌已打印在服务启动日志中：
        <code>{{ "docker compose logs status-api" }}</code>
      </div>

      <label>初始化令牌</label>
      <input v-model="token" type="text" placeholder="启动日志里的那串字符" autocomplete="off" />

      <label>管理员邮箱</label>
      <input v-model="email" type="text" placeholder="you@example.com" autocomplete="username" />
      <p class="muted setup-note">登录后台用这个邮箱接收验证码，不设密码。</p>

      <h2 class="setup-section">邮件服务（可选，可稍后在后台配置）</h2>
      <div class="row2">
        <div><label>SMTP 服务器</label><input v-model="smtpHost" type="text" placeholder="smtp.example.com" /></div>
        <div><label>端口</label><input v-model="smtpPort" type="number" placeholder="465" /></div>
      </div>
      <div class="row2">
        <div><label>账号</label><input v-model="smtpUser" type="text" placeholder="noreply@example.com" /></div>
        <div><label>密码 / 授权码</label><input v-model="smtpPass" type="password" autocomplete="new-password" /></div>
      </div>
      <div class="row2">
        <div><label>发件人（可空）</label><input v-model="smtpFrom" type="text" placeholder="默认与账号相同" /></div>
        <div>
          <label>加密方式</label>
          <select v-model="smtpSecure">
            <option :value="true">SSL（465，推荐）</option>
            <option :value="false">STARTTLS（587）</option>
          </select>
        </div>
      </div>
      <p class="muted setup-note">
        不填也能完成安装，之后在后台「通知」页补配；但没配好之前收不到验证码，只能用日志里的验证码登录。
      </p>

      <div class="row-actions">
        <button class="primary" :disabled="busy" @click="submit">完成安装</button>
        <span class="msg" :class="msgOk ? 'ok' : 'err'">{{ msg }}</span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.setup-card {
  max-width: 520px;
}

.setup-hint {
  font-size: 12px;
  line-height: 1.7;
  color: var(--ink-3);
  background: #f7f8f9;
  border: 1px solid var(--line);
  border-radius: 8px;
  padding: 8px 10px;
  margin-bottom: 12px;
}

.setup-hint code {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 11.5px;
  color: var(--ink-2);
}

.setup-note {
  font-size: 11.5px;
  margin: 4px 0 10px;
}

.setup-section {
  font-size: 13px;
  margin: 18px 0 8px;
  padding-top: 12px;
  border-top: 1px solid var(--line);
}
</style>
