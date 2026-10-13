package domain

import (
	"context"
	"testing"
	"time"
)

// fixedNow 是测试基准时刻。
var fixedNow = time.Date(2026, 10, 13, 12, 0, 0, 0, time.UTC)

// TestIsExpired 覆盖过期判定的各种边界。
func TestIsExpired(t *testing.T) {
	t.Parallel()

	cases := []struct {
		name      string
		expiresAt time.Time
		want      bool
	}{
		{"无过期时间视为永不过期", time.Time{}, false},
		{"过期时间在未来", fixedNow.Add(time.Hour), false},
		{"过期时间在过去", fixedNow.Add(-time.Second), true},
		{"恰好等于当前时刻即视为过期", fixedNow, true},
		{"过期时间恰在 1ns 后", fixedNow.Add(time.Nanosecond), false},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			p := Principal{TenantID: "tenant-a", ExpiresAt: tc.expiresAt}
			if got := p.IsExpired(fixedNow); got != tc.want {
				t.Errorf("IsExpired = %v, want %v", got, tc.want)
			}
		})
	}
}

// TestHasScope 覆盖 scope 查询。
func TestHasScope(t *testing.T) {
	t.Parallel()

	p := Principal{Scopes: []string{"app:read", "app:write"}}
	if !p.HasScope("app:read") {
		t.Error("expected app:read to be present")
	}
	if !p.HasScope("app:write") {
		t.Error("expected app:write to be present")
	}
	if p.HasScope("app:delete") {
		t.Error("app:delete should not be present")
	}
	if p.HasScope("") {
		t.Error("empty scope should not match")
	}

	// 空 scope 列表。
	if (Principal{}).HasScope("anything") {
		t.Error("principal without scopes should have none")
	}
}

// TestContextRoundTrip 验证 Principal 写入与读出。
func TestContextRoundTrip(t *testing.T) {
	t.Parallel()

	p := Principal{TenantID: "tenant-a", SubjectID: "user-1"}
	ctx := WithPrincipal(context.Background(), p)

	got, ok := PrincipalFrom(ctx)
	if !ok {
		t.Fatal("principal should be present in context")
	}
	// Principal 含 slice 不可直接比较，逐字段断言。
	if got.TenantID != p.TenantID || got.SubjectID != p.SubjectID || got.Kind != p.Kind {
		t.Errorf("round trip mismatch: got %+v, want %+v", got, p)
	}
}

// TestContextMissingPrincipal 验证空 context 上读取安全失败。
func TestContextMissingPrincipal(t *testing.T) {
	t.Parallel()

	if _, ok := PrincipalFrom(context.Background()); ok {
		t.Error("principal should be absent from an empty context")
	}
}

// TestSurfaceRoundTrip 验证 Surface 写入与读出。
func TestSurfaceRoundTrip(t *testing.T) {
	t.Parallel()

	ctx := WithSurface(context.Background(), SurfaceEmbed)
	got, ok := SurfaceFrom(ctx)
	if !ok {
		t.Fatal("surface should be present in context")
	}
	if got != SurfaceEmbed {
		t.Errorf("surface = %q, want embed", got)
	}
}

// TestSurfaceMissing 验证空 context 上读取安全失败。
func TestSurfaceMissing(t *testing.T) {
	t.Parallel()

	if _, ok := SurfaceFrom(context.Background()); ok {
		t.Error("surface should be absent from an empty context")
	}
}

// TestAllSurfaces 验证入口面列表完整且顺序稳定。
func TestAllSurfaces(t *testing.T) {
	t.Parallel()

	got := AllSurfaces()
	want := []Surface{SurfaceConsole, SurfaceService, SurfaceEmbed}
	if len(got) != len(want) {
		t.Fatalf("AllSurfaces() = %v, want %v", got, want)
	}
	for i := range want {
		if got[i] != want[i] {
			t.Fatalf("AllSurfaces() = %v, want %v (stable order)", got, want)
		}
	}
}

// TestAllSurfacesReturnsCopy 验证返回值是副本，调用方改写不影响原列表。
func TestAllSurfacesReturnsCopy(t *testing.T) {
	t.Parallel()

	got := AllSurfaces()
	got[0] = "mutated"
	if AllSurfaces()[0] != SurfaceConsole {
		t.Error("AllSurfaces must return a copy, not the underlying slice")
	}
}
