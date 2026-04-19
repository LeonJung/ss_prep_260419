// foxglove_bridge JSON WebSocket client.
//
// We use the public protocol (https://github.com/foxglove/ws-protocol) in
// JSON-only mode: the bridge advertises each ROS 2 topic as a channel
// with schema, we subscribe by channel id, and messages arrive as raw
// bytes containing JSON. Designed to run without the foxglove-sdk build,
// keeping the frontend dependency footprint minimal.
//
// NOTE: service calls are also supported by foxglove_bridge but we keep
// dispatch as an action call driven through a separate HTTP endpoint
// exposed by the task_manager's companion helper (see start_web_gui.sh).

import { reactive, readonly } from 'vue';
import { parse as parseRos2msgDefs } from '@foxglove/rosmsg';
import { MessageReader } from '@foxglove/rosmsg2-serialization';
import type {
  BtExecutionStatus,
  JointState,
  Odometry,
} from '../types';

type ConnectionState = 'disconnected' | 'connecting' | 'connected' | 'error';

interface Channel {
  id: number;
  topic: string;
  encoding: string;
  schemaName: string;
  schema: string;
  schemaEncoding?: string;
}

interface Service {
  id: number;
  name: string;
  type: string;
  requestSchema?: string;
  responseSchema?: string;
}

type RawHandler = (payload: unknown) => void;

const STATE = reactive({
  connection: 'disconnected' as ConnectionState,
  url: '',
  lastError: '' as string,
  serverName: '',
  bt: null as BtExecutionStatus | null,
  joint: null as JointState | null,
  odom: null as Odometry | null,
  motorStatus: null as null | Record<string, unknown>,
  batteryLevel: null as null | number,
});

let ws: WebSocket | null = null;
const topicHandlers = new Map<string, RawHandler[]>();
const channelsByTopic = new Map<string, Channel>();
const channelsById = new Map<number, Channel>();
const services = new Map<string, Service>();

// Cache a MessageReader per channel schema. foxglove_bridge 3.x ships
// the Rust SDK that wraps ROS 2 messages in CDR/ros2msg rather than
// JSON; we decode on the client so the rest of the app still sees
// plain JS objects.
const readersByChannel = new Map<number, MessageReader>();

function readerFor(ch: Channel): MessageReader | null {
  const cached = readersByChannel.get(ch.id);
  if (cached) return cached;
  if (ch.encoding !== 'cdr' || !ch.schema) return null;
  try {
    const defs = parseRos2msgDefs(ch.schema, { ros2: true });
    const reader = new MessageReader(defs);
    readersByChannel.set(ch.id, reader);
    return reader;
  } catch (e) {
    console.warn('[ros] schema parse failed', ch.topic, e);
    return null;
  }
}
let nextSubId = 1;
const subsByTopic = new Map<string, number>();
const pendingSubs = new Set<string>();
const pendingAdvertise = new Map<string, { topic: string; encoding: string; schemaName: string; schema: string }>();
const advertisedByTopic = new Map<string, number>();
let nextClientChanId = 1;

function send(obj: unknown) {
  ws?.send(JSON.stringify(obj));
}

function onChannelAvailable(topic: string) {
  if (!pendingSubs.has(topic)) return;
  const ch = channelsByTopic.get(topic);
  if (!ch) return;
  const subId = nextSubId++;
  subsByTopic.set(topic, subId);
  pendingSubs.delete(topic);
  send({
    op: 'subscribe',
    subscriptions: [{ id: subId, channelId: ch.id }],
  });
}

export function useRos() {
  function connect(url: string) {
    if (ws) ws.close();
    STATE.url = url;
    STATE.connection = 'connecting';
    STATE.lastError = '';
    // ros-jazzy-foxglove-bridge 3.x ships the new Rust SDK, which
    // negotiates with subprotocol 'foxglove.sdk.v1'. Earlier bridge
    // releases used 'foxglove.websocket.v1'; the wire format is the
    // same so only the handshake token changes.
    const sock = new WebSocket(url, 'foxglove.sdk.v1');
    ws = sock;

    sock.binaryType = 'arraybuffer';
    sock.onopen = () => {
      STATE.connection = 'connected';
    };
    sock.onclose = () => {
      STATE.connection = 'disconnected';
      ws = null;
      channelsByTopic.clear();
      channelsById.clear();
      subsByTopic.clear();
    };
    sock.onerror = () => {
      STATE.connection = 'error';
      STATE.lastError = `ws error (${url})`;
    };
    sock.onmessage = (evt) => {
      if (typeof evt.data === 'string') {
        try {
          const msg = JSON.parse(evt.data);
          handleJson(msg);
        } catch {
          // ignore
        }
      } else if (evt.data instanceof ArrayBuffer) {
        handleBinary(evt.data);
      }
    };
  }

  function handleJson(raw: { op: string;[k: string]: unknown }) {
    const msg = raw as unknown as Record<string, unknown>;
    switch (raw.op) {
      case 'serverInfo':
        STATE.serverName = (msg.name as string | undefined) ?? 'foxglove_bridge';
        break;
      case 'advertise': {
        const chans = (msg.channels as Channel[] | undefined) ?? [];
        for (const ch of chans) {
          channelsByTopic.set(ch.topic, ch);
          channelsById.set(ch.id, ch);
          onChannelAvailable(ch.topic);
        }
        break;
      }
      case 'unadvertise': {
        const ids = (msg.channelIds as number[] | undefined) ?? [];
        for (const id of ids) {
          const ch = channelsById.get(id);
          if (ch) channelsByTopic.delete(ch.topic);
          channelsById.delete(id);
        }
        break;
      }
      case 'advertiseServices': {
        const list = (msg.services as Service[] | undefined) ?? [];
        for (const s of list) services.set(s.name, s);
        break;
      }
      case 'serviceCallResponse': {
        const id = msg.callId as number;
        const payload = msg.data as string;
        resolveServiceCall(id, payload);
        break;
      }
      case 'serviceCallFailure': {
        const id = msg.callId as number;
        const reason = (msg.message as string) ?? 'service call failed';
        rejectServiceCall(id, new Error(reason));
        break;
      }
      case 'advertiseClientChannels':
      case 'status':
      default:
        break;
    }
  }

  function handleBinary(buf: ArrayBuffer) {
    const view = new DataView(buf);
    const op = view.getUint8(0);
    if (op !== 1) return; // 1 = MESSAGE_DATA
    const subId = view.getUint32(1, true);
    // bytes 5..12 = receive timestamp (int64 LE)
    const payload = new Uint8Array(buf, 13);
    let topic: string | null = null;
    for (const [t, id] of subsByTopic) {
      if (id === subId) { topic = t; break; }
    }
    if (!topic) return;
    const ch = channelsByTopic.get(topic);
    if (!ch) return;
    let obj: unknown = null;
    if (ch.encoding === 'json') {
      try {
        obj = JSON.parse(new TextDecoder().decode(payload));
      } catch (e) {
        console.warn('[ros] JSON decode fail', topic, e);
        return;
      }
    } else if (ch.encoding === 'cdr') {
      const reader = readerFor(ch);
      if (!reader) return;
      try {
        obj = reader.readMessage(payload);
      } catch (e) {
        console.warn('[ros] CDR decode fail', topic, e);
        return;
      }
    } else {
      // Silently drop unknown encodings.
      return;
    }
    const handlers = topicHandlers.get(topic);
    if (handlers) for (const h of handlers) h(obj);
  }

  function subscribe<T>(topic: string, handler: (v: T) => void) {
    if (!topicHandlers.has(topic)) topicHandlers.set(topic, []);
    topicHandlers.get(topic)!.push(handler as RawHandler);
    if (channelsByTopic.has(topic) && !subsByTopic.has(topic)) {
      onChannelAvailable(topic);
    } else if (!channelsByTopic.has(topic)) {
      pendingSubs.add(topic);
    }
  }

  let nextCallId = 1;
  const pending = new Map<number, {
    resolve: (v: unknown) => void;
    reject: (e: Error) => void;
  }>();

  function resolveServiceCall(id: number, raw: string) {
    const p = pending.get(id);
    if (!p) return;
    pending.delete(id);
    try {
      p.resolve(JSON.parse(raw));
    } catch (e) {
      p.reject(e as Error);
    }
  }
  function rejectServiceCall(id: number, err: Error) {
    const p = pending.get(id);
    if (!p) return;
    pending.delete(id);
    p.reject(err);
  }

  function callService<Req, Res>(
    serviceName: string,
    request: Req,
    timeoutMs = 5000,
  ): Promise<Res> {
    return new Promise((resolve, reject) => {
      if (STATE.connection !== 'connected' || !ws) {
        reject(new Error('not connected'));
        return;
      }
      const svc = services.get(serviceName);
      if (!svc) {
        reject(new Error(`service not advertised: ${serviceName}`));
        return;
      }
      const callId = nextCallId++;
      pending.set(callId, {
        resolve: resolve as (v: unknown) => void,
        reject,
      });
      setTimeout(() => {
        if (pending.has(callId)) {
          pending.delete(callId);
          reject(new Error('service call timeout'));
        }
      }, timeoutMs);
      send({
        op: 'serviceCallRequest',
        serviceId: svc.id,
        callId,
        encoding: 'json',
        data: JSON.stringify(request),
      });
    });
  }

  // ---- app-level wiring ----

  function wireStandardTopics() {
    subscribe<BtExecutionStatus>('/mw_bt_status', (v) => { STATE.bt = v; });
    subscribe<JointState>('/joint_states', (v) => { STATE.joint = v; });
    subscribe<Odometry>('/odom', (v) => { STATE.odom = v; });
    subscribe<{ percentage?: number }>('/battery_state', (v) => {
      if (typeof v.percentage === 'number') STATE.batteryLevel = v.percentage;
    });
  }

  return {
    state: readonly(STATE),
    connect,
    subscribe,
    callService,
    wireStandardTopics,
  };
}
