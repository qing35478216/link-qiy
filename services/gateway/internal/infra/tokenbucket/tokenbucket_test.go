package tokenbucket

import (
	"sync"
	"testing"
	"time"

	"github.com/linkai/gateway/internal/ratelimit"
)

// fixedNow 是测试基准时刻。
var fixedNow = time.Date(2026, 10, 13, 12, 0, 0, 0, time.UTC)

// 测试预算：窗口 1 秒、上限 N 次，便于确定性地触发限流。
func budget(n int) ratelimit.Budget {
	return ratelimit.Budget{Limit: n, Window: time.Second}
}

// TestAllow_ExhaustsAtLimit 验证配额用尽后被拒。
func TestAllow_ExhaustsAtLimit(t *testing.T) {
	t.Parallel()

	now := fixedNow
	l := New(WithClock(func() time.Time { return now }), WithBurstRatio(1))
	b := budget(3)

	for i := 1; i <= 3; i++ {
		d, err := l.Allow("k", b)
		if err != nil {
			t.Fatalf("request %d: unexpected error %v", i, err)
		}
		if !d.Allowed {
			t.Fatalf("request %d should be allowed", i)
		}
	}

	d, err := l.Allow("k", b)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if d.Allowed {
		t.Fatal("4th request should be rejected")
	}
	if d.RetryAfter <= 0 {
		t.Error("rejected decision should carry a positive RetryAfter")
	}
}

// TestAllow_KeyIsolation 验证不同键的配额互不影响。
func TestAllow_KeyIsolation(t *testing.T) {
	t.Parallel()

	l := New(WithClock(func() time.Time { return fixedNow }))
	b := budget(2)

	for i := 0; i < 2; i++ {
		if d, _ := l.Allow("tenant-a", b); !d.Allowed {
			t.Fatalf("tenant-a request %d should pass", i)
		}
	}
	if d, _ := l.Allow("tenant-a", b); d.Allowed {
		t.Fatal("tenant-a should be exhausted")
	}
	// tenant-b 有独立配额，不该受 tenant-a 影响。
	if d, _ := l.Allow("tenant-b", b); !d.Allowed {
		t.Fatal("tenant-b must have its own budget")
	}
}

// TestAllow_RefillsOverTime 验证配额随时间恢复。
func TestAllow_RefillsOverTime(t *testing.T) {
	t.Parallel()

	now := fixedNow
	l := New(WithClock(func() time.Time { return now }))
	// 窗口 100ms、上限 2 → 速率 20/s。
	b := ratelimit.Budget{Limit: 2, Window: 100 * time.Millisecond}

	for i := 0; i < 2; i++ {
		if d, _ := l.Allow("k", b); !d.Allowed {
			t.Fatalf("initial request %d should pass", i)
		}
	}
	if d, _ := l.Allow("k", b); d.Allowed {
		t.Fatal("should be exhausted before refill")
	}

	// 前进 100ms 应补满 2 个令牌。
	now = now.Add(100 * time.Millisecond)
	for i := 0; i < 2; i++ {
		if d, _ := l.Allow("k", b); !d.Allowed {
			t.Fatalf("request %d should pass after refill", i)
		}
	}
}

// TestAllow_RejectsInvalidBudget 验证非法预算被拒。
func TestAllow_RejectsInvalidBudget(t *testing.T) {
	t.Parallel()

	l := New(WithClock(func() time.Time { return fixedNow }))
	for _, b := range []ratelimit.Budget{
		{Limit: 0, Window: time.Second},
		{Limit: -1, Window: time.Second},
		{Limit: 5, Window: 0},
	} {
		if _, err := l.Allow("k", b); err == nil {
			t.Errorf("budget %+v should be rejected", b)
		}
	}
}

// TestAllow_ConcurrentSafety 验证并发访问不产生数据竞争。
//
// 令牌桶是多入口共用的共享状态，竞态会导致超发或 panic。
// 配合 -race 运行才有意义。
func TestAllow_ConcurrentSafety(t *testing.T) {
	t.Parallel()

	l := New(WithClock(func() time.Time { return fixedNow }))
	b := budget(1000)

	var wg sync.WaitGroup
	for i := 0; i < 50; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			for j := 0; j < 20; j++ {
				if _, err := l.Allow("shared", b); err != nil {
					t.Errorf("unexpected error: %v", err)
					return
				}
			}
		}()
	}
	wg.Wait()
}

// TestAllow_ConcurrentNeverExceedsLimit 验证并发下实际发放数不超过上限。
func TestAllow_ConcurrentNeverExceedsLimit(t *testing.T) {
	t.Parallel()

	const limit = 50
	l := New(WithClock(func() time.Time { return fixedNow }))
	b := budget(limit)

	var mu sync.Mutex
	granted := 0

	var wg sync.WaitGroup
	for i := 0; i < 20; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			for j := 0; j < 10; j++ {
				d, err := l.Allow("race", b)
				if err != nil {
					t.Errorf("unexpected error: %v", err)
					return
				}
				if d.Allowed {
					mu.Lock()
					granted++
					mu.Unlock()
				}
			}
		}()
	}
	wg.Wait()

	if granted > limit {
		t.Fatalf("granted %d requests, budget was %d — over-issued", granted, limit)
	}
}

// TestEntryTTLReclaimsIdleKeys 验证空闲键会被回收，防止键空间无限增长。
func TestEntryTTLReclaimsIdleKeys(t *testing.T) {
	t.Parallel()

	now := fixedNow
	l := New(WithClock(func() time.Time { return now }), WithEntryTTL(time.Minute))
	b := budget(5)

	for _, k := range []string{"a", "b", "c", "d"} {
		if _, err := l.Allow(k, b); err != nil {
			t.Fatalf("unexpected error: %v", err)
		}
	}
	if got := l.Size(); got != 4 {
		t.Fatalf("Size = %d, want 4", got)
	}

	// 前进超过 TTL，再访问一个键触发回收扫描。
	now = now.Add(2 * time.Minute)
	if _, err := l.Allow("e", b); err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	// 原 4 个键应被回收，只剩新建的 "e"。
	if got := l.Size(); got != 1 {
		t.Fatalf("Size after sweep = %d, want 1", got)
	}
}

// TestBurstRatioAllowsBurst 验证突发倍数生效。
func TestBurstRatioAllowsBurst(t *testing.T) {
	t.Parallel()

	now := fixedNow
	l := New(WithClock(func() time.Time { return now }), WithBurstRatio(3))
	// 窗口 1 分钟、上限 2 → 稳态速率极低，突发容量 = 2*3 = 6。
	b := ratelimit.Budget{Limit: 2, Window: time.Minute}

	granted := 0
	for i := 0; i < 10; i++ {
		if d, _ := l.Allow("burst", b); d.Allowed {
			granted++
		}
	}
	if granted != 6 {
		t.Fatalf("granted %d, want 6 (limit 2 × burst 3)", granted)
	}
}
