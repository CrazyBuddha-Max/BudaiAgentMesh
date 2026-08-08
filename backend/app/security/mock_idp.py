"""内置演示 OIDC 身份提供方 (仅用于本地演示, 生产环境请接真实 IdP).

挂载于 /mock-idp, 与 backend 同进程:
  GET  /mock-idp/authorize   授权页 (展示演示身份) -> 同意后 302 回 redirect_uri?code&state
  GET  /mock-idp/redirect    内部跳转: 发放一次性 code
  POST /mock-idp/token       用 code 换 access_token (授权码流程)
  GET  /mock-idp/userinfo    返回演示用户 (张三 / analyst)

配合 .env 的 SSO_* 配置即可端到端演示 OAuth2 登录, 无需外部账号.
"""
import secrets
import urllib.parse

from fastapi import FastAPI, Form, Query
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

DEMO_USER = {
    "sub": "demo-zhangsan",
    "preferred_username": "zhangsan",
    "name": "张三",
    "email": "zhangsan@corp.local",
    "role": "analyst",
}

app = FastAPI(title="BudaiAgentMesh 演示 IdP", docs_url=None, redoc_url=None)

_tokens: dict[str, str] = {}  # 一次性 code -> access_token


@app.get("/authorize", response_class=HTMLResponse)
async def authorize(
    client_id: str = Query(...),
    redirect_uri: str = Query(...),
    scope: str = Query("openid profile"),
    state: str = Query(""),
) -> HTMLResponse:
    """授权页: 明确展示将要授予的演示身份, 用户点击同意后回跳应用."""
    code = secrets.token_urlsafe(24)
    html = f"""<!doctype html><html><head><meta charset="utf-8">
<title>BudaiAgentMesh 演示 IdP</title>
<style>
body{{font-family:system-ui,-apple-system,sans-serif;display:flex;justify-content:center;align-items:center;height:100vh;margin:0;background:#f0f2f5}}
.card{{background:#fff;border-radius:14px;padding:32px;width:400px;box-shadow:0 10px 34px rgba(0,0,0,.10)}}
h2{{margin-top:0}} p{{color:#555;line-height:1.6}} .field{{background:#f7f8fa;border-radius:8px;padding:12px 16px;margin:8px 0}}
button{{width:100%;padding:13px;border:0;border-radius:9px;background:#2b6de8;color:#fff;font-size:15px;font-weight:600;cursor:pointer;margin-top:14px}}
button:hover{{background:#1f5bd0}}</style></head>
<body><div class="card">
<h2>演示身份提供方</h2>
<p>应用 <b>{client_id}</b> 请求以下信息:</p>
<div class="field">👤 用户名: <b>张三 (zhangsan)</b></div>
<div class="field">🎭 角色: <b>analyst 分析师</b></div>
<div class="field">📧 邮箱: <b>zhangsan@corp.local</b></div>
<form method="get" action="/mock-idp/redirect">
<input type="hidden" name="code" value="{code}">
<input type="hidden" name="state" value="{state}">
<input type="hidden" name="redirect_uri" value="{urllib.parse.quote(redirect_uri, safe='')}">
<button type="submit">同意授权并登录</button>
</form></div></body></html>"""
    return HTMLResponse(html)


@app.get("/redirect")
async def redirect_endpoint(code: str, state: str, redirect_uri: str) -> RedirectResponse:
    """授权确认后回跳: 发放一次性 code 并携带 state."""
    token = secrets.token_urlsafe(24)
    _tokens[code] = token
    sep = "&" if "?" in redirect_uri else "?"
    return RedirectResponse(f"{redirect_uri}{sep}code={code}&state={state}")


@app.post("/token")
async def token(code: str = Form(...)) -> JSONResponse:
    """授权码换 token."""
    access_token = _tokens.pop(code, secrets.token_urlsafe(24))
    return JSONResponse({"access_token": access_token, "token_type": "Bearer", "expires_in": 3600})


@app.get("/userinfo")
async def userinfo() -> JSONResponse:
    """返回演示用户信息 (含 role 声明, 由 SSO_ROLE_CLAIM 映射)."""
    return JSONResponse(DEMO_USER)
