<script setup>
import { ref, onMounted } from "vue";
import { get, post, del, fmt } from "../api";
import { canWrite } from "../store";

const list = ref([]);
const msg = ref("");
const msgOk = ref(false);
const form = ref({ title: "", body: "", level: "info", pinned: false });

function note(text, ok) {
  msg.value = text || "";
  msgOk.value = !!ok;
}

async function load() {
  try {
    const data = await get("/api/announcements");
    list.value = data.announcements || [];
  } catch (e) {
    note("加载失败：" + e.message, false);
  }
}

async function create() {
  if (!canWrite()) return;
  try {
    await post("/api/announcements", form.value);
    note("已发布", true);
    form.value = { title: "", body: "", level: "info", pinned: false };
    load();
  } catch (e) {
    note("失败：" + e.message, false);
  }
}

async function remove(id) {
  if (!confirm("删除这条公告？")) return;
  try {
    await del(`/api/announcements/${id}`);
    load();
  } catch (e) {
    alert(e.message);
  }
}

onMounted(load);
</script>

<template>
  <div class="page-head">
    <h1>公告</h1>
    <span>{{ list.length ? "共 " + list.length + " 条" : "" }}</span>
  </div>

  <div v-if="canWrite()" class="card">
    <h2>发布公告</h2>
    <div class="row2">
      <div><label>标题</label><input v-model="form.title" type="text" placeholder="例如：本周六凌晨例行维护" /></div>
      <div>
        <label>级别</label>
        <select v-model="form.level">
          <option value="info">普通</option>
          <option value="warning">重要（橙色）</option>
        </select>
      </div>
    </div>
    <label>正文</label>
    <textarea v-model="form.body" placeholder="公告内容，支持换行"></textarea>
    <label class="inline"><input v-model="form.pinned" type="checkbox" /> 置顶</label>
    <div class="row-actions">
      <button class="primary" @click="create">发布公告</button>
      <span class="msg" :class="msgOk ? 'ok' : 'err'">{{ msg }}</span>
    </div>
  </div>

  <div class="card">
    <h2>已发布</h2>
    <p v-if="!list.length" class="empty">还没有公告</p>
    <div v-for="a in list" :key="a.id" class="item">
      <div class="item-h">
        <span v-if="a.pinned" class="badge monitoring">置顶</span>
        {{ a.title }}
      </div>
      <div class="item-s">{{ fmt(a.createdAt) }} · {{ a.level === "warning" ? "重要" : "普通" }}</div>
      <p v-if="a.body" class="body-text">{{ a.body }}</p>
      <div v-if="canWrite()" class="row-actions">
        <button class="danger" @click="remove(a.id)">删除</button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.body-text {
  font-size: 12.5px;
  color: var(--ink-2);
  white-space: pre-wrap;
  margin: 6px 0 0;
  line-height: 1.65;
}
</style>
