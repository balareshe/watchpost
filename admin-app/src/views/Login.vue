<script setup>
import { ref, onMounted, onBeforeUnmount } from "vue";
import { post } from "../api";
import { login } from "../store";

const email = ref(localStorage.getItem("status_admin_email") || "");
const code = ref("");
const note = ref("");
const ok = ref(false);
const busy = ref(false);
const cooldown = ref(0);
let timer = null;

onMounted(() => {
  if (email.value) sendCode();
});

onBeforeUnmount(() => timer && clearInterval(timer));

function setNote(text, good) {
  note.value = text || "";
  ok.value = !!good;
}

function tick() {
  timer && clearInterval(timer);
  timer = setInterval(() => {
    cooldown.value -= 1;
    if (cooldown.value <= 0) {
      clearInterval(timer);
      timer = null;
    }
  }, 1000);
}

async function sendCode() {
  if (busy.value || cooldown.value > 0) return;
  if (!email.value) {
    setNote("请填写邮箱", false);
    return;
  }
  busy.value = true;
  try {
    const res = await post("/api/auth/request-code", { email: email.value.trim() });
    setNote(res.message || "验证码已发送", true);
    localStorage.setItem("status_admin_email", email.value.trim());
    if (res.devCode) {
      setNote("开发模式验证码：" + res.devCode, true);
      code.value = res.devCode;
    }
    cooldown.value = 60;
    tick();
  } catch (e) {
    const wait = /(\d+)\s*秒后再试/.exec(e.message);
    if (wait) {
      cooldown.value = parseInt(wait[1], 10);
      tick();
    }
    setNote(e.message, false);
  } finally {
    busy.value = false;
  }
}

async function doLogin() {
  if (!email.value || !code.value) {
    setNote("请填写邮箱和验证码", false);
    return;
  }
  busy.value = true;
  try {
    await login(email.value.trim(), code.value.trim());
    setNote("", false);
  } catch (e) {
    setNote(e.message, false);
  } finally {
    busy.value = false;
  }
}
</script>

<template>
  <div class="login-wrap">
    <div class="login-card">
      <h1>站点后台登录</h1>
      <p class="sub">使用管理员邮箱接收验证码</p>

      <label>邮箱</label>
      <div class="login-step">
        <input v-model="email" type="text" placeholder="you@example.com" autocomplete="username" />
        <button :disabled="busy || cooldown > 0" @click="sendCode">
          {{ cooldown > 0 ? cooldown + "s 后重发" : "发送验证码" }}
        </button>
      </div>

      <label>验证码</label>
      <div class="login-step">
        <input
          v-model="code"
          type="text"
          inputmode="numeric"
          maxlength="6"
          placeholder="6 位数字"
          autocomplete="one-time-code"
          @keydown.enter="doLogin"
        />
        <button class="primary" :disabled="busy" @click="doLogin">登录</button>
      </div>

      <div class="login-note" :class="{ ok: ok, err: note && !ok }">{{ note }}</div>
    </div>
  </div>
</template>
