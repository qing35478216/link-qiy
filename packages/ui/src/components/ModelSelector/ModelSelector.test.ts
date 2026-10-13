import { describe, expect, it } from 'vitest';
import { mount } from '@vue/test-utils';
import LkModelSelector from './ModelSelector.vue';
import type { ModelSelectorOption } from './ModelSelector.vue';

const models: ModelSelectorOption[] = [
  { code: 'gpt-4o', name: 'GPT-4o', provider: 'OpenAI', capabilities: ['chat', 'vision'], contextLength: 128000, price: { inputPer1k: 0.005, outputPer1k: 0.015 } },
  { code: 'gpt-4o-mini', name: 'GPT-4o mini', provider: 'OpenAI', capabilities: ['chat'], price: { creditPerCall: 2 } },
];

describe('LkModelSelector', () => {
  it('renders selected hint and option details', async () => {
    const wrapper = mount(LkModelSelector, {
      props: { modelValue: 'gpt-4o', models },
    });
    expect(wrapper.text()).toContain('GPT-4o');
    expect(wrapper.text()).toContain('上下文 128000');
  });

  it('emits update:modelValue and change when selecting', async () => {
    const wrapper = mount(LkModelSelector, { props: { models } });
    await wrapper.find('.lk-model-selector__select').trigger('click');
    await wrapper.findComponent({ name: 'ElSelect' }).vm.$emit('change', 'gpt-4o-mini');
    expect(wrapper.emitted('update:modelValue')).toEqual([['gpt-4o-mini']]);
    expect(wrapper.emitted('change')?.[0]?.[0]?.code).toBe('gpt-4o-mini');
  });

  it('renders price per call when creditPerCall', () => {
    const wrapper = mount(LkModelSelector, { props: { modelValue: 'gpt-4o-mini', models } });
    expect(wrapper.text()).toContain('GPT-4o mini');
  });
});
