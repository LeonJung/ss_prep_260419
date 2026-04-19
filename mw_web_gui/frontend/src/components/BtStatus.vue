<script setup lang="ts">
import { computed } from 'vue';
import { useRos } from '../composables/useRos';
import { BT_STATUS_LABELS } from '../types';

const { state } = useRos();
const bt = computed(() => state.bt);

const statusText = computed(() => {
  const s = bt.value?.status ?? 0;
  return BT_STATUS_LABELS[s] ?? `STATUS_${s}`;
});

const statusColor = computed(() => {
  switch (bt.value?.status) {
    case 1: return 'text-amber-300';
    case 2: return 'text-emerald-400';
    case 3: return 'text-rose-400';
    default: return 'text-slate-400';
  }
});

const elapsed = computed(() => {
  const e = bt.value?.elapsed_sec ?? 0;
  return e < 1 ? `${Math.round(e * 1000)} ms` : `${e.toFixed(1)} s`;
});
</script>

<template>
  <section class="rounded-xl bg-panel/70 border border-slate-800 p-4">
    <h2 class="text-xs uppercase tracking-wider text-slate-400 mb-2">
      BT Execution
    </h2>
    <div class="grid grid-cols-2 gap-y-1.5 text-sm">
      <div class="text-slate-400">Status</div>
      <div :class="['font-mono font-semibold', statusColor]">
        {{ statusText }}
      </div>
      <div class="text-slate-400">Task</div>
      <div class="font-mono truncate">{{ bt?.task_id || '—' }}</div>
      <div class="text-slate-400">Tree</div>
      <div class="font-mono truncate">{{ bt?.tree_name || '—' }}</div>
      <div class="text-slate-400">Current Node</div>
      <div class="font-mono truncate text-amber-200">
        {{ bt?.current_node_name || '—' }}
      </div>
      <div class="text-slate-400">Elapsed</div>
      <div class="font-mono">{{ elapsed }}</div>
    </div>
  </section>
</template>
