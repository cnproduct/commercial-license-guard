# Commercial License Guard —— 用户操作与授权管理手册

> **版本**：v1.0.0 旗舰商用版  
> **适用对象**：软件商业化运营团队、技术人员及终身授权客户。

---

## 目录
1. [客户常见使用流程 (Client SOP)](#一客户常见使用流程)
2. [管理员核心运维手册 (Admin SOP)](#二管理员核心运维手册)
3. [Cloudflare Web 控制台操作指南](#三cloudflare-web-控制台操作指南)
4. [常见问题答疑与故障排查 (FAQ)](#四常见问题答疑与故障排查)

---

## 一、客户常见使用流程

### 1. 获取本机硬件识别码 (Machine ID)
初次使用软件前，客户需在命令终端中运行以下指令以获取本机专属硬件指纹：
```bash
python scripts/license_tool.py machine-id
```
- 输出示例：`MID-4C53-9292-ABAA-A5F3`
- 客户将该字符串发送给软件客服/管理员以申请授权。

### 2. 激活授权码
收到管理员签发的专属授权码后，直接在软件中或配置文件中配置：
```bash
python scripts/license_tool.py verify --key "LIC-RSA-eyJwIjp7..."
```
若提示 `valid: true`，代表本设备已被官方成功激活！

---

## 二、管理员核心运维手册

### 1. 私钥生成与安全保管
```bash
python scripts/license_tool.py keygen --out-dir .
```
- `admin_private_key.pem`：**管理员绝对机密**，用于签发所有客户授权。严禁泄漏！
- `public_key.pem`：公钥，随软件发布包交付客户。

### 2. 为新客户签发授权
```bash
python scripts/license_tool.py generate \
    --key-path admin_private_key.pem \
    --mid "MID-XXXX-XXXX-XXXX-XXXX" \
    --name "深圳某跨境大卖" \
    --days 365
```

### 3. 一键混淆编译发布
```bash
python scripts/build_pipeline.py --project-dir . --output-dir dist --name "release-v1.0"
```
系统将自动执行：
1. PyArmor 编译为 `.pyd` 原生二进制；
2. 全盘机密安全审计；
3. 输出纯净无源码压缩包 `dist/release-v1.0.zip`。

---

## 三、Cloudflare Web 控制台操作指南

管理员通过浏览器直接访问：
`https://your-auth-gateway.your-subdomain.workers.dev/admin?key=YOUR_ADMIN_SECRET`

### 1. 实时看板特性
- **授权列表**：查看所有发放出去的授权码、对应客户名称、首次激活时间及到期日；
- **设备绑定**：查看绑定的具体机器硬件指纹（MID）；
- **上架用量**：实时显示客户的累积使用次数。

### 2. 一键远程在线封禁 (Remote Ban)
- 若客户申请退款或私自转让账号，点击列表右侧的 **【在线封禁】** 按钮；
- 状态变为红色 `已封禁`，客户下一次调用任何引擎功能将在 500ms 内被阻断。

### 3. 一键在线续期 (Remote Renew)
- 客户充值续费后，点击 **【续期+30天】** 按钮；
- 输入延长时间，云端即刻生效，无需向客户重新发送新的安装包或授权码！

---

## 四、常见问题答疑与故障排查 (FAQ)

### Q1: 客户更换了电脑怎么办？
**A**: 由于采用硬件一机一码强绑定，旧设备上的授权码无法在新电脑上运行。管理员可登录 Cloudflare Web 控制台将旧授权码封禁，并为客户的新机器码签发新的授权码。

### Q2: 如果客户处于弱网环境或者无法访问海外网络怎么办？
**A**: 系统内嵌双引擎平滑容灾机制。当 Cloudflare 出现网络超时时，系统会自动平滑降级至本地 RSA-2048 离线验签，只要本地硬件指纹和数字签名有效，客户日常业务完全不受公网波动影响。

### Q3: 客户能够篡改授权文件以延长有效期吗？
**A**: 绝对不能。授权码经过 RSA-2048 PSS 非对称高强度加密签名，篡改其中任意一个字符均会导致数字签名验签失败（`InvalidSignature`）并立即停止运行。
