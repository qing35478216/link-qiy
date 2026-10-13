package tokenbucket

import (
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
