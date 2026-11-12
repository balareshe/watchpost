<script setup>
import { session, logout, roleLabel } from "../store";
import { useRouter } from "vue-router";

const router = useRouter();

async function doLogout() {
  await logout();
  router.push({ name: "dash" });
}
</script>

<template>
  <div class="page-head"><h1>设置</h1></div>

  <div class="card">
    <h2>当前账号</h2>
    <div class="item">
      <div class="item-h">{{ session.email }}</div>
      <div class="item-s">
        角色：{{ roleLabel(session.role) }} · 登录有效期 7 天，到期需重新验证
      </div>
    </div>
    <div class="row-actions">
      <button class="danger" @click="doLogout">退出登录</button>
    </div>
  </div>

  <div class="card">
    <h2>说明</h2>
    <p class="muted">
      后台只对「用户」页里授权过的邮箱开放。验证码 10 分钟内有效，连续输错 5 次作废；
      同一邮箱 60 秒内只能请求一次，每小时最多 5 次。
    </p>
  </div>
</template>
