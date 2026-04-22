<script setup lang="ts">
/**
 * Author-facing SubJob spec editor.
 *
 * Minimal JSON-textarea workflow (Phase 4 first cut):
 *   - list existing specs from the repository         (GET  /specs)
 *   - load one into the textarea                      (GET  /specs/<id>)
 *   - edit + validate + save                           (POST /specs)
 *   - dispatch the id currently in the "name" input    (POST /dispatch)
 *
 * A full drag-and-drop graph editor is a future track (kept in the README
 * pending list).  Shipping the text editor first unlocks end-to-end
 * save/load/dispatch without UI debt.
 */
import { onMounted, ref, computed } from 'vue';

interface Props { dispatchUrl: string; }
const props = defineProps<Props>();

const STARTER_SPEC = `{
  "kind": "BehaviorSM",
  "outcomes": ["done", "failed"],
  "behavior_parameters": [],
  "initial_state": "GO_P1",
  "children": {
    "GO_P1": {
      "kind": "StateMachine",
      "outcomes": ["done", "failed"],
      "children": {
        "drive": {
          "kind": "State",
          "ref": "DriveToPoseState",
          "args": {"target_x": 1.0, "target_y": 0.0, "target_yaw": 0.0}
        }
      },
      "transitions": {
        "drive": {
          "succeeded": "done",
          "failed": "failed",
          "lifecycle_error": "failed",
          "timeout": "failed",
          "rejected": "failed"
        }
      }
    }
  },
  "transitions": {
    "GO_P1": {"done": "done", "failed": "failed"}
  }
}`;

const ids = ref<string[]>([]);
const subjobId = ref<string>('');
const specText = ref<string>(STARTER_SPEC);
const commitMessage = ref<string>('');
const message = ref<string>('');
const busy = ref<boolean>(false);

const parseError = computed(() => {
  try {
    const parsed = JSON.parse(specText.value || '{}');
    if (typeof parsed !== 'object' || parsed === null) {
      return 'top-level must be an object';
    }
    if (!('kind' in parsed)) return 'missing "kind" field';
    return '';
  } catch (e) {
    return (e as Error).message;
  }
});

async function refreshList() {
  message.value = '';
  try {
    const r = await fetch(`${props.dispatchUrl}/specs`);
    const body = await r.json();
    ids.value = body.subjob_ids || [];
  } catch (e) {
    message.value = `list failed: ${(e as Error).message}`;
  }
}

async function loadSpec(id: string) {
  if (!id) return;
  message.value = '';
  try {
    const r = await fetch(
      `${props.dispatchUrl}/specs/${encodeURIComponent(id)}`,
    );
    const body = await r.json();
    if (!r.ok || !body.ok) {
      message.value = `load failed: ${body.message || r.status}`;
      return;
    }
    subjobId.value = id;
    specText.value = body.spec_json || '';
    message.value = `loaded ${id}`;
  } catch (e) {
    message.value = `load failed: ${(e as Error).message}`;
  }
}

async function saveSpec() {
  message.value = '';
  if (!subjobId.value) {
    message.value = 'name required';
    return;
  }
  if (parseError.value) {
    message.value = `fix JSON first: ${parseError.value}`;
    return;
  }
  busy.value = true;
  try {
    const spec = JSON.parse(specText.value);
    const r = await fetch(`${props.dispatchUrl}/specs`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        subjob_id: subjobId.value,
        spec,
        commit_message: commitMessage.value || '',
      }),
    });
    const body = await r.json();
    if (!r.ok || !body.ok) {
      message.value = `save failed: ${body.message || r.status}`;
    } else {
      message.value = `saved ${subjobId.value}`;
      refreshList();
    }
  } catch (e) {
    message.value = `save failed: ${(e as Error).message}`;
  } finally {
    busy.value = false;
  }
}

async function dispatchCurrent() {
  message.value = '';
  if (!subjobId.value) {
    message.value = 'name required';
    return;
  }
  busy.value = true;
  try {
    const r = await fetch(`${props.dispatchUrl}/dispatch`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        subjob_id: subjobId.value,
        behavior_parameter: {},
        userdata_in: {},
      }),
    });
    if (!r.ok) {
      message.value = `dispatch failed: ${r.status} ${await r.text()}`;
    } else {
      message.value = `dispatched ${subjobId.value}`;
    }
  } catch (e) {
    message.value = `dispatch failed: ${(e as Error).message}`;
  } finally {
    busy.value = false;
  }
}

onMounted(() => { setTimeout(refreshList, 400); });
</script>

<template>
  <section class="rounded-xl bg-panel/70 border border-slate-800 p-4 space-y-3">
    <div class="flex items-center justify-between">
      <h2 class="text-xs uppercase tracking-wider text-slate-400">Spec Editor</h2>
      <button
        @click="refreshList"
        class="text-xs px-2 py-1 bg-slate-700 hover:bg-slate-600 rounded"
      >
        refresh
      </button>
    </div>

    <div class="flex gap-2 items-center">
      <label class="text-xs text-slate-400 w-14 shrink-0">Name</label>
      <input
        v-model="subjobId"
        list="spec-id-list"
        placeholder="VisitThreePoints"
        class="flex-1 bg-slate-950 border border-slate-700 rounded px-2 py-1 font-mono text-sm"
      />
      <datalist id="spec-id-list">
        <option v-for="id in ids" :key="id" :value="id" />
      </datalist>
      <button
        @click="loadSpec(subjobId)"
        :disabled="!subjobId"
        class="text-xs px-2 py-1 bg-slate-700 hover:bg-slate-600 rounded disabled:opacity-40"
      >
        load
      </button>
    </div>

    <textarea
      v-model="specText"
      rows="14"
      class="w-full bg-slate-950 border border-slate-700 rounded px-2 py-1 font-mono text-xs leading-snug"
      spellcheck="false"
    ></textarea>

    <div class="flex gap-2 items-center">
      <input
        v-model="commitMessage"
        placeholder="commit message (optional)"
        class="flex-1 bg-slate-950 border border-slate-700 rounded px-2 py-1 text-sm"
      />
      <button
        @click="saveSpec"
        :disabled="busy || !!parseError"
        class="text-xs px-3 py-1 bg-accent hover:bg-blue-400 text-white rounded disabled:opacity-40"
      >
        save
      </button>
      <button
        @click="dispatchCurrent"
        :disabled="busy"
        class="text-xs px-3 py-1 bg-emerald-600 hover:bg-emerald-500 text-white rounded disabled:opacity-40"
      >
        dispatch
      </button>
    </div>

    <p v-if="parseError" class="text-rose-300 text-xs font-mono">
      JSON: {{ parseError }}
    </p>
    <p v-if="message" class="text-slate-300 text-xs">{{ message }}</p>
  </section>
</template>
