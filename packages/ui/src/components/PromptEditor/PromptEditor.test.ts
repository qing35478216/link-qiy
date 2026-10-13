import { describe, expect, it } from 'vitest';
import { mount } from '@vue/test-utils';
import LkPromptEditor from './PromptEditor.vue';

describe('LkPromptEditor', () => {
  it('renders value and char count', () => {
    const wrapper = mount(LkPromptEditor, {
      props: { modelValue: '你是专业推演师', maxLength: 8000 },
    });
    expect(wrapper.find('textarea').element.value).toBe('你是专业推演师');
    expect(wrapper.text()).toContain('7/8000');
  });

  it('emits update:modelValue on input', async () => {
    const wrapper = mount(LkPromptEditor, { props: { modelValue: '' } });
    await wrapper.find('textarea').setValue('新提示词');
    expect(wrapper.emitted('update:modelValue')).toEqual([['新提示词']]);
  });

  it('inserts variable token on tag click', async () => {
    const wrapper = mount(LkPromptEditor, {
      props: { modelValue: '开头', variables: ['userName', 'topic'] },
    });
    const tags = wrapper.findAll('.lk-prompt-editor__variable');
    await tags[0].trigger('click');
    expect(wrapper.emitted('update:modelValue')).toEqual([['开头{{userName}}']]);
  });

  it('emits optimize with current value', async () => {
    const wrapper = mount(LkPromptEditor, { props: { modelValue: '待优化' } });
    await wrapper.findAll('button').find((b) => b.text() === '一键优化')!.trigger('click');
    expect(wrapper.emitted('optimize')).toEqual([['待优化']]);
  });

  it('marks over-limit count', () => {
    const wrapper = mount(LkPromptEditor, { props: { modelValue: '123456', maxLength: 3 } });
    expect(wrapper.find('.lk-prompt-editor__count').classes()).toContain(
      'lk-prompt-editor__count--over',
    );
  });
});
