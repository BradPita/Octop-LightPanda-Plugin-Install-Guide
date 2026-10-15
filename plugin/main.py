"""browser-lightpanda —— Octop Lightpanda 瀏覽器插件（kind=tool）

Lightpanda：為機器/AI 而生的輕量 headless 瀏覽器（Zig 重寫、V8 跑 JS、無圖形渲染），
原生說 CDP。本插件用 venv 裡現成的 Playwright 當 CDP 客戶端，連到本機起的
`lightpanda serve`，像操作 Chrome 一樣操作它。

全局路由規則（寫在 ~/.octop/env，可被 per-tool config 覆蓋）：
  OCTOP_BROWSER_PREFERRED=lightpanda  -> 首選
  OCTOP_BROWSER_FALLBACK=chrome         -> 失敗自動回退(Playwright Chromium)
  LIGHTPANDA_DISABLE_TELEMETRY=true    -> 關遙測
  OCTOP_LIGHTPANDA_BIN=...                 -> 二進制路徑

實現要點：所有阻塞 I/O（子進程、同步版 Playwright）都包在 asyncio.to_thread 裡，
避免在事件迴圈內再跑 asyncio.run 的巢狀迴圈問題。
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

# ── 路徑 / 常量 ───────────────────────────────────────────
DEFAULT_BIN = str(Path.home() / ".local" / "bin" / "lightpanda")   # 亦可用 OCTOP_LIGHTPANDA_BIN 覆寫
BASE_DIR = Path.home() / ".octop" / "browser-lightpanda"
SESSIONS_DIR = BASE_DIR / "sessions"
OUT_DIR = BASE_DIR / "out"


def _ensure_dir(p: Path) -> Path:
    p.mkdir(parents=True, exist_ok=True)
    return p


# ── 配置讀取（env 全局層 + per-tool config 個人層） ────────────────
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


# ── 會話 / 狀態文件 ─────────────────────────────────────────────
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


# ── Lightpanda serve 生命週期 ──────────────────────────────────
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
    """確保本會話有活的 lightpanda serve，回傳 port。冪等。"""
    binpath = _bin()
    if not os.path.exists(binpath):
        raise RuntimeError(f"Lightpanda 二進造址不存在：{binpath}")
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
    raise RuntimeError(f"lightpanda serve 未在 15s 內就緒 (port={port})")


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


# ── Playwright 客戶端 ─────────────────────────────────────────
def _sync_playwright():
    from playwright.sync_api import sync_playwright  # 延遲導入
    return sync_playwright


# ── page/context 輔助（跨調用複用） ─────────────────────────────────
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
    """是否為空白/STARTUP target（url≈about:blank）。這類 target 在 Lightpanda 裡
    不能直接 Page.navigate（會報 'No page on the STARTUP session'），要另建真實 target。"""
    try:
        u = (getattr(pg, "url", "") or "").strip().lower()
    except Exception:
        return False
    return u in ("", "about:blank")


def _get_or_create_page(browser, session: str):
    """複用已記錄的 page（跨調用），否則新建並記住其 target key。
    健壯性（實證後加固）：
      ① 複用匹配若命中的其實是空白/STARTUP target → 跳過它，走下方 new_page()
         建真正可導航 target（=Target.createTarget）；
      ② 跨調用重用匹配改用廉價的 url 比對——刻意避免對既有頁逐頁評估
         `page.title()`（那是昂貴 JS 求值；實測「第二條獨立 CDP 連接」下枚舉既有
         頁/取標題最易無響應——正是跨調用會卡的真實點）。再包一層 try，任何異常
         都優雅退回「新建真實 target」，絕不死等複用。"""
    st = _read_state(session, "page")
    target_url = ""
    if isinstance(st, dict) and st.get("key"):
        # 存的 key 可能是 `url#t:title` 合成式或純 url；統一抽取其中 url 段做輕比對
        target_url = str(st.get("key") or "").split("#t:", 1)[0].strip()
    if target_url:
        try:
            for ctx in browser.contexts:
                for pg in ctx.pages:
                    try:
                        pg_url = str(getattr(pg, "url", "") or "")
                    except Exception:
                        continue   # 單頁取 url 異常：忽略該候選、不中斷整圈匹配
                    if pg_url.strip() == target_url and not _is_blank_target(pg):
                        return pg
        except Exception:
            pass   # 枚舉路徑出異常：不強求匹配，落下方新建真實 target
    ctx = browser.contexts[0] if browser.contexts else browser.new_context()
    page = ctx.new_page()
    try:
        _write_state(session, "page", {"key": _page_key(page), "ctx": _ctx_handle(ctx)})
    except Exception:
        pass
    return page


# ── 各動作實裝（都在已打開的 page 上） ───────────────────────────────
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
        return {"mode": mode, "length": 0, "truncated": False, "content": "", "error": f"DOM 提取失敗：{e}"}
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


# ── 核心：在某個引擎上執行一個動作（阻塞塊，走 to_thread） ─────────────
def _op_block(op_name, engine, session, **kw):
    """單線程阻塞：啟 CDP→連→拿/建 page→執行 executor→收尾。回 result dict。"""
    sp = _sync_playwright()
    pw = sp().start()
    browser = None
    try:
        if engine == "lightpanda":
            port = _start_serve(session)
            ws = _cdp_ws(port)
            browser = pw.chromium.connect_over_cdp(ws)
        else:  # chrome：Playwright 自帶 Chromium，直接 launch
            browser = pw.chromium.launch(headless=True, args=["--no-sandbox"])
        page = _get_or_create_page(browser, session)
        result = _EXECUTORS[op_name](pw, browser, page, **kw)
        if isinstance(result, dict):
            result.setdefault("session", session)
        return result
    finally:
        try:
            if browser is not None:
                browser.close()  # connect_over_cdp→僅斷開；launch→殺進程
        except Exception:
            pass
        try:
            pw.stop()
        except Exception:
            pass


async def _run_op(op_name, session, **kw):
    """按 engine_order 依次嘗試（首選→回退）。成功即回。回 (result, meta)。"""
    engines = _engine_order(kw.pop("force_engine", ""))
    last_err = None
    for i, engine in enumerate(engines):
        try:
            result = await asyncio.to_thread(_op_block, op_name, engine, session, **kw)
            return result, {"engine": engine, "used_fallback": i > 0, "error": None}
        except Exception as e:
            last_err = f"[{engine}] {type(e).__name__}: {e}"
            continue
    raise RuntimeError(f"所有引擎都失敗（順序={engines}）。最後錯誤：{last_err}")


# ── lp_fetch：CLI 一鍵抓（跑完 JS），無需常駐；帶 lightpanda→chrome 回退 ─
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
    """一鍵抓取網址內容（自動執行全部 JS 後），轉換為指定格式返回。
    最省資源：無需常駐瀏覽器，一次性起、拿完即收。
    out: markdown | html | text | pdf | png
      - markdown 對「把內容餵給 LLM」最乾淨（結構化文本，無冗餘標籤）。
      - html 是原始 DOM 源碼（含屬性與樣式）。
      - text 是純文字（適合人工閱讀或粗粒度處理）。
      - pdf/png 是渲染產物：會保存到插件輸出目錄並回文件路徑。
    wait_ms: 額外的等待毫秒數（應對動態加載或延時內容），默認 0 立即抓取。
    obey_robots: 是否遵守目標站的 robots.txt 規則，默認 False 快速直取。
    引擎策略：默認首選 Lightpanda（輕量、快、省內存）；若失敗則自動回退到 Chrome(Playwright Chromium)。
    force_engine: 可選指定強制用某個引擎（如 "lightpanda" 或 "chrome"），留空則按全局規則。
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
            # chrome 回退分支：用 Playwright 打開並抽取所需格式
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
    raise RuntimeError(f"lp_fetch 失敗（已嘗試順序={engines}）：{last_err}")


# ── 對外工具函數（都是 async def） ─────────────────────────────────
async def lp_status():
    """查詢 Lightpanda 插件的運行環境與配置摘要：
    - 二進制路徑、是否存在、版本號
    - 當前「首選引擎 / 回退引擎」的設置
    - 遙測開關狀態
    - 會話目錄 / 輸出目錄的位置
    此工具不實際打開瀏覽器，開銷極小，適合體檢與排查。
    """
    binpath = _bin()
    exists = os.path.exists(binpath)
    version = None
    if exists:
        try:
            pr = subprocess.run([binpath, "version"], capture_output=True, text=True, timeout=10)
            version = (pr.stdout or "").strip() or (pr.stderr or "").strip()
        except Exception as e:
            version = f"(查版本失敗: {e})"
    tel = os.environ.get("LIGHTPANDA_DISABLE_TELEMETRY", "(未設置)")
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
    """導航到指定 URL，並保持該會話的瀏覽上下文（方便後續 click/type/screenshot 在同一會話上繼續操作）。
    返回字段包括：最終 URL、頁面標題、HTTP 響應碼、本次使用的引擎、是否觸發了回退、以及 session 名。
    引擎優先級遵循全局規則（默認 Lightpanda 優先，異常自動回退 Chrome）。
    wait_until 可取 load|networkidle 等；timeout_ms 控制超時上限。
    """
    res, meta = await _run_op("navigate", session, url=url, wait_until=wait_until,
                                   timeout_ms=timeout_ms, force_engine=force_engine)
    return {**res, "engine_used": meta["engine"], "used_fallback": meta["used_fallback"]}


async def lp_click(selector: str, session: str = "default", timeout_ms: int = 15000,
                      force_engine: str = ""):
    """點擊當前會話頁面上符合指定 CSS 選擇器的元素。
    點擊後會自動短暫等待 DOM 穩定，以避免競態條件；返回值包含被點擊的選擇器、
    點擊前後的 URL 對比（幫助判斷是否發生了跳轉）、以及所用引擎信息。
    """
    res, meta = await _run_op("click", session, selector=selector,
                                   timeout_ms=timeout_ms, force_engine=force_engine)
    return {**res, "engine_used": meta["engine"], "used_fallback": meta["used_fallback"]}


async def lp_type(selector: str, text: str, session: str = "default", fill: bool = False,
                     timeout_ms: int = 15000, force_engine: str = ""):
    """向當前會話頁面中的指定輸入框寫入文字內容。
    通過 fill 參數切換兩種模式：True 表示直接設置值（適合某些受控組件或下拉框），
    False 表示逐字敲入（會觸發 input/change 事件鏈，更接近真實用戶的鍵入行為）。
    返回寫入的選擇器、字符數、是否使用填充模式，以及對應引擎標識。
    """
    res, meta = await _run_op("type", session, selector=selector, text=text, fill=fill,
                                   timeout_ms=timeout_ms, force_engine=force_engine)
    return {**res, "engine_used": meta["engine"], "used_fallback": meta["used_fallback"]}


async def lp_dom(mode: str = "text", session: str = "default", max_chars: int = 20000,
                   force_engine: str = ""):
    """獲取當前會話頁面的結構化內容表示。mode 參數決定輸出形態：
      html     —— 完整 HTML 源碼（保留標籤與屬性，體積較大，適合程序化處理）
      text      —— 純文本（去除樣式干擾，保持換行結構，閱讀體驗良好）
      markdown   —— 語義化 Markdown（區分標題層級、列表項、引用塊、行內代碼及鏈接錨點，
                      是「將網頁內容高效餵給大語言模型」的最佳實踐選擇）
    max_chars 限制單次返回的最大字符閾值，超出部分會被截斷並在結果中標記 truncated=true，防止巨型頁面撐爆上下文窗口。
    """
    res, meta = await _run_op("dom", session, mode=mode, max_chars=max_chars,
                                   force_engine=force_engine)
    return {**res, "engine_used": meta["engine"], "used_fallback": meta["used_fallback"]}


async def lp_screenshot(path: str = "", full_page: bool = False, session: str = "default",
                             force_engine: str = ""):
    """對當前會話頁面執行截圖操作並將結果持久化為 PNG 圖像文件。
    full_page 置真時會先垂直滾動至頁面底部以捕獲整個文檔流，然後拼接成一張長圖；
    否則只截取當前視口範圍內的可見區域。path 允許自定義最終落盤路徑（必須包含文件名後綴），
    若留空則自動生成帶有時間戳的唯一命名並保存到插件專用的輸出目錄下，避免覆蓋歷史快照。
    返回體涵蓋實際的絕對路徑、二進制尺寸（字節數）、是否全頁模式、歸屬引擎標記等元數據。
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
    """關閉指定會話並終止其後端的 lightpanda serve 守護進程，從而釋放佔用的 TCP 端口與物理內存。
    建議在一次完整的瀏覽任務結束後主動調用，防止長時間累積多個空閒實例造成資源洩漏。
    返回該會話對應的 serve 進程是否成功停止的狀態碼。
    """
    stopped = _stop_serve(session)
    try:
        (_session_dir(session) / "page.json").unlink()
    except Exception:
        pass
    return {"session": session, "serve_stopped": stopped}


# ── 註冊入口 ────────────────────────────────────────────────────
def setup(ctx: PluginContext) -> None:
    ctx.tool("lp_status", lp_status,
             description="查詢 Lightpanda 瀏覽器插件的運行狀態：二進制路徑/版本、首選與回退引擎、遙測開關、會話與輸出目錄。")
    ctx.tool("lp_fetch", lp_fetch,
             description="一鍵抓取網址（自動執行 JS 後）並轉成 Markdown/HTML/text/PDF/PNG。無需常駐、最省資源；首選 Lightpanda，失敗自動回退 Chrome。",
             config_fields=[
                 {"name": "bin_path", "type": "text", "required": False},
                 {"name": "default_out", "type": "select", "options": ["markdown", "html", "text"], "required": False},
                 {"name": "default_wait_ms", "type": "number", "required": False},
             ])
    ctx.tool("lp_navigate", lp_navigate,
             description="打開/導航到網址並保持會話狀態（供後續 click/type/screenshot 複用）。回最終URL、標題、HTTP狀態碼與所用引擎。")
    ctx.tool("lp_click", lp_click,
             description="點擊當前會話頁面上的 CSS 選擇器元素。等待 DOM 穩定後回點擊前後URL與所用引擎。")
    ctx.tool("lp_type", lp_type,
             description="向當前會話輸入框寫入文字。fill=True 直接賦值，False 逐字敲入觸發事件。適用於表單填寫。")
    ctx.tool("lp_dom", lp_dom,
             description="獲取當前會話頁面的結構化內容：mode 支持 html/text/markdown 三種形態，其中 markdown 最適合高效餵給 LLM。超大頁面可按 max_chars 截斷並標註 truncated 標誌。")
    ctx.tool("lp_screenshot", lp_screenshot,
             description="對當前會話頁面執行截圖並保存為 PNG 圖像文件。full_page 置真時可滾動整頁拼接成長圖；否則僅截取當前視口範圍。可自定義落盤路徑，留空則自動生成時間戳命名。")
    ctx.tool("lp_close", lp_close,
             description="關閉指定會話並終止其後端的 lightpanda serve 進程，釋放佔用的端口與內存資源。建議在完整瀏覽任務結束後調用。")
