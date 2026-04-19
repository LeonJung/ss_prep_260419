<script setup lang="ts">
import { onMounted, computed } from 'vue';
import ConnectionStatus from './components/ConnectionStatus.vue';
import BtStatus from './components/BtStatus.vue';
import BtTreeView from './components/BtTreeView.vue';
import RobotState from './components/RobotState.vue';
import TaskList from './components/TaskList.vue';
import { useRos } from './composables/useRos';

const { connect, wireStandardTopics } = useRos();

// Everything is proxied through Vite, so a single cloudflared tunnel
// on port 5173 is enough. We connect to /ws on the same origin and
// issue dispatch POSTs to /api/dispatch.
function defaultWsUrl(): string {
  const params = new URLSearchParams(window.location.search);
  const override = params.get('wsUrl');
  if (override) return override;
  const scheme = window.location.protocol === 'https:' ? 'wss' : 'ws';
  return `${scheme}://${window.location.host}/ws`;
}

function defaultDispatchUrl(): string {
  const params = new URLSearchParams(window.location.search);
  const override = params.get('dispatchUrl');
  if (override) return override;
  return `${window.location.origin}/api`;
}

const dispatchUrl = defaultDispatchUrl();

onMounted(() => {
  wireStandardTopics();
  connect(defaultWsUrl());
});
</script>

<template>
  <header class="flex items-center justify-between gap-3 px-4 py-3 border-b border-slate-800 bg-slate-900/40 flex-none">
    <div class="flex items-center gap-2">
      <div class="w-8 h-8 rounded-lg bg-gradient-to-br from-blue-500 to-emerald-400 flex items-center justify-center font-bold text-slate-900">
        mw
      </div>
      <div>
        <h1 class="text-base font-semibold leading-tight">Task Manager</h1>
        <p class="text-xs text-slate-400">live monitor &amp; dispatch</p>
      </div>
    </div>
    <ConnectionStatus />
  </header>

  <main class="flex-1 overflow-auto p-3 md:p-4">
    <div
      class="grid gap-3 md:gap-4 max-w-7xl mx-auto"
      style="grid-template-columns: minmax(0, 1fr) minmax(260px, 340px);"
    >
      <!-- left column: tree viewer fills width on md+, collapses on small -->
      <div class="space-y-3 md:space-y-4 min-w-0">
        <BtTreeView />
        <BtStatus />
      </div>
      <!-- right column: task list + robot state -->
      <aside class="space-y-3 md:space-y-4 min-w-0">
        <TaskList :dispatch-url="dispatchUrl" />
        <RobotState />
      </aside>
    </div>
  </main>
</template>

<style scoped>
@media (max-width: 768px) {
  main > div {
    grid-template-columns: 1fr !important;
  }
}
</style>
