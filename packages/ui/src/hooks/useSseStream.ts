/**
 * useSseStream —— SSE 流式渲染 hook（docs/04 2.3）。
 * 状态机：idle → connecting → open → closed；错误进入 error 并按退避重连（默认 3 次）。
 * 重连/结束/错误均由调用方通过回调感知；hook 只负责连接生命周期。
 */
import { ref } from 'vue';
import type { Ref } from 'vue';

export type SseStreamStatus = 'idle' | 'connecting' | 'open' | 'closed' | 'error';

export interface UseSseStreamOptions {
  /** 每条 SSE data 载荷（已按 JSON 解析失败时回落原始字符串） */
  onMessage?: (data: unknown) => void;
  /** 终局事件（runtime-events.yaml 的 done） */
  onEnd?: () => void;
  onError?: (error: Error) => void;
  maxRetries?: number;
  retryBaseMs?: number;
  /** 注入 fetch 便于测试 */
  fetchImpl?: typeof fetch;
}

export interface SseStreamHandle {
  status: Ref<SseStreamStatus>;
  retryCount: Ref<number>;
  start: () => Promise<void>;
  stop: () => void;
}

export function useSseStream(url: string, options: UseSseStreamOptions = {}): SseStreamHandle {
  const {
    onMessage,
    onEnd,
    onError,
    maxRetries = 3,
    retryBaseMs = 500,
    fetchImpl = fetch,
  } = options;

  const status = ref<SseStreamStatus>('idle');
  const retryCount = ref(0);
  const controller = new AbortController();
  let stopped = false;
  let ended = false;

  function sleep(ms: number): Promise<void> {
    return new Promise((resolve) => setTimeout(resolve, ms));
  }

  async function connect(): Promise<void> {
    if (stopped) return;
    status.value = 'connecting';
    try {
      const response = await fetchImpl(url, { signal: controller.signal, headers: { Accept: 'text/event-stream' } });
      if (!response.ok || !response.body) {
        throw new Error(`SSE 响应异常: ${response.status}`);
      }
      status.value = 'open';
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';
      for (;;) {
        const { done, value } = await reader.read();
        if (done || ended) break;
        buffer += decoder.decode(value, { stream: true });
        const frames = buffer.split('\n\n');
        buffer = frames.pop() ?? '';
        for (const frame of frames) {
          handleFrame(frame);
        }
      }
      if (!stopped && !ended) {
        status.value = 'closed';
        onEnd?.();
      }
    } catch (error) {
      if (stopped || (error as Error).name === 'AbortError') return;
      if (retryCount.value < maxRetries) {
        retryCount.value += 1;
        await sleep(retryBaseMs * 2 ** (retryCount.value - 1));
        await connect();
        return;
      }
      status.value = 'error';
      onError?.(error as Error);
    }
  }

  function handleFrame(frame: string): void {
    const dataLines = frame
      .split('\n')
      .filter((line) => line.startsWith('data:'))
      .map((line) => line.slice(5).trim());
    if (dataLines.length === 0) return;
    const payload = dataLines.join('\n');
    if (payload === '[DONE]') {
      ended = true;
      status.value = 'closed';
      onEnd?.();
      return;
    }
    try {
      onMessage?.(JSON.parse(payload));
    } catch {
      onMessage?.(payload);
    }
  }

  return {
    status,
    retryCount,
    start: connect,
    stop: (): void => {
      stopped = true;
      controller.abort();
      if (status.value !== 'error') status.value = 'closed';
    },
  };
}
