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
