<script setup>
import { ref, onMounted } from "vue";
import { get, post, patch, del } from "../api";
import { canWrite } from "../store";

const list = ref([]);
const msg = ref("");
const msgOk = ref(false);
const form = ref({ name: "", url: "", interval: 60 });

function note(text, ok) {
  msg.value = text || "";
  msgOk.value = !!ok;
}

async function load() {
  try {
    const data = await get("/api/nodes");
    list.value = (data.nodes || []).sort((a, b) => (a.order || 0) - (b.order || 0));
  } catch (e) {
    note("加载失败：" + e.message, false);
  }
}

async function move(index, dir) {
  if (!canWrite()) return;
  const target = index + dir;
  if (target < 0 || target >= list.value.length) return;
  const a = list.value[index];
  const b = list.value[target];
  let oa = a.order || 0;
  let ob = b.order || 0;
  if (oa === ob) {
    oa = index * 10 + 10;
    ob = target * 10 + 10;
  }
  try {
    await Promise.all([
      patch(`/api/nodes/${a.id}`, { order: ob }),
      patch(`/api/nodes/${b.id}`, { order: oa })
    ]);
    load();
  } catch (e) {
    alert(e.message);
  }
}

async function add() {
  if (!canWrite()) return;
  if (!form.value.name || !form.value.url) {
    note("名称和地址都要填", false);
    return;
  }
  const maxOrder = list.value.reduce((m, n) => Math.max(m, n.order || 0), 0);
  try {
    await post("/api/nodes", { ...form.value, order: maxOrder + 10 });
    note("已添加", true);
    form.value = { name: "", url: "", interval: 60 };
    load();
  } catch (e) {
    note("失败：" + e.message, false);
  }
}

async function setSlow(id, value) {
  const num = Number(value);
  try {
    await patch(`/api/nodes/${id}`, { slowMs: value === "" || Number.isNaN(num) || num <= 0 ? null : num });
    load();
  } catch (e) {
    alert(e.message);
  }
}

async function remove(id) {
  if (!canWrite()) return;
  if (!confirm("删除这个节点？")) return;
  try {
    await del(`/api/nodes/${id}`);
    load();
  } catch (e) {
    alert(e.message);
  }
}

onMounted(load);
</script>

<template>
  <div class="page-head">
    <h1>节点与排序</h1>
    <span>内置节点由 Gatus 探测；自定义节点由监控端探测</span>
  </div>

  <div class="card">
    <h2>显示顺序</h2>
    <p v-if="!list.length" class="empty">加载中…</p>
    <div v-for="(n, i) in list" :key="n.id" class="item">
      <div class="item-h">
        <span v-if="!n.builtin" class="badge custom">自定义</span>
        {{ n.name }}
      </div>
      <div class="item-s">
        {{ n.url || "内置探针（Gatus）" }} · 间隔 {{ n.interval || 60 }}s · 顺序 {{ n.order || 0 }}
        <template v-if="n.slowMs"> · 慢阈值 {{ n.slowMs }}ms</template>
      </div>
      <div v-if="canWrite()" class="row-actions">
        <button :disabled="i === 0" @click="move(i, -1)">↑ 上移</button>
        <button :disabled="i === list.length - 1" @click="move(i, 1)">↓ 下移</button>
        <input
          class="slow-input"
          type="number"
          min="0"
          step="50"
          :value="n.slowMs || ''"
          placeholder="慢阈值"
          @change="setSlow(n.id, $event.target.value)"
        />
        <button v-if="!n.builtin" class="danger" @click="remove(n.id)">删除</button>
      </div>
    </div>
  </div>

  <div v-if="canWrite()" class="card">
    <h2>添加节点</h2>
    <div class="row2">
      <div><label>节点名称</label><input v-model="form.name" type="text" placeholder="例如：节气画廊" /></div>
      <div><label>地址（完整 URL）</label><input v-model="form.url" type="text" placeholder="https://example.com/health" /></div>
    </div>
    <div class="row2">
      <div><label>探测间隔（秒，≥30）</label><input v-model.number="form.interval" type="number" min="30" /></div>
      <div class="row-actions" style="align-items: flex-end">
        <button class="primary" @click="add">添加节点</button>
        <span class="msg" :class="msgOk ? 'ok' : 'err'">{{ msg }}</span>
      </div>
    </div>
  </div>
</template>
