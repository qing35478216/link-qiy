// Command gateway 是 LinkAI 的 API 网关进程。
//
// 它只做协议/连接/路由四件事（鉴权、限流、CORS 三角分离、反向代理），
// 不含任何业务或 AI 逻辑——业务在 Python 服务侧。
package main

import (
	"context"
	"log/slog"
	"os"
	"os/signal"
	"syscall"
	"time"

	_ "github.com/linkai/gateway/internal/infra/proxy" // 装配反代适配器

	"github.com/linkai/gateway/internal/config"
	"github.com/linkai/gateway/internal/server"
)

func main() {
	logger := slog.New(slog.NewJSONHandler(os.Stdout, &slog.HandlerOptions{
		Level: slog.LevelInfo,
	}))
	slog.SetDefault(logger)

	cfg, err := config.Load()
	if err != nil {
		// 启动期配置错误必须显式失败，且原因要可读。
		logger.Error("gateway config invalid", "error", err)
		os.Exit(1)
	}

	srv, err := server.New(server.Deps{Cfg: cfg})
	if err != nil {
		logger.Error("gateway assembly failed", "error", err)
		os.Exit(1)
	}

	go func() {
		logger.Info("gateway started", "addr", cfg.Addr)
		if err := srv.ListenAndServe(); err != nil {
			logger.Error("gateway serve failed", "error", err)
			os.Exit(1)
		}
	}()

	// 优雅关闭：收到终止信号后给在途请求一个收尾窗口。
	quit := make(chan os.Signal, 1)
	signal.Notify(quit, syscall.SIGINT, syscall.SIGTERM)
	<-quit
	logger.Info("gateway shutting down")

	ctx, cancel := context.WithTimeout(context.Background(), 15*time.Second)
	defer cancel()
	if err := srv.Shutdown(ctx); err != nil {
		logger.Error("gateway shutdown failed", "error", err)
		os.Exit(1)
	}
	logger.Info("gateway stopped")
}
