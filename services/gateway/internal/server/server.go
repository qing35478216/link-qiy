// Package server 是网关的装配层：把四个横切机制组装成一条处理链。
//
// 装配顺序即安全语义，不可随意调整：
//
//	① 路由解析   —— 只匹配路由并标记入口面，不做任何鉴权判断
//	② CORS       —— 必须在鉴权之前：OPTIONS 预检不携带凭证，
//	                若先过鉴权则所有跨域预检都会 401
//	③ 鉴权       —— 确立 Principal 与租户
//	④ 限流       —— 依赖 ③ 写入的 Principal 定租户配额
//	⑤ 路由转发   —— 依赖 ③ 的租户上下文转发到上游
//
// 为什么 ① 与 ⑤ 拆成两段：入口面必须在鉴权前就能确定（② 的前提），
// 而租户校验与转发必须看到 Principal（③ 的产物）。
//
// ② 与 ③⑤ 之间的顺序是"CORS 不与鉴权/路由耦合"的体现：
// CORS 中间件只从 context 读 Surface（由 ① 写入），
// 它不 import 鉴权与限流任一包，三者可各自单测。
package server

import (
	"context"
	"errors"
	"fmt"
	"net/http"
	"time"

	"github.com/go-chi/chi/v5"
	"github.com/go-chi/chi/v5/middleware"

	"github.com/linkai/gateway/internal/auth"
	"github.com/linkai/gateway/internal/config"
	"github.com/linkai/gateway/internal/cors"
	"github.com/linkai/gateway/internal/domain"
	"github.com/linkai/gateway/internal/infra/apikey"
	infraJWT "github.com/linkai/gateway/internal/infra/jwt"
	"github.com/linkai/gateway/internal/infra/proxy"
	"github.com/linkai/gateway/internal/infra/tokenbucket"
	"github.com/linkai/gateway/internal/ratelimit"
	"github.com/linkai/gateway/internal/routing"
)

// Deps 是装配所需的依赖。
type Deps struct {
	// Cfg 启动配置。
	Cfg *config.Config
	// KeyStore API Key 存储。生产接 Redis/DB；骨架阶段用内存实现。
	KeyStore apikey.Store
}

// Server 是网关实例。
type Server struct {
	cfg    *config.Config
	router chi.Router
	http   *http.Server
}

// New 装配网关。
//
// 装配期错误（配置非法、路由冲突、CORS 策略冲突）一律返回 error，
// 由 main 终止进程——启动失败必须是显式的，不能带着半成品配置跑起来。
func New(d Deps) (*Server, error) {
	if d.Cfg == nil {
		return nil, errors.New("server: nil config")
	}
	if err := d.Cfg.Validate(); err != nil {
		return nil, err
	}

	authMW, err := buildAuth(d.Cfg, d.KeyStore)
	if err != nil {
		return nil, err
	}
	limitMW, err := buildRateLimit(d.Cfg)
	if err != nil {
		return nil, err
	}
	corsMW, err := buildCORS(d.Cfg)
	if err != nil {
		return nil, err
	}
	resolver, forwarder, err := buildRouting(d.Cfg)
	if err != nil {
		return nil, err
	}

	r := chi.NewRouter()
	r.Use(middleware.RequestID)
	r.Use(middleware.Recoverer)
	r.Use(middleware.Timeout(60 * time.Second))

	// 健康检查不经任何横切机制：探针不该被鉴权/限流影响。
	r.Get("/healthz", func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte(`{"status":"ok"}`))
	})
	r.Get("/readyz", func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte(`{"status":"ready"}`))
	})

	// 装配链：路由解析 → CORS → 鉴权 → 限流 → 转发。
	r.Group(func(api chi.Router) {
		api.Use(resolver.Handle)
		api.Use(corsMW.Handle)
		api.Use(authMW.Handle)
		api.Use(limitMW.Handle)
		// 转发是终点而非中间件：没有匹配路由的请求已被 Resolver 拦成 404，
		// 走到这里的请求一定已解析出上游。
		api.NotFound(routing.HandleUnmatched)
		api.MethodNotAllowed(routing.HandleUnmatched)
		api.Handle("/*", forwarder.Handle(http.NotFoundHandler()))
	})

	return &Server{
		cfg: d.Cfg,
		// 斜杠路由已由路由注册表显式声明，这里关闭 chi 的自动斜杠重定向，
		// 避免 /service/v1/chat/ 与 /service/v1/chat 落到不同上游。
		router: r,
		http: &http.Server{
			Addr:              d.Cfg.Addr,
			Handler:           r,
			ReadHeaderTimeout: 10 * time.Second,
			ReadTimeout:       d.Cfg.ReadTimeout,
			WriteTimeout:      d.Cfg.WriteTimeout,
			IdleTimeout:       120 * time.Second,
		},
	}, nil
}

// Handler 暴露路由，供测试直接驱动。
func (s *Server) Handler() http.Handler { return s.router }

// buildAuth 装配鉴权：注册 JWT 与 API Key 两个适配器（铁律 4）。
func buildAuth(cfg *config.Config, store apikey.Store) (*auth.Middleware, error) {
	reg := auth.NewRegistry()
	reg.Register(infraJWT.New(infraJWT.Config{
		Secret: []byte(cfg.JWTSecret),
		Issuer: cfg.JWTIssuer,
		Leeway: cfg.JWTLeeway,
	}))
	if store == nil {
		store = apikey.NewMemoryStore()
	}
	reg.Register(apikey.New(store, time.Now))
	return auth.NewMiddleware(reg, time.Now), nil
}

// buildRateLimit 装配三维限流。
func buildRateLimit(cfg *config.Config) (*ratelimit.Middleware, error) {
	reg := ratelimit.NewPolicyRegistry()

	// 租户级：始终启用，是多租户平台的兜底闸门。
	tenantBucket := tokenbucket.New()
	if err := reg.Register(ratelimit.Policy{
		Dimension: ratelimit.DimensionTenant,
		Budget:    ratelimit.Budget{Limit: cfg.TenantRate, Window: cfg.TenantWindow},
		Limiter:   tenantBucket,
	}); err != nil {
		return nil, fmt.Errorf("register tenant policy: %w", err)
	}

	// 凭证级：防止单个 Key 打满整个租户配额。
	if cfg.KeyRate > 0 {
		keyBucket := tokenbucket.New()
		if err := reg.Register(ratelimit.Policy{
			Dimension: ratelimit.DimensionKey,
			Budget:    ratelimit.Budget{Limit: cfg.KeyRate, Window: cfg.KeyWindow},
			Limiter:   keyBucket,
		}); err != nil {
			return nil, fmt.Errorf("register key policy: %w", err)
		}
	}

	// 端点级：防止单个重接口（如对话）被刷。
	if cfg.EndpointRate > 0 {
		endpointBucket := tokenbucket.New()
		if err := reg.Register(ratelimit.Policy{
			Dimension: ratelimit.DimensionEndpoint,
			Budget:    ratelimit.Budget{Limit: cfg.EndpointRate, Window: cfg.EndpointWindow},
			Limiter:   endpointBucket,
		}); err != nil {
			return nil, fmt.Errorf("register endpoint policy: %w", err)
		}
	}

	return ratelimit.NewMiddleware(reg, nil), nil
}

// buildCORS 装配三组独立跨域策略。
func buildCORS(cfg *config.Config) (*cors.Middleware, error) {
	reg := cors.NewRegistry()

	// console：控制台。允许携带 Cookie，故不得用通配来源。
	consolePolicy, err := cors.NewPolicy(domain.SurfaceConsole,
		cors.WithAllowedOrigins(cfg.CORSConsoleOrigins...),
		cors.WithAllowedMethods("GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"),
		cors.WithAllowedHeaders("Authorization", "Content-Type", auth.HeaderTenantID, auth.HeaderAPIKey),
		cors.WithExposeHeaders("X-Request-Id", "X-RateLimit-Remaining"),
		cors.WithCredentials(cfg.CORSAllowCredentials),
		cors.WithMaxAge(600),
	)
	if err != nil {
		return nil, fmt.Errorf("console cors policy: %w", err)
	}
	if err := reg.Register(consolePolicy); err != nil {
		return nil, fmt.Errorf("register console cors: %w", err)
	}

	// service：开放 API。以 Bearer/API Key 认证，不依赖 Cookie，
	// 因此可安全使用通配来源（面向任意服务端的 SDK 调用）。
	servicePolicy, err := cors.NewPolicy(domain.SurfaceService,
		cors.WithAllowedOrigins(cfg.CORSServiceOrigins...),
		cors.WithAllowedMethods("GET", "POST", "OPTIONS"),
		cors.WithAllowedHeaders("Authorization", "Content-Type", auth.HeaderTenantID, auth.HeaderAPIKey),
		cors.WithExposeHeaders("X-Request-Id", "X-RateLimit-Remaining"),
		cors.WithMaxAge(600),
	)
	if err != nil {
		return nil, fmt.Errorf("service cors policy: %w", err)
	}
	if err := reg.Register(servicePolicy); err != nil {
		return nil, fmt.Errorf("register service cors: %w", err)
	}

	// embed：网页嵌入。第三方站点来源不可预知，用通配 + 禁止凭证。
	embedPolicy, err := cors.NewPolicy(domain.SurfaceEmbed,
		cors.WithAllowedOrigins(append(cfg.CORSEmbedOrigins, "*")...),
		cors.WithAllowedMethods("POST", "OPTIONS"),
		cors.WithAllowedHeaders("Content-Type"),
		cors.WithCredentials(false),
		cors.WithMaxAge(300),
	)
	if err != nil {
		return nil, fmt.Errorf("embed cors policy: %w", err)
	}
	if err := reg.Register(embedPolicy); err != nil {
		return nil, fmt.Errorf("register embed cors: %w", err)
	}

	return cors.NewMiddleware(reg), nil
}

// buildRouting 装配上游注册表、路由表，返回解析器与转发器两段。
func buildRouting(cfg *config.Config) (*routing.Resolver, *routing.Middleware, error) {
	table := routing.NewTable()

	for _, uc := range cfg.Upstreams {
		surface := domain.Surface(uc.Surface)
		if surface == "" {
			// 未声明入口面时按 service 处理：开放 API 是最保守的默认值。
			surface = domain.SurfaceService
		}
		if err := table.RegisterUpstream(routing.Upstream{
			Name:           uc.Name,
			Target:         uc.Target,
			Surface:        surface,
			RequiredScopes: uc.RequiredScopes,
		}); err != nil {
			return nil, nil, fmt.Errorf("register upstream %q: %w", uc.Name, err)
		}
	}

	for _, rc := range cfg.Routes {
		if err := table.RegisterRoute(routing.Route{
			Method:     rc.Method,
			PathPrefix: rc.PathPrefix,
			Upstream:   rc.Upstream,
		}); err != nil {
			return nil, nil, fmt.Errorf("register route %s %s: %w", rc.Method, rc.PathPrefix, err)
		}
	}

	if len(cfg.Routes) == 0 {
		return nil, nil, errors.New("server: no routes registered")
	}
	return routing.NewResolver(table), routing.NewMiddleware(proxy.New()), nil
}

// ListenAndServe 启动网关。
func (s *Server) ListenAndServe() error {
	if err := s.http.ListenAndServe(); err != nil && !errors.Is(err, http.ErrServerClosed) {
		return err
	}
	return nil
}

// Shutdown 优雅关闭。
func (s *Server) Shutdown(ctx context.Context) error {
	return s.http.Shutdown(ctx)
}
