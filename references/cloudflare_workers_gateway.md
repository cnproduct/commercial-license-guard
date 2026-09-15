# Cloudflare Workers Serverless Gateway & Real-time Web Control

This reference details how to deploy and manage a zero-cost, zero-maintenance global edge authentication gateway using Cloudflare Workers and KV, controlled remotely via API and a built-in Web Admin Dashboard.

---

## 1. Architectural Highlights

- **Zero Infrastructure Cost**: Runs entirely on the Cloudflare Free Tier (100,000 requests/day, 0 server maintenance, 0 database hosting).
- **Sub-10ms Global Edge Latency**: Worker logic runs on Cloudflare's worldwide CDN edge points close to users.
- **Browser-Assisted Deployment**: Deploy directly via an existing authenticated Chrome browser session without requiring `wrangler` CLI login or API tokens on dev machines.
- **Real-Time Remote Control**: Instantly ban pirated keys, renew subscriptions, and monitor usage.

---

## 2. Browser-Assisted Deployment SOP

When deploying without the local `wrangler` CLI:
1. Ensure Google Chrome is logged into the Cloudflare Dashboard (`https://dash.cloudflare.com`).
2. Navigate to **Workers & Pages**:
   - Click **Create application** ➔ **Create Worker**.
   - Name the Worker (e.g., `commercial-auth-gateway`).
   - Click **Deploy**.
3. Create a **KV Namespace**:
   - Under **Storage & Databases** ➔ **KV**, click **Create namespace**.
   - Name: `WB_LICENSES`.
4. Bind KV to the Worker:
   - Go to Worker **Settings** ➔ **Bindings** ➔ **Add**.
   - Type: **KV Namespace**.
   - Variable Name: `WB_LICENSES`.
   - KV Namespace: select `WB_LICENSES`.
5. Set Environment Variable:
   - Add Secret: `ADMIN_SECRET = "<YOUR_SECURE_ADMIN_KEY>"`.
6. Paste Worker Code:
   - Go to **Quick Edit** (Code editor).
   - Paste contents of `templates/worker.js`.
   - Click **Save and Deploy**.

---

## 3. KV Data Schema (`WB_LICENSES`)

Each license key (e.g. `LIC-RSA-...`) is stored as a Key in the KV namespace, with a JSON string Value:

```json
{
  "name": "Acme Cross-Border Ltd",
  "machine_id": "MID-A51C-F5A2-8A9A-5388",
  "status": "ACTIVE",
  "expires_at": "2027-09-15 23:59:59",
  "usage_count": 1420,
  "first_activated_at": "2026-09-15T01:10:00Z",
  "last_verified_at": "2026-09-15T06:00:00Z",
  "last_used_at": "2026-09-15T06:09:59Z",
  "permissions": ["listing", "pricing", "stocks", "fast_list"]
}
```

### Status Flags
- `ACTIVE`: Normal authorized operation.
- `BANNED`: Remotely revoked. Any client request using this key will be instantly blocked with `HTTP 403`.

---

## 4. API Endpoints

### Client Endpoints

#### 1. Verify License: `GET /api/verify?key={key}&mid={mid}`
- **Purpose**: Checks status, expiration, and hardware binding.
- **Auto-Bind Feature**: If the license record does not yet have a `machine_id`, the worker binds the requesting `mid` on first use.
- **Responses**:
  - `200 OK`: `{"valid": true, "name": "...", "expires_at": "..."}`
  - `403 Forbidden`: Banned, expired, or MID mismatch.
  - `404 Not Found`: License does not exist in KV.

#### 2. Report Usage: `POST /api/report_usage`
- **Payload**: `{"key": "LIC-RSA-...", "amount": 25}`
- **Purpose**: Increments `usage_count` in KV for real-time analytics.

---

### Admin Endpoints (Protected by `X-Admin-Secret` or `?key=`)

#### 3. Web Dashboard: `GET /admin?key={ADMIN_SECRET}`
- Renders an interactive Web UI displaying:
  - All active licenses, client names, bound MIDs, expiry dates, and usage counts.
  - One-click **Online Ban** / **Unban** button.
  - One-click **Renew (+30 days)** prompt.

#### 4. Remote Ban: `POST /admin/api/ban`
- **Payload**: `{"license_key": "LIC-RSA-...", "reason": "Chargeback"}`
- **Response**: `{"ok": true, "status": "BANNED"}`

#### 5. Remote Renew: `POST /admin/api/renew`
- **Payload**: `{"license_key": "LIC-RSA-...", "days": 30}`
- **Response**: `{"ok": true, "expires_at": "2027-10-15 23:59:59"}`

---

## 5. Client Integration Pattern (`cloud_auth.py`)

```python
class CloudAuthClient:
    def __init__(self, endpoint, timeout=6):
        self.endpoint = endpoint
        self.timeout = timeout

    def verify_license(self, license_key: str, machine_id: str) -> dict:
        url = f"{self.endpoint}/api/verify?key={quote(license_key)}&mid={quote(machine_id)}"
        try:
            resp = requests.get(url, timeout=self.timeout)
            if resp.status_code == 200:
                return {"valid": True, "data": resp.json()}
            elif resp.status_code == 403:
                return {"valid": False, "error": resp.json().get("error")}
            else:
                return {"valid": False, "network_error": True}
        except Exception:
            # Network or timeout failure -> trigger local fallback
            return {"valid": False, "network_error": True}
```
