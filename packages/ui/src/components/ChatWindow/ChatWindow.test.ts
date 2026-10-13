import { describe, expect, it } from 'vitest';
import { mount } from '@vue/test-utils';
import LkChatWindow from './ChatWindow.vue';
import type { ChatWindowMessage } from './ChatWindow.vue';

const messages: ChatWindowMessage[] = [
  { id: '1', role: 'user', content: '你好' },
  { id: '2', role: 'assistant', content: '在的', status: 'streaming' },
];

describe('LkChatWindow', () => {
  it('renders messages with role alignment and streaming cursor', () => {
    const wrapper = mount(LkChatWindow, { props: { messages } });
    expect(wrapper.text()).toContain('你好');
    expect(wrapper.text()).toContain('在的');
    const userMsg = wrapper.find('.lk-chat-window__message--user');
    expect(userMsg.classes()).toContain('lk-chat-window__message--user');
    expect(wrapper.find('.lk-chat-window__cursor').exists()).toBe(true);
  });

  it('emits send on button click and clears draft', async () => {
    const wrapper = mount(LkChatWindow, { props: { messages: [] } });
    await wrapper.find('textarea').setValue('问点什么');
    await wrapper.find('.lk-chat-window__send').trigger('click');
    expect(wrapper.emitted('send')).toEqual([['问点什么']]);
    expect((wrapper.find('textarea').element as HTMLTextAreaElement).value).toBe('');
  });

  it('disables send when draft is blank', () => {
    const wrapper = mount(LkChatWindow, { props: { messages: [] } });
    expect(wrapper.find('.lk-chat-window__send').attributes('disabled')).toBeDefined();
  });

  it('emits stop instead of send while streaming', async () => {
    const wrapper = mount(LkChatWindow, { props: { messages, streaming: true } });
    await wrapper.find('.lk-chat-window__stop').trigger('click');
    expect(wrapper.emitted('stop')).toHaveLength(1);
    expect(wrapper.find('.lk-chat-window__send').exists()).toBe(false);
  });

  it('renders guide chips and emits select-guide', async () => {
    const wrapper = mount(LkChatWindow, {
      props: { messages: [], guideQuestions: ['能做什么？'] },
    });
    await wrapper.find('.lk-chat-window__guide').trigger('click');
    expect(wrapper.emitted('select-guide')).toEqual([['能做什么？']]);
  });
});
