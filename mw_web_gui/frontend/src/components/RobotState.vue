<script setup lang="ts">
import { computed } from 'vue';
import { useRos } from '../composables/useRos';

const { state } = useRos();

const joints = computed(() => {
  const j = state.joint;
  if (!j) return [];
  return j.name.map((n, i) => ({
    name: n,
    position: j.position?.[i] ?? 0,
    velocity: j.velocity?.[i] ?? 0,
  }));
});

const odomPose = computed(() => {
  const o = state.odom;
  if (!o) return null;
  const p = o.pose.pose.position;
  const q = o.pose.pose.orientation;
  // yaw from quat
  const siny = 2 * (q.w * q.z + q.x * q.y);
  const cosy = 1 - 2 * (q.y * q.y + q.z * q.z);
  const yaw = Math.atan2(siny, cosy);
  return {
    x: p.x,
    y: p.y,
    yaw,
    vx: o.twist.twist.linear.x,
    wz: o.twist.twist.angular.z,
  };
});

const batteryPct = computed(() => {
  const b = state.batteryLevel;
  return b == null ? null : Math.round(b * 100);
});
</script>

<template>
  <section class="rounded-xl bg-panel/70 border border-slate-800 p-4 space-y-3">
    <h2 class="text-xs uppercase tracking-wider text-slate-400">Robot State</h2>

    <div v-if="odomPose" class="space-y-1">
      <div class="text-xs text-slate-500 uppercase">Odom</div>
      <div class="grid grid-cols-3 gap-x-2 font-mono text-sm">
        <div><span class="text-slate-500">x</span> {{ odomPose.x.toFixed(2) }}</div>
        <div><span class="text-slate-500">y</span> {{ odomPose.y.toFixed(2) }}</div>
        <div><span class="text-slate-500">θ</span> {{ odomPose.yaw.toFixed(2) }}</div>
        <div><span class="text-slate-500">vx</span> {{ odomPose.vx.toFixed(2) }}</div>
        <div><span class="text-slate-500">ωz</span> {{ odomPose.wz.toFixed(2) }}</div>
      </div>
    </div>

    <div v-if="batteryPct != null" class="space-y-1">
      <div class="text-xs text-slate-500 uppercase">Battery</div>
      <div class="flex items-center gap-2">
        <div class="flex-1 h-2 bg-slate-800 rounded overflow-hidden">
          <div
            class="h-full bg-emerald-500"
            :style="{ width: `${batteryPct}%` }"
          />
        </div>
        <span class="font-mono text-sm w-10 text-right">{{ batteryPct }}%</span>
      </div>
    </div>

    <div v-if="joints.length" class="space-y-1">
      <div class="text-xs text-slate-500 uppercase">Joints</div>
      <div class="space-y-0.5 font-mono text-xs">
        <div
          v-for="j in joints"
          :key="j.name"
          class="grid grid-cols-[1fr_auto_auto] gap-x-3"
        >
          <span class="text-slate-300 truncate">{{ j.name }}</span>
          <span>{{ j.position.toFixed(3) }}</span>
          <span class="text-slate-500">{{ j.velocity.toFixed(3) }} /s</span>
        </div>
      </div>
    </div>

    <div
      v-if="!odomPose && !joints.length && batteryPct == null"
      class="text-slate-500 text-sm"
    >
      no robot state yet
    </div>
  </section>
</template>
