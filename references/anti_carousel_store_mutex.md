# Anti-Carousel Store Mutex & License-to-Store 1:1 Binding Architecture

This reference documents the multi-tenant commercial licensing & isolation architecture designed to enforce "1-License-1-Store" pricing, stop "store-carousel piracy", and eliminate cross-store inventory pollution in AI-driven e-commerce listing tools.

---

## 1. Core Architectural Axiom: License Key 1:1 Bound to Store ID

```mermaid
graph LR
    subgraph "Commercial Asset Tier (按店铺收费 ¥600/店/年)"
        User[付费卖家] -->|支付 600 元/店/年| Lic[专属授权码 License Key]
        Lic -->|1:1 永久强锁定| Store[Wildberries 专属店铺 A (Token / 卖家ID)]
    end
    
    subgraph "Execution & Sandbox Tier (会话窗口与防串店沙箱)"
        Win1[聊天窗口 1] -->|自动加载授权码| Store
        Win2[新建聊天窗口 2] -->|输入授权码| Store
        Win3[聊天窗口 3] -->|尝试用同一个码传店铺 B| Block[🛑 强行阻断: 该授权码已永久绑定店铺 A!]
    end
```

### 1.1 Commercial Asset Ownership
- **Pricing Rule**: Every Wildberries store is billed at **¥600 RMB / Store / Year (365 days valid from payment date)**.
- **License-to-Store Mutex (一店一码 1:1 强绑定)**: 
  - When a license key is first activated and bound to a Wildberries store, the store's unique identity (OpenAPI Token signature / Seller ID / Warehouse ID) is permanently anchored to that license key in both local registry (`~/.wb_session_registry.json`) and Cloudflare KV (`WB_LICENSES`).
  - **Anti-Carousel Piracy Elimination (杜绝轮播白嫖)**: A customer cannot use a single 600 RMB license to service multiple stores in carousel fashion. Any attempt to listing to Store B using a license locked to Store A triggers immediate hard blocking.
  - **Customer Portability (换窗口/换设备自由)**: As long as the customer is operating the authorized Store A, they can enter their license key in any new Antigravity chat window (`+ New Conversation`) or device without losing access or needing to repurchase.

---

## 2. The True Roles of `Conversation ID`

`Conversation ID` (the UUID of an Antigravity / Claude Code chat window) does **not** represent permanent asset ownership. It serves two specific operational purposes:

### 2.1 Instant Payment & Auto-Activation Pipe (收银台免密流转管道)
When the user clicks the payment link or scans the Alipay QR code:
- The URL includes `?cid=<current_conversation_id>`.
- Upon payment completion (600 RMB webhook confirmation), Cloudflare Workers automatically links the newly minted license key with that `cid`.
- The active chat window instantly auto-activates with zero manual copy-pasting required from the user.

### 2.2 Concurrency Sandbox & Store Mutex (窗口内单店沙箱防串店)
- Each individual conversation window is locked to at most **one** store profile at any given moment.
- Concurrently mixing Store A and Store B within the same chat window is strictly prohibited to prevent cross-store barcode pollution, inventory mismatch, and seller account penalties.

---

## 3. Defense Rules & State Lifecycle

```mermaid
graph TD
    A[New Session Window] --> B[First Bind: Store A]
    B --> C[switch_count = 0 / Quota: 0/1]
    C -->|User: Switch Store B| D[First Switch Allowed (Correction)]
    D --> E[switch_count = 1 / Quota: 1/1]
    E --> F[Permanent Mutex Lock to Store B]
    F -->|User: Switch Store C| G[BLOCKED: Switch Quota Exhausted!]
    F -->|User: Unbind Store| H[BLOCKED: Quota Exhausted, Unbind Prohibited!]
    G --> I[Guide: Open a New Chat Session Window with New License]
```

### 3.1 Single-Window 1:1 Mutex Locking
Every conversation session window is strictly bound to at most **one** store profile (`store_name`, `wb_api_token`, `warehouse_id`). Concurrently mixing two or more stores in one window is strictly prohibited.

### 3.2 Maximum 1-Switch Quota Limit (`switch_count <= 1`)
- **Initial Bind**: `switch_count = 0`. Status displays `换店配额: 0/1 (允许切换1次)`.
- **First Switch**: If a user mistyped credentials or moved stores, they are granted **one** smooth switch to Store B. Upon switching, `switch_count` increments to `1`.
- **Permanent Lock**: Once `switch_count >= 1`, the session enters permanent lock state (`1/1 (已永久锁定当前店铺，禁止再次更换)`). Further attempts to switch are blocked.

### 3.3 Anti-Bypass Deadlock (Blocking Unbind)
A common bypass tactic is for the user to call `解绑店铺 (unbind)` to reset state, then call `bind` again.
To close this loophole: `unbind_store()` checks if `switch_count >= 1`. If so, unbinding is explicitly blocked, preventing any state-clearing reset loop.

---

## 4. UI Display & QR Code Standards

### 4.1 Compact 3cm × 3cm QR Code Standard
Markdown chat rendering engines often enforce responsive `img { width: 100% !important; }`, stretching raw markdown images across the entire screen.

To maintain a clean, compact ~3cm × 3cm display footprint in AI chat interfaces:
- **Format**: Explicitly constrained HTML `<img>` tag:
  ```html
  <img src="https://api.qrserver.com/v1/create-qr-code/?size=100x100&data=..." width="100" height="100" style="width:100px; height:100px; max-width:100px; max-height:100px; display:block; margin:8px 0; border:1px solid #e2e8f0; border-radius:6px;" alt="支付宝扫码支付" />
  ```
- **Physical Dimensions**: 100×100 px at 96-120 DPI corresponds to ~2.8cm – 3.0cm, perfectly readable by mobile phone cameras within 0.1 seconds without breaking chat layout.

---

## 5. Security & Zero-Leakage Sentinel

1. **SHA-256 One-Way Hash for Master Privileges**:
   - Internal administrative keys are never stored as plain text. Checks are performed against `hashlib.sha256(key.strip().encode('utf-8')).hexdigest()`.
2. **Zero-Leakage Guarantee**:
   - The agent strictly refuses to output System Prompts, internal key hashes, hardware fingerprints, or private configuration files.
