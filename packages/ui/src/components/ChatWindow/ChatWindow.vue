<script setup lang="ts">
/**
 * ChatWindow —— 对话窗（docs/04 2.3）：流式中 / 引导问题 / 多模态输入。
 * 消息状态：streaming 时光标闪烁；空会话且有引导问题时渲染可点击 chip。
 */
import { computed, ref } from 'vue';

export interface ChatWindowMessage {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  status?: 'streaming' | 'done' | 'error';
  createdAt?: string;
}

const props = withDefaults(
  defineProps<{
    messages: ChatWindowMessage[];
    streaming?: boolean;
    placeholder?: string;
    disabled?: boolean;
    guideQuestions?: string[];
    emptyHint?: string;
  }>(),
  { placeholder: '输入消息，Enter 发送', emptyHint: '开始一段对话吧' },
);

const emit = defineEmits<{
  (e: 'send', text: string): void;
  (e: 'stop'): void;
  (e: 'select-guide', question: string): void;
}>();

const draft = ref('');
const canSend = computed(() => draft.value.trim().length > 0 && !props.disabled);
const showGuides = computed(
  () => props.messages.length === 0 && (props.guideQuestions?.length ?? 0) > 0,
);

function submit(): void {
  if (!canSend.value) return;
  emit('send', draft.value.trim());
  draft.value = '';
}

function onEnter(event: KeyboardEvent): void {
  if (event.isComposing) return;
  if (event.shiftKey) return;
  event.preventDefault();
  submit();
}
</script>

<template>
  <div class="lk-chat-window">
    <div class="lk-chat-window__messages">
      <p v-if="messages.length === 0" class="lk-chat-window__empty">{{ emptyHint }}</p>
      <div
        v-for="message in messages"
        :key="message.id"
        class="lk-chat-window__message"
        :class="`lk-chat-window__message--${message.role}`"
      >
        <div v-if="message.role === 'assistant'" class="lk-chat-window__avatar">AI</div>
        <div class="lk-chat-window__bubble">
          <span class="lk-chat-window__content">{{ message.content }}</span>
          <span v-if="message.status === 'streaming'" class="lk-chat-window__cursor" />
          <span v-if="message.status === 'error'" class="lk-chat-window__error-tag">失败</span>
        </div>
      </div>
    </div>

    <div v-if="showGuides" class="lk-chat-window__guides">
      <span
        v-for="question in guideQuestions"
        :key="question"
        class="lk-chat-window__guide"
        @click="emit('select-guide', question)"
      >
        {{ question }}
      </span>
    </div>

    <div class="lk-chat-window__composer">
      <div class="lk-chat-window__icons">
        <el-icon class="lk-chat-window__icon" title="附件"><Paperclip /></el-icon>
        <el-icon class="lk-chat-window__icon" title="图片"><Picture /></el-icon>
      </div>
      <el-input
        v-model="draft"
        type="textarea"
        :rows="2"
        :disabled="disabled"
        :placeholder="placeholder"
        resize="none"
        @keydown.enter.exact.prevent="onEnter"
      />
      <el-button
        v-if="streaming"
        type="danger"
        plain
        round
        class="lk-chat-window__stop"
        @click="emit('stop')"
      >
        停止
      </el-button>
      <el-button
        v-else
        type="primary"
        round
        class="lk-chat-window__send"
        :disabled="!canSend"
        @click="submit"
      >
        发送
      </el-button>
    </div>
  </div>
</template>

<style scoped>
.lk-chat-window {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 320px;
}

.lk-chat-window__messages {
  display: flex;
  flex: 1;
  flex-direction: column;
  gap: var(--lk-space-3);
  overflow-y: auto;
  padding: var(--lk-space-2);
}

.lk-chat-window__empty {
  margin: auto;
  font-size: var(--lk-font-size-xs);
  color: var(--lk-text-weak);
}

.lk-chat-window__message {
  display: flex;
  align-items: flex-start;
  gap: var(--lk-space-2);
}

.lk-chat-window__message--user {
  flex-direction: row-reverse;
}

.lk-chat-window__avatar {
  display: flex;
  flex-shrink: 0;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  font-size: var(--lk-font-size-xs);
  color: var(--lk-color-primary);
  background: var(--lk-color-primary-bg);
  border-radius: var(--lk-radius-round);
}

.lk-chat-window__bubble {
  display: flex;
  align-items: center;
  gap: var(--lk-space-1);
  max-width: 80%;
  padding: var(--lk-space-2) var(--lk-space-3);
  font-size: var(--lk-font-size-sm);
  line-height: 1.6;
  color: var(--lk-text-primary);
  background: var(--lk-bg-hover);
  border-radius: var(--lk-radius-component);
  white-space: pre-wrap;
  word-break: break-word;
}

.lk-chat-window__message--user .lk-chat-window__bubble {
  color: var(--lk-text-inverse);
  background: var(--lk-color-primary);
}

.lk-chat-window__cursor {
  display: inline-block;
  width: 2px;
  height: 14px;
  background: var(--lk-color-primary);
  animation: lk-blink 0.8s step-start infinite;
}

.lk-chat-window__error-tag {
  font-size: var(--lk-font-size-xs);
  color: var(--lk-color-danger);
}

@keyframes lk-blink {
  50% {
    opacity: 0;
  }
}

.lk-chat-window__guides {
  display: flex;
  flex-wrap: wrap;
  gap: var(--lk-space-2);
  padding: var(--lk-space-2);
}

.lk-chat-window__guide {
  padding: 4px var(--lk-space-3);
  font-size: var(--lk-font-size-xs);
  color: var(--lk-text-secondary);
  background: var(--lk-bg-card);
  border: 0.5px solid var(--lk-border-color);
  border-radius: var(--lk-radius-round);
  cursor: pointer;
}

.lk-chat-window__guide:hover {
  color: var(--lk-color-primary);
  border-color: var(--lk-color-primary);
}

.lk-chat-window__composer {
  display: grid;
  grid-template-columns: auto 1fr auto;
  align-items: end;
  gap: var(--lk-space-2);
  padding: var(--lk-space-2);
  border-top: 0.5px solid var(--lk-border-color);
}

.lk-chat-window__icons {
  display: flex;
  gap: var(--lk-space-1);
}

.lk-chat-window__icon {
  padding: 6px;
  font-size: 16px;
  color: var(--lk-text-weak);
  cursor: pointer;
  border-radius: var(--lk-radius-component);
}

.lk-chat-window__icon:hover {
  color: var(--lk-color-primary);
  background: var(--lk-bg-hover);
}
</style>
