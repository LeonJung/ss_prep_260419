<script setup lang="ts">
/**
 * Live HFSM state-chart viewer powered by VueFlow.
 *
 * Reads /mw_hfsm_status.spec_json (a hierarchical spec produced by
 * mw_hfsm_engine's spec_dumper — see future PR) and highlights the node
 * whose dotted path equals `active_state`.
 *
 * Phase 1 behavior: the executor does not yet serialize its BehaviorSM
 * into spec_json, so this view stays in a friendly empty state ("no SubJob
 * dispatched") until that serializer lands.  The parser below already
 * handles the JSON shape we'll emit, so when the serializer ships the
 * render will work without further frontend changes.
 *
 * Expected spec_json shape (hierarchical):
 *   {
 *     "id": "VisitThreePoints",
 *     "kind": "BehaviorSM" | "StateMachine" | "State",
 *     "children": [
 *        { "name": "GO_P1", "id": "Step", "kind": "StateMachine", "children": [...] },
 *        ...
 *     ]
 *   }
 */
import { computed, nextTick, watch } from 'vue';
import { VueFlow, type Node, type Edge, useVueFlow } from '@vue-flow/core';
import { Background } from '@vue-flow/background';
import { Controls } from '@vue-flow/controls';
import { MiniMap } from '@vue-flow/minimap';
import { useRos } from '../composables/useRos';

const { state } = useRos();

interface SpecNode {
  id?: string;
  ref?: string;
  kind?: string;
  children?: Record<string, SpecNode> | SpecNode[];
}

interface ParsedNode {
  id: string;
  label: string;
  children: ParsedNode[];
  depth: number;
  isLeaf: boolean;
  path: string; // dot-joined ancestor names
}

function parseHfsmSpec(specJson: string, rootName: string): ParsedNode | null {
  if (!specJson) return null;
  let spec: SpecNode;
  try {
    spec = JSON.parse(specJson);
  } catch {
    return null;
  }
  let counter = 0;
  const walk = (
    node: SpecNode, depth: number, parentPath: string, assignedName: string,
  ): ParsedNode => {
    counter += 1;
    const id = `n${counter}`;
    // For the root, use the assigned name (SubJob id).  For children,
    // the dict key from the parent becomes the segment — see loop below.
    const segment = assignedName;
    const kind = node.kind ?? '';
    const path = parentPath ? `${parentPath}.${segment}` : segment;

    // Engine's to_spec emits children as a {name: spec} dict.  Legacy
    // specs (or some future editors) may emit an array; accept both.
    const raw = node.children;
    const entries: Array<[string, SpecNode]> = !raw
      ? []
      : Array.isArray(raw)
        ? raw.map((c, i) => [c.id || String(i), c])
        : Object.entries(raw);
    const children = entries.map(
      ([name, child]) => walk(child, depth + 1, path, name),
    );

    // Build a label: "kind: name" for containers, "kind: ref" for leaves.
    let label = segment;
    if (kind === 'State' && node.ref) {
      label = `${segment}\n↳ ${node.ref}`;
    } else if (kind) {
      label = `${kind}: ${segment}`;
    }
    return {
      id,
      label,
      children,
      depth,
      isLeaf: children.length === 0,
      path,
    };
  };
  return walk(spec, 0, '', rootName);
}

function layout(root: ParsedNode) {
  const nodes: Node[] = [];
  const edges: Edge[] = [];
  const xStep = 240;
  const yStep = 110;
  let cursor = 0;
  const positions = new Map<string, { x: number; y: number }>();
  const visit = (n: ParsedNode) => {
    if (n.isLeaf) {
      positions.set(n.id, { x: cursor * xStep, y: n.depth * yStep });
      cursor += 1;
    } else {
      n.children.forEach(visit);
      const firstPos = positions.get(n.children[0].id)!;
      const lastPos = positions.get(n.children[n.children.length - 1].id)!;
      positions.set(n.id, {
        x: (firstPos.x + lastPos.x) / 2,
        y: n.depth * yStep,
      });
    }
  };
  visit(root);

  const emit = (n: ParsedNode, parent?: ParsedNode) => {
    const pos = positions.get(n.id)!;
    nodes.push({
      id: n.id,
      position: pos,
      data: { label: n.label, path: n.path, isLeaf: n.isLeaf },
      type: 'default',
      class: n.isLeaf ? 'hfsm-leaf' : 'hfsm-composite',
    });
    if (parent) {
      edges.push({
        id: `${parent.id}->${n.id}`,
        source: parent.id,
        target: n.id,
        type: 'smoothstep',
      });
    }
    n.children.forEach((c) => emit(c, n));
  };
  emit(root);

  return { nodes, edges };
}

const graph = computed(() => {
  // Use the published subjob_id as the root segment so active_state paths
  // (which start with the SubJob class name, e.g. "VisitThreePoints.GO_P1")
  // line up with the nodes we render here.
  const rootName = state.hfsm?.subjob_id || 'SubJob';
  const root = parseHfsmSpec(state.hfsm?.spec_json ?? '', rootName);
  return root ? layout(root) : { nodes: [] as Node[], edges: [] as Edge[] };
});

const elements = computed<(Node | Edge)[]>(() => [
  ...graph.value.nodes.map<Node>((n) => {
    const active = state.hfsm?.active_state &&
      (n.data as { path?: string }).path === state.hfsm.active_state;
    return {
      ...n,
      style: {
        ...(active ? { boxShadow: '0 0 0 3px #f59e0b' } : {}),
        padding: '8px 12px',
        whiteSpace: 'pre-wrap',
        fontSize: '11px',
        fontFamily: 'ui-monospace, SFMono-Regular, monospace',
        background: active ? '#78350f' : '#1e293b',
        color: active ? '#fff8e1' : '#e2e8f0',
        border: active ? '1px solid #f59e0b' : '1px solid #334155',
        borderRadius: '6px',
        minWidth: '160px',
      },
    };
  }),
  ...graph.value.edges,
]);

const { fitView, onInit } = useVueFlow();

onInit(() => {
  setTimeout(() => fitView({ padding: 0.2, duration: 0 }), 20);
});

watch(
  () => state.hfsm?.spec_json,
  async () => {
    await nextTick();
    requestAnimationFrame(() =>
      requestAnimationFrame(() =>
        fitView({ padding: 0.2, duration: 0 }),
      ),
    );
  },
  { flush: 'post' },
);
</script>

<template>
  <section class="rounded-xl bg-panel/70 border border-slate-800 p-3">
    <div class="flex items-center justify-between mb-2">
      <h2 class="text-xs uppercase tracking-wider text-slate-400">
        HFSM State Chart (live)
      </h2>
      <span v-if="!state.hfsm?.spec_json" class="text-xs text-slate-500">
        no SubJob running — dispatch one to populate
      </span>
    </div>
    <div class="bg-slate-950 rounded" style="height: 420px; width: 100%;">
      <VueFlow
        :nodes="(elements.filter(e => !('source' in e)) as Node[])"
        :edges="(elements.filter(e => 'source' in e) as Edge[])"
        :fit-view-on-init="true"
        :default-viewport="{ zoom: 0.6 }"
        :min-zoom="0.1"
        :max-zoom="2"
        :pan-on-drag="true"
      >
        <Background color="#334155" />
        <Controls />
        <MiniMap pannable zoomable />
      </VueFlow>
    </div>
  </section>
</template>
