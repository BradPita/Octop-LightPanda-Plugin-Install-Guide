# Lightpanda 瀏覽器插件 · Octop 安裝指引

**繁體中文** ｜ [简体中文](README.zh-CN.md) ｜ [English](README.en.md)

> **這份文件給誰看？** 給 **Octop 設備上的 Agent**（或想手動安裝的人）看。用戶通常只會說一句「照這份指引把 Lightpanda 裝上」，你就照著一步步做。
> **最省力的用法**：把本倉庫交給 Agent，讓它逐步執行；到第 6 步跑出「🎉 全綠」就完成了。
> **一句話總結**：把 Lightpanda 裝成 Octop 插件 —— 需要瀏覽器時**優先走 Lightpanda**、搞不定**自動回退 Chrome**、**遙測關閉**、且與原本的 Chromium **新舊並存**。
> 本指引在 Debian/Ubuntu 系 x86_64 機器實測通過（示例環境：Linux Mint 22.3，2026-10）。

---

## 目錄

- [0. 背景：Lightpanda 是什麼、裝完得到什麼](#0-背景lightpanda-是什麼裝完得到什麼)
- [1. 前置檢查（新設備先跑這段確認環境 OK）](#1-前置檢查新設備先跑這段確認環境-ok)
- [2. 安裝 Lightpanda 二進制](#2-安裝-lightpanda-二進制)
- [3. 安裝插件（複製本倉庫的 plugin/）](#3-安裝插件複製本倉庫的-plugin)
- [4. 寫全域路由規則（~/.octop/env）](#4-寫全域路由規則octopenv)
- [5. 重載進運行時](#5-重載進運行時)
- [6. 端到端驗證（scripts/lightpanda-verify-all.py）](#6-端到端驗證scriptslightpanda-verify-allpy)
- [7. 用法速查（lp_* 工具）](#7-用法速查lp_-工具)
- [8. 除錯手冊（兩個核心 bug ＋ 常見坑）](#8-除錯手冊兩個核心-bug-常見坑)
- [9. 回滾／升級](#9-回滾升級)
- [附錄 A：檔案與路徑速查](#附錄-a檔案與路徑速查)｜[附錄 B：最小冒煙](#附錄-b最小冒煙一行命令)

### 本倉庫檔案

| 路徑 | 內容 |
|---|---|
| `README.md` / `README.zh-CN.md` / `README.en.md` | 本指引的繁中／簡中／英文版 |
| `plugin/plugin.yaml` | 插件清單（7 行） |
| `plugin/main.py` | 插件本體（605 行，含 8 個 `lp_*` 工具） |
| `scripts/lightpanda-verify-all.py` | 一條龍端到端驗證腳本 |

> 本倉庫所有中文（含程式碼註解）統一為**繁體中文**；簡中與英文版指引以連結指向同一份程式碼，避免同一份文件內簡繁混用。

---

## 0. 背景：Lightpanda 是什麼、裝完得到什麼

**Lightpanda** 是「**為機器／AI 而生的輕量 headless 瀏覽器**」：以 **Zig** 重寫、用 **V8** 執行 JS、**不做圖形渲染**、**原生支援 CDP（Chrome DevTools Protocol）**。

現行 Octop 內建的 `browser_use` 工具，本質是「**Python Playwright 經 CDP 驅動 Chromium**」；而 Lightpanda 原生也講 CDP —— **天生對得上**，用同一條 CDP 通道就能驅動，不必另寫一套驅動。

裝完後你會得到：

- 一個 Lightpanda 二進制：`~/.local/bin/lightpanda`（`lightpanda version` 可查版本）。
- 一個 Octop 插件 `browser-lightpanda`：掛進運行時、暴露 **8 個 `lp_*` 工具**（開網頁、抓內容／轉 Markdown、點擊、填表、讀 DOM、截圖、關閉會話）。
- 一套**全域路由規則**（寫進 `~/.octop/env`）：**首選 Lightpanda，失敗自動回退 Chrome**。
- **遙測關閉**（`LIGHTPANDA_DISABLE_TELEMETRY=true`）。
- **新舊並存**：舊的 Playwright-Chromium（內建 `browser_use`）**原樣保留當回退**，不是取代關係。

一句話：裝完後 Agent 要開網頁、抓內容、截圖，直接調那幾個 `lp_*`；預設走 Lightpanda、搞不定自動切 Chrome，使用者不用操心細節。

---

## 1. 前置檢查（新設備先跑這段確認環境 OK）

Lightpanda 官方 Linux 二進制**鏈接 glibc**；Alpine／musl 會報 `cannot execute: required file not found`。所以要先確認：是 Debian／Ubuntu 系、`x86_64`、且有 glibc。

另外，我們是靠 **venv 裡的 Playwright（Python）當 CDP 客戶端**去連 Lightpanda 的，所以也要確認 octop 運行時在 `~/.octop/`、且那個 venv 裡**裝了 Playwright**。

先跑下面這段**只讀體檢**（不改動任何東西）：

```bash
# 1) 系統與架構（要 Linux / x86_64；記下 base 發行版，別是 Alpine / musl）
cat /etc/os-release | grep -E '^(NAME|VERSION)='
uname -m                      # 應是 x86_64
ldd --version 2>&1 | head -1  # 有 glibc 輸出即可

# 2) octop 運行時與 venv python 在不在
echo "HOME=$HOME"
ls -d ~/.octop
ls ~/.octop/venv/bin/python

# 3) venv 裡有沒有 Playwright（CDP 客戶端靠它）
~/.octop/venv/bin/python -c "import playwright, playwright.sync_api as s; print('playwright OK')"

# 4) octop CLI 在不在、目前有哪些插件（裝之前應該沒有 browser-lightpanda）
which octop
octop plugin list
```

**判讀要點：**

- `uname -m` 要是 `x86_64`；`/etc/os-release` 要是常見發行版（Linux Mint／Ubuntu／Debian）。**若是 Alpine／musl → 換成 glibc 系發行版，或改走 Docker**。
- `~/.octop/` 要在；`~/.octop/venv/bin/python` 要在。
- `import playwright` 要成功（關鍵）。若失敗＝venv 還沒裝 Playwright → `~/.octop/venv/bin/pip install playwright`，並視情況 `playwright install chromium`。
- `octop` CLI 要在。`octop plugin list` 此刻還沒有 `browser-lightpanda`（正常，第 3 步才安裝）。

> ⚠️ `octop plugin list` 顯示的 `[not loaded]` 只是 **CLI 自己那個進程的視角**，**不代表真正在跑的 server** 到底載入沒有。**別被它誤導。** 真正的依據是第 5 步 `octop plugin reload` 是否回 `Reloaded N`、`octop agent reload <ID>` 是否回 `ok`。

---

## 2. 安裝 Lightpanda 二進制

一行安裝（拉官方 `lightpanda-x86_64-linux` 二進制，預設落到 `~/.local/bin/lightpanda`）：

```bash
curl -fsSL https://pkg.lightpanda.io/install.sh | bash
```

裝完**立即核對版本**（要印出一個版本號，例如 `1.1.0-nightly.10552+dd2cd5d7f`，而不是報錯）：

```bash
ls -l ~/.local/bin/lightpanda      # 確認二進制確實在這裡
~/.local/bin/lightpanda version      # 例：1.1.0-nightly.10552+dd2cd5d7f
```

**備選裝法**（curl 不通時）：

- **Docker 鏡像**：`docker pull` 官方鏡像，再 `docker run ... lightpanda version`（適合不想落地本機的場景）。
- **手動下載**：到官方 GitHub Releases 取對應 `lightpanda-x86_64-linux`，`chmod +x` 後放進 `~/.local/bin/lightpanda`。

**常見坑：**

- `cannot execute: required file not found` → 多半是 musl／Alpine。換 glibc 系，或走 Docker。
- `lightpanda: command not found` → `~/.local/bin` 不在 PATH；改用絕對路徑，或把它加進 PATH。
- 裝完 `version` 仍報錯 → 重跑安裝、確認拉到的是 `x86_64-linux` 構建（別拿到 arm 包）。

---

## 3. 安裝插件（複製本倉庫的 plugin/）

Octop 插件就是 `~/.octop/plugins/<id>/` 下的一個目錄，內含兩份檔案：

- **`plugin.yaml`**（清單）：`id / version / name / description / icon / kind: tool / entry: main.py`。
- **`main.py`**（本體，605 行）：每個工具都是 **`async def`**（docstring 即給模型看的描述、參數帶預設值）；底部 `def setup(ctx)` 用 `ctx.tool("名字", 函數, description=...)` 逐個掛載；配置走 `get_tool_config`（個人層 > 全域 env 分層）。

**安裝動作**＝把本倉庫 `plugin/` 下的兩份檔案複製到 `~/.octop/plugins/browser-lightpanda/`：

```bash
# 若你已 clone 本倉庫（<repo> 為倉庫路徑）
mkdir -p ~/.octop/plugins/browser-lightpanda
cp <repo>/plugin/plugin.yaml ~/.octop/plugins/browser-lightpanda/
cp <repo>/plugin/main.py     ~/.octop/plugins/browser-lightpanda/

# 確認落地
ls -l ~/.octop/plugins/browser-lightpanda/
~/.octop/venv/bin/python -m py_compile ~/.octop/plugins/browser-lightpanda/main.py && echo "SYNTAX OK"
```

> 沒有 clone 的話，直接用 GitHub 頁面把 `plugin/plugin.yaml` 與 `plugin/main.py` 另存到上述目錄即可（**整段原樣存**，別漏行）。

**`main.py` 結構速覽**（看懂、日後改碼用，不用背）：

- **頂部常量**：`DEFAULT_BIN`（二進制路徑，預設取 `Path.home()/".local/bin/lightpanda"`）、`BASE_DIR / SESSIONS_DIR / OUT_DIR`（會話狀態、產物輸出目錄）。
- **配置層**：`get_tool_config`（個人層 > 全域 env）決定 `bin_path`、首選／回退引擎；`_telemetry_env()` 預設關遙測。
- **會話／狀態**：每個 session 獨立目錄，持久化 cookie／登入態（`serve.json`、`page.json`），跨呼叫復用。
- **CDP 核心**：`_start_serve()` 冪等啟動 `lightpanda serve --port N` → 解析 ws（`_cdp_ws()`）→ Playwright `connect_over_cdp(ws)` → 執行 page 動作（goto／click／type／screenshot…）。
- **引擎路由**：`_engine_order(force_engine)` 依序回傳 `[首選, 回退]`；`force_engine` 可指定單一引擎。
- **★ 關鍵健壯性（第 8 節兩個 bug 的修復都活在這段）**：`_is_blank_target(pg)` 判定空白／STARTUP target；`_get_or_create_page()` 跨呼叫重用**只比對廉價的 `pg.url`（刻意不碰 `page.title()`）、外層包 `try` 兜底**，任何異常都退回「新建真實 target」，絕不死等復用。
- **8 個對外工具**（`lp_status / lp_fetch / lp_navigate / lp_click / lp_type / lp_dom / lp_screenshot / lp_close`）＋ 底部 `setup(ctx)` 註冊段。

---

## 4. 寫全域路由規則（~/.octop/env）

要讓這套引擎路由**對整臺 Octop 實例的所有 Agent／使用者生效、重啟不丟**，就寫進全域環境檔 `~/.octop/env`（個別使用者仍可透過 per-tool config 覆蓋，屬分層結構）。

把下面 4 行 **追加**進去 —— **別整檔覆蓋**（別把已有的其他行，例如既有的 `OCTOP_PRINTER_NAME=<印表機名>` 給沖掉）：

```bash
# 追加到 ~/.octop/env（保留既有行）
OCTOP_BROWSER_PREFERRED=lightpanda      # 首選引擎
OCTOP_BROWSER_FALLBACK=chrome           # 失敗時自動回退（= 現有 Playwright Chromium / browser_use）
OCTOP_LIGHTPANDA_BIN=~/.local/bin/lightpanda   # ← 按本機實際絕對路徑填
LIGHTPANDA_DISABLE_TELEMETRY=true       # 關閉遙測
```

**要點：**

- **`OCTOP_LIGHTPANDA_BIN` 一定要填該設備上 Lightpanda 二進制的真實絕對路徑**（例如 `~/.local/bin/lightpanda` 或展開後的完整路徑）。填錯＝找不到二進制。
- 四行語意：首選 lightpanda、回退 chrome、指定二進制路徑、關閉遙測。
- 寫完 `cat ~/.octop/env` 核對這 4 行都在、且原有行沒被刪。

---

## 5. 重載進運行時

插件躺在磁碟上還不夠，要讓 *真正在跑的 server* 撿到它、並把那幾個 `lp_*` 工具注入你的 Agent，需跑兩步重載：

```bash
# [1/2] 重新掃描磁碟上的所有插件 → 撿到剛安裝的 browser-lightpanda
octop plugin reload
# 預期輸出：Reloaded N plugin(s)   （N ≥ 1）

# [2/2] 重載你的 Agent，把 lp_* 工具注入它的工具清單
octop agent reload <你的AGENT_ID>
# 預期輸出：ok
```

- `<你的AGENT_ID>` 換成你在該實例裡的 Agent 識別碼（`octop agent list` 可查）。
- 兩步都成功（`Reloaded N` ＋ `ok`）→ `lp_*` 就進你的工具清單了。
- 再次提醒：`plugin list` 裡的 `[not loaded]` 是 **CLI 自身進程**的視角，別當成 server 狀態；以上面兩步的返回值為準。

---

## 6. 端到端驗證（scripts/lightpanda-verify-all.py）

裝完＋重載後，跑一次本倉庫的驗證腳本。它會**直接 import 插件的 `main.py`、裸調那些 async 工具函數**（證明引擎確實活著、不依賴 octop 是否已注入），逐項覆蓋：

**status → Lightpanda（fetch·navigate·screenshot·close）→ Chrome 回退（fetch·navigate·close）→ 跨呼叫（navigate 後第二條獨立連線 screenshot）**

每步印 ✅／❌ 並附證據（http 狀態、title、PNG magic、markdown 長度、交叉核對）；全過＝**✅ 通過 N 項 · ❌ 失敗 0 項 / 🎉 全綠**、exit 0。

```bash
# 建議先把路徑指到本機實際值（腳本支援這兩個環境變數）
export OCTOP_LIGHTPANDA_BIN=~/.local/bin/lightpanda
export LP_PLUGIN_DIR=~/.octop/plugins/browser-lightpanda

python3 <repo>/scripts/lightpanda-verify-all.py /tmp/verify-out
# 預期末行：✅ 通過 18 項 · ❌ 失敗 0 項 … 🎉 全綠！… 且 exit 0
```

**參考輸出（實測通過，供對照）：**

```text
[load] 插件模組載入自 .../browser-lightpanda (3.1s) · 預算=100s
  ✅ [ 3.1s] T1 lp_status：配置正確 preferred=lightpanda / fallback=chrome / bin=~/.local/bin/lightpanda
  ✅ [ 4.2s] T2 lp_fetch(example.com,markdown)：engine=lightpanda / md 960B / 與直抓交叉核對同篇(共享10)
  ✅ [ 6.7s] T3 lp_navigate(example.com)：engine=lightpanda / http=200 / title='Example Domain'
  ✅ [ 7.3s] T4 lp_screenshot：engine=lightpanda / PNG 10583B / magic=89504e47
  ✅ [ 7.8s] T5 lp_close
  ✅ [ 9.7s] T6a lp_fetch(force=chrome)：engine=chrome / 952B
  ✅ [12.2s] T6b lp_navigate(campfire,force=chrome)：engine=chrome / title='Outdoor Odyssey Nomad Backpack' / http=200
  ✅ [13.8s] T7a lp_navigate(xcall) → T7b 第二條獨立連線 screenshot 無卡死 → T7c close
═══════ 總判定 ═══════
  ✅ 通過 18 項 · ❌ 失敗 0 項 · 總耗時 14.8s
  🎉 全綠！Lightpanda(首選) 與 Chrome(回退) 雙引擎 + 跨呼叫 全部工作
[DONE] PASS · 18 項通過 · 總耗時 14.8s
```

看到「🎉 全綠！」＝Lightpanda（首選）與 Chrome（回退）雙引擎＋跨呼叫，在你的設備上都工作、**可以使用了**。

> 為什麼驗證走「裸調函數」、不等 octop 注入？—— 它直接打到 Lightpanda／Playwright／CDP 這條真鏈，乾淨證明*引擎本身*工作，與「octop 有沒有把工具塞進對話」解耦，是最有力的排障第一手。octop 側可用性由第 5 步兩步重載的返回值保證。

---

## 7. 用法速查（lp_* 工具）

裝完重載後，8 個 `lp_*` 就在 Agent 的工具清單裡；需要瀏覽器時直接調（**預設 lightpanda、失敗自動切 chrome、遙測已關**）。它是**非常駐**的：閒置零佔、用到才啟動、用完主動收。

| 想做 | 工具 | 補充 |
|---|---|---|
| 開／導航到某頁，保持會話 | `lp_navigate(url, session="default")` | 回最終 url／title／http ＋ 用的哪個引擎；供後續 click／type／screenshot 在同一 session 續操作 |
| 一鍵抓頁（跑完 JS）→ 內容 | `lp_fetch(url, out="markdown"｜"html"｜"text"｜"pdf"｜"png")` | 無需常駐、最省；**markdown 餵 LLM 最乾淨** |
| 點頁上某個元素 | `lp_click(selector, session=...)` | CSS 選擇器；點後自動短暫等 DOM 穩定 |
| 往輸入框寫字 | `lp_type(selector, text, session=..., fill=False)` | `fill=True` 直接設值；`False` 逐字鍵入（觸發 input／change 事件鏈） |
| 讀頁結構化內容 | `lp_dom(mode="html"｜"text"｜"markdown", session=...)` | **markdown 區分標題／列表／引用／程式碼／連結錨，餵 LLM 最佳** |
| 截圖存 PNG | `lp_screenshot(path="", full_page=False, session=...)` | `full_page=True` 滾動整頁拼長圖；`path` 留空自動以時間戳落地 |
| 關閉會話（並停後端 serve） | `lp_close(session="default")` | 釋放 port／記憶體；一整輪任務後建議主動叫 |
| 看運行狀態／配置 | `lp_status()` | 回二進制路徑＋版本、首選／回退、遙測、目錄；不實開瀏覽器、開銷極小 |

- **會話（session）**：同一 session 的多通呼叫共享瀏覽上下文（cookie／登入態／當前頁），方便串「開頁 → 填表 → 點提交 → 截圖」；用完 `lp_close` 收掉。不同 session 互不影響。
- **引擎路由**：通常不用管 —— 預設 lightpanda 優先，某個操作在 Lightpanda 上搞不定會**自動回退 Chrome** 完成，結果裡帶 `engine_used`／`used_fallback` 標記。特殊場景可用 `force_engine="lightpanda"` 或 `"chrome"` 強制走某一邊。

一句口訣：開網頁／抓內容／截圖／互動 → `lp_navigate`、`lp_fetch`、`lp_screenshot`、`lp_dom`（預設 lightpanda），難纏站它會自動切 chrome；用完 `lp_close` 釋放。

---

## 8. 除錯手冊（兩個核心 bug ＋ 常見坑）

這段收錄實際安裝過程真正踩到的兩個問題（症狀 → 根因 → 修法 → 怎麼核對修好），加上幾項通用坑。核心特徵：**`lp_navigate`（CDP 路）反覆卡或爆錯，而 `lp_fetch`（CLI 路）1 秒就回** —— 問題**不在二進制**，而在 **CDP 的 target／page 管理**。（這兩個修復都已內建在 `plugin/main.py`，正常情況下你不必再改。）

### 8.1 Bug①：STARTUP target 不可導航（致命，必修）

- **症狀**：`lp_navigate` 卡到逾時，或拋 `Protocol error (Page.navigate): No page on the STARTUP session; create a real target with Target.createTarget`。
- **根因**：`connect_over_cdp` 之後，Playwright 會挑一個*現成*的 page 出來；但 Lightpanda 剛啟動時那個唯一的頁面就是 **STARTUP** 佔位頁（about:blank）。`_get_or_create_page` 若走「複用既有 page」分支，很可能就拿這個 STARTUP 頁去做 `goto` —— 而 STARTUP 不是一個能直接 navigate 的真 target → 卡死／報錯。
- **修法（已內建）**：加 `_is_blank_target(pg)` 判定；`_get_or_create_page` 複用匹配時**若命中 blank／STARTUP → 跳過**，改走 `ctx.new_page()`（= `Target.createTarget`）建一個真正可導航的 target，再 goto。
- **怎麼核對修好**：跑 `scripts/lightpanda-verify-all.py`，**T3 lp_navigate 要 ✅ 且 http=200**（參考機 1.9s 通過）。若仍卡／爆 → 這段沒修上。

### 8.2 Bug②：跨呼叫在「第二條獨立 CDP 連線」下卡死（加固，建議修）

- **症狀**：同一 session 的**第二次**獨立 `lp_*` 呼叫（例如 `lp_navigate` 之後單獨再調 `lp_screenshot`）卡住、>72s 沒反應。
- **根因**：`connect_over_cdp` 本身不慢（~0.03s）、serve 也能正確複用；真正卡住的是「連上之後、去**枚舉／探測既有開啟中的 page**、逐頁讀 url／title 那段」—— 尤其 `page.title()` 這種較貴的 CDP 查詢，在*第二條獨立連線*上下文裡最容易掛住（第一條通常沒事）。簡言之：**連得上、但「讀既有頁狀態」會卡。**
- **修法（已內建）**：複用匹配改成**只比對廉價的 `pg.url`（刻意不調 `page.title()`）**；整段再包一層 `try` —— 任何異常就**優雅退回新建一個真 target**，絕不死等。
- **怎麼核對修好**：`scripts/lightpanda-verify-all.py` 的 **T7（cross-call）navigate → screenshot** 要 ✅ 且**不卡**（參考機 T7 全程 ~2.2s）。T7b screenshot 若長時間不回 → 這段還沒修。

### 8.3 其他常見坑

- **殘留 `lightpanda serve` 進程**：多輪測試／中斷後常留一堆 serve（各佔一個 port）。排障前先清：`pkill -f "lightpanda serve"`，再用 `pgrep -af "lightpanda serve"` 確認清乾淨。
- **`pkill -f` 自比陷阱**：若你當前 shell 命令行**本身也含** `"lightpanda serve"` 字串（例如在 grep／echo 裡打了這串），`pkill -f` 有可能把你自己那條 shell 也匹配進去、把自己 SIGTERM 掉（exit −15）。穩做法：`pgrep -f "lightpanda serve"` 列出 pid，**剔除自身 pid（`$$`）再 kill**。
- **120 秒工具硬上限**：execute／工具側常有 ≈**120 秒**上限。一整輪塞太多引擎案例（fetch＋navigate＋screenshot × 多站）累加超過就會被殺（exit 124）—— **未必是卡死**，可能只是總量撞線。**對策**：分步跑（每次一小段）、或把預算調大（`LP_BUDGET=180`）、非必要環節拆開。
- **冷 V8 JIT／首次偏慢**：Lightpanda 用 V8，**首次**跑某類頁面或剛啟動 serve 可能稍慢（JIT 未熱身）；同條件下後續會快。遇「首次慢、之後順」屬正常，別慌。
- **別把特定站點文案寫死進斷言**：驗證腳本的 T2 fetch 用 example.com，斷言靠 `engine + 非空 + 直抓交叉核對`，而非寫死某句標題文字。換站時照此 —— **斷結構、長度、交叉核對**，別斷具體標點。
- **網路／DNS 抖動**：某些時段導航／抓取變慢甚至逾時，多數**重試一次即好**；持續再查 DNS、代理，或換站測試。
- **port 衝突**：`_start_serve` 會挑 free port 啟動 serve；極端情況可能撞佔用。一般冪等邏輯自避；若撞 → 清殘留 serve 再試。

---

## 9. 回滾／升級

- **回滾（不用了）**：刪 `~/.octop/plugins/browser-lightpanda/` 整個目錄 → `octop plugin reload` ＋ `octop agent reload <ID>`（讓它從運行時消失）→ 可選刪二進制 `rm ~/.local/bin/lightpanda` → 可選清掉 `~/.octop/env` 那 4 行。
- **升級 Lightpanda 二進制**：重跑安裝／換新版覆蓋 `~/.local/bin/lightpanda` → `~/.local/bin/lightpanda version` 核對新版號 → 再跑一次 `scripts/lightpanda-verify-all.py` 確認仍全綠。**插件 `main.py` 不用動**（它指向 `OCTOP_LIGHTPANDA_BIN` 所指的二進制）。
- **改了插件程式碼後**：務必 `octop plugin reload` ＋ `octop agent reload`（程式碼變更不會自動熱更）。

---

## 附錄 A：檔案與路徑速查

| 項目 | 路徑／值 | 說明 |
|---|---|---|
| Lightpanda 二進制 | `~/.local/bin/lightpanda` | `lightpanda version` 查版本 |
| 插件目錄 | `~/.octop/plugins/browser-lightpanda/` | Octop 插件根 |
| 插件清單 | `~/.octop/plugins/browser-lightpanda/plugin.yaml` | 7 行元資料 |
| 插件本體 | `~/.octop/plugins/browser-lightpanda/main.py` | 605 行、8 個 `lp_*` 工具 |
| 全域路由 env | `~/.octop/env` | 4 行：`OCTOP_BROWSER_PREFERRED／FALLBACK／LIGHTPANDA_BIN`、`LIGHTPANDA_DISABLE_TELEMETRY` |
| 會話狀態 | `~/.octop/browser-lightpanda/sessions/<session>/` | `serve.json`／`page.json`（cookie、登入態） |
| 產物輸出 | `~/.octop/browser-lightpanda/out/` | 截圖、PDF 等 |
| 本指引 | 本倉庫 `README.md`（＋ `README.zh-CN.md`／`README.en.md`） | 你正在看的這份 |
| 驗證腳本 | 本倉庫 `scripts/lightpanda-verify-all.py` | 第 6 步的一條龍全綠腳本 |
| 插件源碼 | 本倉庫 `plugin/plugin.yaml`、`plugin/main.py` | 第 3 步要落地的兩份檔 |

## 附錄 B：最小冒煙（一行命令）

不想一上來就跑全套？先這一條確認 Lightpanda 二進制本體能跑：

```bash
~/.local/bin/lightpanda version && echo "Lightpanda binary OK"
```

打出版本號 ＋ echo 一行 OK ＝ 二進制沒壞。要進一步確認整套插件、雙引擎、跨呼叫，再跑第 6 步的 `scripts/lightpanda-verify-all.py`。

---

## 授權與致謝

- **Lightpanda** 本體為 **AGPL-3.0**（見其官方倉庫）。本指引與插件程式碼僅為接入用途；若要把二進制隨產品分發給第三方，請自行評估 AGPL 的傳染性條款。
- 本倉庫的插件程式碼（`plugin/`、`scripts/`）可自由取用於你的 Octop 實例。
