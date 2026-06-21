import { get, post } from './api';

type StoredValue = string | null;

class MemoryStorage {
  private values = new Map<string, string>();

  getItem(key: string): StoredValue {
    return this.values.has(key) ? this.values.get(key)! : null;
  }

  setItem(key: string, value: string): void {
    this.values.set(key, String(value));
  }

  removeItem(key: string): void {
    this.values.delete(key);
  }

  clear(): void {
    this.values.clear();
  }
}

const storage = new MemoryStorage();
Object.defineProperty(globalThis, 'localStorage', {
  value: storage,
  configurable: true,
});

function jsonResponse(status: number, data: unknown): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: { 'content-type': 'application/json' },
  });
}

function assert(condition: unknown, message: string): void {
  if (!condition) {
    throw new Error(message);
  }
}

async function validatesConcurrentRefresh(): Promise<void> {
  storage.clear();
  storage.setItem('auth_token', 'old-token');
  storage.setItem('refresh_token', 'refresh-ok');

  let refreshCalls = 0;
  const protectedAuthHeaders: string[] = [];

  globalThis.fetch = async (url, init) => {
    const requestUrl = String(url);
    const headers = init?.headers as Record<string, string>;
    if (requestUrl.endsWith('/auth/refresh')) {
      refreshCalls += 1;
      await new Promise(resolve => setTimeout(resolve, 5));
      return jsonResponse(200, {
        tokens: {
          accessToken: 'new-token',
          refreshToken: 'new-refresh',
          expiresIn: 3600,
          tokenType: 'Bearer',
        },
      });
    }

    protectedAuthHeaders.push(headers.Authorization);
    if (headers.Authorization === 'Bearer old-token') {
      return jsonResponse(401, { error: 'expired' });
    }
    return jsonResponse(200, { ok: true });
  };

  const [first, second] = await Promise.all([
    get<{ ok: boolean }>('/protected'),
    get<{ ok: boolean }>('/protected'),
  ]);

  assert(first.data.ok && second.data.ok, 'both protected requests should retry successfully');
  assert(refreshCalls === 1, `expected one refresh call, saw ${refreshCalls}`);
  assert(
    protectedAuthHeaders.filter(value => value === 'Bearer new-token').length === 2,
    'both retried requests should use the refreshed token',
  );
  assert(storage.getItem('auth_token') === 'new-token', 'new access token should be stored');
  assert(storage.getItem('refresh_token') === 'new-refresh', 'new refresh token should be stored');
}

async function validatesRefreshFailureClearsAuth(): Promise<void> {
  storage.clear();
  storage.setItem('auth_token', 'old-token');
  storage.setItem('refresh_token', 'bad-refresh');
  storage.setItem('tot_auth_tokens', JSON.stringify({ accessToken: 'old-token', refreshToken: 'bad-refresh' }));

  globalThis.fetch = async (url) => {
    if (String(url).endsWith('/auth/refresh')) {
      return jsonResponse(403, { error: 'invalid refresh' });
    }
    return jsonResponse(401, { error: 'expired' });
  };

  try {
    await get('/protected');
    throw new Error('request should fail when refresh fails');
  } catch (error) {
    assert((error as { code?: number }).code === 401, 'refresh failure should throw typed 401');
  }

  assert(storage.getItem('auth_token') === null, 'access token should be cleared');
  assert(storage.getItem('refresh_token') === null, 'refresh token should be cleared');
  assert(storage.getItem('tot_auth_tokens') === null, 'stored token bundle should be cleared');
}

async function validatesRefreshEndpointDoesNotLoop(): Promise<void> {
  storage.clear();
  storage.setItem('auth_token', 'old-token');
  storage.setItem('refresh_token', 'bad-refresh');

  let calls = 0;
  globalThis.fetch = async () => {
    calls += 1;
    return jsonResponse(401, { error: 'refresh denied' });
  };

  try {
    await post('/auth/refresh', { refreshToken: 'bad-refresh' });
    throw new Error('refresh endpoint request should fail');
  } catch (error) {
    assert((error as { code?: number }).code === 401, 'refresh endpoint should throw typed 401');
  }

  assert(calls === 1, `refresh endpoint should not recurse, saw ${calls} calls`);
}

await validatesConcurrentRefresh();
await validatesRefreshFailureClearsAuth();
await validatesRefreshEndpointDoesNotLoop();

console.log('api refresh validation passed');
