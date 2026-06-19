package ws

import (
	"net/http/httptest"
	"testing"
)

func TestCheckWebSocketOriginAllowsLoopbackDefaults(t *testing.T) {
	t.Setenv(allowedOriginsEnv, "")

	origins := []string{
		"http://localhost:3000",
		"http://127.0.0.1:5173",
		"http://[::1]:8080",
	}

	for _, origin := range origins {
		req := httptest.NewRequest("GET", "/ws", nil)
		req.Header.Set("Origin", origin)

		if !checkWebSocketOrigin(req) {
			t.Fatalf("expected loopback origin %q to be allowed by default", origin)
		}
	}
}

func TestCheckWebSocketOriginRejectsRemoteOriginByDefault(t *testing.T) {
	t.Setenv(allowedOriginsEnv, "")

	req := httptest.NewRequest("GET", "/ws", nil)
	req.Header.Set("Origin", "https://evil.example")

	if checkWebSocketOrigin(req) {
		t.Fatal("expected remote origin to be rejected when no allowlist is configured")
	}
}

func TestCheckWebSocketOriginUsesConfiguredAllowlist(t *testing.T) {
	t.Setenv(allowedOriginsEnv, "https://app.example, https://admin.example/")

	allowed := httptest.NewRequest("GET", "/ws", nil)
	allowed.Header.Set("Origin", "https://admin.example")
	if !checkWebSocketOrigin(allowed) {
		t.Fatal("expected configured origin to be allowed")
	}

	rejected := httptest.NewRequest("GET", "/ws", nil)
	rejected.Header.Set("Origin", "http://localhost:3000")
	if checkWebSocketOrigin(rejected) {
		t.Fatal("expected unconfigured local origin to be rejected once an allowlist is set")
	}
}

func TestCheckWebSocketOriginAllowsRequestsWithoutOrigin(t *testing.T) {
	t.Setenv(allowedOriginsEnv, "https://app.example")

	req := httptest.NewRequest("GET", "/ws", nil)
	if !checkWebSocketOrigin(req) {
		t.Fatal("expected non-browser request without Origin header to be allowed")
	}
}

func TestCheckWebSocketOriginRejectsMalformedOrigin(t *testing.T) {
	t.Setenv(allowedOriginsEnv, "")

	req := httptest.NewRequest("GET", "/ws", nil)
	req.Header.Set("Origin", "://not-a-valid-origin")

	if checkWebSocketOrigin(req) {
		t.Fatal("expected malformed origin to be rejected")
	}
}
