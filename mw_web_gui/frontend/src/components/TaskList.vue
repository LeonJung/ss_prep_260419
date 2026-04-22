<script setup lang="ts">
import { onMounted, ref } from 'vue';
import { useRos } from '../composables/useRos';

interface Props {
  dispatchUrl: string;
}
const props = defineProps<Props>();

const { state } = useRos();
const tasks = ref<string[]>([]);
const busy = ref(false);
const error = ref('');

async function refresh() {
  error.value = '';
  try {
    // Use HTTP proxy; foxglove_bridge 3.x JSON service calls return
    // empty responses for custom service types.
    const resp = await fetch(`${props.dispatchUrl}/tasks`);
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const body = await resp.json();
    tasks.value = body.task_ids ?? [];
  } catch (e) {
    error.value = (e as Error).message;
  }
}

async function dispatch(subjob_id: string) {
  busy.value = true;
  error.value = '';
  try {
    const resp = await fetch(`${props.dispatchUrl}/dispatch`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      // behavior_parameter and userdata_in are empty for now — the
      // per-SubJob parameter editor lands with the spec-loader track.
      body: JSON.stringify({
        subjob_id,
        behavior_parameter: {},
        userdata_in: {},
      }),
    });
    if (!resp.ok) {
      throw new Error(`HTTP ${resp.status}: ${await resp.text()}`);
    }
  } catch (e) {
    error.value = (e as Error).message;
  } finally {
    busy.value = false;
  }
}

onMounted(() => {
  // Poll once on mount; the user can also hit the refresh button.
  setTimeout(refresh, 400);
});
</script>

<template>
  <section class="rounded-xl bg-panel/70 border border-slate-800 p-4 space-y-3">
    <div class="flex items-center justify-between">
      <h2 class="text-xs uppercase tracking-wider text-slate-400">Tasks</h2>
      <button
        @click="refresh"
        :disabled="state.connection !== 'connected'"
        class="text-xs px-2 py-1 bg-slate-700 hover:bg-slate-600 rounded disabled:opacity-40"
      >
        refresh
      </button>
    </div>

    <p v-if="error" class="text-rose-300 text-xs">{{ error }}</p>

    <div v-if="tasks.length === 0" class="text-slate-500 text-sm">
      no tasks stored — use <code>ros2 service call /mw_task_repository/save_task</code>
    </div>

    <ul class="space-y-1.5">
      <li
        v-for="t in tasks"
        :key="t"
        class="flex items-center justify-between gap-2 bg-slate-800/60 rounded px-3 py-2"
      >
        <span class="font-mono text-sm">{{ t }}</span>
        <button
          @click="dispatch(t)"
          :disabled="busy || (state.hfsm?.status === 1)"
          class="text-xs px-3 py-1 bg-accent hover:bg-blue-400 text-white rounded disabled:opacity-40"
        >
          dispatch
        </button>
      </li>
    </ul>
  </section>
</template>
