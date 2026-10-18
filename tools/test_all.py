import sys, time, random, jwt, json
sys.path.insert(0, "/home/claude/ga2/repo")
import main
from fastapi.testclient import TestClient
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization
c = TestClient(main.app); EX = main.EXAM_ORIGIN; ok = lambda m: print("PASS", m)

# Q3
r = c.options("/stats", headers={"Origin": "https://dash-tylzgy.example.com", "Access-Control-Request-Method": "GET"})
assert r.headers.get("access-control-allow-origin") == "https://dash-tylzgy.example.com"
r = c.options("/stats", headers={"Origin": "https://evil-x.com", "Access-Control-Request-Method": "GET"})
assert "access-control-allow-origin" not in r.headers
vals = [random.randint(-500, 500) for _ in range(20)]
r = c.get("/stats", params={"values": ",".join(map(str, vals))}); j = r.json()
assert j == {"email": main.EMAIL, "count": 20, "sum": sum(vals), "min": min(vals), "max": max(vals), "mean": sum(vals)/20}
assert r.headers["x-request-id"] and float(r.headers["x-process-time"]) >= 0; ok("Q3")

# Q4 with a throwaway key swapped in
k = rsa.generate_private_key(public_exponent=65537, key_size=2048)
main.JWT_PUBLIC_KEY = k.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode()
base = {"iss": main.JWT_ISSUER, "aud": main.JWT_AUDIENCE, "sub": "sub-x", "email": main.EMAIL, "exp": int(time.time()) + 300}
good = jwt.encode(base, k, algorithm="RS256")
r = c.post("/verify", json={"token": good}); assert r.status_code == 200 and r.json() == {"valid": True, "email": main.EMAIL, "sub": "sub-x", "aud": main.JWT_AUDIENCE}
for bad in [dict(base, exp=int(time.time()) - 10), dict(base, aud="wrong")]:
    assert c.post("/verify", json={"token": jwt.encode(bad, k, algorithm="RS256")}).status_code == 401
h, p, s = good.split("."); import base64
p2 = base64.urlsafe_b64encode(json.dumps(dict(base, sub="hacker")).encode()).decode().rstrip("=")
r = c.post("/verify", json={"token": f"{h}.{p2}.{s}"}); assert r.status_code == 401 and r.json() == {"valid": False}; ok("Q4")

# Q5 (mirror of browser grader)
base5 = {"port": 8457, "workers": 15, "debug": True, "log_level": "warning", "api_key": "****"}
r = c.get("/effective-config", headers={"Origin": EX}); assert r.json() == base5, r.json()
assert r.headers["access-control-allow-origin"] == "*"
r = c.get("/effective-config?set=port=8123&set=debug=false&set=log_level=error&set=workers=3").json()
assert r == {"port": 8123, "workers": 3, "debug": False, "log_level": "error", "api_key": "****"}; ok("Q5")

# Q7
assert c.post("/analytics", json={"events": []}, headers={"X-API-Key": "wrong-key"}).status_code == 401
assert c.post("/analytics", json={"events": []}).status_code == 401
ev = [{"user": "user-1", "amount": 300, "ts": 1}, {"user": "user-2", "amount": -40, "ts": 1}, {"user": "user-2", "amount": 120, "ts": 1}, {"user": "user-3", "amount": 0, "ts": 1}]
r = c.post("/analytics", json={"events": ev}, headers={"X-API-Key": main.ANALYTICS_API_KEY}).json()
assert r == {"email": main.EMAIL, "total_events": 4, "unique_users": 3, "revenue": 420, "top_user": "user-1"}, r; ok("Q7")

# Q8
import re
m0 = int(re.search(r"^http_requests_total (\d+)", c.get("/metrics").text, re.M).group(1))
for n in [3, 5, 2]: assert c.get(f"/work?n={n}").json() == {"email": main.EMAIL, "done": n}
m1 = int(re.search(r"^http_requests_total (\d+)", c.get("/metrics").text, re.M).group(1)); assert m1 - m0 >= 3
hz = c.get("/healthz").json(); assert hz["status"] == "ok" and hz["uptime_s"] >= 0
logs = c.get("/logs/tail?limit=10").json(); assert all({"level","ts","path","request_id"} <= set(e) for e in logs) and any("/work" in e["path"] for e in logs); ok("Q8")

# Q10 regex fallback
txt = "INVOICE #4471\nVendor: Acme-k3j9 Industries Ltd.\nIssued: 2026-01-04\nSubtotal: 1,100.00\nTotal due: EUR 1,234.56\nPayment due by 2026-03-15"
r = c.post("/extract", json={"text": txt}); print("   Q10 regex ->", r.json())
assert c.post("/extract", json={"text": ""}).status_code != 500
assert c.post("/extract", content=b"garbage", headers={"Content-Type": "application/json"}).status_code != 500; ok("Q10 (no-500)")

# Q11
a = c.post("/orders", json={"amount": 100}, headers={"Idempotency-Key": "k1", "X-Client-Id": "grader-idem"})
b = c.post("/orders", json={"amount": 100}, headers={"Idempotency-Key": "k1", "X-Client-Id": "grader-idem"})
assert a.status_code == 201 and a.json()["id"] == b.json()["id"]
seen, cur = [], ""
while True:
    j = c.get("/orders", params={"limit": 6, **({"cursor": cur} if cur else {})}, headers={"X-Client-Id": "grader-pager"}).json()
    assert len(j["items"]) <= 6; seen += [i["id"] for i in j["items"]]; cur = j["next_cursor"]
    if not cur: break
assert seen == list(range(1, 44))
st = [c.get("/orders?limit=1", headers={"X-Client-Id": "grader-flood", "Origin": EX}) for _ in range(22)]
r429 = next(x for x in st if x.status_code == 429); assert r429.headers.get("retry-after") and r429.headers.get("access-control-allow-origin") == "*"
assert [x.status_code for x in st].index(429) == 17
assert c.get("/orders?limit=1", headers={"X-Client-Id": "other"}).status_code == 200; ok("Q11")

# Q12
r = c.get("/ping", headers={"X-Request-ID": "rid-abc", "X-Client-Id": "m-ctx1", "Origin": EX})
assert r.json() == {"email": main.EMAIL, "request_id": "rid-abc"} and r.headers["x-request-id"] == "rid-abc" and r.headers["access-control-allow-origin"] == EX
r = c.get("/ping", headers={"X-Client-Id": "m-ctx2"}); assert r.json()["request_id"] and r.headers["x-request-id"] == r.json()["request_id"]
pf = c.options("/ping", headers={"Origin": "https://app-poq0ho.example.com", "Access-Control-Request-Method": "GET", "Access-Control-Request-Headers": "x-client-id,x-request-id"})
assert pf.status_code == 200 and pf.headers["access-control-allow-origin"] == "https://app-poq0ho.example.com"
assert "access-control-allow-origin" not in c.get("/ping", headers={"Origin": "https://evil.com"}).headers
codes = [c.get("/ping", headers={"X-Client-Id": "m-flood"}).status_code for _ in range(14)]; assert codes.index(429) == 9
assert c.get("/ping", headers={"X-Client-Id": "m-fresh"}).status_code == 200; ok("Q12")

# Q13 / Q14
assert c.get("/stream-answer").json() == json.loads(open("/home/claude/ga2/q13.json").read()); ok("Q13")
print("   Q14 ->", c.get("/docker-cache-answer").json())
