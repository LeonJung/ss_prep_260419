<script setup lang="ts">
/**
 * Live BT tree viewer powered by VueFlow. Parses the XML text carried
 * on /mw_bt_status (field `tree_xml`), builds a tidy top-down layout,
 * and highlights the node whose `name` matches `current_node_name`.
 */
import { computed, nextTick, watch } from 'vue';
import { VueFlow, type Node, type Edge, useVueFlow } from '@vue-flow/core';
import { Background } from '@vue-flow/background';
import { Controls } from '@vue-flow/controls';
import { MiniMap } from '@vue-flow/minimap';
import { useRos } from '../composables/useRos';

const { state } = useRos();

interface ParsedNode {
  id: string;
  label: string;
  children: ParsedNode[];
  depth: number;
  isLeaf: boolean;
  nodeName: string; // BT "name" attribute for current-node matching
}

function parseBtXml(xml: string): ParsedNode | null {
  if (!xml) return null;
  const doc = new DOMParser().parseFromString(xml, 'application/xml');
  const tree = doc.querySelector('BehaviorTree');
  if (!tree) return null;

  let counter = 0;
  const walk = (el: Element, depth: number): ParsedNode => {
    // Snapshot the id BEFORE recursing into children; otherwise the
    // final counter (after all descendants walked) is what the closure
    // sees, and every ancestor collides with its last-visited descendant.
    counter += 1;
    const id = `n${counter}`;
    const children = Array.from(el.children)
      .filter((c) => c.nodeType === 1)
      .map((c) => walk(c, depth + 1));
    const name = el.getAttribute('name') ?? '';
    const tag = el.tagName;
    const attrs = Array.from(el.attributes)
      .filter((a) => a.name !== 'name')
      .map((a) => `${a.name}=${a.value}`)
      .join(' ');
    const label = name
      ? `${tag}: ${name}${attrs ? `\n${attrs}` : ''}`
      : `${tag}${attrs ? `\n${attrs}` : ''}`;
    return {
      id,
      label,
      children,
      depth,
      isLeaf: children.length === 0,
      nodeName: name,
    };
  };

  const root = Array.from(tree.children).find((c) => c.nodeType === 1);
  return root ? walk(root, 0) : null;
}

function layout(root: ParsedNode) {
  const nodes: Node[] = [];
  const edges: Edge[] = [];
  const xStep = 240;
  const yStep = 110;
  // assign x by in-order traversal leaves-first, y by depth
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
      data: { label: n.label, nodeName: n.nodeName, isLeaf: n.isLeaf },
      type: 'default',
      class: n.isLeaf ? 'bt-leaf' : 'bt-composite',
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
  const root = parseBtXml(state.bt?.tree_xml ?? '');
  return root ? layout(root) : { nodes: [] as Node[], edges: [] as Edge[] };
});

const elements = computed<(Node | Edge)[]>(() => [
  ...graph.value.nodes.map<Node>((n) => {
    const active = state.bt?.current_node_name &&
      (n.data as { nodeName?: string }).nodeName === state.bt.current_node_name;
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

// Fit once when VueFlow's internal store is ready (covers the case where
// tree_xml arrives before the component finishes mounting).
onInit(() => {
  setTimeout(() => fitView({ padding: 0.2, duration: 0 }), 20);
});

// Re-fit whenever the tree topology changes. flush:'post' delays until
// DOM is updated; nextTick + double rAF gives VueFlow time to compute
// its internal layout before we ask it to fit, otherwise fit sees zero
// nodes and the viewport stays at its default (user sees empty canvas).
watch(
  () => state.bt?.tree_xml,
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
        BT Tree (live)
      </h2>
      <span v-if="!state.bt?.tree_xml" class="text-xs text-slate-500">
        no tree loaded — dispatch a task
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
