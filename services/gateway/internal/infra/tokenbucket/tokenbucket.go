// Package tokenbucket 提供基于令牌桶的进程内限流器。
//
// 选型说明见 docs/选型对比.md：候选库 ulule/limiter 自 2024-12 起无提交
// （活跃度不满足铁律 8 核查项 ①），故改用 Go 官方 golang.org/x/time/rate
// 作为算法内核，外层自行实现按维度的键空间管理——内核本身是标准库级别的成熟实现。
package tokenbucket

import (
	"sync"
	"time"

	"golang.org/x/time/rate"

	"github.com/linkai/gateway/internal/ratelimit"
)

// entry 是一个键的桶状态。
type entry struct {
	limiter *rate.Limiter
	// limit/burst 记录当前生效的配置。只在配置真正变化时才调用
	// rate.Limiter 的 SetLimit/SetBurst——这两个方法会把令牌补满，
	// 若每次请求都调用，桶会被无限续命，限流形同虚设。
	limit    rate.Limit
	burst    int
	lastSeen time.Time
}

// Limiter 是进程内令牌桶限流器。
//
// 并发安全：所有状态访问由 mu 保护。适合单实例部署；
// 多实例横向扩容时替换为 Redis 实现即可，ratelimit.Limiter 接口不变。
type Limiter struct {
	mu      sync.Mutex
	buckets map[string]*entry

	// burstRatio 突发容量相对稳态速率的倍数。
	burstRatio float64
	// entryTTL 空闲键的回收时间，避免键空间无限增长。
	entryTTL time.Duration
	// now 可注入，便于测试。
	now func() time.Time
	// lastSweep 上次回收扫描时刻。
	lastSweep time.Time
}

// Option 是 Limiter 的可选配置。
type Option func(*Limiter)

// WithBurstRatio 设置突发倍数，默认 1（不允许突发）。
func WithBurstRatio(r float64) Option {
	return func(l *Limiter) {
		if r > 0 {
			l.burstRatio = r
		}
	}
}

// WithEntryTTL 设置空闲键回收时间，默认 10 分钟。
func WithEntryTTL(d time.Duration) Option {
	return func(l *Limiter) {
		if d > 0 {
			l.entryTTL = d
		}
	}
}

// WithClock 注入时钟，供测试使用。
func WithClock(now func() time.Time) Option {
	return func(l *Limiter) {
		if now != nil {
			l.now = now
		}
	}
}

// New 创建令牌桶限流器。
func New(opts ...Option) *Limiter {
	l := &Limiter{
		buckets:    make(map[string]*entry),
		burstRatio: 1,
		entryTTL:   10 * time.Minute,
		now:        time.Now,
	}
	for _, opt := range opts {
		opt(l)
	}
	l.lastSweep = l.now()
	return l
}

// Allow 实现 ratelimit.Limiter。
//
// 语义：固定速率 rate = Limit/Window，突发上限 = ceil(rate * burstRatio)。
// 用 x/time/rate 的 Limiter.Allow() 消费令牌——它内部按时间连续补充，
// 比"固定窗口计数器"更平滑，不会出现窗口边界的双倍突发。
func (l *Limiter) Allow(key string, budget ratelimit.Budget) (ratelimit.Decision, error) {
	if err := budget.Validate(); err != nil {
		return ratelimit.Decision{}, err
	}

	perSecond := rate.Limit(float64(budget.Limit) / budget.Window.Seconds())
	burst := budget.Limit
	if l.burstRatio != 1 {
		burst = int(float64(budget.Limit)*l.burstRatio + 0.5)
		if burst < 1 {
			burst = 1
		}
	}

	// 必须在锁内采样时钟。锁外采样会让并发 goroutine 拿着过期时间戳进锁，
	// 而 x/time/rate 的 reserveN 在 ok 时会执行 lim.last = t——
	// 过期时间戳会把 lim.last 拨回过去，后续 advance() 便把
	// "已被消费过的那段时间" 重复计入补充量，凭空多出令牌。
	// 实测（配额 50/秒、128 goroutine × 500 次）：修复前放行 170（超额 228%），
	// 修复后 51（-1.7%）。回归用例见 gateproof_test.go 的真实时钟用例。
	l.mu.Lock()
	defer l.mu.Unlock()

	now := l.now()

	l.sweepLocked(now)

	e, ok := l.buckets[key]
	if !ok {
		e = &entry{
			limiter: rate.NewLimiter(perSecond, burst),
			limit:   perSecond,
			burst:   burst,
		}
		l.buckets[key] = e
	}
	// 仅在配额配置变化时同步到桶；SetLimit/SetBurst 会补满令牌，
	// 每次都调用会让限流失效。同时用 SetXxxAt 传入注入的时钟，
	// 避免内部 time.Now() 与测试时钟不一致。
	if e.limit != perSecond {
		e.limiter.SetLimitAt(now, perSecond)
		e.limit = perSecond
	}
	if e.burst != burst {
		e.limiter.SetBurstAt(now, burst)
		e.burst = burst
	}
	e.lastSeen = now

	// 用 ReserveN 而非 AllowN：ReserveN 能算出"要等多久才有令牌"，
	// 便于返回 Retry-After。但 ReserveN 对未来时刻总是 ok=true，
	// 所以必须自行判定 delay 是否可接受，不接受就 Cancel 并拒绝。
	reservation := e.limiter.ReserveN(now, 1)
	if !reservation.OK() {
		// n 超过突发容量：即使桶是空的也永远等不到，直接拒绝。
		return ratelimit.Decision{
			Allowed: false,
			Limit:   budget.Limit,
		}, nil
	}

	delay := reservation.DelayFrom(now)
	if delay > 0 {
		// 需要等未来才有令牌 → 本次拒绝，并把预留的令牌还回去。
		reservation.CancelAt(now)
		return ratelimit.Decision{
			Allowed:    false,
			Limit:      budget.Limit,
			Remaining:  0,
			RetryAfter: delay,
			ResetAt:    now.Add(delay),
		}, nil
	}

	remaining := e.limiter.TokensAt(now)
	if remaining < 0 {
		remaining = 0
	}
	return ratelimit.Decision{
		Allowed:   true,
		Limit:     budget.Limit,
		Remaining: int(remaining),
		ResetAt:   now.Add(budget.Window),
	}, nil
}

// sweepLocked 回收长时间未使用的键。调用方必须已持锁。
func (l *Limiter) sweepLocked(now time.Time) {
	if now.Sub(l.lastSweep) < l.entryTTL {
		return
	}
	l.lastSweep = now
	for k, e := range l.buckets {
		if now.Sub(e.lastSeen) > l.entryTTL {
			delete(l.buckets, k)
		}
	}
}

// Size 返回当前活跃键数量，供测试与监控使用。
func (l *Limiter) Size() int {
	l.mu.Lock()
	defer l.mu.Unlock()
	return len(l.buckets)
}

// 编译期断言：令牌桶必须满足 ratelimit.Limiter 接口。
var _ ratelimit.Limiter = (*Limiter)(nil)
