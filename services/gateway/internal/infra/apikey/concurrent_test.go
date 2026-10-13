package apikey

import (
	"fmt"
	"sync"
	"testing"
	"time"
)

// TestMemoryStoreConcurrentAccess 验证 Key 校验（读）与吊销（写）并发安全。
//
// 这条用例的存在理由：鉴权在每个请求上读 Key，管理接口并发写 Key。
// 修复前 MemoryStore 用无锁 map，并发时会触发 Go runtime 的
// `concurrent map writes` —— 那是 fatal error，直接崩进程而非返回错误，
// 因此普通的"断言不报错"用例根本抓不到，必须真的并发跑。
func TestMemoryStoreConcurrentAccess(t *testing.T) {
	t.Parallel()

	store := NewMemoryStore()
	for i := 0; i < 50; i++ {
		store.Add(KeyRecord{
			KeyHash:   HashKey(fmt.Sprintf("sk-%d", i)),
			TenantID:  fmt.Sprintf("tenant-%d", i),
			SubjectID: "app-1",
		})
	}

	var wg sync.WaitGroup
	// 8 个读者：模拟并发鉴权
	for r := 0; r < 8; r++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			for j := 0; j < 200; j++ {
				_, err := store.Lookup(HashKey(fmt.Sprintf("sk-%d", j%50)))
				if err != nil {
					t.Errorf("lookup failed: %v", err)
					return
				}
			}
		}()
	}
	// 2 个写者：模拟 Key 签发与吊销
	for w := 0; w < 2; w++ {
		wg.Add(1)
		go func(id int) {
			defer wg.Done()
			for j := 0; j < 100; j++ {
				store.Add(KeyRecord{
					KeyHash:   HashKey(fmt.Sprintf("sk-new-%d-%d", id, j)),
					TenantID:  "tenant-new",
					ExpiresAt: time.Now().Add(time.Hour),
				})
				store.Revoke(HashKey(fmt.Sprintf("sk-%d", j%50)))
			}
		}(w)
	}
	wg.Wait()
}

// TestRevokeBlocksAuthentication 验证吊销后鉴权被拒。
func TestRevokeBlocksAuthentication(t *testing.T) {
	t.Parallel()

	store := NewMemoryStore()
	store.Add(KeyRecord{
		KeyHash:   HashKey("sk-revokable"),
		TenantID:  "tenant-a",
		SubjectID: "app-1",
	})
	a := New(store, nil)

	r := requestWithKey("sk-revokable")
	if _, err := a.Authenticate(r); err != nil {
		t.Fatalf("key should be valid before revoke, got %v", err)
	}

	store.Revoke(HashKey("sk-revokable"))

	if _, err := a.Authenticate(r); err == nil {
		t.Fatal("revoked key must be rejected")
	}
}
