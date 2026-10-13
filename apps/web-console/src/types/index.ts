/**
 * types/ —— 契约类型唯一出口（铁律：全部 re-export 自 @linkai/sdk-ts 生成物，零手写）。
 */
export type {
  AdvancedConfig,
  App,
  AppConfig,
  AppType,
  BasicConfig,
  DataConfig,
  KnowledgeConfig,
  KnowledgeConfigMissStrategy,
  ListApps200,
  ListAppsParams,
  ListAppsType,
  LoginByPhone200,
  LoginByPhoneBody,
  ModelPromptConfig,
  ModelPromptConfigVariablesItem,
  PluginsConfig,
  PluginsConfigExecStrategy,
  PutAppConfig200,
  QuotaSummary,
  QuotaSummaryPlan,
  QuotaSummaryUsage,
  RefreshToken200,
  SendSmsCodeBody,
  ShareConfig,
  UserProfile,
  UserProfilePlan,
} from '@linkai/sdk-ts/console';

export type {
  ApiKey,
  ChatCompletionRequest,
  ChatCompletionResponse,
  ListApiKeys200,
  ListModels200,
  Model,
  ModelCapabilitiesItem,
  ModelPrice,
} from '@linkai/sdk-ts/service';
