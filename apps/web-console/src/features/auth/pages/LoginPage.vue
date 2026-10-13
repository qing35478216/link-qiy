<script setup lang="ts">
/**
 * LoginPage —— 手机号 + 短信验证码登录（契约：loginByPhone 强制协议勾选）。
 * Phase 0：验证码经 MSW Mock 任意值可登；微信扫码登录入口占位（契约已冻结）。
 */
import { computed, reactive, ref } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { ElMessage } from 'element-plus';
import { useAuthStore } from '@/app/stores/auth-store';

const authStore = useAuthStore();
const route = useRoute();
const router = useRouter();

const form = reactive({
  phone: '',
  smsCode: '',
  agreementAccepted: false,
});
const submitting = ref(false);
const countdown = ref(0);
let timer: ReturnType<typeof setInterval> | undefined;

const phoneValid = computed(() => /^1[3-9]\d{9}$/.test(form.phone));
const codeValid = computed(() => form.smsCode.length >= 4);
const canSubmit = computed(
  () => phoneValid.value && codeValid.value && form.agreementAccepted && !submitting.value,
);

async function sendCode(): Promise<void> {
  if (!phoneValid.value || countdown.value > 0) return;
  try {
    await authStore.sendSmsCode(form.phone);
    ElMessage.success('验证码已发送（Mock 环境任意 4 位数字可登）');
    countdown.value = 60;
    timer = setInterval(() => {
      countdown.value -= 1;
      if (countdown.value <= 0) clearInterval(timer);
    }, 1000);
  } catch {
    ElMessage.error('验证码发送失败，请稍后重试');
  }
}

async function onSubmit(): Promise<void> {
  if (!canSubmit.value) return;
  submitting.value = true;
  try {
    await authStore.loginWithPhone(form.phone, form.smsCode, form.agreementAccepted);
    await authStore.loadProfile();
    const redirect = typeof route.query.redirect === 'string' ? route.query.redirect : '/console/factory';
    await router.push(redirect);
  } catch {
    ElMessage.error('登录失败，请检查验证码');
  } finally {
    submitting.value = false;
  }
}
</script>

<template>
  <div class="login-page">
    <div class="login-page__panel">
      <div class="login-page__brand">
        <span class="login-page__logo">L</span>
        <h1 class="login-page__title">Link.AI 控制台</h1>
        <p class="login-page__subtitle">平台做框架，用户做创造</p>
      </div>

      <el-form label-position="top" class="login-page__form" @submit.prevent="onSubmit">
        <el-form-item label="手机号">
          <el-input v-model="form.phone" placeholder="请输入手机号" maxlength="11" />
        </el-form-item>

        <el-form-item label="验证码">
          <div class="login-page__code-row">
            <el-input v-model="form.smsCode" placeholder="请输入验证码" maxlength="8" />
            <el-button :disabled="!phoneValid || countdown > 0" @click="sendCode">
              {{ countdown > 0 ? `${countdown}s 后重发` : '获取验证码' }}
            </el-button>
          </div>
        </el-form-item>

        <el-checkbox v-model="form.agreementAccepted" class="login-page__agreement">
          我已阅读并同意《用户协议》与《隐私政策》
        </el-checkbox>

        <el-button
          type="primary"
          size="large"
          class="login-page__submit"
          :loading="submitting"
          :disabled="!canSubmit"
          @click="onSubmit"
        >
          登录
        </el-button>
      </el-form>
    </div>
  </div>
</template>

<style scoped>
.login-page {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 100vh;
  background: var(--lk-bg-page);
}

.login-page__panel {
  width: 380px;
  padding: var(--lk-space-8);
  background: var(--lk-bg-card);
  border: 0.5px solid var(--lk-border-color);
  border-radius: var(--lk-radius-modal);
  box-shadow: var(--lk-shadow-float);
}

.login-page__brand {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--lk-space-1);
}

.login-page__logo {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 44px;
  height: 44px;
  font-size: var(--lk-font-size-xl);
  font-weight: 700;
  color: var(--lk-text-inverse);
  background: var(--lk-color-primary);
  border-radius: var(--lk-radius-component);
}

.login-page__title {
  margin: var(--lk-space-2) 0 0;
  font-size: var(--lk-font-size-lg);
  color: var(--lk-text-primary);
}

.login-page__subtitle {
  margin: 0;
  font-size: var(--lk-font-size-xs);
  color: var(--lk-text-weak);
}

.login-page__form {
  margin-top: var(--lk-space-6);
}

.login-page__code-row {
  display: flex;
  gap: var(--lk-space-2);
  width: 100%;
}

.login-page__agreement {
  margin-bottom: var(--lk-space-4);
}

.login-page__submit {
  width: 100%;
}
</style>
