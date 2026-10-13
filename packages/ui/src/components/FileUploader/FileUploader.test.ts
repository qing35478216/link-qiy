import { describe, expect, it } from 'vitest';
import { mount } from '@vue/test-utils';
import LkFileUploader from './FileUploader.vue';

function createFile(name: string, size: number): File {
  const file = new File(['x'], name, { type: 'text/plain' });
  Object.defineProperty(file, 'size', { value: size });
  return file;
}

/** 走真实链路：向隐藏 file input 派发 change 事件 */
async function selectFiles(wrapper: ReturnType<typeof mount>, files: File[]): Promise<void> {
  const input = wrapper.find('input[type="file"]').element as HTMLInputElement;
  Object.defineProperty(input, 'files', { value: files, configurable: true });
  input.dispatchEvent(new Event('change', { bubbles: true }));
  await wrapper.vm.$nextTick();
}

describe('LkFileUploader', () => {
  it('accepts valid file and emits change', async () => {
    const wrapper = mount(LkFileUploader, { props: { accept: '.txt', maxSizeMb: 1 } });
    await selectFiles(wrapper, [createFile('a.txt', 100)]);
    expect(wrapper.emitted('change')?.[0]?.[0]).toEqual([
      expect.objectContaining({ name: 'a.txt', size: 100, status: 'ready' }),
    ]);
    expect(wrapper.text()).toContain('a.txt');
  });

  it('rejects oversized file and emits error', async () => {
    const wrapper = mount(LkFileUploader, { props: { maxSizeMb: 1 } });
    await selectFiles(wrapper, [createFile('big.txt', 5 * 1024 * 1024)]);
    expect(wrapper.emitted('error')?.[0]?.[0]).toContain('超过 1MB 限制');
    expect(wrapper.find('.lk-file-uploader__list').exists()).toBe(false);
  });

  it('rejects disallowed type', async () => {
    const wrapper = mount(LkFileUploader, { props: { accept: '.pdf,.txt' } });
    await selectFiles(wrapper, [createFile('evil.exe', 10)]);
    expect(wrapper.emitted('error')?.[0]?.[0]).toContain('类型不支持');
  });

  it('removes file from list', async () => {
    const wrapper = mount(LkFileUploader, { props: {} });
    await selectFiles(wrapper, [createFile('a.txt', 100)]);
    await wrapper.find('.lk-file-uploader__item button').trigger('click');
    expect(wrapper.find('.lk-file-uploader__list').exists()).toBe(false);
    expect(wrapper.emitted('change')?.at(-1)?.[0]).toEqual([]);
  });
});
