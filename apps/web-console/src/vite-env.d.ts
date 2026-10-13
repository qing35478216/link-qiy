/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** 控制台 API baseURL（契约 console-api.yaml） */
  readonly VITE_API_BASE_URL?: string;
  /** 用户面 API baseURL（契约 service-api.yaml） */
  readonly VITE_SERVICE_API_BASE_URL?: string;
  /** MSW Mock 开关，默认开（Phase 0） */
  readonly VITE_ENABLE_MSW?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
