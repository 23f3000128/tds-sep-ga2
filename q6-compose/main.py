# Q6 - FastAPI + Redis counter, run with docker compose, exposed by a tunnel
import os
import redis
from fastapi import FastAPI

app = FastAPI()
r = redis.Redis(host=os.environ.get("REDIS_HOST", "redis"), port=6379, decode_responses=True)


@app.post("/hit/{key}")
def hit(key: str):
    return {"key": key, "count": r.incr(f"hits:{key}")}


@app.get("/count/{key}")
def count(key: str):
    return {"key": key, "count": int(r.get(f"hits:{key}") or 0)}


@app.get("/healthz")
def healthz():
    r.ping()  # raises if Redis is down
    return {"status": "ok", "redis": "up"}
