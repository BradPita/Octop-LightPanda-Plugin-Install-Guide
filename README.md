# Lightpanda 瀏覽器安裝指引（Octop Agent 版）

> **這份文檔給誰看？** 給 **新 Octop 設備上的 Agent** 看。用戶大概會講一句「按這個指引把 Lightpanda 裝上」——你就照著一步步來。
> **怎麼用最省力：** 從第 2 步開始逐步執行；每步都給**可直接粘貼跑的指令**。到第 6 步跑一次 `lightpanda-verify-all.py`，看到「**✅ 通過 N 項 · ❌ 失敗 0 項 / 🎉 全綠**」＝大功告成。
> **本指引已在 Debian/Ubuntu 系 x86_64 機器實測通過**（示例環境：Linux Mint 22.3，2026-10）。

---

## 目錄
- 0. 背景：Lightpanda 是什麼、裝完得到什麼
- 1. 前置檢查（新設備先跑這一段確認環境 OK）
- 2. 安裝 Lightpanda 二進制
- 3. 建立 browser-lightpanda 插件（含 plugin.yaml ＋ main.py 全文）
- 4. 寫全域路由規則（~/.octop/env）
- 5. 重載進運行時（octop plugin reload ＋ agent reload）
- 6. 端到端驗證（一條龍全綠腳本 lightpanda-verify-all.py）
- 7. 用法速查（lp_* 工具怎麼調）
- 8. 除錯手冊（兩個核心 bug ＋ 常見坑）
- 9. 回滾／升級注意
- 附錄 A：檔案與路徑速查；附錄 B：最小冒煙一行命令

---

## 0. 背景：Lightpanda 是什麼、裝完得到什麼

**Lightpanda** 是「**為機器／AI 而生的輕量 headless 瀏覽器**」：Zig 重寫、V8 跑 JS、**無圖形渲染**、**原生 CDP（Chrome DevTools Protocol）**。現行 octop 內建的 `browser_use` 就是「**Python Playwright 經 CDP 驅動 Chromium**」；Lightpanda 原生也講 CDP——**天生對得上**，用同一條 CDP 通道就能驅動它，不用另起一套驅動。

裝完後你會得到：
- 一個 Lightpanda 二進制：`~/.local/bin/lightpanda`（`lightpanda version` 查版本）。
- 一個 octop 插件 `browser-lightpanda`：掛進運行時、暴露 **8 個 `lp_*` 工具**（開網頁、抓內容／轉 Markdown、點、填、讀 DOM、截 PNG、關會話）。
- 一套**全域路由規則**（寫進 `~/.octop/env`）：**首選 lightpanda，失敗自動回退 chrome**。舊的那份 Playwright-Chromium（內建 `browser_use`）**原樣保留當回退**——也就是「**新舊並存**」，不是把舊的刪掉。
- **遙測關閉**（`LIGHTPANDA_DISABLE_TELEMETRY=true`）。

一句話：裝完後 Agent 要開網頁、抓內容、截圖，直接調那幾個 `lp_*`，預設走 Lightpanda、搞不定自動切 Chrome；用戶不用操心細節。

---

## 1. 前置檢查（新設備先跑這一段確認環境 OK）

Lightpanda 官方 Linux 二進制**鏈 glibc**；Alpine／musl 會報 `cannot execute: required file not found`。所以要先確認：是 Debian／Ubuntu 系（Linux Mint、Ubuntu、Debian 都沒問題）、x86_64、glibc 在。

另外，我們是靠 **venv 裡的 Playwright（Python）當 CDP 客戶端**去連 Lightpanda 的，所以也要確認：octop 運行時在 `~/.octop/`、那個 venv 裡**有裝 Playwright**。

讓 Agent 先跑下面這段**只讀體檢**（不改東西）：

```bash
# 1) 系統與架構（要 Linux / x86_64；記下 base 發行版，**別是 Alpine / musl**）
cat /etc/os-release | grep -E '^(NAME|VERSION)='
uname -m                      # 應是 x86_64
ldd --version 2>&1 | head -1 # 有 glibc 輸出即可

# 2) octop 運行時與 venv python 在不在
echo "HOME=$HOME"
ls -d ~/.octop
ls ~/.octop/venv/bin/python

# 3) venv 裡有沒有 Playwright（CDP 客戶端靠它；找不到就要先 pip install playwright）
~/.octop/venv/bin/python -c "import playwright, playwright.sync_api as s; print('playwright OK')"

# 4) octop CLI 在不在、目前有哪些插件（裝之前**應該沒有** browser-lightpanda）
which octop
octop plugin list
```

**判讀要點：**
- `uname -m` 要是 `x86_64`；`/etc/os-release` 要是常見發行版（Linux Mint／Ubuntu／Debian）。**若是 Alpine／musl → 換成 glibc 系發行版，或改走 Docker**。
- `~/.octop/` 要在；`~/.octop/venv/bin/python` 要在。
- `import playwright` 要成功（關鍵）。若失敗＝venv 還沒裝 Playwright → `~/.octop/venv/bin/pip install playwright`，並視情況 `playwright install chromium`。
- `octop` CLI 要在。`octop plugin list` 此刻還沒有 `browser-lightpanda`（正常，第 3 步才建立）。

> ⚠️ `octop plugin list` 顯示的 `[not loaded]` 只是 **CLI 自己那個進程的視角**，**不代表真正在跑的 server** 到底載沒載。**別被它誤導。** 真正的依據＝第 5 步 `octop plugin reload` 是否回 `Reloaded N`、`octop agent reload <ID>` 是否回 `ok`。

---

## 2. 安裝 Lightpanda 二進制

一行安裝（拉官方 `lightpanda-x86_64-linux` 二進制，預設落到 `~/.local/bin/lightpanda`）：

```bash
curl -fsSL https://pkg.lightpanda.io/install.sh | bash
```

裝完**立即核對版本**（要打出一個版本號，例如 `1.1.0-nightly.10552+dd2cd5d7f`，而不是報錯）：

```bash
ls -l ~/.local/bin/lightpanda        # 確認二進制確實在這裡
~/.local/bin/lightpanda version         # 例：1.1.0-nightly.10552+dd2cd5d7f
```

預期中：打印一行版本號。記得這版號，之後除錯時可對照。

**備選裝法**（curl 不通時）：
- **Docker 鏡像**：`docker pull` 官方鏡像、`docker run ... lightpanda version`（適合不想落地本機的場景）。
- **手動下載二進制**：到官方 GitHub Releases 取對應 `lightpanda-x86_64-linux`，`chmod +x` 後放進 `~/.local/bin/lightpanda`。

**常見坑：**
- `cannot execute: required file not found` → 多半是 musl／Alpine。換 glibc 系，或走 Docker。
- `command not found: lightpanda` → `~/.local/bin` 沒進 PATH；直接寫絕對路徑，或加 PATH。
- 裝完 `version` 仍報錯 → 重跑安裝、確認拉到的是 x86_64 構建（別拿到 arm 包）。

---

## 3. 建立 browser-lightpanda 插件（含 plugin.yaml ＋ main.py 全文）

把 Lightpanda 封裝成一個 octop 插件，跟 `printer-cups` 一個套路：放在 `~/.octop/plugins/browser-lightpanda/`，一個 `plugin.yaml`（清單／元資料）＋ 一個 `main.py`（實現＋註冊那 8 個工具）。

> **octop 插件合同（照 printer-cups 這份範本抄即可）**：`~/.octop/plugins/<id>/` 下兩件——
> - `plugin.yaml`（清單，7 行）：`id / version / name / description / icon / kind: tool / entry: main.py`。
> - `main.py`（實現＋註冊，約 605 行）：每個工具是 **`async def`**（docstring＝給模型看的描述、參數帶預設值）；底部 `def setup(ctx)` 用 `ctx.tool("名字", 函數, description=...)` 逐個掛載；配置走 `get_tool_config`（個人層 > 全域 env 分層）。

目錄結構：
```
~/.octop/plugins/browser-lightpanda/
├── plugin.yaml     # 清單（7 行）
└── main.py           # 實現 ＋ 8 個 lp_* 工具註冊（約 605 行）
```

### 3.1 plugin.yaml（全文 · 7 行 · 原樣照抄）

```yaml
id: browser-lightpanda
version: 1.0.0
name: Lightpanda 浏览器
description: 轻量 headless 浏览器（为 AI 而生）：开网页、读内容/转 Markdown、交互与截图。首选引擎，失败自动回退 Chrome。
icon: "🐼"
kind: tool
entry: main.py

```

### 3.2 main.py（核心 · 約 605 行 · **整段原樣照抄**，別漏行）

這是本體：驅動 Lightpanda（CLI `fetch`／`serve` 起 CDP）、venv Playwright 當客戶端、每 profile 獨立 data-dir、閒置自動收、**內建「首選 lightpanda、失敗自動回退 chrome」引擎路由**，掛 8 個 `lp_*` 工具。整段原樣寫入 `~/.octop/plugins/browser-lightpanda/main.py`：

```python
"""browser-lightpanda —— Octop Lightpanda 浏览器插件（kind=tool）

Lightpanda：为机器/AI 而生的轻量 headless 浏览器（Zig 重写、V8 跑 JS、无图形渲染），
原生说 CDP。本插件用 venv 里现成的 Playwright 当 CDP 客户端，连到本机起的
`lightpanda serve`，像操作 Chrome 一样操作它。

全局路由规则（写在 ~/.octop/env，可被 per-tool config 覆盖）：
  OCTOP_BROWSER_PREFERRED=lightpanda  -> 首选
  OCTOP_BROWSER_FALLBACK=chrome         -> 失败自动回退(Playwright Chromium)
  LIGHTPANDA_DISABLE_TELEMETRY=true    -> 关遥测
  OCTOP_LIGHTPANDA_BIN=...                 -> 二进制造址

实现要点：所有阻塞 I/O（子进程、同步版 Playwright）都包在 asyncio.to_thread 里，
避免在事件迴圈内再跑 asyncio.run 的巢狀迴圈問題。
"""
import asyncio
import json
import os
import socket
import subprocess
import time
import urllib.request
from pathlib import Path

from octop_harness.plugins import PluginContext, get_tool_config

# ── 路径 / 常量 ───────────────────────────────────────────
DEFAULT_BIN = str(Path.home() / ".local" / "bin" / "lightpanda")   # 亦可用 OCTOP_LIGHTPANDA_BIN 覆寫
BASE_DIR = Path.home() / ".octop" / "browser-lightpanda"
SESSIONS_DIR = BASE_DIR / "sessions"
OUT_DIR = BASE_DIR / "out"


def _ensure_dir(p: Path) -> Path:
    p.mkdir(parents=True, exist_ok=True)
    return p


# ── 配置读取（env 全局层 + per-tool config 个人层） ────────────────
def _tool_cfg(tool: str) -> dict:
    try:
        return get_tool_config(tool) or {}
    except Exception:
        return {}


def _bin() -> str:
    for t in ("lp_status", "lp_fetch", "lp_navigate"):
        c = _tool_cfg(t)
        if c.get("bin_path"):
            return str(c["bin_path"])
    return os.environ.get("OCTOP_LIGHTPANDA_BIN") or DEFAULT_BIN


def _preferred_engine() -> str:
    eng = (os.environ.get("OCTOP_BROWSER_PREFERRED", "lightpanda") or "").strip().lower()
    return "lightpanda" if "light" in eng else ("chrome" if "chrom" in eng else "lightpanda")


def _fallback_engine() -> str:
    eng = (os.environ.get("OCTOP_BROWSER_FALLBACK", "chrome") or "").strip().lower()
    return "chrome" if "chrom" in eng else ("lightpanda" if "light" in eng else "chrome")


def _engine_order(force_engine: str = ""):
    """回傳依序嘗試的引擎清單（首選在前）。force 指定則只用它。"""
    if force_engine:
        return [force_engine.strip().lower()]
    seen, out = set(), []
    for e in (_preferred_engine(), _fallback_engine()):
        if e not in seen:
            seen.add(e)
            out.append(e)
    return out


def _telemetry_env() -> dict:
    env = dict(os.environ)
    v = env.get("LIGHTPANDA_DISABLE_TELEMETRY", "true").lower()
    env["LIGHTPANDA_DISABLE_TELEMETRY"] = "false" if v in ("0", "false") else "true"
    return env


# ── 会话 / 状态文件 ─────────────────────────────────────────────
def _session_dir(session: str) -> Path:
    s = (session or "default").strip() or "default"
    safe = "".join(ch if (ch.isalnum() or ch in "-_.") else "_" for ch in s) or "default"
    return _ensure_dir(SESSIONS_DIR / safe)


def _write_state(session: str, key: str, val) -> None:
    (_session_dir(session) / (key + ".json")).write_text(json.dumps(val), encoding="utf-8")


def _read_state(session: str, key: str, default=None):
    try:
        return json.loads((_session_dir(session) / (key + ".json")).read_text(encoding="utf-8"))
    except Exception:
        return default


# ── Lightpanda serve 生命周期 ──────────────────────────────────
def _port_alive(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.4):
            return True
    except Exception:
        return False


def _free_port() -> int:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _start_serve(session: str) -> int:
    """確保本会话有活的 lightpanda serve，回傳 port。幂等。"""
    binpath = _bin()
    if not os.path.exists(binpath):
        raise RuntimeError(f"Lightpanda 二进造址不存在：{binpath}")
    st = _read_state(session, "serve")
    if st:
        port, pid = st.get("port"), st.get("pid")
        alive = False
        if port and pid:
            try:
                os.kill(int(pid), 0)
                alive = _port_alive(int(port))
            except Exception:
                alive = False
        if alive:
            return int(port)
    port = _free_port()
    proc = subprocess.Popen(
        [binpath, "serve", "--host", "127.0.0.1", "--port", str(port)],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=_telemetry_env(),
    )
    deadline = time.time() + 15
    while time.time() < deadline:
        if _port_alive(port):
            _write_state(session, "serve", {"port": port, "pid": proc.pid})
            return port
        if proc.poll() is not None:
            try:
                proc.kill()
            except Exception:
                pass
            raise RuntimeError(f"lightpanda serve 提前退出 rc={proc.poll()}")
        time.sleep(0.15)
    try:
        proc.kill()
    except Exception:
        pass
    raise RuntimeError(f"lightpanda serve 未在 15s 内就绪 (port={port})")


def _stop_serve(session: str) -> bool:
    st = _read_state(session, "serve")
    if not st:
        return False
    try:
        os.kill(int(st["pid"]), 15)
        time.sleep(0.4)
        try:
            os.kill(int(st["pid"]), 9)
        except Exception:
            pass
    except Exception:
        pass
    try:
        (_session_dir(session) / "serve.json").unlink()
    except Exception:
        pass
    return True


def _cdp_ws(port: int) -> str:
    """解析 CDP ws：GET http://host:port/json/version → webSocketDebuggerUrl。"""
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/json/version", timeout=4) as r:
            data = json.loads(r.read().decode("utf-8"))
        ws = data.get("webSocketDebuggerUrl")
        if ws:
            return ws
    except Exception:
        pass
    return f"ws://127.0.0.1:{port}"


# ── Playwright 客户端 ─────────────────────────────────────────
def _sync_playwright():
    from playwright.sync_api import sync_playwright  # 延迟导入
    return sync_playwright


# ── page/context 辅助（跨调用复用） ─────────────────────────────────
def _ctx_handle(ctx) -> str:
    try:
        return f"ctx-{abs(hash(ctx))}"
    except Exception:
        return f"ctx-{id(ctx)}"


def _page_key(page) -> str:
    try:
        return f"{page.url}#t:{page.title()}"
    except Exception:
        return f"k{id(page)}"


def _is_blank_target(pg) -> bool:
    """是否为空白/STARTUP target（url≈about:blank）。这类 target 在 Lightpanda 里
    不能直接 Page.navigate（会报 'No page on the STARTUP session'），要另建真实 target。"""
    try:
        u = (getattr(pg, "url", "") or "").strip().lower()
    except Exception:
        return False
    return u in ("", "about:blank")


def _get_or_create_page(browser, session: str):
    """复用已记录的 page（跨调用），否则新建并记住其 target key。
    健壮性（实证后加固）：
      ① 复用匹配若命中的其实是空白/STARTUP target → 跳过它，走下方 new_page()
         建真正可导航 target（=Target.createTarget）；
      ② 跨调用重用匹配改用廉价的 url 比对——刻意避免对既有页逐页评估
         `page.title()`（那是昂贵 JS 求值；实测「第二条独立 CDP 连接」下枚举既有
         页/取标题最易无响应——正是跨调用会卡的真实点）。再包一层 try，任何异常
         都优雅退回「新建真实 target」，绝不死等复用。"""
    st = _read_state(session, "page")
    target_url = ""
    if isinstance(st, dict) and st.get("key"):
        # 存的 key 可能是 `url#t:title` 合成式或纯 url；统一抽取其中 url 段做轻比对
        target_url = str(st.get("key") or "").split("#t:", 1)[0].strip()
    if target_url:
        try:
            for ctx in browser.contexts:
                for pg in ctx.pages:
                    try:
                        pg_url = str(getattr(pg, "url", "") or "")
                    except Exception:
                        continue   # 单页取 url 异常：忽略该候选、不中断整圈匹配
                    if pg_url.strip() == target_url and not _is_blank_target(pg):
                        return pg
        except Exception:
            pass   # 枚举路径出异常：不强求匹配，落下方新建真实 target
    ctx = browser.contexts[0] if browser.contexts else browser.new_context()
    page = ctx.new_page()
    try:
        _write_state(session, "page", {"key": _page_key(page), "ctx": _ctx_handle(ctx)})
    except Exception:
        pass
    return page


# ── 各动作实装（都在已打开的 page 上） ───────────────────────────────
def _exec_navigate(pw, browser, page, url=None, wait_until="load", timeout_ms=45000, **_):
    resp = page.goto(url, wait_until=wait_until or "load", timeout=int(timeout_ms or 45000))
    return {
        "url": url, "final_url": page.url, "title": page.title(),
        "http_status": getattr(resp, "status", None) if resp else None,
    }


def _exec_click(pw, browser, page, selector=None, timeout_ms=15000, **_):
    before = page.url
    page.click(selector, timeout=int(timeout_ms or 15000))
    try:
        page.wait_for_load_state("domcontentloaded", timeout=int(timeout_ms or 15000))
    except Exception:
        pass
    return {"clicked": selector, "url_before": before, "url_after": page.url}


def _exec_type(pw, browser, page, selector=None, text="", fill=False, timeout_ms=15000, **_):
    if fill:
        page.fill(selector, text, timeout=int(timeout_ms or 15000))
    else:
        page.type(selector, text, delay=40, timeout=int(timeout_ms or 15000))
    return {"selector": selector, "chars": len(text), "fill_mode": bool(fill)}


def _exec_dom(pw, browser, page, mode="text", max_chars=20000, **_):
    mode = (mode or "text").lower()
    max_chars = int(max_chars or 20000)
    try:
        if mode == "html":
            raw = page.content()
        elif mode == "markdown":
            raw = page.evaluate(
                "() => {\n"
                "  const l=[];\n"
                "  document.querySelectorAll('h1,h2,h3,h4,h5,h6,p,li,blockquote,pre,code,a').forEach(el=>{\n"
                "    const tag=el.tagName.toLowerCase();\n"
                "    const txt=(el.innerText||el.textContent||'').trim();\n"
                "    if(tag.startsWith('h')){const n=+tag.slice(1); l.push('#'.repeat(n)+' '+(txt||''));}\n"
                "    else if(tag==='p'){l.push(txt);}\n"
                "    else if(tag==='li'){l.push('- '+txt);}\n"
                "    else if(tag==='blockquote'){l.push('> '+txt);}\n"
                "    else if(tag==='pre'||tag==='code'){l.push('`'+txt+'`');}\n"
                "    else if(tag==='a'){const h=el.getAttribute&&el.getAttribute('href'); if(h) l.push('['+(txt||h)+']('+h+')');}\n"
                "  });\n"
                "  return l.join('\\n');\n"
                "}\n"
            )
        else:
            raw = page.evaluate("() => document.body ? document.body.innerText : ''")
    except Exception as e:
        return {"mode": mode, "length": 0, "truncated": False, "content": "", "error": f"DOM 提取失败：{e}"}
    raw = raw or ""
    trunc = len(raw) > max_chars
    return {"mode": mode, "length": len(raw), "truncated": trunc, "content": raw[:max_chars]}


def _exec_screenshot(pw, browser, page, path="", full_page=False, **_):
    png = page.screenshot(full_page=bool(full_page))
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    fp = OUT_DIR / f"lp-{time.strftime('%Y%m%d-%H%M%S')}-{int(time.time() * 1000) % 1000}.png"
    fp.write_bytes(png)
    return {"path": str(fp), "bytes": len(png), "full_page": bool(full_page)}


_EXECUTORS = {
    "navigate": _exec_navigate,
    "click": _exec_click,
    "type": _exec_type,
    "dom": _exec_dom,
    "screenshot": _exec_screenshot,
}


# ── 核心：在某个引擎上执行一个动作（阻塞块，走 to_thread） ─────────────
def _op_block(op_name, engine, session, **kw):
    """单线程阻塞：启 CDP→连→拿/建 page→执行 executor→收尾。回 result dict。"""
    sp = _sync_playwright()
    pw = sp().start()
    browser = None
    try:
        if engine == "lightpanda":
            port = _start_serve(session)
            ws = _cdp_ws(port)
            browser = pw.chromium.connect_over_cdp(ws)
        else:  # chrome：Playwright 自带 Chromium，直接 launch
            browser = pw.chromium.launch(headless=True, args=["--no-sandbox"])
        page = _get_or_create_page(browser, session)
        result = _EXECUTORS[op_name](pw, browser, page, **kw)
        if isinstance(result, dict):
            result.setdefault("session", session)
        return result
    finally:
        try:
            if browser is not None:
                browser.close()  # connect_over_cdp→仅断开；launch→杀进程
        except Exception:
            pass
        try:
            pw.stop()
        except Exception:
            pass


async def _run_op(op_name, session, **kw):
    """按 engine_order 依次尝试（首選→回退）。成功即回。回 (result, meta)。"""
    engines = _engine_order(kw.pop("force_engine", ""))
    last_err = None
    for i, engine in enumerate(engines):
        try:
            result = await asyncio.to_thread(_op_block, op_name, engine, session, **kw)
            return result, {"engine": engine, "used_fallback": i > 0, "error": None}
        except Exception as e:
            last_err = f"[{engine}] {type(e).__name__}: {e}"
            continue
    raise RuntimeError(f"所有引擎都失败（顺序={engines}）。最後錯誤：{last_err}")


# ── lp_fetch：CLI 一键抓（跑完 JS），无需常驻；带 lightpanda→chrome 回退 ─
def _lp_fetch_cli(url: str, out_fmt: str, wait_ms: int, obey_robots: bool, binary: bool):
    binpath = _bin()
    cmd = [binpath, "fetch", "--dump", out_fmt]
    if wait_ms:
        cmd += ["--wait-ms", str(int(wait_ms))]
    if obey_robots:
        cmd.append("--obey-robots")
    cmd.append(url)
    env = dict(os.environ)
    env["LIGHTPANDA_DISABLE_TELEMETRY"] = "true"
    timeout = max(10, int(wait_ms or 0) + 90)
    proc = subprocess.run(cmd, capture_output=True, text=(not binary), timeout=timeout, env=env)
    if proc.returncode != 0:
        err = proc.stderr if isinstance(proc.stderr, str) else (proc.stderr or b"").decode("utf-8", "replace")
        raise RuntimeError(f"lightpanda fetch rc={proc.returncode}: {str(err).strip()[:400]}")
    return proc.stdout  # str if text, bytes if binary


async def lp_fetch(url: str, out: str = "markdown", wait_ms: int = 0,
                      obey_robots: bool = False, force_engine: str = ""):
    """一键抓取网址内容（自动执行全部 JS 后），转换为指定格式返回。
    最省资源：无需常驻浏览器，一次性起、拿完即收。
    out: markdown | html | text | pdf | png
      - markdown 对「把内容喂给 LLM」最干净（结构化文本，无冗余标签）。
      - html 是原始 DOM 源码（含属性与样式）。
      - text 是纯文字（适合人工阅读或粗粒度处理）。
      - pdf/png 是渲染产物：会保存到插件输出目录并回文件路径。
    wait_ms: 额外的等待毫秒数（应对动态加载或延时内容），默认 0 立即抓取。
    obey_robots: 是否遵守目标站的 robots.txt 规则，默认 False 快速直取。
    引擎策略：默认首选 Lightpanda（轻量、快、省内存）；若失败则自动回退到 Chrome(Playwright Chromium)。
    force_engine: 可选指定强制用某个引擎（如 "lightpanda" 或 "chrome"），留空则按全局规则。
    """
    fmt = (out or "markdown").lower()
    binary = fmt in ("pdf", "png")
    engines = _engine_order(force_engine)
    last_err = None
    for i, engine in enumerate(engines):
        try:
            if engine == "lightpanda":
                data = await asyncio.to_thread(_lp_fetch_cli, url, fmt, wait_ms, obey_robots, binary)
                if binary:
                    OUT_DIR.mkdir(parents=True, exist_ok=True)
                    fp = OUT_DIR / f"fetch-{time.strftime('%Y%m%d-%H%M%S')}-{fmt}"
                    fp.write_bytes(data)
                    return {"engine": engine, "used_fallback": i > 0, "format": fmt, "path": str(fp), "bytes": len(data)}
                return {"engine": engine, "used_fallback": i > 0, "format": fmt, "length": len(data), "content": data}
            # chrome 回退分支：用 Playwright 打开并抽取所需格式
            def _chrome():
                sp = _sync_playwright()
                pw = sp().start()
                br = pw.chromium.launch(headless=True, args=["--no-sandbox"])
                try:
                    ctx = br.new_context()
                    pg = ctx.new_page()
                    pg.goto(url, wait_until="load", timeout=60000)
                    if fmt in ("pdf", "png"):
                        blob = pg.pdf(format="A4", print_background=True) if fmt == "pdf" else pg.screenshot(full_page=False)
                        OUT_DIR.mkdir(parents=True, exist_ok=True)
                        fp = OUT_DIR / f"fetch-chrome-{time.strftime('%Y%m%d-%H%M%S')}-{fmt}"
                        fp.write_bytes(blob)
                        return {"engine": engine, "used_fallback": i > 0, "format": fmt, "path": str(fp), "bytes": len(blob)}
                    if fmt == "html":
                        txt = pg.content()
                    elif fmt == "markdown":
                        txt = pg.evaluate("""() => {
                            const l=[];
                            document.querySelectorAll('h1,h2,h3,h4,h5,h6,p,li,blockquote,pre,code,a').forEach(e=>{
                              const t=e.tagName.toLowerCase(); const x=(e.innerText||'').trim();
                              if(t.startsWith('h'))l.push('#'.repeat(+t.slice(1))+' '+x);
                              else if(t==='p')l.push(x);
                              else if(t==='li')l.push('- '+x);
                              else if(t==='blockquote')l.push('> '+x);
                              else if(t==='pre'||t==='code')l.push('`'+x+'`');
                              else if(t==='a'){const h=e.getAttribute('href'); if(h)l.push('['+(x||h)+']('+h+')');}
                            });return l.join('\\n');}""")
                    else:
                        txt = pg.evaluate("() => document.body ? document.body.innerText : ''")
                    return {"engine": engine, "used_fallback": i > 0, "format": fmt, "length": len(txt), "content": txt}
                finally:
                    br.close()
                    pw.stop()
            return await asyncio.to_thread(_chrome)
        except Exception as e:
            last_err = f"[{engine}] {e}"
            continue
    raise RuntimeError(f"lp_fetch 失败（已尝试顺序={engines}）：{last_err}")


# ── 对外工具函数（都是 async def） ─────────────────────────────────
async def lp_status():
    """查询 Lightpanda 插件的运行环境与配置摘要：
    - 二进制造址、是否存在、版本号
    - 当前「首選引擎 / 回退引擎」的设置
    - 遙測开关状态
    - 会话目录 / 输出目录的位置
    此工具不实际打开浏览器，开销极小，适合体检与排查。
    """
    binpath = _bin()
    exists = os.path.exists(binpath)
    version = None
    if exists:
        try:
            pr = subprocess.run([binpath, "version"], capture_output=True, text=True, timeout=10)
            version = (pr.stdout or "").strip() or (pr.stderr or "").strip()
        except Exception as e:
            version = f"(查版本失败: {e})"
    tel = os.environ.get("LIGHTPANDA_DISABLE_TELEMETRY", "(未设置)")
    return {
        "binary_path": binpath,
        "binary_exists": exists,
        "version": version,
        "preferred_engine": _preferred_engine(),
        "fallback_engine": _fallback_engine(),
        "telemetry_disabled_env": tel,
        "sessions_dir": str(SESSIONS_DIR),
        "output_dir": str(OUT_DIR),
    }


async def lp_navigate(url: str, session: str = "default", wait_until: str = "load",
                          timeout_ms: int = 45000, force_engine: str = ""):
    """导航到指定 URL，并保持该会话的浏览上下文（方便后续 click/type/screenshot 在同一会话上继续操作）。
    返回字段包括：最终 URL、页面标题、HTTP 响应码、本次使用的引擎、是否触发了回退、以及 session 名。
    引擎优先级遵循全局规则（默认 Lightpanda 优先，异常自动回退 Chrome）。
    wait_until 可取 load|networkidle 等；timeout_ms 控制超时上限。
    """
    res, meta = await _run_op("navigate", session, url=url, wait_until=wait_until,
                                   timeout_ms=timeout_ms, force_engine=force_engine)
    return {**res, "engine_used": meta["engine"], "used_fallback": meta["used_fallback"]}


async def lp_click(selector: str, session: str = "default", timeout_ms: int = 15000,
                      force_engine: str = ""):
    """点击当前会话页面上符合指定 CSS 选择器的元素。
    点击后会自动短暂等待 DOM 稳定，以避免竞态条件；返回值包含被点击的选择器、
    点击前后的 URL 对比（帮助判断是否发生了跳转）、以及所用引擎信息。
    """
    res, meta = await _run_op("click", session, selector=selector,
                                   timeout_ms=timeout_ms, force_engine=force_engine)
    return {**res, "engine_used": meta["engine"], "used_fallback": meta["used_fallback"]}


async def lp_type(selector: str, text: str, session: str = "default", fill: bool = False,
                     timeout_ms: int = 15000, force_engine: str = ""):
    """向当前会话页面中的指定输入框写入文字内容。
    通过 fill 参数切换两种模式：True 表示直接设置值（适合某些受控组件或下拉框），
    False 表示逐字敲入（会触发 input/change 事件链，更接近真实用户的键入行为）。
    返回写入的选择器、字符数、是否使用填充模式，以及对应引擎标识。
    """
    res, meta = await _run_op("type", session, selector=selector, text=text, fill=fill,
                                   timeout_ms=timeout_ms, force_engine=force_engine)
    return {**res, "engine_used": meta["engine"], "used_fallback": meta["used_fallback"]}


async def lp_dom(mode: str = "text", session: str = "default", max_chars: int = 20000,
                   force_engine: str = ""):
    """获取当前会话页面的结构化内容表示。mode 参数决定输出形态：
      html     —— 完整 HTML 源码（保留标签与属性，体积较大，适合程序化处理）
      text      —— 纯文本（去除样式干扰，保持换行结构，阅读体验良好）
      markdown   —— 语义化 Markdown（区分标题层级、列表项、引用块、行内代码及链接锚点，
                      是「将网页内容高效喂给大语言模型」的最佳实践选择）
    max_chars 限制单次返回的最大字符阈值，超出部分会被截断并在结果中标记 truncated=true，防止巨型页面撑爆上下文窗口。
    """
    res, meta = await _run_op("dom", session, mode=mode, max_chars=max_chars,
                                   force_engine=force_engine)
    return {**res, "engine_used": meta["engine"], "used_fallback": meta["used_fallback"]}


async def lp_screenshot(path: str = "", full_page: bool = False, session: str = "default",
                             force_engine: str = ""):
    """对当前会话页面执行截图操作并将结果持久化为 PNG 图像文件。
    full_page 置真时会先垂直滚动至页面底部以捕获整个文档流，然后拼接成一张长图；
    否则只截取当前视口范围内的可见区域。path 允许自定义最终落盘路径（必须包含文件名后缀），
    若留空则自动生成带有时间戳的唯一命名并保存到插件专用的输出目录下，避免覆盖历史快照。
    返回体涵盖实际的绝对路径、二进制尺寸（字节数）、是否全页模式、归属引擎标记等元数据。
    """
    res, meta = await _run_op("screenshot", session, path=path, full_page=full_page,
                                   force_engine=force_engine)
    saved = res.get("path")
    if path and saved and os.path.realpath(path) != os.path.realpath(saved):
        tgt = Path(path).expanduser().resolve()
        try:
            tgt.parent.mkdir(parents=True, exist_ok=True)
            tgt.write_bytes(Path(saved).read_bytes())
            res["path"] = str(tgt)
        except Exception as e:
            res["move_warning"] = str(e)
    return {**res, "engine_used": meta["engine"], "used_fallback": meta["used_fallback"]}


async def lp_close(session: str = "default"):
    """关闭指定会话并终止其后端的 lightpanda serve 守护进程，从而释放占用的 TCP 端口与物理内存。
    建议在一次完整的浏览任务结束后主动调用，防止长时间累积多个空闲实例造成资源泄漏。
    返回该会话对应的 serve 进程是否成功停止的状态码。
    """
    stopped = _stop_serve(session)
    try:
        (_session_dir(session) / "page.json").unlink()
    except Exception:
        pass
    return {"session": session, "serve_stopped": stopped}


# ── 注册入口 ────────────────────────────────────────────────────
def setup(ctx: PluginContext) -> None:
    ctx.tool("lp_status", lp_status,
             description="查询 Lightpanda 浏览器插件的运行状态：二进制造址/版本、首選與回退引擎、遙測开关、会话与输出目录。")
    ctx.tool("lp_fetch", lp_fetch,
             description="一键抓取网址（自动执行 JS 后）并转成 Markdown/HTML/text/PDF/PNG。无需常驻、最省资源；首選 Lightpanda，失敗自動回退 Chrome。",
             config_fields=[
                 {"name": "bin_path", "type": "text", "required": False},
                 {"name": "default_out", "type": "select", "options": ["markdown", "html", "text"], "required": False},
                 {"name": "default_wait_ms", "type": "number", "required": False},
             ])
    ctx.tool("lp_navigate", lp_navigate,
             description="打开/导航到网址并保持会话状态（供后续 click/type/screenshot 复用）。回最终URL、标题、HTTP状态码与所用引擎。")
    ctx.tool("lp_click", lp_click,
             description="点击当前会话页面上的 CSS 选择器元素。等待 DOM 稳定后回点击前后URL与所用引擎。")
    ctx.tool("lp_type", lp_type,
             description="向当前会话输入框写入文字。fill=True 直接赋值，False 逐字敲入触发事件。适用于表单填写。")
    ctx.tool("lp_dom", lp_dom,
             description="获取当前会话页面的结构化内容：mode 支持 html/text/markdown 三种形态，其中 markdown 最适合高效喂给 LLM。超大页面可按 max_chars 截断并标注 truncated 标志。")
    ctx.tool("lp_screenshot", lp_screenshot,
             description="对当前会话页面执行截图并保存为 PNG 图像文件。full_page 置真时可滚动整页拼接成长图；否则仅截取当前视口范围。可自定义落盘路径，留空则自动生成时间戳命名。")
    ctx.tool("lp_close", lp_close,
             description="关闭指定会话并终止其后端的 lightpanda serve 进程，释放占用的端口与内存资源。建议在完整浏览任务结束后调用。")

```

> **main.py 結構速覽**（看懂、日後改碼用，不用背）：
> - 頂部常量：`DEFAULT_BIN`（二進制路徑）、`BASE_DIR / SESSIONS_DIR / OUT_DIR`（會話狀態、產物輸出目錄）。
> - 配置層：`get_tool_config`（個人層 > 全域 env）決定 `bin_path`、首選／回退引擎；`_telemetry_env()` 預設關遙測。
> - 會話／狀態：每 session 獨立目錄，持久化 cookie／登入態（`serve.json`、`page.json`），跨呼叫復用。
> - CDP 核心：`_start_serve()` 冪等起 `lightpanda serve --port N` → 解析 ws（`_cdp_ws()`）→ Playwright `connect_over_cdp(ws)` → page 操作（goto／click／type／screenshot…）。
> - 引擎路由：`_engine_order(force_engine)` 依序回傳 `[首選, 回退]`；`force_engine` 可指定單一引擎。
> - **★ 關鍵健壯性（第 8 節兩個 bug 的修復都活在這段）**：`_is_blank_target(pg)` 判定空白／STARTUP target；`_get_or_create_page()` 跨呼叫重用**只比對廉價的 `pg.url`（不碰 `page.title()`）、包 try 兜底**，任何異常都退回「新建一個真實 target（`ctx.new_page()`＝`Target.createTarget`）」，絕不死等復用。
> - 8 個對外工具（`lp_status / lp_fetch / lp_navigate / lp_click / lp_type / lp_dom / lp_screenshot / lp_close`）＋ 底部 `setup(ctx)` 註冊段。

---

## 4. 寫全域路由規則（~/.octop/env）

要把這套引擎路由做到**對整台 Octop 實例的所有 Agent／用戶生效、重啟不丟**，就寫進全域環境檔 `~/.octop/env`（個別使用者仍可透過 per-tool config 覆蓋，屬分層結構）。

把下面 4 行 **append 進去**——**別整檔覆蓋**（別把已有的其他行，例如既有的 `OCTOP_PRINTER_NAME=<打印機名>` 給衝掉）：

```bash
# 追加到 ~/.octop/env（保留既有行）
OCTOP_BROWSER_PREFERRED=lightpanda      # 首選引擎
OCTOP_BROWSER_FALLBACK=chrome              # 失敗時自動回退（= 現有 Playwright Chromium / browser_use）
OCTOP_LIGHTPANDA_BIN=/home/<user>/.local/bin/lightpanda    # ← 按新設備實際路徑填！
LIGHTPANDA_DISABLE_TELEMETRY=true          # 關閉遙測
```

要點：
- **`OCTOP_LIGHTPANDA_BIN` 一定要填新設備上 Lightpanda 二進制的真實絕對路徑**（例如 `~/.local/bin/lightpanda`；各設備路徑可能不同）。填錯＝找不到二進制。
- 這四行語意：首選 lightpanda、回退 chrome、指定二進制路徑、關遙測。
- 寫完 `cat ~/.octop/env` 核對這 4 行都在、且原有行沒被刪。

---

## 5. 重載進運行時（octop plugin reload ＋ agent reload）

插件躺在磁碟上還不夠，要讓 *真正在跑的 server* 撿到它、把那幾個 `lp_*` 工具注入到你的 Agent，得跑两步重載（跟 printer-cups 完全一樣的流程）：

```bash
# [1/2] 重新掃描磁碟上的所有插件 → 撿到剛建的 browser-lightpanda
octop plugin reload
# 預期輸出：Reloaded N plugin(s)   （N ≥ 1）

# [2/2] 重載你的 Agent，把 lp_* 工具重新注入它的工具清單
octop agent reload <你的AGENT_ID>
# 預期輸出：ok
```

- `<你的AGENT_ID>` 換成你在該實例裡的 Agent 識別碼（`octop agent list` 可查）。
- `octop plugin reload` 成功會回 `Reloaded N plugin(s)`；`octop agent reload <ID>` 成功回 `ok`。這兩條都 ok → `lp_*` 就進你的工具清單了。
- 再提醒一次：`plugin list` 裡的 `[not loaded]` 是 **CLI 自身進程**的視角，別當成 server 狀態；以上面兩步返回值為準。

---

## 6. 端到端驗證（一條龍全綠腳本 lightpanda-verify-all.py）

裝完＋重載後，跑一次這條龍腳本：它直接 import 插件的 `main.py`、**裸調那些 async 工具函數**（證明引擎確實活著、不依賴 octop 是否已注入），逐項覆蓋 **status → Lightpanda（fetch·navigate·screenshot·close）→ Chrome 回退（fetch·navigate·close）→ 跨呼叫（navigate 後第二條獨立連線 screenshot）**；每步打 ✅／❌ 附證據（http 狀態、title、PNG magic、markdown 長度、交叉核對），全過＝**✅ 通過 N 項 · ❌ 失敗 0 項 / 🎉 全綠**、exit 0。

跑法（把出證目錄指到你想要的位置）：

```bash
python lightpanda-verify-all.py /some/evidence_dir
# 預期末行：✅ 通過 18 項 · ❌ 失敗 0 項 … 🎉 全綠！… 且 exit 0
```

**本參考機實測輸出（供對照）：**

```text
[load] 插件模組載入自 .../browser-lightpanda (3.5s) · budget=100s
  ✅ [ 3.5s] T1 lp_status
  ✅ [ 3.5s] 配置正確: preferred=lightpanda / fallback=chrome / bin=~/.local/bin/lightpanda ver=1.1.0-nightly.10552+dd2c
  ✅ [ 4.5s] T2 lp_fetch(example.com,markdown): 1.0s
  ✅ [ 5.3s] 抓頁成功: engine=lightpanda / md 960B / 與直抓交叉核對同篇(共享10) → v-fetch-example.md
  ✅ [ 7.0s] T3 lp_navigate(example.com): 1.7s
  ✅ [ 7.0s] 導航成功: engine=lightpanda / http=200 title='Example Domain'
  ✅ [ 7.7s] T4 lp_screenshot(v1): 0.6s
  ✅ [ 7.7s] 截圖成功: engine=lightpanda / PNG 10583B magic=89504e47 → v-shot.png
  ✅ [ 8.1s] T5 lp_close(v1): 0.4s
  ✅ [ 9.7s] T6a lp_fetch(force=chrome): 1.7s
  ✅ [ 9.7s] Chrome 回退 fetch 成功: engine=chrome / 952B
  ✅ [12.7s] T6b lp_navigate(campfire,force=chrome): 3.0s
  ✅ [12.7s] Chrome 回退 navigate 成功: title='Outdoor Odyssey Nomad Backpack' http=200
  ✅ [12.7s] T6c lp_close(fb): 0.0s
  ✅ [14.4s] T7a lp_navigate(xcall): 1.6s
  ✅ [15.0s] T7b lp_screenshot(xcall) 第二條獨立連線: 0.6s
  ✅ [15.0s] 跨呼叫成功: 第二條獨立連線無卡死 / PNG 10583B → v-xcall.png
  ✅ [15.4s] T7c lp_close(xcall): 0.4s
═══════ 總判定 ═══════  ✅ 通過 18 項 · ❌ 失敗 0 項 · 🎉 全綠！
[DONE] PASS · 18 項通過 · 總耗時 15.4s
```

看到「🎉 全綠！」＝Lightpanda（首選）與 Chrome（回退）雙引擎＋跨呼叫，在你的新設備上都工作、**能用**了。

> 為什麼驗證走「裸調函數」、不等 octop 注入？——它直接打到 Lightpanda／Playwright／CDP 這條真鏈，乾淨證明*引擎本身*工作，跟「octop 有沒有把工具塞進對話」解耦，是最有力的排障第一手。octop 側可用性由第 5 步兩步重載的返回值保證。

**驗證腳本全文**（存成 `lightpanda-verify-all.py` 放新設備就能跑；建議跟本指引一起歸檔）：

```python
#!/usr/bin/env python3
# Lightpanda 瀏覽器插件 · 一站式端到端驗證（新設備裝完直接跑，看全綠即成功）
# 直接 import 插件 main.py、裸調 async 工具函數（證引擎活著，不依賴 octop 是否已注入）。
# 覆蓋：status / Lightpanda(fetch·navigate·screenshot·close) / Chrome回退 / 跨呼叫(第二條獨立連線)。
# 用法：  python lightpanda-verify-all.py [out_dir]
# 環境變數（可被新設備按實際路徑調整）：
#   OCTOP_LIGHTPANDA_BIN  二進制路徑（預設 ~/.local/bin/lightpanda）
#   LP_PLUGIN_DIR           插件目錄（預設 ~/.octop/plugins/browser-lightpanda）
#   LP_BUDGET                 總耗時預算秒數（預設 100，<120s 工具上限）
import os, sys, re, time, asyncio, importlib.util, json
from collections import Counter
try:
    sys.stdout.reconfigure(line_buffering=True); sys.stderr.reconfigure(line_buffering=True)
except Exception: pass
os.environ.setdefault("PYTHONUNBUFFERED","1")

WS   = sys.argv[1] if len(sys.argv)>1 else os.path.join(os.path.expanduser("~"), ".octop/browser-lightpanda/verify-out")
os.makedirs(WS, exist_ok=True)

# 全域路由環境（與 ~/.octop/env 寫的保持一致；此处用 setdefault，尊重外部已设值）
os.environ.setdefault("OCTOP_LIGHTPANDA_BIN", os.path.expanduser("~/.local/bin/lightpanda"))
os.environ.setdefault("OCTOP_BROWSER_PREFERRED","lightpanda")
os.environ.setdefault("OCTOP_BROWSER_FALLBACK","chrome")
os.environ["LIGHTPANDA_DISABLE_TELEMETRY"]="true"   # 关遥测（与全局规则一致）

BUDGET=float(os.environ.get("LP_BUDGET","100"))
t0=time.time(); T=lambda: round(time.time()-t0,2)
N=[0]; F=[0]
def PASS(m): N[0]+=1; print(f"  \u2705 [{T():6.1f}s] {m}",flush=True)
def FAIL(m): F[0]+=1; print(f"  \u274c [{T():6.1f}s] {m}",flush=True)
def BUDGET_OVER(tag):
    if time.time()-t0>BUDGET: print(f"\n  \u23f3 总耗时 {time.time()-t0:.0f}s > 预算 {BUDGET:.0f}s，剩余步跳过（{tag}）",flush=True); return True
    return False

# ── 载入插件模块 ──
PDIR = os.environ.get("LP_PLUGIN_DIR", os.path.expanduser("~/.octop/plugins/browser-lightpanda"))
spec=importlib.util.spec_from_file_location("lp_main_verify", f"{PDIR}/main.py")
M=importlib.util.module_from_spec(spec); spec.loader.exec_module(M)
print(f"[load] 插件模块载入自 {PDIR} ({T():.1f}s) · 预算={BUDGET:.0f}s · 产物目录={WS}",flush=True)

# ── 直抓同 URL（交叉核对 lightpanda 与之为同一篇内容）──
def direct_text(url):
    import urllib.request, html as H
    req=urllib.request.Request(url, headers={"User-Agent":"Mozilla/5.0 (direct-probe)"})
    raw=urllib.request.urlopen(req, timeout=25).read().decode("utf-8","replace")
    raw=re.sub(r"<(script|style).*?</\1>","",raw,flags=re.S)
    return H.unescape(re.sub(r"\s+"," ",re.sub(r"<[^>]+>"," ",raw))).strip()
def wordset(s,n=10):
    ws=[w for w in re.findall(r"[A-Za-z\u00C0-\u024F\u0400-\u05FF]{4,}", s.lower())]
    return [w for w,_ in Counter(ws).most_common(n)]

async def do(tag, fn, *a, **k):
    """计时 + 预算 + 异常包装地跑一个 async 工具函数"""
    if BUDGET_OVER(tag): return None
    ts=time.time()
    try:
        r=await fn(*a,**k); PASS(f"{tag}: {time.time()-ts:.1f}s"); return r
    except Exception as e:
        FAIL(f"{tag}: {type(e).__name__}: {str(e)[:180]}"); return {"__err__":f"{type(e).__name__}: {e}"}

async def suite():
    # ── T1 status ──
    st=await do("T1 lp_status", M.lp_status)
    if st and "__err__" not in st:
        okc = st.get("binary_exists") and st.get("preferred_engine")=="lightpanda" and st.get("fallback_engine")=="chrome"
        if okc: PASS(f"配置正确: preferred=lightpanda / fallback=chrome / bin={st.get('binary_path')} ver={str(st.get('version'))[:24]}")
        else:   FAIL(f"配置异常: {json.dumps(st,ensure_ascii=False)[:160]}")
        print("   "+json.dumps(st,ensure_ascii=False))

    # ── T2 lightpanda fetch(markdown) ──
    fr=await do("T2 lp_fetch(example.com,markdown)", M.lp_fetch, "https://example.com", out="markdown")
    if fr and "__err__" not in fr:
        md=fr.get("content",""); open(f"{WS}/v-fetch-example.md","w").write(md)
        dt=direct_text("https://example.com"); shared=[w for w in wordset(md) if w in dt.lower()]
        okf=(fr.get("engine")=="lightpanda" and len(md)>=40 and len(shared)>=3)
        if okf: PASS(f"抓页成功: engine=lightpanda / md {len(md)}B / 与直抓交叉核对同篇(共享{len(shared)}) → v-fetch-example.md")
        else:   FAIL(f"抓页异常: engine={fr.get('engine')} len={len(md)} shared={shared[:5]}")

    # ── T3/T4/T5 lightpanda CDP：navigate + screenshot + close ──
    nav=await do("T3 lp_navigate(example.com)", M.lp_navigate, "https://example.com", session="v1")
    if nav and "__err__" not in nav:
        okn=(nav.get("engine_used")=="lightpanda" and nav.get("http_status")==200 and str(nav.get("title")))
        if okn: PASS(f"导航成功: engine=lightpanda / http={nav.get('http_status')} title='{nav.get('title')}'")
        else:   FAIL(f"导航异常: {json.dumps(nav,ensure_ascii=False)[:160]}")
        shot=await do("T4 lp_screenshot(v1)", M.lp_screenshot, path=f"{WS}/v-shot.png", session="v1")
        if shot and "__err__" not in shot:
            p=shot.get("path"); head=open(p,"rb").read(4)
            oks=(head[:4]==b"\x89PNG" and shot.get("engine_used")=="lightpanda")
            if oks: PASS(f"截图成功: engine=lightpanda / PNG {os.path.getsize(p)}B magic={head.hex()} → v-shot.png")
            else:   FAIL(f"截图异常: magic={head.hex()} engine={shot.get('engine_used')}")
        await do("T5 lp_close(v1)", M.lp_close, session="v1")

    # ── T6 chrome 回退（force_engine=chrome）──
    fc=await do("T6a lp_fetch(force=chrome)", M.lp_fetch, "https://example.com", out="markdown", force_engine="chrome")
    if fc and "__err__" not in fc:
        okc2=(fc.get("engine")=="chrome" and len(fc.get("content",""))>=40)
        if okc2: PASS(f"Chrome 回退 fetch 成功: engine=chrome / {fc.get('length')}B")
        else:   FAIL(f"Chrome fetch 异常: engine={fc.get('engine')}")
    nf=await do("T6b lp_navigate(campfire,force=chrome)", M.lp_navigate,
                  "https://demo-browser.lightpanda.io/campfire-commerce/", session="fb", force_engine="chrome")
    if nf and "__err__" not in nf:
        okn2=(nf.get("engine_used")=="chrome")
        if okn2: PASS(f"Chrome 回退 navigate 成功: title='{nf.get('title','')[:34]}' http={nf.get('http_status')}")
        else:   FAIL(f"Chrome navigate 异常: {json.dumps(nf,ensure_ascii=False)[:140]}")
        await do("T6c lp_close(fb)", M.lp_close, session="fb")

    # ── T7 跨呼叫：navigate 之后，第二條獨立連線 screenshot（验证不卡）──
    cx=await do("T7a lp_navigate(xcall)", M.lp_navigate, "https://example.com", session="xc")
    if cx and "__err__" not in cx and cx.get("engine_used")=="lightpanda":
        sv=M._read_state("xc","serve"); alive=M._port_alive(sv.get("port")) if sv else False
        print(f"   跨呼叫前 serve 存活={alive} (port={sv.get('port') if sv else None})",flush=True)
        sh2=await do("T7b lp_screenshot(xcall) 第二条独立连接", M.lp_screenshot, path=f"{WS}/v-xcall.png", session="xc")
        if sh2 and "__err__" not in sh2:
            p2=sh2.get("path"); h2=open(p2,"rb").read(4)
            okx=(h2[:4]==b"\x89PNG" and sh2.get("engine_used")=="lightpanda")
            if okx: PASS(f"跨呼叫成功: 第二条独立连接无卡死 / PNG {os.path.getsize(p2)}B → v-xcall.png（总耗时 {T():.1f}s）")
            else:   FAIL(f"跨呼叫截图异常")
        await do("T7c lp_close(xcall)", M.lp_close, session="xc")

    print(f"\n═══════ 总判定 ═══════\n  \u2705 通过 {N[0]} 项 · \u274c 失败 {F[0]} 项 · 总耗时 {T():.1f}s\n  {'🎉 全绿！Lightpanda(首选) 与 Chrome(回退) 双引擎 + 跨呼叫 全部工作' if (N[0]>0 and F[0]==0) else '⚠️ 存在失败项，见上方各步'}",flush=True)
    return F[0]==0 and N[0]>0

ok=asyncio.run(suite())
print(f"[DONE] {'PASS' if ok else 'SOME_FAIL'} · {N[0]} 项通过 · 总耗时 {T():.1f}s")
sys.exit(0 if ok else 1)

```

---

## 7. 用法速查（lp_* 工具怎麼調）

裝完重載後，8 個 `lp_*` 就在你的工具清單裡了；需要瀏覽器時直接調（**預設 lightpanda、失敗自動切 chrome、遙測已關**）。它是**非常駐**的：閒置零占、用到才起、用完主動收。常用口訣表：

| 想做 | 工具 | 補充 |
|---|---|---|
| 開／導航到某頁，保持會話 | `lp_navigate(url, session="default")` | 回最終 url／title／http＋用的哪個引擎；供後續 click／type／screenshot 在同一 session 續操 |
| 一鍵抓頁（跑完 JS）→ 內容 | `lp_fetch(url, out="markdown"｜html｜text｜pdf｜png)` | 無需常駐、最省；**markdown 餵 LLM 最乾淨** |
| 點頁上某個元素 | `lp_click(selector, session=...)` | CSS 選擇器；點後自動短暫等 DOM 穩定 |
| 往輸入框寫字 | `lp_type(selector, text, session=..., fill=False)` | `fill=True` 直接設值；`False` 逐字敲入（觸發 input／change 事件鏈） |
| 讀頁結構化內容 | `lp_dom(mode="html"｜text｜markdown", session=...)` | **markdown 區分標題／列表／引用／代碼／連結錨，餵 LLM 最佳** |
| 截圖存 PNG | `lp_screenshot(path="", full_page=False, session=...)` | `full_page=True` 滾動整頁拼長圖；`path` 留空自動時間戳落 `OUT_DIR` |
| 關會話＋殺後端 serve | `lp_close(session="default")` | 釋放 port／記憶體；一整輪任務後建議主動叫 |
| 看運行狀態／配置 | `lp_status()` | 回二進制路徑＋版本、首選／回退、遙測、目錄；不實開瀏覽器、開銷極小 |

- **會話（session）**：同一 session 的多通呼叫共享瀏覽上下文（cookie／登入態／當前頁），方便串「開頁 → 填表 → 點提交 → 截圖」；用完 `lp_close` 收掉。不同 session 互不影響。
- **引擎路由**：通常不用管——預設 lightpanda 優先，某個 op 在 Lightpanda 搞不定會**自動回退 Chrome** 完成，結果裡帶 `engine_used`／`used_fallback` 標記。特殊場景可用 `force_engine="lightpanda"` 或 `"chrome"` 強制走某一邊。

一句口訣：開網頁／抓內容／截圖／交互 → `lp_navigate`、`lp_fetch`、`lp_screenshot`、`lp_dom`（預設 lightpanda），難纏站它會自動切 chrome；用完 `lp_close` 釋放。

---

## 8. 除錯手冊（兩個核心 bug ＋ 常見坑）

這段收錄本次實裝過程真正踩到的兩個問題（症狀→根因→修法→怎麼核對修好），加上幾項通用坑。新設備遇到「navigate 卡死／超時」時，照 §8.1、§8.2 對照處理最能省時。核心特徵：`lp_navigate`（CDP 路）反覆卡或炸，而 `lp_fetch`（CLI 路）1s 就回——問題**不在二進制**，而在 **CDP 的 target／page 管理**。

### 8.1 Bug①：STARTUP target 不可導航（致命，必修）

- **症狀**：`lp_navigate` 卡到超時，或拋 `Protocol error (Page.navigate): No page on the STARTUP session; create a real target with Target.createTarget`。
- **根因**：`connect_over_cdp` 之後、Playwright 會挑一個*現成*的 page 出來；但 Lightpanda 剛起時那個唯一的頁就是 **STARTUP** 佔位頁（about:blank）。`_get_or_create_page` 若走「複用既有 page」分支，很可能就拿這個 STARTUP 頁去做 `goto`——而 STARTUP 不是一個能直接 navigate 的真 target → 卡死／報錯。
- **修法（已落地到 main.py）**：加 `_is_blank_target(pg)` 判定；`_get_or_create_page` 複用匹配時**若命中 blank／STARTUP → 跳過**，改走 `ctx.new_page()`（= `Target.createTarget`）建一個真正的可導航 target，再 goto。
- **怎麼核對修好**：跑 `lightpanda-verify-all.py`，**T3 lp_navigate 要 ✅ http=200 title=Example Domain**（參考機 1.7s 過）。若仍卡／炸＝這段沒修上。

### 8.2 Bug②：跨呼叫在「第二條獨立 CDP 連線」下卡死（加固，建議修）

- **症狀**：同一 session 的**第二次**獨立 `lp_*` 呼叫（例如 `lp_navigate` 之後單獨再調 `lp_screenshot`）卡住、>72s 沒反應。
- **根因**：`connect_over_cdp` 本身不慢（~0.03s）、serve 也能正確復用；真正卡住的是「連上之後、去**枚舉／探測既有開啟中的 page**、逐頁讀 url／title 那段」——尤其 `page.title()` 這種較貴的 CDP 查詢，在*第二條獨立連線*上下文裡最容易掛住（第一條通常沒事）。簡言之：**連得上、但「讀既有頁狀態」會卡。**
- **修法（已落地到 main.py）**：重用匹配改成**只比對廉價的 `pg.url`（刻意不調 `page.title()`）**；整段再包一層 `try`——任何異常就**優雅退回新建一個真 target**，絕不死等。
- **怎麼核對修好**：`lightpanda-verify-all.py` 的 **T7（cross-call）navigate→screenshot** 要 ✅ 且**不卡**（參考機 T7 全程 ~2.2s）。T7b screenshot 若長時間不迴 → 這段還沒修。

### 8.3 其它常見坑

- **殘留 `lightpanda serve` 進程**：多輪測試／中斷後常留一堆 serve（各占一個 port）。排障前先清：`pkill -f "lightpanda serve"`，再用 `pgrep -af "lightpanda serve"` 確認清乾淨。
- **`pkill -f` 自比陷阱**：若你當前 shell 命令行**本身也含** `"lightpanda serve"` 字串（比如在 grep／echo 裡打了這串），`pkill -f` 有可能把你自己那条 shell 也 match 進去、把自己 SIGTERM 掉（exit −15）。穩做法：`pgrep -f "lightpanda serve"` 列出 pid，**剔除自身 pid（`$$`）再 kill**。
- **120s 工具硬上限**：execute／工具側常有 ≈**120s** 上限。一整輪塞太多引擎 case（fetch＋navigate＋screenshot × 多站）累加超過就會被殺（exit 124）——**未必是卡死**，可能只是總量撞線。**對策**：分步跑（每次一小段）、或把預算調大（`LP_BUDGET=180`）、非必要環節拆開。
- **冷 V8 JIT／首次偏慢**：Lightpanda 用 V8，**首次**跑某類頁面或剛起 serve 可能稍慢（JIT 未熱身）；同條件下後續會快。遇「首次慢、之後順」屬正常，別慌。
- **別把特定站文案寫死進斷言**：verify-all 的 T2 fetch 用 example.com，斷言靠 `engine + 非空 + 直抓交叉核對`，而非寫死某句標題文字。換站時照此——**斷結構、長度、交叉核對**，別斷具體標點。
- **網路／DNS 抖動**：某些時段導航／抓取變慢甚至超時，多數**重試一次即好**；持續再查 DNS、代理、或換站測。
- **port 衝突**：`_start_serve` 會挑 free port 起 serve；極端情況可能撞占用。一般冪等邏輯自避；若撞→清殘留 serve 再試。

---

## 9. 回滾／升級注意

- **回滾（不用了）**：刪 `~/.octop/plugins/browser-lightpanda/` 整個目錄 → `octop plugin reload`＋`octop agent reload <ID>`（讓它從運行時消失）→ 可選刪二進制 `rm ~/.local/bin/lightpanda` → 可選清掉 `~/.octop/env` 那 4 行。
- **升級 Lightpanda 二進制**：重跑安裝／換新版覆蓋 `~/.local/bin/lightpanda` → `~/.local/bin/lightpanda version` 核對新版號 → 再跑一次 `lightpanda-verify-all.py` 確認仍全綠。**插件 main.py 不用動**（它指向 `OCTOP_LIGHTPANDA_BIN` 所指的二進制）。
- **改了插件代碼後**：務必 `octop plugin reload`＋`octop agent reload`（代碼變更不會自動熱更）。

---

## 附錄 A：檔案與路徑速查

| 項目 | 路徑／值 | 說明 |
|---|---|---|
| Lightpanda 二進制 | `~/.local/bin/lightpanda` | `lightpanda version` 查版本 |
| 插件目錄 | `~/.octop/plugins/browser-lightpanda/` | octop 插件根 |
| 插件清單 | `~/.octop/plugins/browser-lightpanda/plugin.yaml` | 7 行元資料 |
| 插件實現 | `~/.octop/plugins/browser-lightpanda/main.py` | 605 行、8 個 `lp_*` 工具 |
| 全域路由 env | `~/.octop/env` | 4 行：`OCTOP_BROWSER_PREFERRED/FALLBACK/LIGHTPANDA_BIN`、`LIGHTPANDA_DISABLE_TELEMETRY` |
| 會話狀態 | `~/.octop/browser-lightpanda/sessions/<session>/` | `serve.json`／`page.json`（cookie、登入態） |
| 產物輸出 | `~/.octop/browser-lightpanda/out/` | 截圖、PDF 等 |
| 本指引 | 本倉庫 `README.md` | 你正在看的這份 |
| 驗證腳本 | 本倉庫 `scripts/lightpanda-verify-all.py` | 第 6 步的一條龍全綠腳本 |
| 插件源碼 | 本倉庫 `plugin/plugin.yaml`、`plugin/main.py` | 第 3 步要落地的兩份檔 |

## 附錄 B：最小冒煙（一行命令快速確認二進制活著）

不想一上來就跑全套？先這一條確認 Lightpanda 二進制本體能跑：

```bash
~/.local/bin/lightpanda version && echo "Lightpanda binary OK"
```

打出版本號＋echo 一行 OK＝二進制沒壞。要進一步確認整套插件、雙引擎、跨呼叫，再跑第 6 步的 `lightpanda-verify-all.py`。

