import { describe, expect, it, vi } from 'vitest';
import { mount } from '@vue/test-utils';
import LkFileUploader from './FileUploader.vue';

function createFile(name: string, size: number, type = 'text/plain'): File {
  const file = new File(['x'], name, { type });
  Object.defineProperty(file, 'size', { value: size });
  return file;
}

describe('LkFileUploader', () => {
  it('accepts valid file and emits change', async () => {
    const wrapper = mount(LkFileUploader, {
      props: { accept: '.txt', maxSizeMb: 1 },
    });
    const upload = wrapper.findComponent({ name: 'ElUpload' });
    upload.vm.$emit('change', { raw: createFile('a.txt', 100) }, [{ raw: createFile('a.txt', 100), name: 'a.txt' }]);
    await wrapper.vm.$nextTick();
    expect(wrapper.emitted('change')?.[0]?.[0]).toEqual([
      expect.objectContaining({ name: 'a.txt', size: 100, status: 'ready' }),
    ]);
    expect(wrapper.text()).toContain('a.txt');
  });

  it('rejects oversized file and emits error', async () => {
    const wrapper = mount(LkFileUploader, { props: { maxSizeMb: 1 } });
    const upload = wrapper.findComponent({ name: 'ElUpload' });
    upload.vm.$emit('change', { raw: createFile('big.txt', 5 * 1024 * 1024) }, []);
    await wrapper.vm.$nextTick();
    expect(wrapper.emitted('error')?.[0]?.[0]).toContain('超过 1MB 限制');
  });

  it('rejects disallowed type', async () => {
    const wrapper = mount(LkFileUploader, { props: { accept: '.pdf,.txt' } });
    const upload = wrapper.findComponent({ name: 'ElUpload' });
    upload.vm.$emit('change', { raw: createFile('evil.exe', 10) }, []);
    await wrapper.vm.$nextTick();
    expect(wrapper.emitted('error')?.[0]?.[0]).toContain('类型不支持');
  });

  it('removes file from list', async () => {
    const wrapper = mount(LkFileUploader, { props: {} });
    const upload = wrapper.findComponent({ name: 'ElUpload' });
    const file = createFile('a.txt', 100);
    upload.vm.$emit('change', { raw: file }, [{ raw: file, name: 'a.txt' }]);
    await wrapper.vm.$nextTick();
    await wrapper.find('.lk-file-uploader__item button').trigger('click');
    expect(wrapper.find('.lk-file-uploader__list').exists()).toBe(false);
    expect(wrapper.emitted('change')?.at(-1)?.[0]).toEqual([]);
  });
});
