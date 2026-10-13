package tokenbucket

import (
	"strings"
	"sync"
	"sync/atomic"
	"testing"
	"time"

	"github.com/linkai/gateway/internal/ratelimit"
)

// TestGateProof_OverdraftWithRealClock 用真实推进时钟复现并发超发。
//
// 这个用例的存在理由：原有并发用例注入冻结时钟，时间不推进，
// 缺陷形态（锁外采样时钟导致 lim.last 被拨回过去）根本无法出现。
// 故本用例刻意用真实时钟——
//
//	配额 50/秒，128 goroutine × 500 次。
//	理论上限 ≈ burst(50) + 补充速率(50/s) × 实际耗时。
//	修复前实测放行 141~174（超额 173%~239%）；修复后应回落到 51 附近。
func TestGateProof_OverdraftWithRealClock(t *testing.T) {
	const (
		limit      = 50
		window     = time.Second
		goroutines = 128
		perG       = 500
	)

	l := New() // 真实时钟，不注入冻结时钟

	start := time.Now()
	var granted atomic.Int64
	var wg sync.WaitGroup
	for i := 0; i < goroutines; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			for j := 0; j < perG; j++ {
				d, err := l.Allow("shared", ratelimit.Budget{Limit: limit, Window: window})
				if err == nil && d.Allowed {
					granted.Add(1)
				}
			}
		}()
	}
	wg.Wait()
	elapsed := time.Since(start)

	// 理论上界：突发容量 + 补充速率 × 耗时。留 25% 余量吸收调度抖动。
	refill := float64(limit) / window.Seconds() * elapsed.Seconds()
	theoretical := float64(limit) + refill
	budget := theoretical * 1.25

	got := float64(granted.Load())
	t.Logf("elapsed=%v  放行=%d  理论上界=%.1f  允许上界=%.1f  超额=%+.1f%%",
		elapsed, granted.Load(), theoretical, budget, (got-theoretical)/theoretical*100)

	if got > budget {
		t.Fatalf("并发超发：放行 %d，超出理论上界 %.1f（配额 %d/%v）",
			granted.Load(), budget, limit, window)
	}
}

// TestEntryTTLMustExceedWindow 锁定"键回收时间必须长于限流窗口"这条不变量。
//
// 门禁复评提出：若把 entryTTL 调到小于窗口，键会在窗口内被回收，
// 下次访问拿到全新满桶 → 配额被重置 → 开出绕过面，
// 而此前没有任何东西拦住这个配置。
//
// 这条断言的价值在于：它把"默认值恰好正确"变成"配置错误立刻失败"。
func TestEntryTTLMustExceedWindow(t *testing.T) {
	t.Parallel()

	t.Run("entryTTL 小于窗口时拒绝配置", func(t *testing.T) {
		t.Parallel()
		// 回收时间 10s，但窗口 1 分钟 → 键会在窗口内被回收
		l := New(WithEntryTTL(10 * time.Second))
		_, err := l.Allow("k", ratelimit.Budget{Limit: 5, Window: time.Minute})
		if err == nil {
			t.Fatal("entryTTL < 窗口必须被拒绝，否则配额会被重置形成绕过")
		}
		if !strings.Contains(err.Error(), "entryTTL") {
			t.Errorf("错误信息应说明是 entryTTL 的问题，实际: %v", err)
		}
	})

	t.Run("entryTTL 等于窗口时也拒绝", func(t *testing.T) {
		t.Parallel()
		// 相等同样不安全：恰好在窗口结束时回收，边界上仍可重置
		l := New(WithEntryTTL(time.Minute))
		if _, err := l.Allow("k", ratelimit.Budget{Limit: 5, Window: time.Minute}); err == nil {
			t.Fatal("entryTTL == 窗口必须被拒绝（边界不安全）")
		}
	})

	t.Run("entryTTL 大于窗口时正常放行", func(t *testing.T) {
		t.Parallel()
		l := New(WithEntryTTL(10 * time.Minute))
		d, err := l.Allow("k", ratelimit.Budget{Limit: 5, Window: time.Minute})
		if err != nil {
			t.Fatalf("合法配置不应报错: %v", err)
		}
		if !d.Allowed {
			t.Error("合法配置下应放行")
		}
	})
}

// TestIdleKeyDoesNotResetQuotaWhileWindowOpen 验证安全配置下闲置不构成绕过。
//
// 注意窗口的语义：Budget.Window 决定**补充速率**（limit per window），
// 不是硬性重置窗口。所以闲置足够久后桶被补满是令牌桶的正常行为，不是绕过。
//
// 真正要防的是"键被提前回收导致拿到全新满桶"——即便按速率本不该补满。
// 故本用例让闲置时长**不足以补回一个令牌**（速率 3/60s=0.05/s，
// 补 1 个令牌需 20s），此时若仍然放行，说明发生了提前回收。
func TestIdleKeyDoesNotResetQuotaWhileWindowOpen(t *testing.T) {
	t.Parallel()

	now := fixedNow
	// entryTTL=1h，远大于任何测试闲置时长 → 键不会被回收
	l := New(WithClock(func() time.Time { return now }), WithEntryTTL(time.Hour))
	b := ratelimit.Budget{Limit: 3, Window: time.Minute} // 速率 0.05/s

	for i := 0; i < 3; i++ {
		if d, _ := l.Allow("tenant-a", b); !d.Allowed {
			t.Fatalf("前 %d 次应放行", i+1)
		}
	}
	// 闲置 10s：按速率只补回 0.5 个令牌，不足以放行一次
	now = now.Add(10 * time.Second)
	if d, _ := l.Allow("tenant-a", b); d.Allowed {
		t.Error("按补充速率此刻不该有令牌；若放行说明键被提前回收、配额被重置")
	}
}
