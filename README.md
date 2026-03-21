# fastapi-limiter

Rate limiting for FastAPI. Two ways to use it: as a dependency on individual routes, or as middleware across the whole app.

```python
from fastapi import Depends
from fastapi_limiter import RateLimiter

@app.get("/search", dependencies=[Depends(RateLimiter(limit=10, window=60))])
async def search():
    ...
```

---

## Install

```bash
pip install fastapi-limiter
```

---

## Usage

### Per-route limiting

Attach `RateLimiter` as a dependency to any route. Each client (by IP + path) gets its own counter.

```python
from fastapi import FastAPI, Depends
from fastapi_limiter import RateLimiter

app = FastAPI()

# 10 requests per minute
@app.get("/api/search", dependencies=[Depends(RateLimiter(limit=10, window=60))])
async def search(q: str):
    return {"results": []}

# 3 requests per 10 seconds — stricter endpoint
@app.post("/api/generate", dependencies=[Depends(RateLimiter(limit=3, window=10))])
async def generate(prompt: str):
    return {"output": "..."}
```

When the limit is hit, the client gets a `429 Too Many Requests` with a `Retry-After` header.

### Global middleware

Apply one limit across all routes. Useful for simple APIs where you don't need per-endpoint control.

```python
from fastapi_limiter import RateLimitMiddleware

app.add_middleware(
    RateLimitMiddleware,
    limit=100,        # 100 requests
    window=60,        # per minute
    exclude_paths=["/health", "/metrics"],
)
```

### Custom key function

By default the rate limit key is `{client_ip}:{route_path}`. You can change it — for example, to key by authenticated user instead of IP:

```python
from fastapi import Request

def key_by_user(request: Request) -> str:
    user_id = request.headers.get("X-User-Id", "anonymous")
    return f"{user_id}:{request.url.path}"

@app.get("/data", dependencies=[Depends(RateLimiter(limit=100, window=3600, key_func=key_by_user))])
async def data():
    ...
```

### Custom backend

The default backend is in-memory (single process). Pass your own backend to share state across workers:

```python
from fastapi_limiter import RateLimiter, InMemoryBackend

shared_backend = InMemoryBackend()

limiter = RateLimiter(limit=10, window=60, backend=shared_backend)
```

Redis backend is on the roadmap.

---

## Response headers

Successful requests include:

```
X-RateLimit-Limit: 10
X-RateLimit-Remaining: 7
```

Blocked requests (429) include:

```
Retry-After: 42
X-RateLimit-Limit: 10
X-RateLimit-Remaining: 0
```

---

## How it works

Uses a sliding window algorithm. Each request timestamp is stored in a deque. On each new request, timestamps older than the window are dropped, and the current count is compared against the limit. The in-memory backend is thread-safe.

---

## Development

```bash
git clone https://github.com/kpalubicki/fastapi-limiter.git
cd fastapi-limiter
pip install -e ".[dev]"
pytest
```

---

## Roadmap

- Redis backend
- async-native backend
- PyPI release

---

## License

MIT
