<script setup lang="ts">
import { computed } from 'vue';
import { useRos } from '../composables/useRos';
import { HFSM_STATUS_LABELS } from '../types';

const { state } = useRos();
const hfsm = computed(() => state.hfsm);

const statusText = computed(() => {
  const s = hfsm.value?.status ?? 0;
  return HFSM_STATUS_LABELS[s] ?? `STATUS_${s}`;
});

const statusColor = computed(() => {
  switch (hfsm.value?.status) {
    case 1: return 'text-amber-300';
    case 2: return 'text-emerald-400';
    case 3: return 'text-rose-400';
    default: return 'text-slate-400';
  }
});

const elapsed = computed(() => {
  const e = hfsm.value?.elapsed_sec ?? 0;
  return e < 1 ? `${Math.round(e * 1000)} ms` : `${e.toFixed(1)} s`;
});

const userdataPreview = computed(() => {
  const raw = hfsm.value?.userdata_snapshot_json || '';
  if (!raw) return '—';
  try {
    const obj = JSON.parse(raw);
    const keys = Object.keys(obj);
    if (keys.length === 0) return '{}';
    return keys.slice(0, 3).join(', ') + (keys.length > 3 ? '…' : '');
  } catch {
    return raw.length > 40 ? raw.slice(0, 40) + '…' : raw;
  }
});
</script>

<template>
  <section class="rounded-xl bg-panel/70 border border-slate-800 p-4">
    <h2 class="text-xs uppercase tracking-wider text-slate-400 mb-2">
      HFSM Execution
    </h2>
    <div class="grid grid-cols-2 gap-y-1.5 text-sm">
      <div class="text-slate-400">Status</div>
      <div :class="['font-mono font-semibold', statusColor]">
        {{ statusText }}
      </div>
      <div class="text-slate-400">SubJob</div>
      <div class="font-mono truncate">{{ hfsm?.subjob_id || '—' }}</div>
      <div class="text-slate-400">Active State</div>
      <div class="font-mono truncate text-amber-200">
        {{ hfsm?.active_state || '—' }}
      </div>
      <div class="text-slate-400">Userdata keys</div>
      <div class="font-mono truncate">{{ userdataPreview }}</div>
      <div class="text-slate-400">Elapsed</div>
      <div class="font-mono">{{ elapsed }}</div>
    </div>
  </section>
</template>
