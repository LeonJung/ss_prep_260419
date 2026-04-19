<script setup lang="ts">
import { computed } from 'vue';
import { useRos } from '../composables/useRos';

const { state } = useRos();

const badge = computed(() => {
  switch (state.connection) {
    case 'connected': return 'bg-emerald-500';
    case 'connecting': return 'bg-amber-400';
    case 'error': return 'bg-rose-500';
    default: return 'bg-slate-500';
  }
});

const label = computed(() => state.connection.toUpperCase());
</script>

<template>
  <div class="flex items-center gap-2 px-3 py-1.5 bg-slate-800/60 rounded-lg text-xs">
    <span :class="['w-2.5 h-2.5 rounded-full', badge]" />
    <span class="font-mono">{{ label }}</span>
    <span class="text-slate-400 hidden sm:inline">{{ state.url }}</span>
    <span v-if="state.lastError" class="text-rose-300">{{ state.lastError }}</span>
  </div>
</template>
