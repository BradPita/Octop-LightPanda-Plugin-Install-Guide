#!/usr/bin/env python3
# Lightpanda 瀏覽器插件 · 一站式端到端驗證（新設備裝完直接跑，看全綠即成功）
# 直接 import 插件 main.py、裸調 async 工具函數（證引擎活著，不依賴 octop 是否已注入）。
# 覆蓋：status / Lightpanda(fetch·navigate·screenshot·close) / Chrome回退 / 跨呼叫(第二條獨立連線)。
# 用法：  python lightpanda-verify-all.py [out_dir]
# 環境變數（可被新設備按實際路徑調整）：
#   OCTOP_LIGHTPANDA_BIN  二進制路徑（預設 /home/agentk/.local/bin/lightpanda）
#   LP_PLUGIN_DIR           插件目錄（預設 /home/agentk/.octop/plugins/browser-lightpanda）
#   LP_BUDGET                 總耗時預算秒數（預設 100，<120s 工具上限）
import os, sys, re, time, asyncio, importlib.util, json
from collections import Counter
try:
    sys.stdout.reconfigure(line_buffering=True); sys.stderr.reconfigure(line_buffering=True)
except Exception: pass
os.environ.setdefault("PYTHONUNBUFFERED","1")

WS   = sys.argv[1] if len(sys.argv)>1 else os.path.join(os.path.expanduser("~"), ".octop/browser-lightpanda/verify-out")
os.makedirs(WS, exist_ok=True)

# 全域路由環境（與 ~/.octop/env 寫的保持一致；此處用 setdefault，尊重外部已設值）
os.environ.setdefault("OCTOP_LIGHTPANDA_BIN", "/home/agentk/.local/bin/lightpanda")
os.environ.setdefault("OCTOP_BROWSER_PREFERRED","lightpanda")
os.environ.setdefault("OCTOP_BROWSER_FALLBACK","chrome")
os.environ["LIGHTPANDA_DISABLE_TELEMETRY"]="true"   # 關遙測（與全局規則一致）

BUDGET=float(os.environ.get("LP_BUDGET","100"))
t0=time.time(); T=lambda: round(time.time()-t0,2)
N=[0]; F=[0]
def PASS(m): N[0]+=1; print(f"  \u2705 [{T():6.1f}s] {m}",flush=True)
def FAIL(m): F[0]+=1; print(f"  \u274c [{T():6.1f}s] {m}",flush=True)
def BUDGET_OVER(tag):
    if time.time()-t0>BUDGET: print(f"\n  \u23f3 總耗時 {time.time()-t0:.0f}s > 預算 {BUDGET:.0f}s，剩餘步跳過（{tag}）",flush=True); return True
    return False

# ── 載入插件模塊 ──
PDIR = os.environ.get("LP_PLUGIN_DIR","/home/agentk/.octop/plugins/browser-lightpanda")
spec=importlib.util.spec_from_file_location("lp_main_verify", f"{PDIR}/main.py")
M=importlib.util.module_from_spec(spec); spec.loader.exec_module(M)
print(f"[load] 插件模塊載入自 {PDIR} ({T():.1f}s) · 預算={BUDGET:.0f}s · 產物目錄={WS}",flush=True)

# ── 直抓同 URL（交叉核對 lightpanda 與之為同一篇內容）──
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
    """計時 + 預算 + 異常包裝地跑一個 async 工具函數"""
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
        if okc: PASS(f"配置正確: preferred=lightpanda / fallback=chrome / bin={st.get('binary_path')} ver={str(st.get('version'))[:24]}")
        else:   FAIL(f"配置異常: {json.dumps(st,ensure_ascii=False)[:160]}")
        print("   "+json.dumps(st,ensure_ascii=False))

    # ── T2 lightpanda fetch(markdown) ──
    fr=await do("T2 lp_fetch(example.com,markdown)", M.lp_fetch, "https://example.com", out="markdown")
    if fr and "__err__" not in fr:
        md=fr.get("content",""); open(f"{WS}/v-fetch-example.md","w").write(md)
        dt=direct_text("https://example.com"); shared=[w for w in wordset(md) if w in dt.lower()]
        okf=(fr.get("engine")=="lightpanda" and len(md)>=40 and len(shared)>=3)
        if okf: PASS(f"抓頁成功: engine=lightpanda / md {len(md)}B / 與直抓交叉核對同篇(共享{len(shared)}) → v-fetch-example.md")
        else:   FAIL(f"抓頁異常: engine={fr.get('engine')} len={len(md)} shared={shared[:5]}")

    # ── T3/T4/T5 lightpanda CDP：navigate + screenshot + close ──
    nav=await do("T3 lp_navigate(example.com)", M.lp_navigate, "https://example.com", session="v1")
    if nav and "__err__" not in nav:
        okn=(nav.get("engine_used")=="lightpanda" and nav.get("http_status")==200 and str(nav.get("title")))
        if okn: PASS(f"導航成功: engine=lightpanda / http={nav.get('http_status')} title='{nav.get('title')}'")
        else:   FAIL(f"導航異常: {json.dumps(nav,ensure_ascii=False)[:160]}")
        shot=await do("T4 lp_screenshot(v1)", M.lp_screenshot, path=f"{WS}/v-shot.png", session="v1")
        if shot and "__err__" not in shot:
            p=shot.get("path"); head=open(p,"rb").read(4)
            oks=(head[:4]==b"\x89PNG" and shot.get("engine_used")=="lightpanda")
            if oks: PASS(f"截圖成功: engine=lightpanda / PNG {os.path.getsize(p)}B magic={head.hex()} → v-shot.png")
            else:   FAIL(f"截圖異常: magic={head.hex()} engine={shot.get('engine_used')}")
        await do("T5 lp_close(v1)", M.lp_close, session="v1")

    # ── T6 chrome 回退（force_engine=chrome）──
    fc=await do("T6a lp_fetch(force=chrome)", M.lp_fetch, "https://example.com", out="markdown", force_engine="chrome")
    if fc and "__err__" not in fc:
        okc2=(fc.get("engine")=="chrome" and len(fc.get("content",""))>=40)
        if okc2: PASS(f"Chrome 回退 fetch 成功: engine=chrome / {fc.get('length')}B")
        else:   FAIL(f"Chrome fetch 異常: engine={fc.get('engine')}")
    nf=await do("T6b lp_navigate(campfire,force=chrome)", M.lp_navigate,
                  "https://demo-browser.lightpanda.io/campfire-commerce/", session="fb", force_engine="chrome")
    if nf and "__err__" not in nf:
        okn2=(nf.get("engine_used")=="chrome")
        if okn2: PASS(f"Chrome 回退 navigate 成功: title='{nf.get('title','')[:34]}' http={nf.get('http_status')}")
        else:   FAIL(f"Chrome navigate 異常: {json.dumps(nf,ensure_ascii=False)[:140]}")
        await do("T6c lp_close(fb)", M.lp_close, session="fb")

    # ── T7 跨呼叫：navigate 之後，第二條獨立連線 screenshot（驗證不卡）──
    cx=await do("T7a lp_navigate(xcall)", M.lp_navigate, "https://example.com", session="xc")
    if cx and "__err__" not in cx and cx.get("engine_used")=="lightpanda":
        sv=M._read_state("xc","serve"); alive=M._port_alive(sv.get("port")) if sv else False
        print(f"   跨呼叫前 serve 存活={alive} (port={sv.get('port') if sv else None})",flush=True)
        sh2=await do("T7b lp_screenshot(xcall) 第二條獨立連接", M.lp_screenshot, path=f"{WS}/v-xcall.png", session="xc")
        if sh2 and "__err__" not in sh2:
            p2=sh2.get("path"); h2=open(p2,"rb").read(4)
            okx=(h2[:4]==b"\x89PNG" and sh2.get("engine_used")=="lightpanda")
            if okx: PASS(f"跨呼叫成功: 第二條獨立連接無卡死 / PNG {os.path.getsize(p2)}B → v-xcall.png（總耗時 {T():.1f}s）")
            else:   FAIL(f"跨呼叫截圖異常")
        await do("T7c lp_close(xcall)", M.lp_close, session="xc")

    print(f"\n═══════ 總判定 ═══════\n  \u2705 通過 {N[0]} 項 · \u274c 失敗 {F[0]} 項 · 總耗時 {T():.1f}s\n  {'🎉 全綠！Lightpanda(首選) 與 Chrome(回退) 雙引擎 + 跨呼叫 全部工作' if (N[0]>0 and F[0]==0) else '⚠️ 存在失敗項，見上方各步'}",flush=True)
    return F[0]==0 and N[0]>0

ok=asyncio.run(suite())
print(f"[DONE] {'PASS' if ok else 'SOME_FAIL'} · {N[0]} 項通過 · 總耗時 {T():.1f}s")
sys.exit(0 if ok else 1)
