# Lightpanda 浏览器插件 · Octop 安装指引

[繁體中文](README.md) ｜ **简体中文** ｜ [English](README.en.md)

> **这份文档给谁看？** 给 **Octop 设备上的 Agent**（或想手动安装的人）看。用户通常只会说一句「照这份指引把 Lightpanda 装上」，你就照着一步步做。
> **最省力的用法**：把本仓库交给 Agent，让它逐步运行；到第 6 步跑出「🎉 全绿」就完成了。
> **一句话总结**：把 Lightpanda 装成 Octop 插件 —— 需要浏览器时**优先走 Lightpanda**、搞不定**自动回退 Chrome**、**遥测关闭**、且与原本的 Chromium **新旧并存**。
> 本指引在 Debian/Ubuntu 系 x86_64 机器实测通过（示例环境：Linux Mint 22.3，2026-10）。

---

## 目录

- [0. 背景：Lightpanda 是什么、装完得到什么](#0-背景lightpanda-是什么装完得到什么)
- [1. 前置检查（新设备先跑这段确认环境 OK）](#1-前置检查新设备先跑这段确认环境-ok)
- [2. 安装 Lightpanda 二进制](#2-安装-lightpanda-二进制)
- [3. 安装插件（复制本仓库的 plugin/）](#3-安装插件复制本仓库的-plugin)
- [4. 写全局路由规则（~/.octop/env）](#4-写全局路由规则octopenv)
- [5. 重载进运行时](#5-重载进运行时)
- [6. 端到端验证（scripts/lightpanda-verify-all.py）](#6-端到端验证scriptslightpanda-verify-allpy)
- [7. 用法速查（lp_* 工具）](#7-用法速查lp_-工具)
- [8. 调试手册（两个核心 bug ＋ 常见坑）](#8-调试手册两个核心-bug-常见坑)
- [9. 回滚／升级](#9-回滚升级)
- [附录 A：文件与路径速查](#附录-a文件与路径速查)｜[附录 B：最小冒烟](#附录-b最小冒烟一行命令)

### 本仓库文件

| 路径 | 内容 |
|---|---|
| `README.md` / `README.zh-CN.md` / `README.en.md` | 本指引的繁中／简中／英文版 |
| `plugin/plugin.yaml` | 插件清单（7 行） |
| `plugin/main.py` | 插件本体（605 行，含 8 个 `lp_*` 工具） |
| `scripts/lightpanda-verify-all.py` | 一条龙端到端验证脚本 |

> 本仓库所有中文（含代码注解）统一为**繁体中文**；简中与英文版指引以链接指向同一份代码，避免同一份文档内简繁混用。

---

## 0. 背景：Lightpanda 是什么、装完得到什么

**Lightpanda** 是「**为机器／AI 而生的轻量 headless 浏览器**」：以 **Zig** 重写、用 **V8** 运行 JS、**不做图形渲染**、**原生支持 CDP（Chrome DevTools Protocol）**。

现行 Octop 内置的 `browser_use` 工具，本质是「**Python Playwright 经 CDP 驱动 Chromium**」；而 Lightpanda 原生也讲 CDP —— **天生对得上**，用同一条 CDP 信道就能驱动，不必另写一套驱动。

装完后你会得到：

- 一个 Lightpanda 二进制：`~/.local/bin/lightpanda`（`lightpanda version` 可查版本）。
- 一个 Octop 插件 `browser-lightpanda`：挂进运行时、暴露 **8 个 `lp_*` 工具**（开网页、抓内容／转 Markdown、点击、填表、读 DOM、截屏、关闭会话）。
- 一套**全局路由规则**（写进 `~/.octop/env`）：**首选 Lightpanda，失败自动回退 Chrome**。
- **遥测关闭**（`LIGHTPANDA_DISABLE_TELEMETRY=true`）。
- **新旧并存**：旧的 Playwright-Chromium（内置 `browser_use`）**原样保留当回退**，不是取代关系。

一句话：装完后 Agent 要开网页、抓内容、截屏，直接调那几个 `lp_*`；默认走 Lightpanda、搞不定自动切 Chrome，用户不用操心细节。

---

## 1. 前置检查（新设备先跑这段确认环境 OK）

Lightpanda 官方 Linux 二进制**链接 glibc**；Alpine／musl 会报 `cannot execute: required file not found`。所以要先确认：是 Debian／Ubuntu 系、`x86_64`、且有 glibc。

另外，我们是靠 **venv 里的 Playwright（Python）当 CDP 客户端**去连 Lightpanda 的，所以也要确认 octop 运行时在 `~/.octop/`、且那个 venv 里**装了 Playwright**。

先跑下面这段**只读体检**（不改动任何东西）：

```bash
# 1) 系统与架构（要 Linux / x86_64；记下 base 发行版，别是 Alpine / musl）
cat /etc/os-release | grep -E '^(NAME|VERSION)='
uname -m                      # 应是 x86_64
ldd --version 2>&1 | head -1  # 有 glibc 输出即可

# 2) octop 运行时与 venv python 在不在
echo "HOME=$HOME"
ls -d ~/.octop
ls ~/.octop/venv/bin/python

# 3) venv 里有没有 Playwright（CDP 客户端靠它）
~/.octop/venv/bin/python -c "import playwright, playwright.sync_api as s; print('playwright OK')"

# 4) octop CLI 在不在、目前有哪些插件（装之前应该没有 browser-lightpanda）
which octop
octop plugin list
```

**判读要点：**

- `uname -m` 要是 `x86_64`；`/etc/os-release` 要是常见发行版（Linux Mint／Ubuntu／Debian）。**若是 Alpine／musl → 换成 glibc 系发行版，或改走 Docker**。
- `~/.octop/` 要在；`~/.octop/venv/bin/python` 要在。
- `import playwright` 要成功（关键）。若失败＝venv 还没装 Playwright → `~/.octop/venv/bin/pip install playwright`，并视情况 `playwright install chromium`。
- `octop` CLI 要在。`octop plugin list` 此刻还没有 `browser-lightpanda`（正常，第 3 步才安装）。

> ⚠️ `octop plugin list` 显示的 `[not loaded]` 只是 **CLI 自己那个进程的视角**，**不代表真正在跑的 server** 到底加载没有。**别被它误导。** 真正的依据是第 5 步 `octop plugin reload` 是否回 `Reloaded N`、`octop agent reload <ID>` 是否回 `ok`。

---

## 2. 安装 Lightpanda 二进制

一行安装（拉官方 `lightpanda-x86_64-linux` 二进制，默认落到 `~/.local/bin/lightpanda`）：

```bash
curl -fsSL https://pkg.lightpanda.io/install.sh | bash
```

装完**立即核对版本**（要印出一个版本号，例如 `1.1.0-nightly.10552+dd2cd5d7f`，而不是报错）：

```bash
ls -l ~/.local/bin/lightpanda      # 确认二进制确实在这里
~/.local/bin/lightpanda version      # 例：1.1.0-nightly.10552+dd2cd5d7f
```

**备选装法**（curl 不通时）：

- **Docker 镜像**：`docker pull` 官方镜像，再 `docker run ... lightpanda version`（适合不想落地本机的场景）。
- **手动下载**：到官方 GitHub Releases 取对应 `lightpanda-x86_64-linux`，`chmod +x` 后放进 `~/.local/bin/lightpanda`。

**常见坑：**

- `cannot execute: required file not found` → 多半是 musl／Alpine。换 glibc 系，或走 Docker。
- `lightpanda: command not found` → `~/.local/bin` 不在 PATH；改用绝对路径，或把它加进 PATH。
- 装完 `version` 仍报错 → 重跑安装、确认拉到的是 `x86_64-linux` 构建（别拿到 arm 包）。

---

## 3. 安装插件（复制本仓库的 plugin/）

Octop 插件就是 `~/.octop/plugins/<id>/` 下的一个目录，内含两份文件：

- **`plugin.yaml`**（清单）：`id / version / name / description / icon / kind: tool / entry: main.py`。
- **`main.py`**（本体，605 行）：每个工具都是 **`async def`**（docstring 即给模型看的描述、参数带默认值）；底部 `def setup(ctx)` 用 `ctx.tool("名字", 函数, description=...)` 逐个挂载；配置走 `get_tool_config`（个人层 > 全局 env 分层）。

**安装动作**＝把本仓库 `plugin/` 下的两份文件复制到 `~/.octop/plugins/browser-lightpanda/`：

```bash
# 若你已 clone 本仓库（<repo> 为仓库路径）
mkdir -p ~/.octop/plugins/browser-lightpanda
cp <repo>/plugin/plugin.yaml ~/.octop/plugins/browser-lightpanda/
cp <repo>/plugin/main.py     ~/.octop/plugins/browser-lightpanda/

# 确认落地
ls -l ~/.octop/plugins/browser-lightpanda/
~/.octop/venv/bin/python -m py_compile ~/.octop/plugins/browser-lightpanda/main.py && echo "SYNTAX OK"
```

> 没有 clone 的话，直接用 GitHub 页面把 `plugin/plugin.yaml` 与 `plugin/main.py` 另存到上述目录即可（**整段原样存**，别漏行）。

**`main.py` 结构速览**（看懂、日后改码用，不用背）：

- **顶部常量**：`DEFAULT_BIN`（二进制路径，默认取 `Path.home()/".local/bin/lightpanda"`）、`BASE_DIR / SESSIONS_DIR / OUT_DIR`（会话状态、产物输出目录）。
- **配置层**：`get_tool_config`（个人层 > 全局 env）决定 `bin_path`、首选／回退引擎；`_telemetry_env()` 默认关遥测。
- **会话／状态**：每个 session 独立目录，持久化 cookie／登录态（`serve.json`、`page.json`），跨调用复用。
- **CDP 核心**：`_start_serve()` 幂等启动 `lightpanda serve --port N` → 解析 ws（`_cdp_ws()`）→ Playwright `connect_over_cdp(ws)` → 运行 page 动作（goto／click／type／screenshot…）。
- **引擎路由**：`_engine_order(force_engine)` 依序回传 `[首选, 回退]`；`force_engine` 可指定单一引擎。
- **★ 关键健壮性（第 8 节两个 bug 的修复都活在这段）**：`_is_blank_target(pg)` 判定空白／STARTUP target；`_get_or_create_page()` 跨调用重用**只比对廉价的 `pg.url`（刻意不碰 `page.title()`）、外层包 `try` 兜底**，任何异常都退回「新建真实 target」，绝不死等复用。
- **8 个对外工具**（`lp_status / lp_fetch / lp_navigate / lp_click / lp_type / lp_dom / lp_screenshot / lp_close`）＋ 底部 `setup(ctx)` 注册段。

---

## 4. 写全局路由规则（~/.octop/env）

要让这套引擎路由**对整台 Octop 实例的所有 Agent／用户生效、重启不丢**，就写进全局环境档 `~/.octop/env`（个别用户仍可通过 per-tool config 覆盖，属分层结构）。

把下面 4 行 **追加**进去 —— **别整档覆盖**（别把已有的其他行，例如既有的 `OCTOP_PRINTER_NAME=<打印机名>` 给冲掉）：

```bash
# 追加到 ~/.octop/env（保留既有行）
OCTOP_BROWSER_PREFERRED=lightpanda      # 首选引擎
OCTOP_BROWSER_FALLBACK=chrome           # 失败时自动回退（= 现有 Playwright Chromium / browser_use）
OCTOP_LIGHTPANDA_BIN=~/.local/bin/lightpanda   # ← 按本机实际绝对路径填
LIGHTPANDA_DISABLE_TELEMETRY=true       # 关闭遥测
```

**要点：**

- **`OCTOP_LIGHTPANDA_BIN` 一定要填该设备上 Lightpanda 二进制的真实绝对路径**（例如 `~/.local/bin/lightpanda` 或展开后的完整路径）。填错＝找不到二进制。
- 四行语意：首选 lightpanda、回退 chrome、指定二进制路径、关闭遥测。
- 写完 `cat ~/.octop/env` 核对这 4 行都在、且原有行没被删。

---

## 5. 重载进运行时

插件躺在磁盘上还不够，要让 *真正在跑的 server* 捡到它、并把那几个 `lp_*` 工具注入你的 Agent，需跑两步重载：

```bash
# [1/2] 重新扫描磁盘上的所有插件 → 捡到刚安装的 browser-lightpanda
octop plugin reload
# 预期输出：Reloaded N plugin(s)   （N ≥ 1）

# [2/2] 重载你的 Agent，把 lp_* 工具注入它的工具清单
octop agent reload <你的AGENT_ID>
# 预期输出：ok
```

- `<你的AGENT_ID>` 换成你在该实例里的 Agent 识别码（`octop agent list` 可查）。
- 两步都成功（`Reloaded N` ＋ `ok`）→ `lp_*` 就进你的工具清单了。
- 再次提醒：`plugin list` 里的 `[not loaded]` 是 **CLI 自身进程**的视角，别当成 server 状态；以上面两步的返回值为准。

---

## 6. 端到端验证（scripts/lightpanda-verify-all.py）

装完＋重载后，跑一次本仓库的验证脚本。它会**直接 import 插件的 `main.py`、裸调那些 async 工具函数**（证明引擎确实活着、不依赖 octop 是否已注入），逐项覆盖：

**status → Lightpanda（fetch·navigate·screenshot·close）→ Chrome 回退（fetch·navigate·close）→ 跨调用（navigate 后第二条独立连接 screenshot）**

每步印 ✅／❌ 并附证据（http 状态、title、PNG magic、markdown 长度、交叉核对）；全过＝**✅ 通过 N 项 · ❌ 失败 0 项 / 🎉 全绿**、exit 0。

```bash
# 建议先把路径指到本机实际值（脚本支持这两个环境变量）
export OCTOP_LIGHTPANDA_BIN=~/.local/bin/lightpanda
export LP_PLUGIN_DIR=~/.octop/plugins/browser-lightpanda

python3 <repo>/scripts/lightpanda-verify-all.py /tmp/verify-out
# 预期末行：✅ 通过 18 项 · ❌ 失败 0 项 … 🎉 全绿！… 且 exit 0
```

**参考输出（实测通过，供对照）：**

```text
[load] 插件模块加载自 .../browser-lightpanda (3.1s) · 预算=100s
  ✅ [ 3.1s] T1 lp_status：配置正确 preferred=lightpanda / fallback=chrome / bin=~/.local/bin/lightpanda
  ✅ [ 4.2s] T2 lp_fetch(example.com,markdown)：engine=lightpanda / md 960B / 与直抓交叉核对同篇(共享10)
  ✅ [ 6.7s] T3 lp_navigate(example.com)：engine=lightpanda / http=200 / title='Example Domain'
  ✅ [ 7.3s] T4 lp_screenshot：engine=lightpanda / PNG 10583B / magic=89504e47
  ✅ [ 7.8s] T5 lp_close
  ✅ [ 9.7s] T6a lp_fetch(force=chrome)：engine=chrome / 952B
  ✅ [12.2s] T6b lp_navigate(campfire,force=chrome)：engine=chrome / title='Outdoor Odyssey Nomad Backpack' / http=200
  ✅ [13.8s] T7a lp_navigate(xcall) → T7b 第二条独立连接 screenshot 无卡死 → T7c close
═══════ 总判定 ═══════
  ✅ 通过 18 项 · ❌ 失败 0 项 · 总耗时 14.8s
  🎉 全绿！Lightpanda(首选) 与 Chrome(回退) 双引擎 + 跨调用 全部工作
[DONE] PASS · 18 项通过 · 总耗时 14.8s
```

看到「🎉 全绿！」＝Lightpanda（首选）与 Chrome（回退）双引擎＋跨调用，在你的设备上都工作、**可以使用了**。

> 为什么验证走「裸调函数」、不等 octop 注入？—— 它直接打到 Lightpanda／Playwright／CDP 这条真链，干净证明*引擎本身*工作，与「octop 有没有把工具塞进对话」解耦，是最有力的排障第一手。octop 侧可用性由第 5 步两步重载的返回值保证。

---

## 7. 用法速查（lp_* 工具）

装完重载后，8 个 `lp_*` 就在 Agent 的工具清单里；需要浏览器时直接调（**默认 lightpanda、失败自动切 chrome、遥测已关**）。它是**非常驻**的：闲置零占、用到才启动、用完主动收。

| 想做 | 工具 | 补充 |
|---|---|---|
| 开／导航到某页，保持会话 | `lp_navigate(url, session="default")` | 回最终 url／title／http ＋ 用的哪个引擎；供后续 click／type／screenshot 在同一 session 续操作 |
| 一键抓页（跑完 JS）→ 内容 | `lp_fetch(url, out="markdown"｜"html"｜"text"｜"pdf"｜"png")` | 无需常驻、最省；**markdown 喂 LLM 最干净** |
| 点页上某个元素 | `lp_click(selector, session=...)` | CSS 选择器；点后自动短暂等 DOM 稳定 |
| 往输入框写字 | `lp_type(selector, text, session=..., fill=False)` | `fill=True` 直接设值；`False` 逐字键入（触发 input／change 事件链） |
| 读页结构化内容 | `lp_dom(mode="html"｜"text"｜"markdown", session=...)` | **markdown 区分标题／列表／引用／代码／链接锚，喂 LLM 最佳** |
| 截屏存 PNG | `lp_screenshot(path="", full_page=False, session=...)` | `full_page=True` 滚动整页拼长图；`path` 留空自动以时间戳落地 |
| 关闭会话（并停后端 serve） | `lp_close(session="default")` | 释放 port／内存；一整轮任务后建议主动叫 |
| 看运行状态／配置 | `lp_status()` | 回二进制路径＋版本、首选／回退、遥测、目录；不实开浏览器、开销极小 |

- **会话（session）**：同一 session 的多通调用共享浏览上下文（cookie／登录态／当前页），方便串「开页 → 填表 → 点提交 → 截屏」；用完 `lp_close` 收掉。不同 session 互不影响。
- **引擎路由**：通常不用管 —— 默认 lightpanda 优先，某个操作在 Lightpanda 上搞不定会**自动回退 Chrome** 完成，结果里带 `engine_used`／`used_fallback` 标记。特殊场景可用 `force_engine="lightpanda"` 或 `"chrome"` 强制走某一边。

一句口诀：开网页／抓内容／截屏／交互 → `lp_navigate`、`lp_fetch`、`lp_screenshot`、`lp_dom`（默认 lightpanda），难缠站它会自动切 chrome；用完 `lp_close` 释放。

---

## 8. 调试手册（两个核心 bug ＋ 常见坑）

这段收录实际安装过程真正踩到的两个问题（症状 → 根因 → 修法 → 怎么核对修好），加上几项通用坑。核心特征：**`lp_navigate`（CDP 路）反复卡或爆错，而 `lp_fetch`（CLI 路）1 秒就回** —— 问题**不在二进制**，而在 **CDP 的 target／page 管理**。（这两个修复都已内置在 `plugin/main.py`，正常情况下你不必再改。）

### 8.1 Bug①：STARTUP target 不可导航（致命，必修）

- **症状**：`lp_navigate` 卡到逾时，或抛 `Protocol error (Page.navigate): No page on the STARTUP session; create a real target with Target.createTarget`。
- **根因**：`connect_over_cdp` 之后，Playwright 会挑一个*现成*的 page 出来；但 Lightpanda 刚启动时那个唯一的页面就是 **STARTUP** 占位页（about:blank）。`_get_or_create_page` 若走「复用既有 page」分支，很可能就拿这个 STARTUP 页去做 `goto` —— 而 STARTUP 不是一个能直接 navigate 的真 target → 卡死／报错。
- **修法（已内置）**：加 `_is_blank_target(pg)` 判定；`_get_or_create_page` 复用匹配时**若命中 blank／STARTUP → 跳过**，改走 `ctx.new_page()`（= `Target.createTarget`）建一个真正可导航的 target，再 goto。
- **怎么核对修好**：跑 `scripts/lightpanda-verify-all.py`，**T3 lp_navigate 要 ✅ 且 http=200**（参考机 1.9s 通过）。若仍卡／爆 → 这段没修上。

### 8.2 Bug②：跨调用在「第二条独立 CDP 连接」下卡死（加固，建议修）

- **症状**：同一 session 的**第二次**独立 `lp_*` 调用（例如 `lp_navigate` 之后单独再调 `lp_screenshot`）卡住、>72s 没反应。
- **根因**：`connect_over_cdp` 本身不慢（~0.03s）、serve 也能正确复用；真正卡住的是「连上之后、去**枚举／探测既有打开中的 page**、逐页读 url／title 那段」—— 尤其 `page.title()` 这种较贵的 CDP 查找，在*第二条独立连接*上下文里最容易挂住（第一条通常没事）。简言之：**连得上、但「读既有页状态」会卡。**
- **修法（已内置）**：复用匹配改成**只比对廉价的 `pg.url`（刻意不调 `page.title()`）**；整段再包一层 `try` —— 任何异常就**优雅退回新建一个真 target**，绝不死等。
- **怎么核对修好**：`scripts/lightpanda-verify-all.py` 的 **T7（cross-call）navigate → screenshot** 要 ✅ 且**不卡**（参考机 T7 全程 ~2.2s）。T7b screenshot 若长时间不回 → 这段还没修。

### 8.3 其他常见坑

- **残留 `lightpanda serve` 进程**：多轮测试／中断后常留一堆 serve（各占一个 port）。排障前先清：`pkill -f "lightpanda serve"`，再用 `pgrep -af "lightpanda serve"` 确认清干净。
- **`pkill -f` 自比陷阱**：若你当前 shell 命令行**本身也含** `"lightpanda serve"` 字符串（例如在 grep／echo 里打了这串），`pkill -f` 有可能把你自己那条 shell 也匹配进去、把自己 SIGTERM 掉（exit −15）。稳做法：`pgrep -f "lightpanda serve"` 列出 pid，**剔除自身 pid（`$$`）再 kill**。
- **120 秒工具硬上限**：execute／工具侧常有 ≈**120 秒**上限。一整轮塞太多引擎案例（fetch＋navigate＋screenshot × 多站）累加超过就会被杀（exit 124）—— **未必是卡死**，可能只是总量撞线。**对策**：分步跑（每次一小段）、或把预算调大（`LP_BUDGET=180`）、非必要环节拆开。
- **冷 V8 JIT／首次偏慢**：Lightpanda 用 V8，**首次**跑某类页面或刚启动 serve 可能稍慢（JIT 未热身）；同条件下后续会快。遇「首次慢、之后顺」属正常，别慌。
- **别把特定站点文案写死进断言**：验证脚本的 T2 fetch 用 example.com，断言靠 `engine + 非空 + 直抓交叉核对`，而非写死某句标题文本。换站时照此 —— **断结构、长度、交叉核对**，别断具体标点。
- **网络／DNS 抖动**：某些时段导航／抓取变慢甚至逾时，多数**重试一次即好**；持续再查 DNS、代理，或换站测试。
- **port 冲突**：`_start_serve` 会挑 free port 启动 serve；极端情况可能撞占用。一般幂等逻辑自避；若撞 → 清残留 serve 再试。

---

## 9. 回滚／升级

- **回滚（不用了）**：删 `~/.octop/plugins/browser-lightpanda/` 整个目录 → `octop plugin reload` ＋ `octop agent reload <ID>`（让它从运行时消失）→ 可选删二进制 `rm ~/.local/bin/lightpanda` → 可选清掉 `~/.octop/env` 那 4 行。
- **升级 Lightpanda 二进制**：重跑安装／换新版覆盖 `~/.local/bin/lightpanda` → `~/.local/bin/lightpanda version` 核对新版号 → 再跑一次 `scripts/lightpanda-verify-all.py` 确认仍全绿。**插件 `main.py` 不用动**（它指向 `OCTOP_LIGHTPANDA_BIN` 所指的二进制）。
- **改了插件代码后**：务必 `octop plugin reload` ＋ `octop agent reload`（代码变更不会自动热更）。

---

## 附录 A：文件与路径速查

| 项目 | 路径／值 | 说明 |
|---|---|---|
| Lightpanda 二进制 | `~/.local/bin/lightpanda` | `lightpanda version` 查版本 |
| 插件目录 | `~/.octop/plugins/browser-lightpanda/` | Octop 插件根 |
| 插件清单 | `~/.octop/plugins/browser-lightpanda/plugin.yaml` | 7 行元数据 |
| 插件本体 | `~/.octop/plugins/browser-lightpanda/main.py` | 605 行、8 个 `lp_*` 工具 |
| 全局路由 env | `~/.octop/env` | 4 行：`OCTOP_BROWSER_PREFERRED／FALLBACK／LIGHTPANDA_BIN`、`LIGHTPANDA_DISABLE_TELEMETRY` |
| 会话状态 | `~/.octop/browser-lightpanda/sessions/<session>/` | `serve.json`／`page.json`（cookie、登录态） |
| 产物输出 | `~/.octop/browser-lightpanda/out/` | 截屏、PDF 等 |
| 本指引 | 本仓库 `README.md`（＋ `README.zh-CN.md`／`README.en.md`） | 你正在看的这份 |
| 验证脚本 | 本仓库 `scripts/lightpanda-verify-all.py` | 第 6 步的一条龙全绿脚本 |
| 插件源码 | 本仓库 `plugin/plugin.yaml`、`plugin/main.py` | 第 3 步要落地的两份档 |

## 附录 B：最小冒烟（一行命令）

不想一上来就跑全套？先这一条确认 Lightpanda 二进制本体能跑：

```bash
~/.local/bin/lightpanda version && echo "Lightpanda binary OK"
```

打出版本号 ＋ echo 一行 OK ＝ 二进制没坏。要进一步确认整套插件、双引擎、跨调用，再跑第 6 步的 `scripts/lightpanda-verify-all.py`。

---

## 授权与致谢

- **Lightpanda** 本体为 **AGPL-3.0**（见其官方仓库）。本指引与插件代码仅为接入用途；若要把二进制随产品分发给第三方，请自行评估 AGPL 的传染性条款。
- 本仓库的插件代码（`plugin/`、`scripts/`）可自由取用于你的 Octop 实例。
