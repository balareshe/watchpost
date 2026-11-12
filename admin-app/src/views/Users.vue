<script setup>
import { ref, onMounted } from "vue";
import { get, post, patch, del, fmt } from "../api";
import { session, isAdmin, roleLabel } from "../store";

const list = ref([]);
const msg = ref("");
const msgOk = ref(false);
const form = ref({ email: "", role: "viewer", name: "" });

function roleClass(role) {
  return role === "admin" ? "monitoring" : role === "maintainer" ? "investigating" : "resolved";
}

function note(text, ok) {
  msg.value = text || "";
  msgOk.value = !!ok;
}

async function load() {
  try {
    const data = await get("/api/users");
    list.value = data.users || [];
  } catch (e) {
    note("加载失败：" + e.message, false);
  }
}

async function add() {
  if (!form.value.email.includes("@")) {
    note("请填写正确邮箱", false);
    return;
  }
  try {
    await post("/api/users", form.value);
    note("已添加", true);
    form.value = { email: "", role: "viewer", name: "" };
    load();
  } catch (e) {
    note("失败：" + e.message, false);
  }
}

async function saveRole(id, role) {
  try {
    await patch(`/api/users/${id}`, { role });
    load();
  } catch (e) {
    alert(e.message);
  }
}

async function toggle(id, enabled) {
  try {
    await patch(`/api/users/${id}`, { enabled: !enabled });
    load();
  } catch (e) {
    alert(e.message);
  }
}

async function remove(id) {
  if (!confirm("删除该用户？其登录会话会立即失效。")) return;
  try {
    await del(`/api/users/${id}`);
    load();
  } catch (e) {
    alert(e.message);
  }
}

onMounted(load);
</script>

<template>
  <div class="page-head">
    <h1>用户</h1>
    <span>{{ list.length ? "共 " + list.length + " 人" : "" }}</span>
  </div>

  <div v-if="isAdmin()" class="card">
    <h2>添加用户</h2>
    <div class="row2">
      <div><label>邮箱</label><input v-model="form.email" type="text" placeholder="someone@example.com" /></div>
      <div>
        <label>角色</label>
        <select v-model="form.role">
          <option value="admin">管理员（全部权限）</option>
          <option value="maintainer">维护人员（可操作，不能管账号）</option>
          <option value="viewer">只读（只能看概览）</option>
        </select>
      </div>
    </div>
    <label>备注名（可空）</label>
    <input v-model="form.name" type="text" placeholder="例如：值班同事" />
    <div class="row-actions">
      <button class="primary" @click="add">添加</button>
      <span class="msg" :class="msgOk ? 'ok' : 'err'">{{ msg }}</span>
    </div>
  </div>

  <div class="card">
    <h2>已授权用户</h2>
    <p v-if="!list.length" class="empty">还没有用户</p>
    <div v-for="u in list" :key="u.id" class="item">
      <div class="item-h">
        <span class="badge" :class="roleClass(u.role)">{{ roleLabel(u.role) }}</span>
        {{ u.email }}
        <span v-if="u.email.toLowerCase() === (session.email || '').toLowerCase()" class="muted">（当前账号）</span>
      </div>
      <div class="item-s">
        <template v-if="u.name">{{ u.name }} · </template>
        加入 {{ fmt(u.createdAt) }} · 最后登录 {{ u.lastLoginAt ? fmt(u.lastLoginAt) : "从未" }}
        <template v-if="u.enabled === false"> · 已停用</template>
      </div>
      <div v-if="isAdmin()" class="row-actions">
        <select :value="u.role" @change="saveRole(u.id, $event.target.value)">
          <option value="admin">管理员</option>
          <option value="maintainer">维护人员</option>
          <option value="viewer">只读</option>
        </select>
        <button @click="toggle(u.id, u.enabled !== false)">{{ u.enabled === false ? "启用" : "停用" }}</button>
        <button
          v-if="u.email.toLowerCase() !== (session.email || '').toLowerCase()"
          class="danger"
          @click="remove(u.id)"
        >删除</button>
      </div>
    </div>
  </div>
</template>
