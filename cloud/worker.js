/**
 * Cloudflare Workers Commercial License & Anti-Piracy Gateway
 * Zero-server, zero-maintenance global edge authentication and remote management
 */

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    const path = url.pathname;
    const method = request.method;

    // CORS Headers
    const corsHeaders = {
      "Access-Control-Allow-Origin": "*",
      "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
      "Access-Control-Allow-Headers": "Content-Type, Authorization, X-Admin-Secret",
    };

    if (method === "OPTIONS") {
      return new Response(null, { headers: corsHeaders });
    }

    const adminSecret = env.ADMIN_SECRET || "CHANGE_ME_IN_WORKER_VARIABLES";

    // 1. Health Check
    if (path === "/" || path === "/health") {
      return new Response(JSON.stringify({ status: "healthy", service: "Commercial License Gateway", timestamp: new Date().toISOString() }), {
        headers: { ...corsHeaders, "Content-Type": "application/json" }
      });
    }

    // 2. Client License Verification Endpoint: GET /api/verify?key=...&mid=...
    if (path === "/api/verify" && method === "GET") {
      const key = url.searchParams.get("key");
      const mid = url.searchParams.get("mid");

      if (!key) {
        return new Response(JSON.stringify({ valid: false, error: "Missing license key" }), {
          status: 400,
          headers: { ...corsHeaders, "Content-Type": "application/json" }
        });
      }

      // Check KV Database
      if (!env.WB_LICENSES) {
        return new Response(JSON.stringify({ valid: false, error: "KV namespace WB_LICENSES not bound" }), {
          status: 500,
          headers: { ...corsHeaders, "Content-Type": "application/json" }
        });
      }

      const recordJson = await env.WB_LICENSES.get(key);
      if (!recordJson) {
        return new Response(JSON.stringify({ valid: false, error: "License not found or expired" }), {
          status: 404,
          headers: { ...corsHeaders, "Content-Type": "application/json" }
        });
      }

      let record;
      try {
        record = JSON.parse(recordJson);
      } catch (e) {
        return new Response(JSON.stringify({ valid: false, error: "Malformed license record" }), {
          status: 500,
          headers: { ...corsHeaders, "Content-Type": "application/json" }
        });
      }

      // Check Status (e.g. BANNED, SUSPENDED, ACTIVE)
      if (record.status === "BANNED") {
        return new Response(JSON.stringify({ valid: false, error: "License has been remotely REVOKED/BANNED by administrator", ban_reason: record.ban_reason || "Violation of terms" }), {
          status: 403,
          headers: { ...corsHeaders, "Content-Type": "application/json" }
        });
      }

      // Check Expiration
      if (record.expires_at) {
        const expDate = new Date(record.expires_at.replace(" ", "T"));
        if (new Date() > expDate) {
          return new Response(JSON.stringify({ valid: false, error: "License has expired", expires_at: record.expires_at }), {
            status: 403,
            headers: { ...corsHeaders, "Content-Type": "application/json" }
          });
        }
      }

      // Check Hardware Binding (Machine ID)
      if (record.machine_id && mid && record.machine_id !== mid) {
        return new Response(JSON.stringify({ valid: false, error: "Hardware mismatch: License is bound to another machine", bound_mid: record.machine_id, request_mid: mid }), {
          status: 403,
          headers: { ...corsHeaders, "Content-Type": "application/json" }
        });
      }

      // First-time binding: If license has no machine_id, bind to request MID
      if (!record.machine_id && mid) {
        record.machine_id = mid;
        record.first_activated_at = new Date().toISOString();
        await env.WB_LICENSES.put(key, JSON.stringify(record));
      }

      // Log verification event
      record.last_verified_at = new Date().toISOString();
      await env.WB_LICENSES.put(key, JSON.stringify(record));

      return new Response(JSON.stringify({
        valid: true,
        license_key: key,
        name: record.name,
        machine_id: record.machine_id,
        expires_at: record.expires_at,
        permissions: record.permissions || ["listing", "pricing", "stocks", "fast_list"]
      }), {
        headers: { ...corsHeaders, "Content-Type": "application/json" }
      });
    }

    // 3. Client Usage Reporting Endpoint: POST /api/report_usage
    if (path === "/api/report_usage" && method === "POST") {
      try {
        const body = await request.json();
        const { key, amount = 1 } = body;
        if (!key || !env.WB_LICENSES) {
          return new Response(JSON.stringify({ ok: false }), { status: 400, headers: corsHeaders });
        }
        const recordJson = await env.WB_LICENSES.get(key);
        if (recordJson) {
          const record = JSON.parse(recordJson);
          record.usage_count = (record.usage_count || 0) + Number(amount);
          record.last_used_at = new Date().toISOString();
          await env.WB_LICENSES.put(key, JSON.stringify(record));
          return new Response(JSON.stringify({ ok: true, total_usage: record.usage_count }), {
            headers: { ...corsHeaders, "Content-Type": "application/json" }
          });
        }
        return new Response(JSON.stringify({ ok: false, error: "License not found" }), { status: 404, headers: corsHeaders });
      } catch (e) {
        return new Response(JSON.stringify({ ok: false, error: e.message }), { status: 500, headers: corsHeaders });
      }
    }

    // --- Admin Operations (Protected by Secret) ---
    const reqSecret = request.headers.get("X-Admin-Secret") || url.searchParams.get("key");
    const isAdmin = reqSecret === adminSecret;

    // 4. Admin Web Dashboard: GET /admin
    if (path === "/admin" && method === "GET") {
      if (!isAdmin) {
        return new Response("Unauthorized: Invalid Admin Secret. Append ?key=YOUR_SECRET to the URL.", {
          status: 401,
          headers: { "Content-Type": "text/html; charset=utf-8" }
        });
      }

      // Fetch all licenses from KV
      const listRes = await env.WB_LICENSES.list();
      const licenses = [];
      for (const k of listRes.keys) {
        const val = await env.WB_LICENSES.get(k.name);
        try {
          licenses.push({ key: k.name, ...JSON.parse(val) });
        } catch (e) {
          licenses.push({ key: k.name, raw: val });
        }
      }

      const html = `<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <title>商业授权与防复刻云端控制台</title>
  <style>
    body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #f8fafc; color: #1e293b; padding: 24px; margin: 0; }
    .header { display: flex; justify-content: space-between; align-items: center; border-bottom: 2px solid #e2e8f0; padding-bottom: 16px; margin-bottom: 24px; }
    h1 { font-size: 20px; font-weight: 700; color: #0f172a; margin: 0; }
    .badge { padding: 4px 10px; border-radius: 9999px; font-size: 12px; font-weight: 600; }
    .badge-active { background: #dcfce7; color: #166534; }
    .badge-banned { background: #fee2e2; color: #991b1b; }
    table { width: 100%; border-collapse: collapse; background: #ffffff; border-radius: 8px; overflow: hidden; box-shadow: 0 1px 3px rgba(0,0,0,0.05); }
    th, td { padding: 12px 16px; text-align: left; font-size: 13px; border-bottom: 1px solid #f1f5f9; }
    th { background: #f1f5f9; font-weight: 600; color: #475569; }
    tr:hover { background: #f8fafc; }
    button { padding: 6px 12px; border-radius: 6px; border: none; font-size: 12px; font-weight: 500; cursor: pointer; transition: 0.15s; }
    .btn-ban { background: #ef4444; color: white; }
    .btn-ban:hover { background: #dc2626; }
    .btn-unban { background: #10b981; color: white; }
    .btn-unban:hover { background: #059669; }
    .btn-renew { background: #3b82f6; color: white; margin-left: 4px; }
    .btn-renew:hover { background: #2563eb; }
    .key-cell { font-family: monospace; font-size: 11px; word-break: break-all; max-width: 260px; }
  </style>
</head>
<body>
  <div class="header">
    <h1>🛡️ 商业授权与防复刻云端控制台</h1>
    <span style="font-size: 13px; color: #64748b;">授权实例总计: <strong>${licenses.length}</strong></span>
  </div>

  <table>
    <thead>
      <tr>
        <th>授权客户</th>
        <th>绑定机器码 (MID)</th>
        <th>授权码 (License Key)</th>
        <th>到期时间</th>
        <th>累积用量</th>
        <th>状态</th>
        <th>管理操作</th>
      </tr>
    </thead>
    <tbody>
      ${licenses.map(lic => `
        <tr>
          <td><strong>${lic.name || "未命名客户"}</strong></td>
          <td><code>${lic.machine_id || "未激活首机"}</code></td>
          <td class="key-cell">${lic.key}</td>
          <td>${lic.expires_at || "永久"}</td>
          <td>${lic.usage_count || 0} 件</td>
          <td>
            <span class="badge ${lic.status === "BANNED" ? "badge-banned" : "badge-active"}">
              ${lic.status === "BANNED" ? "已封禁" : "正常授权"}
            </span>
          </td>
          <td>
            ${lic.status === "BANNED" 
              ? `<button class="btn-unban" onclick="action('unban', '${encodeURIComponent(lic.key)}')">解封</button>`
              : `<button class="btn-ban" onclick="action('ban', '${encodeURIComponent(lic.key)}')">在线封禁</button>`
            }
            <button class="btn-renew" onclick="renew('${encodeURIComponent(lic.key)}')">续期+30天</button>
          </td>
        </tr>
      `).join("")}
    </tbody>
  </table>

  <script>
    const adminKey = "${reqSecret}";
    async function action(type, key) {
      if (!confirm("确认对该授权执行 " + type + " 操作？")) return;
      const res = await fetch("/admin/api/" + type + "?key=" + adminKey, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ license_key: decodeURIComponent(key) })
      });
      if (res.ok) { location.reload(); } else { alert("操作失败: " + await res.text()); }
    }
    async function renew(key) {
      const days = prompt("请输入要延期的天数 (默认 30 天):", "30");
      if (!days) return;
      const res = await fetch("/admin/api/renew?key=" + adminKey, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ license_key: decodeURIComponent(key), days: parseInt(days) })
      });
      if (res.ok) { location.reload(); } else { alert("续期失败: " + await res.text()); }
    }
  </script>
</body>
</html>`;

      return new Response(html, {
        headers: { "Content-Type": "text/html; charset=utf-8" }
      });
    }

    // 5. Admin API: Remote Ban / Revoke: POST /admin/api/ban
    if (path === "/admin/api/ban" && method === "POST") {
      if (!isAdmin) return new Response("Unauthorized", { status: 401, headers: corsHeaders });
      const { license_key, reason = "Manual ban by admin" } = await request.json();
      const val = await env.WB_LICENSES.get(license_key);
      if (!val) return new Response("Not found", { status: 404, headers: corsHeaders });
      const rec = JSON.parse(val);
      rec.status = "BANNED";
      rec.ban_reason = reason;
      rec.banned_at = new Date().toISOString();
      await env.WB_LICENSES.put(license_key, JSON.stringify(rec));
      return new Response(JSON.stringify({ ok: true, license_key, status: "BANNED" }), {
        headers: { ...corsHeaders, "Content-Type": "application/json" }
      });
    }

    // 6. Admin API: Remote Unban: POST /admin/api/unban
    if (path === "/admin/api/unban" && method === "POST") {
      if (!isAdmin) return new Response("Unauthorized", { status: 401, headers: corsHeaders });
      const { license_key } = await request.json();
      const val = await env.WB_LICENSES.get(license_key);
      if (!val) return new Response("Not found", { status: 404, headers: corsHeaders });
      const rec = JSON.parse(val);
      rec.status = "ACTIVE";
      delete rec.banned_at;
      delete rec.ban_reason;
      await env.WB_LICENSES.put(license_key, JSON.stringify(rec));
      return new Response(JSON.stringify({ ok: true, license_key, status: "ACTIVE" }), {
        headers: { ...corsHeaders, "Content-Type": "application/json" }
      });
    }

    // 7. Admin API: Remote Renewal: POST /admin/api/renew
    if (path === "/admin/api/renew" && method === "POST") {
      if (!isAdmin) return new Response("Unauthorized", { status: 401, headers: corsHeaders });
      const { license_key, days = 30 } = await request.json();
      const val = await env.WB_LICENSES.get(license_key);
      if (!val) return new Response("Not found", { status: 404, headers: corsHeaders });
      const rec = JSON.parse(val);
      let curExp = rec.expires_at ? new Date(rec.expires_at.replace(" ", "T")) : new Date();
      if (isNaN(curExp.getTime()) || curExp < new Date()) {
        curExp = new Date();
      }
      curExp.setDate(curExp.getDate() + Number(days));
      const pad = (n) => String(n).padStart(2, "0");
      rec.expires_at = `${curExp.getFullYear()}-${pad(curExp.getMonth() + 1)}-${pad(curExp.getDate())} 23:59:59`;
      await env.WB_LICENSES.put(license_key, JSON.stringify(rec));
      return new Response(JSON.stringify({ ok: true, license_key, expires_at: rec.expires_at }), {
        headers: { ...corsHeaders, "Content-Type": "application/json" }
      });
    }

    return new Response("Not Found", { status: 404, headers: corsHeaders });
  }
};
