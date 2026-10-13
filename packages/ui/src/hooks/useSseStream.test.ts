import { describe, expect, it, vi } from 'vitest';
import { nextTick } from 'vue';
import { useSseStream } from './useSseStream';

function sseResponse(frames: string[]): Response {
  const body = new ReadableStream<Uint8Array>({
    start(controller) {
      const encoder = new TextEncoder();
      for (const frame of frames) controller.enqueue(encoder.encode(`${frame}\n\n`));
      controller.close();
    },
  });
  return new Response(body, { status: 200, headers: { 'Content-Type': 'text/event-stream' } });
}

describe('useSseStream', () => {
  it('parses data frames and closes on [DONE]', async () => {
    const onMessage = vi.fn();
    const onEnd = vi.fn();
    const fetchImpl = vi.fn().mockResolvedValue(sseResponse(['data: {"text":"你好"}', 'data: [DONE]']));
    const stream = useSseStream('https://mock/sse', { onMessage, onEnd, fetchImpl });

    await stream.start();
    await nextTick();

    expect(stream.status.value).toBe('closed');
    expect(onMessage).toHaveBeenCalledWith({ text: '你好' });
    expect(onEnd).toHaveBeenCalledTimes(1);
  });

  it('retries on failure then errors after maxRetries', async () => {
    vi.useFakeTimers();
    const onError = vi.fn();
    const fetchImpl = vi.fn().mockRejectedValue(new Error('network down'));
    const stream = useSseStream('https://mock/sse', {
      onError,
      fetchImpl,
      maxRetries: 2,
      retryBaseMs: 10,
    });

    const started = stream.start();
    await vi.runAllTimersAsync();
    await started;

    expect(stream.retryCount.value).toBe(2);
    expect(stream.status.value).toBe('error');
    expect(onError).toHaveBeenCalledTimes(1);
    vi.useRealTimers();
  });

  it('stops without error when aborted', async () => {
    const fetchImpl = vi.fn().mockImplementation((_url: string, init: RequestInit) => {
      return new Promise((_resolve, reject) => {
        init.signal?.addEventListener('abort', () => reject(new DOMException('aborted', 'AbortError')));
      });
    });
    const stream = useSseStream('https://mock/sse', { fetchImpl });
    const started = stream.start();
    stream.stop();
    await started;
    expect(stream.status.value).toBe('closed');
  });
});
