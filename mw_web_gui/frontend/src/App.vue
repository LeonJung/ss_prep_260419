<script setup lang="ts">
import { onMounted, computed } from 'vue';
import ConnectionStatus from './components/ConnectionStatus.vue';
import HfsmStatus from './components/HfsmStatus.vue';
import HfsmStateView from './components/HfsmStateView.vue';
import RobotState from './components/RobotState.vue';
import SpecEditor from './components/SpecEditor.vue';
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

  <main class="flex-1 overflow-auto p-4" style="min-width: 1280px;">
    <div
      class="grid gap-4 max-w-7xl mx-auto"
      style="grid-template-columns: minmax(0, 1fr) minmax(320px, 380px); min-width: 1200px;"
    >
      <!-- left column: state chart + execution status -->
      <div class="space-y-4 min-w-0">
        <HfsmStateView />
        <HfsmStatus />
      </div>
      <!-- right column: task list + spec editor + robot state -->
      <aside class="space-y-4 min-w-0">
        <TaskList :dispatch-url="dispatchUrl" />
        <SpecEditor :dispatch-url="dispatchUrl" />
        <RobotState />
      </aside>
    </div>
  </main>
</template>

<style scoped>
/* Force PC-sized layout even on phone viewports.  Phones scroll
   horizontally rather than collapsing into a single column. */
</style>
