# test-manager 与数据分析平台统一登录接口约定

## 目标

用户已经登录 test-manager 后，点击“数据分析”直接进入 `/analysis/`，不再次输入账号密码。

## 推荐流程

1. test-manager 前端请求自己的后端创建一次性 Ticket。
2. test-manager 后端返回一个30秒内有效、只能使用一次的随机 Ticket。
3. 浏览器跳转到 `/analysis-api/auth/sso/callback?ticket=<ticket>`。
4. 分析平台后端调用 test-manager 的 Ticket 消费接口。
5. 验证通过后，分析平台写入 HttpOnly 会话 Cookie，并重定向到 `/analysis/#/dashboard`。

## test-manager 创建 Ticket

```http
POST /api/sso/tickets
Authorization: Bearer <test-manager-access-token>
Content-Type: application/json

{"target": "analysis", "redirect": "/analysis/"}
```

建议响应：

```json
{"ticket": "high-entropy-one-time-ticket", "expiresIn": 30}
```

前端跳转：

```js
const result = await createAnalysisTicket()
window.location.assign(
  `/analysis-api/auth/sso/callback?ticket=${encodeURIComponent(result.ticket)}`
)
```

## test-manager 消费 Ticket

```http
POST /api/sso/tickets/consume
X-SSO-Secret: <server-shared-secret>
Content-Type: application/json

{"ticket": "high-entropy-one-time-ticket", "target": "analysis"}
```

响应可以直接返回用户对象，也可以放在 `data` 字段中：

```json
{
  "data": {
    "userId": "1024",
    "username": "admin",
    "displayName": "管理员",
    "roles": ["admin"],
    "permissions": ["analysis:view", "analysis:run", "analysis:export"]
  }
}
```

## 安全约束

- Ticket 有效期不超过60秒，推荐30秒，且只能消费一次。
- Ticket 必须绑定目标系统 `analysis`。
- 不在 URL 中传递用户密码或长期访问令牌。
- 消费接口只允许服务器调用，并校验共享密钥或客户端证书。
- 正式环境开启 HTTPS，并设置 `WEB_COOKIE_SECURE=true`。

## 分析平台配置

```dotenv
MANAGER_URL=https://server.example.com/
MANAGER_SSO_VERIFY_URL=https://server.example.com/api/sso/tickets/consume
MANAGER_SSO_SHARED_SECRET=<server-shared-secret>
WEB_COOKIE_SECURE=true
```
