"""
TDS 2026-09 GA2 - one FastAPI app for every "paste your URL" question.

Endpoint map (question number = order on the GA2 page):
  Q3  Metrics API + strict CORS ........ GET  /stats?values=1,2,3
  Q4  OAuth / JWT verification ......... POST /verify
  Q5  12-factor config precedence ...... GET  /effective-config?set=key=value
  Q7  POST analytics ................... POST /analytics
  Q8  Observability .................... GET  /work, /metrics, /healthz, /logs/tail
  Q10 Structured invoice extraction .... POST /extract
  Q11 Orders: idempotency + pagination . POST /orders, GET /orders
  Q12 Middleware stack ................. GET  /ping
  Q13 Ollama stream reassembly ......... GET  /stream-answer
  Q14 Docker build cache ............... GET  /docker-cache-answer
"""

import base64
import json
import os
import re
import time
import uuid
from collections import deque

import httpx
import jwt
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, PlainTextResponse, Response
from pydantic import BaseModel

EMAIL = "23f3000128@ds.study.iitm.ac.in"
EXAM_ORIGIN = "https://exam.sanand.workers.dev"

app = FastAPI()
START_TIME = time.time()


# ======================================================================
# Shared middleware: CORS (per path) + rate limit + request id + logs
# ======================================================================

# Q3: only this origin may get Access-Control-Allow-Origin on /stats
Q3_ALLOWED_ORIGINS = {"https://dash-tylzgy.example.com"}

# Q12: only this origin (plus the exam page) may get ACAO on /ping
Q12_ALLOWED_ORIGINS = {"https://app-poq0ho.example.com", EXAM_ORIGIN}

# Rate limits: (requests allowed, window seconds) per path
Q11_RATE_LIMIT = 17   # /orders  -> 17 requests / 10 s per X-Client-Id
Q12_RATE_LIMIT = 9    # /ping    ->  9 requests / 10 s per X-Client-Id
RATE_WINDOW_SECONDS = 10

rate_buckets = {}                  # (path, client_id) -> [window_start, count]
request_count = 0                  # Q8 http_requests_total
log_entries = deque(maxlen=500)    # Q8 structured logs


def allowed_origin_for(path, origin):
    """Return the origin to echo in Access-Control-Allow-Origin, or None."""
    if not origin:
        return None
    if path.startswith("/stats"):
        return origin if origin in Q3_ALLOWED_ORIGINS else None
    if path.startswith("/ping"):
        return origin if origin in Q12_ALLOWED_ORIGINS else None
    return "*"   # every other endpoint is open to any origin


def rate_limit_for(path):
    if path.startswith("/orders"):
        return Q11_RATE_LIMIT
    if path.startswith("/ping"):
        return Q12_RATE_LIMIT
    return None


def is_rate_limited(path, client_id):
    """Fixed-window counter. Returns seconds to wait if limited, else 0."""
    limit = rate_limit_for(path)
    if limit is None:
        return 0
    key = (path, client_id)
    now = time.time()
    window = rate_buckets.get(key)
    if window is None or now - window[0] >= RATE_WINDOW_SECONDS:
        rate_buckets[key] = [now, 1]
        return 0
    window[1] += 1
    if window[1] > limit:
        return max(1, int(RATE_WINDOW_SECONDS - (now - window[0])) + 1)
    return 0


@app.middleware("http")
async def main_middleware(request: Request, call_next):
    global request_count
    start = time.perf_counter()
    path = request.url.path
    request_count += 1

    # Request context: reuse inbound X-Request-ID, else make a new one
    request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
    request.state.request_id = request_id

    origin = request.headers.get("origin")
    acao = allowed_origin_for(path, origin)
    is_preflight = (request.method == "OPTIONS"
                    and "access-control-request-method" in request.headers)

    if is_preflight:
        if acao:
            response = Response(status_code=200)
            response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
            response.headers["Access-Control-Allow-Headers"] = (
                request.headers.get("access-control-request-headers") or "*")
            response.headers["Access-Control-Max-Age"] = "600"
        else:
            response = PlainTextResponse("Disallowed CORS origin", status_code=400)
    else:
        client_id = request.headers.get("x-client-id", "anonymous")
        wait = is_rate_limited(path, client_id)
        if wait:
            response = JSONResponse({"error": "rate limit exceeded"}, status_code=429)
            response.headers["Retry-After"] = str(wait)
        else:
            response = await call_next(request)

    if acao:
        response.headers["Access-Control-Allow-Origin"] = acao
        response.headers["Access-Control-Expose-Headers"] = "X-Request-ID, X-Process-Time, Retry-After"
        if acao != "*":
            response.headers["Vary"] = "Origin"

    response.headers["X-Request-ID"] = request_id
    response.headers["X-Process-Time"] = f"{time.perf_counter() - start:.6f}"

    log_entries.append({
        "level": "INFO" if response.status_code < 400 else "WARNING",
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "method": request.method,
        "path": path,
        "status": response.status_code,
        "request_id": request_id,
    })
    print(json.dumps(log_entries[-1]), flush=True)
    return response


@app.get("/")
def home():
    return {"status": "ok", "email": EMAIL}


# ======================================================================
# Q3 - Deploy a CORS-Aware Metrics API            submit: base URL
# ======================================================================
@app.get("/stats")
def stats(values: str = ""):
    numbers = [int(v) for v in values.split(",") if v.strip()]
    if not numbers:
        return JSONResponse({"error": "values is empty"}, status_code=400)
    return {
        "email": EMAIL,
        "count": len(numbers),
        "sum": sum(numbers),
        "min": min(numbers),
        "max": max(numbers),
        "mean": sum(numbers) / len(numbers),
    }


# ======================================================================
# Q4 - OAuth 2.0 / OIDC Token Verification        submit: <base>/verify
# ======================================================================
JWT_ISSUER = "https://idp.exam.local"
JWT_AUDIENCE = "tds-noglu4k4.apps.exam.local"
JWT_PUBLIC_KEY = """-----BEGIN PUBLIC KEY-----
MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEA2okOHspNjgA+2rTLbeuY
cxiP/hG8C6Sb9iwg3yiLAA4HCnpITcbWCSelbvbYGuc3EbNy4xFyf5Cbj5DHJMID
EkryOgyd2giIIIBOUBj8S63uGcnRpOBh9NFatfNwheKuzsPuVNldu6A9cNteNpXc
WyJjG2axVfmq7i6SuKr1JoWYG7xTTAvKPujSl4OtsQfO3h5NepzdfXpr28oNnzfW
ed+zclR6BcmNNo/WVfJ4xyCLSf0BCOgdTgW6PdaChd1l9VDetJZVEgC5tkyvXsfI
SI6iyrYbKR0NEBSqq4XkadEjsCs4F1RncsS4LlgniT7GlkL9Mce3b0wGLs9/7ZIX
dQIDAQAB
-----END PUBLIC KEY-----"""


class TokenRequest(BaseModel):
    token: str = ""


@app.post("/verify")
def verify(body: TokenRequest):
    try:
        claims = jwt.decode(
            body.token,
            JWT_PUBLIC_KEY,
            algorithms=["RS256"],
            audience=JWT_AUDIENCE,
            issuer=JWT_ISSUER,
            options={"require": ["exp", "iss", "aud"]},
        )
    except Exception:
        return JSONResponse({"valid": False}, status_code=401)
    return {
        "valid": True,
        "email": claims.get("email"),
        "sub": claims.get("sub"),
        "aud": claims.get("aud"),
    }


# ======================================================================
# Q5 - Resolve 12-Factor Config Precedence  submit: <base>/effective-config
# ======================================================================
# Layer 1: defaults (hardcoded)
CONFIG_DEFAULTS = {"port": 8000, "workers": 1, "debug": False,
                   "log_level": "info", "api_key": "default-secret-000"}
# Layer 2: config.development.yaml
CONFIG_YAML = {"workers": 15, "debug": False}
# Layer 3: .env file  (NUM_WORKERS would be aliased to "workers")
CONFIG_DOTENV_RAW = {"APP_PORT": "8028", "APP_DEBUG": "true",
                     "APP_LOG_LEVEL": "warning", "APP_API_KEY": "key-d9sxwx375m"}
# Layer 4: OS environment variables (APP_* prefix)
CONFIG_OSENV_RAW = {"APP_PORT": "8457", "APP_DEBUG": "true"}


def env_to_config(raw):
    config = {}
    for name, value in raw.items():
        if name == "NUM_WORKERS":
            config["workers"] = value
        elif name.startswith("APP_"):
            key = name[4:].lower()
            config["workers" if key == "num_workers" else key] = value
    return config


def coerce(key, value):
    if key in ("port", "workers"):
        return int(value)
    if key == "debug":
        return value if isinstance(value, bool) else str(value).strip().lower() in ("1", "true", "yes", "on")
    return str(value)


@app.get("/effective-config")
def effective_config(request: Request):
    config = dict(CONFIG_DEFAULTS)
    config.update(CONFIG_YAML)
    config.update(env_to_config(CONFIG_DOTENV_RAW))
    config.update(env_to_config(CONFIG_OSENV_RAW))
    # Highest precedence: CLI overrides ?set=key=value
    for item in request.query_params.getlist("set"):
        if "=" in item:
            key, value = item.split("=", 1)
            key = key.strip().lower()
            config["workers" if key == "num_workers" else key] = value
    result = {key: coerce(key, value) for key, value in config.items()}
    result["api_key"] = "****"
    return result


# ======================================================================
# Q7 - POST Analytics Endpoint                    submit: <base>/analytics
# ======================================================================
ANALYTICS_API_KEY = "ak_maj6toiiwmacf8x8lhmyzs7q"


@app.post("/analytics")
async def analytics(request: Request):
    if request.headers.get("x-api-key") != ANALYTICS_API_KEY:
        return JSONResponse({"error": "invalid or missing API key"}, status_code=401)
    body = await request.json()
    events = body.get("events", [])
    revenue = 0
    user_totals = {}
    for event in events:
        amount = float(event.get("amount", 0))
        if amount > 0:
            revenue += amount
            user_totals[event["user"]] = user_totals.get(event["user"], 0) + amount
    top_user = max(user_totals, key=user_totals.get) if user_totals else None
    return {
        "email": EMAIL,
        "total_events": len(events),
        "unique_users": len({event.get("user") for event in events}),
        "revenue": int(revenue) if revenue == int(revenue) else revenue,
        "top_user": top_user,
    }


# ======================================================================
# Q8 - Observability: metrics, health, logs        submit: base URL
# ======================================================================
@app.get("/work")
def work(n: int = 1):
    total = 0
    for i in range(max(n, 0)):
        total += i * i
    return {"email": EMAIL, "done": n}


@app.get("/metrics")
def metrics():
    text = (
        "# HELP http_requests_total Total HTTP requests received.\n"
        "# TYPE http_requests_total counter\n"
        f"http_requests_total {request_count}\n"
    )
    return PlainTextResponse(text, media_type="text/plain; version=0.0.4")


@app.get("/healthz")
def healthz():
    return {"status": "ok", "uptime_s": round(time.time() - START_TIME, 3)}


@app.get("/logs/tail")
def logs_tail(limit: int = 20):
    limit = max(1, min(limit, 500))
    return list(log_entries)[-limit:]


# ======================================================================
# Q10 - Structured invoice extraction             submit: <base>/extract
# ======================================================================
# Uses an LLM through AI Pipe when AIPIPE_TOKEN is set; regex fallback otherwise.
AIPIPE_URL = "https://aipipe.org/openai/v1/chat/completions"
AIPIPE_TOKEN = os.environ.get("AIPIPE_TOKEN", "")


class InvoiceRequest(BaseModel):
    text: str = ""


class Invoice(BaseModel):
    vendor: str
    amount: float
    currency: str
    date: str


def regex_extract(text):
    # Planted vendors look like "Acme-k3j9 Industries Ltd." -> take the rest of that line
    vendor = re.search(r"([A-Z][\w&]*-[A-Za-z0-9]{3,}\b[^\n;]*)", text)
    if not vendor:
        vendor = re.search(r"(?:vendor|from|supplier|billed by|seller)\s*[:\-]?\s*([^\n,;]+)", text, re.I)
    currency = re.search(r"\b(USD|EUR|GBP)\b", text, re.I)
    if not currency:
        symbol = re.search(r"[$€£]", text)
        currency_code = {"$": "USD", "€": "EUR", "£": "GBP"}.get(symbol.group(0)) if symbol else "USD"
    else:
        currency_code = currency.group(1).upper()
    number = r"[^0-9\n]{0,25}([0-9][0-9,]*(?:\.[0-9]+)?)"
    amount_match = (re.search(r"(?:total\s+due|amount\s+due|balance\s+due|grand\s+total|amount\s+payable|total\s+amount)" + number, text, re.I)
                    or re.search(r"\b(?<!sub)total\b" + number, text, re.I)
                    or re.search(r"\bamount\b" + number, text, re.I)
                    or re.search(r"([0-9][0-9,]*\.[0-9]{2})", text))
    dates = re.findall(r"\d{4}-\d{2}-\d{2}", text)
    due_date = re.search(r"due[^0-9\n]{0,30}(\d{4}-\d{2}-\d{2})", text, re.I)
    return {
        "vendor": (vendor.group(1).strip() if vendor else ""),
        "amount": float(amount_match.group(1).replace(",", "")) if amount_match else 0.0,
        "currency": currency_code,
        "date": due_date.group(1) if due_date else (dates[-1] if dates else ""),
    }


def llm_extract(text):
    prompt = (
        "Extract these fields from the invoice text and reply with only a JSON object: "
        '{"vendor": string (full vendor company name), "amount": number (the TOTAL DUE), '
        '"currency": 3-letter uppercase code, "date": payment DUE date as YYYY-MM-DD}.\n\n'
        f"Invoice text:\n{text}"
    )
    response = httpx.post(
        AIPIPE_URL,
        headers={"Authorization": f"Bearer {AIPIPE_TOKEN}"},
        json={"model": "gpt-4.1-mini", "temperature": 0,
              "response_format": {"type": "json_object"},
              "messages": [{"role": "user", "content": prompt}]},
        timeout=25,
    )
    response.raise_for_status()
    return json.loads(response.json()["choices"][0]["message"]["content"])


@app.post("/extract", response_model=Invoice)
def extract(body: InvoiceRequest):
    text = body.text or ""
    fallback = regex_extract(text)
    data = dict(fallback)
    if AIPIPE_TOKEN and text.strip():
        try:
            data.update({k: v for k, v in llm_extract(text).items() if v not in (None, "")})
        except Exception:
            pass
    # Normalise into the schema
    try:
        amount = float(str(data.get("amount", 0)).replace(",", ""))
    except ValueError:
        amount = fallback["amount"]
    date_match = re.search(r"\d{4}-\d{2}-\d{2}", str(data.get("date", "")))
    return Invoice(
        vendor=str(data.get("vendor") or ""),
        amount=amount,
        currency=str(data.get("currency") or "USD").upper()[:3],
        date=date_match.group(0) if date_match else fallback["date"],
    )


# ======================================================================
# Q11 - Orders: idempotency + cursor pagination + rate limit   submit: base URL
# ======================================================================
TOTAL_ORDERS = 43
idempotency_store = {}   # Idempotency-Key -> created order
created_orders_count = 0


@app.post("/orders", status_code=201)
async def create_order(request: Request):
    global created_orders_count
    key = request.headers.get("idempotency-key")
    if key and key in idempotency_store:
        return JSONResponse(idempotency_store[key], status_code=201)
    try:
        body = await request.json()
    except Exception:
        body = {}
    created_orders_count += 1
    order = {"id": f"ord-{created_orders_count}", "amount": body.get("amount")}
    if key:
        idempotency_store[key] = order
    return order


def encode_cursor(offset):
    return base64.urlsafe_b64encode(f"offset:{offset}".encode()).decode()


def decode_cursor(cursor):
    try:
        return int(base64.urlsafe_b64decode(cursor.encode()).decode().split(":")[1])
    except Exception:
        return 0


@app.get("/orders")
def list_orders(limit: int = 10, cursor: str = ""):
    limit = max(1, min(limit, 100))
    offset = decode_cursor(cursor) if cursor else 0
    ids = list(range(1, TOTAL_ORDERS + 1))[offset:offset + limit]
    items = [{"id": order_id, "amount": order_id * 10} for order_id in ids]
    next_offset = offset + len(ids)
    next_cursor = encode_cursor(next_offset) if next_offset < TOTAL_ORDERS else None
    return {"items": items, "next_cursor": next_cursor}


# ======================================================================
# Q12 - Middleware stack: rate limit + CORS + request context   submit: base URL
# ======================================================================
@app.get("/ping")
def ping(request: Request):
    return {"email": EMAIL, "request_id": request.state.request_id}


# ======================================================================
# Q13 - Recover a fragmented LLM stream   submit: <base>/stream-answer
# ======================================================================
@app.get("/stream-answer")
def stream_answer():
    return {
        "A": {"text": "Report job-3a4538fe: café\nReady ✓", "complete": True, "error": None},
        "B": {"text": "Partial job-3a4538fe", "complete": False, "error": None},
        "C": {"text": "Draft job-3a4538fe", "complete": False, "error": "model unloaded"},
    }


# ======================================================================
# Q14 - Diagnose Docker build cache misses   submit: <base>/docker-cache-answer
# ======================================================================
# L2 (pip install) = 41 s, L4 (compileall) = 12 s, L5 (unittest) = 29 s
@app.get("/docker-cache-answer")
def docker_cache_answer():
    return {
        "A": {"steps": ["L3", "L4", "L5"], "seconds": 41},              # src/app.py content changed
        "B": {"steps": ["L1", "L2", "L3", "L4", "L5"], "seconds": 82},  # requirements.txt changed
        "C": {"steps": [], "seconds": 0},                                # touch: mtime ignored by COPY checksum
        "D": {"steps": [], "seconds": 0},                                # README.md is .dockerignored
        "E": {"steps": ["L4", "L5"], "seconds": 41},                     # L4 instruction text changed
    }
