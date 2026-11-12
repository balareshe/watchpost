<script setup>
import { ref, computed, onMounted, onBeforeUnmount, watch, nextTick } from "vue";

const props = defineProps({
  modelValue: { type: String, default: "" },
  placeholder: { type: String, default: "选择日期和时间" },
  min: { type: String, default: "" }
});
const emit = defineEmits(["update:modelValue"]);

const WEEK = ["一", "二", "三", "四", "五", "六", "日"];
const root = ref(null);
const open = ref(false);
const view = ref(startOfMonth(new Date()));
const draft = ref({ date: "", hour: "00", minute: "00" });

function pad(n) {
  return String(n).padStart(2, "0");
}

function startOfMonth(d) {
  return new Date(d.getFullYear(), d.getMonth(), 1);
}

function parse(value) {
  if (!value) return null;
  const [d, t = ""] = value.split("T");
  const [y, m, day] = d.split("-").map(Number);
  if (!y || !m || !day) return null;
  const [hh = "00", mm = "00"] = t.split(":");
  return { y, m, day, hour: hh.slice(0, 2), minute: mm.slice(0, 2) };
}

function toValue(dateObj, hour, minute) {
  return `${dateObj.getFullYear()}-${pad(dateObj.getMonth() + 1)}-${pad(dateObj.getDate())}T${hour}:${minute}`;
}

const display = computed(() => {
  const p = parse(props.modelValue);
  if (!p) return "";
  return `${p.y}-${pad(p.m)}-${pad(p.day)} ${p.hour}:${p.minute}`;
});

const hours = Array.from({ length: 24 }, (_, i) => pad(i));
const minutes = Array.from({ length: 12 }, (_, i) => pad(i * 5));

const monthLabel = computed(() => `${view.value.getFullYear()} 年 ${view.value.getMonth() + 1} 月`);

const cells = computed(() => {
  const first = startOfMonth(view.value);
  const offset = (first.getDay() + 6) % 7; // 周一为第一列
  const start = new Date(first);
  start.setDate(first.getDate() - offset);
  const list = [];
  for (let i = 0; i < 42; i += 1) {
    const d = new Date(start);
    d.setDate(start.getDate() + i);
    list.push({
      date: d,
      day: d.getDate(),
      inMonth: d.getMonth() === view.value.getMonth(),
      isToday: sameDay(d, new Date()),
      selected: draft.value.date && sameDay(d, new Date(draft.value.date)),
      disabled: props.min ? d < startOfMonth(new Date(props.min.slice(0, 7) + "-01")) && d.getMonth() < new Date(props.min).getMonth() : false
    });
  }
  return list;
});

function sameDay(a, b) {
  return a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth() && a.getDate() === b.getDate();
}

function openPanel() {
  const p = parse(props.modelValue);
  const base = p ? new Date(p.y, p.m - 1, p.day) : new Date();
  draft.value = {
    date: p ? toValue(base, p.hour, p.minute) : "",
    hour: p ? p.hour : pad(new Date().getHours()),
    minute: p ? p.minute : pad(Math.floor(new Date().getMinutes() / 5) * 5)
  };
  view.value = startOfMonth(base);
  open.value = true;
  nextTick(() => document.addEventListener("mousedown", onOutside));
}

function close() {
  open.value = false;
  document.removeEventListener("mousedown", onOutside);
}

function onOutside(ev) {
  if (root.value && !root.value.contains(ev.target)) close();
}

function shiftMonth(delta) {
  view.value = new Date(view.value.getFullYear(), view.value.getMonth() + delta, 1);
}

function pick(cell) {
  draft.value.date = toValue(cell.date, draft.value.hour, draft.value.minute);
}

function setTime(part, value) {
  draft.value[part] = value;
  if (draft.value.date) {
    const d = new Date(draft.value.date);
    draft.value.date = toValue(d, draft.value.hour, draft.value.minute);
  }
}

function confirm() {
  if (!draft.value.date) return;
  const d = new Date(draft.value.date);
  emit("update:modelValue", toValue(d, draft.value.hour, draft.value.minute));
  close();
}

function pickToday() {
  const now = new Date();
  draft.value.date = toValue(now, draft.value.hour, draft.value.minute);
  view.value = startOfMonth(now);
}

function pickNow() {
  const now = new Date();
  draft.value.hour = pad(now.getHours());
  draft.value.minute = pad(Math.floor(now.getMinutes() / 5) * 5);
  draft.value.date = toValue(now, draft.value.hour, draft.value.minute);
  view.value = startOfMonth(now);
}

function clear() {
  emit("update:modelValue", "");
  close();
}

watch(open, (val) => {
  if (!val) document.removeEventListener("mousedown", onOutside);
});

onMounted(() => {
  document.removeEventListener("mousedown", onOutside);
});

onBeforeUnmount(() => {
  document.removeEventListener("mousedown", onOutside);
});
</script>

<template>
  <div ref="root" class="dp">
    <button type="button" class="dp-trigger" :class="{ empty: !display, on: open }" @click="open ? close() : openPanel()">
      <span>{{ display || placeholder }}</span>
      <svg width="14" height="14" viewBox="0 0 16 16" aria-hidden="true">
        <path
          d="M3 5.5A1.5 1.5 0 0 1 4.5 4h7A1.5 1.5 0 0 1 13 5.5v7A1.5 1.5 0 0 1 11.5 14h-7A1.5 1.5 0 0 1 3 12.5v-7Z"
          fill="none" stroke="currentColor" stroke-width="1.3"
        />
        <path d="M3 7h10M5.5 2.5v3M10.5 2.5v3" fill="none" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" />
      </svg>
    </button>

    <div v-if="open" class="dp-panel">
      <div class="dp-head">
        <button type="button" class="dp-nav" @click="shiftMonth(-1)" aria-label="上个月">‹</button>
        <span class="dp-month">{{ monthLabel }}</span>
        <button type="button" class="dp-nav" @click="shiftMonth(1)" aria-label="下个月">›</button>
      </div>

      <div class="dp-week">
        <span v-for="w in WEEK" :key="w">{{ w }}</span>
      </div>

      <div class="dp-grid">
        <button
          v-for="(c, i) in cells"
          :key="i"
          type="button"
          class="dp-cell"
          :class="{
            muted: !c.inMonth,
            today: c.isToday,
            on: c.selected
          }"
          @click="pick(c)"
        >{{ c.day }}</button>
      </div>

      <div class="dp-time">
        <span class="dp-time-label">时间</span>
        <select :value="draft.hour" @change="setTime('hour', $event.target.value)">
          <option v-for="h in hours" :key="h" :value="h">{{ h }}</option>
        </select>
        <span class="dp-colon">:</span>
        <select :value="draft.minute" @change="setTime('minute', $event.target.value)">
          <option v-for="m in minutes" :key="m" :value="m">{{ m }}</option>
        </select>
        <div class="dp-quick">
          <button type="button" @click="pickToday">今天</button>
          <button type="button" @click="pickNow">现在</button>
        </div>
      </div>

      <div class="dp-foot">
        <button type="button" class="dp-link" @click="clear">清空</button>
        <div class="dp-actions">
          <button type="button" @click="close">取消</button>
          <button type="button" class="primary" :disabled="!draft.date" @click="confirm">确定</button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.dp {
  position: relative;
}

.dp-trigger {
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  height: 34px;
  padding: 0 10px;
  border: 1px solid var(--line);
  border-radius: 7px;
  background: #fff;
  color: var(--ink);
  font-size: 13px;
  font-variant-numeric: tabular-nums;
  text-align: left;
}

.dp-trigger.empty {
  color: var(--ink-3);
}

.dp-trigger.on,
.dp-trigger:focus {
  outline: none;
  border-color: #9aa4ae;
  box-shadow: 0 0 0 3px rgba(31, 35, 40, 0.06);
}

.dp-trigger svg {
  color: var(--ink-3);
  flex: 0 0 auto;
}

.dp-panel {
  position: absolute;
  z-index: 40;
  top: calc(100% + 6px);
  left: 0;
  width: 304px;
  background: #fff;
  border: 1px solid var(--line);
  border-radius: 10px;
  box-shadow: 0 12px 32px rgba(16, 24, 40, 0.12);
  padding: 10px 10px 8px;
}

.dp-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 6px;
}

.dp-month {
  font-size: 13px;
  font-weight: 600;
}

.dp-nav {
  width: 26px;
  height: 26px;
  padding: 0;
  border: 0;
  background: transparent;
  font-size: 16px;
  line-height: 1;
  color: var(--ink-2);
  border-radius: 6px;
}

.dp-nav:hover {
  background: #f3f5f6;
}

.dp-week,
.dp-grid {
  display: grid;
  grid-template-columns: repeat(7, 1fr);
  gap: 2px;
}

.dp-week span {
  text-align: center;
  font-size: 11px;
  color: var(--ink-3);
  padding: 4px 0;
}

.dp-cell {
  height: 30px;
  padding: 0;
  border: 0;
  background: transparent;
  border-radius: 6px;
  font-size: 12.5px;
  color: var(--ink);
  font-variant-numeric: tabular-nums;
}

.dp-cell:hover {
  background: #f3f5f6;
}

.dp-cell.muted {
  color: #c4c9ce;
}

.dp-cell.today {
  color: #1d4ed8;
  font-weight: 600;
}

.dp-cell.on {
  background: #1f2328;
  color: #fff;
  font-weight: 600;
}

.dp-time {
  display: flex;
  align-items: center;
  flex-wrap: nowrap;
  gap: 6px;
  margin-top: 8px;
  padding-top: 8px;
  border-top: 1px solid var(--line);
}

.dp-time-label {
  font-size: 12px;
  color: var(--ink-3);
  white-space: nowrap;
  flex: 0 0 auto;
}

.dp-time select {
  width: 58px;
  flex: 0 0 auto;
  height: 28px;
  padding: 0 4px;
  font-size: 12.5px;
  border-radius: 6px;
}

.dp-colon {
  color: var(--ink-3);
  margin: 0 -2px;
}

.dp-quick {
  margin-left: auto;
  display: flex;
  gap: 4px;
  flex: 0 0 auto;
}

.dp-quick button {
  font-size: 12px;
  padding: 3px 9px;
  border-radius: 999px;
  color: var(--ink-2);
  white-space: nowrap;
}

.dp-quick button:hover {
  border-color: #9aa4ae;
  color: var(--ink);
}

.dp-foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: 8px;
  padding-top: 8px;
  border-top: 1px solid var(--line);
}

.dp-link {
  border: 0;
  background: none;
  padding: 0;
  font-size: 12px;
  color: var(--ink-3);
}

.dp-link:hover {
  color: #b42318;
}

.dp-actions {
  display: flex;
  gap: 6px;
}

.dp-actions button {
  font-size: 12.5px;
  padding: 4px 12px;
  border-radius: 7px;
}

.dp-actions .primary {
  background: #1f2328;
  border-color: #1f2328;
  color: #fff;
}
</style>
