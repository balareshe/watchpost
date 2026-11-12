<script setup>
import { onMounted, watch } from "vue";
import { useRouter, useRoute } from "vue-router";
import { ref } from "vue";
import { session, loadSession, logout, isAdmin, canWrite, isViewer } from "./store";
import { get } from "./api";
import Login from "./views/Login.vue";

const router = useRouter();
const route = useRoute();
const version = ref("");

// 每个页面允许的角色
const ALLOWED = {
  dash: ["admin", "maintainer", "viewer"],
  tickets: ["admin", "maintainer"],
  ticket: ["admin", "maintainer"],
  incidents: ["admin", "maintainer"],
  announcements: ["admin", "maintainer"],
  maintenance: ["admin", "maintainer"],
  nodes: ["admin", "maintainer"],
  users: ["admin"],
  site: ["admin"],
  notifications: ["admin"],
  settings: ["admin", "maintainer", "viewer"]
};

const NAV = [
  { name: "dash", label: "概览" },
  { name: "tickets", label: "工单" },
  { name: "incidents", label: "事件" },
  { name: "announcements", label: "公告" },
  { name: "maintenance", label: "维护" },
  { name: "nodes", label: "节点" },
  { name: "users", label: "用户" },
  { name: "site", label: "系统设置" },
  { name: "notifications", label: "通知" },
  { name: "settings", label: "设置" }
];

onMounted(async () => {
  await loadSession();
  get("/api/health").then((h) => { version.value = h.version || ""; }).catch(() => {});
  window.addEventListener("auth:expired", () => {
    session.authed = false;
  });
});

watch(
  [() => route.name, () => session.role, () => session.authed],
  () => {
    if (!session.authed) return;
    const roles = ALLOWED[route.name] || ["admin"];
    if (!roles.includes(session.role)) router.replace({ name: "dash" });
  },
  { immediate: true }
);

function visible(item) {
  const roles = ALLOWED[item.name] || ["admin"];
  return roles.includes(session.role);
}

function go(name) {
  router.push({ name });
}

async function doLogout() {
  await logout();
  router.push({ name: "dash" });
}
</script>

<template>
  <div v-if="!session.ready" class="booting">加载中…</div>

  <Login v-else-if="!session.authed" />

  <div v-else class="shell">
    <aside class="side">
      <div class="side-brand">
        站点状态
        <span>事件 · 公告 · 维护 · 节点</span>
      </div>

      <nav>
        <button
          v-for="item in NAV.filter(visible)"
          :key="item.name"
          :class="{ on: route.name === item.name }"
          @click="go(item.name)"
        >{{ item.label }}</button>
      </nav>

      <div class="side-foot">
        <div class="side-user">{{ session.email }}</div>
        <button class="link" @click="doLogout">退出登录</button>
        <a href="/" target="_blank" rel="noopener">查看站点 ›</a>
        <span class="ver">v{{ version }}</span>
      </div>
    </aside>

    <main class="content">
      <div v-if="isViewer()" class="readonly-note">
        当前账号为<strong>只读</strong>，只能查看概览。需要操作请联系管理员。
      </div>
      <router-view />
    </main>
  </div>
</template>
