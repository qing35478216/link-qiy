package domain

import "context"

// principalKey 是 Principal 在 context 中的键类型。
//
// 定义在 domain（最内层）而非 auth 或 ratelimit 包，是为了让鉴权写入、
// 限流读取共用同一个键：Go 的 context key 按类型比较，两个包各定义一个
// 未导出的同名类型会导致读取永远失败。放在 domain 里，
// 两个横切包都"向内依赖"domain，符合铁律 2，且互不 import。
type principalKey struct{}

// WithPrincipal 把 Principal 写入 context。仅供中间件与测试使用。
func WithPrincipal(ctx context.Context, p Principal) context.Context {
	return context.WithValue(ctx, principalKey{}, p)
}

// PrincipalFrom 从 context 读取 Principal。第二个返回值表示是否存在。
func PrincipalFrom(ctx context.Context) (Principal, bool) {
	p, ok := ctx.Value(principalKey{}).(Principal)
	return p, ok
}

// surfaceKey 是 Surface 在 context 中的键类型，同样定义在最内层，
// 让路由层（写）与 CORS 层（读）无需互相 import。
type surfaceKey struct{}

// WithSurface 把入口面写入 context。仅供路由层与测试使用。
func WithSurface(ctx context.Context, s Surface) context.Context {
	return context.WithValue(ctx, surfaceKey{}, s)
}

// SurfaceFrom 从 context 读取入口面。第二个返回值表示是否存在。
func SurfaceFrom(ctx context.Context) (Surface, bool) {
	s, ok := ctx.Value(surfaceKey{}).(Surface)
	return s, ok
}
