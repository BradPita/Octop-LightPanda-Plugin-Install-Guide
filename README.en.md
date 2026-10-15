# Lightpanda Browser Plugin · Octop Install Guide

[繁體中文](README.md) ｜ [简体中文](README.zh-CN.md) ｜ **English**

> **Who is this for?** For an **Agent running on an Octop host** (or anyone installing manually). The user will typically just say *"follow this guide and install Lightpanda"* — work through it step by step.
> **Fastest path**: hand this repo to an Agent and let it run the steps; when step 6 prints "🎉 all green", you're done.
> **TL;DR**: Lightpanda becomes an Octop plugin — the **preferred** browser engine, with **automatic fallback to Chrome**, **telemetry disabled**, running **side by side** with the existing Chromium.
> Verified on a Debian/Ubuntu-family x86_64 host (reference environment: Linux Mint 22.3, Oct 2026).

---

## Table of contents

- [0. Background: what Lightpanda is and what you get](#0-background-what-lightpanda-is-and-what-you-get)
- [1. Pre-flight checks](#1-pre-flight-checks)
- [2. Install the Lightpanda binary](#2-install-the-lightpanda-binary)
- [3. Install the plugin (copy `plugin/` from this repo)](#3-install-the-plugin-copy-plugin-from-this-repo)
- [4. Write the global routing rules (`~/.octop/env`)](#4-write-the-global-routing-rules-octopenv)
- [5. Reload into the runtime](#5-reload-into-the-runtime)
- [6. End-to-end verification (`scripts/lightpanda-verify-all.py`)](#6-end-to-end-verification-scriptslightpanda-verify-allpy)
- [7. Usage cheat-sheet (`lp_*` tools)](#7-usage-cheat-sheet-lp_-tools)
- [8. Troubleshooting (two core bugs + common pitfalls)](#8-troubleshooting-two-core-bugs--common-pitfalls)
- [9. Rollback / upgrade](#9-rollback--upgrade)
- [Appendix A: paths cheat-sheet](#appendix-a-paths-cheat-sheet)｜[Appendix B: one-line smoke test](#appendix-b-one-line-smoke-test)

### Files in this repo

| Path | Contents |
|---|---|
| `README.md` / `README.zh-CN.md` / `README.en.md` | This guide in Traditional Chinese / Simplified Chinese / English |
| `plugin/plugin.yaml` | Plugin manifest (7 lines) |
| `plugin/main.py` | The plugin itself (605 lines, exposes the 8 `lp_*` tools) |
| `scripts/lightpanda-verify-all.py` | One-shot end-to-end verification script |

> All Chinese text in this repo (including code comments) is **Traditional Chinese**. The Simplified and English guides link to the same source files rather than inlining them, so no single document mixes the two Chinese scripts.

---

## 0. Background: what Lightpanda is and what you get

**Lightpanda** is a *lightweight headless browser built for machines/AI*: written from scratch in **Zig**, running JavaScript on **V8**, doing **no graphical rendering**, and speaking **CDP (Chrome DevTools Protocol)** natively.

Octop's built-in `browser_use` tool is essentially *"Python Playwright driving Chromium over CDP"*. Lightpanda speaks CDP too — so it is a **natural fit**: the same CDP channel drives it, with no separate driver to write.

After installing, you get:

- A Lightpanda binary at `~/.local/bin/lightpanda` (`lightpanda version` reports the build).
- An Octop plugin `browser-lightpanda` exposing **8 `lp_*` tools** (open pages, fetch content / convert to Markdown, click, type, read the DOM, screenshot, close sessions).
- A set of **global routing rules** (in `~/.octop/env`): **Lightpanda first, automatic fallback to Chrome on failure**.
- **Telemetry disabled** (`LIGHTPANDA_DISABLE_TELEMETRY=true`).
- **Old and new side by side**: the existing Playwright Chromium (`browser_use`) is kept untouched as the fallback — nothing is replaced.

In short: once installed, the Agent just calls `lp_*` when it needs a browser; Lightpanda handles it by default, Chrome takes over when Lightpanda can't, and the user never has to think about it.

---

## 1. Pre-flight checks

Lightpanda's official Linux build is linked against **glibc**; on Alpine/musl it fails with `cannot execute: required file not found`. So first confirm: Debian/Ubuntu family, `x86_64`, glibc present.

We also drive Lightpanda with **Playwright (Python) from the octop venv as the CDP client**, so confirm `~/.octop/` exists and that venv has Playwright installed.

Run this **read-only health check** first (it changes nothing):

```bash
# 1) OS and architecture (needs Linux / x86_64; note the base distro — not Alpine/musl)
cat /etc/os-release | grep -E '^(NAME|VERSION)='
uname -m                      # should be x86_64
ldd --version 2>&1 | head -1  # glibc output expected

# 2) Is the octop runtime and its venv python present?
echo "HOME=$HOME"
ls -d ~/.octop
ls ~/.octop/venv/bin/python

# 3) Does that venv have Playwright? (the CDP client depends on it)
~/.octop/venv/bin/python -c "import playwright, playwright.sync_api as s; print('playwright OK')"

# 4) Is the octop CLI available, and which plugins exist? (browser-lightpanda should NOT be there yet)
which octop
octop plugin list
```

**How to read the results:**

- `uname -m` must be `x86_64`; `/etc/os-release` should be a mainstream distro (Linux Mint / Ubuntu / Debian). **On Alpine/musl → use a glibc distro, or go the Docker route.**
- `~/.octop/` must exist; `~/.octop/venv/bin/python` must exist.
- The `import playwright` line must succeed (critical). If it fails, install it: `~/.octop/venv/bin/pip install playwright` (and run `playwright install chromium` if needed).
- The `octop` CLI must be on PATH. `octop plugin list` will not show `browser-lightpanda` yet — that's expected (it's created in step 3).

> ⚠️ The `[not loaded]` marker shown by `octop plugin list` reflects **the CLI process's own view only** — it does **not** tell you whether the *running server* loaded the plugin. **Don't be misled by it.** The real signals are `octop plugin reload` returning `Reloaded N` and `octop agent reload <ID>` returning `ok` (step 5).

---

## 2. Install the Lightpanda binary

One-liner (pulls the official `lightpanda-x86_64-linux` binary; by default it lands in `~/.local/bin/lightpanda`):

```bash
curl -fsSL https://pkg.lightpanda.io/install.sh | bash
```

Then **verify the version immediately** (it should print a version string such as `1.1.0-nightly.10552+dd2cd5d7f`, not an error):

```bash
ls -l ~/.local/bin/lightpanda      # confirm the binary is there
~/.local/bin/lightpanda version      # e.g. 1.1.0-nightly.10552+dd2cd5d7f
```

**Alternative installs** (if curl doesn't work):

- **Docker image**: pull the official image and run `docker run ... lightpanda version` (good if you don't want anything on the host).
- **Manual download**: grab `lightpanda-x86_64-linux` from the official GitHub Releases, `chmod +x` it, and put it at `~/.local/bin/lightpanda`.

**Common pitfalls:**

- `cannot execute: required file not found` → almost always musl/Alpine. Switch to a glibc distro or use Docker.
- `lightpanda: command not found` → `~/.local/bin` isn't on PATH; use the absolute path, or add it to PATH.
- `version` still fails after install → reinstall and make sure you fetched the `x86_64-linux` build (not an arm package).

---

## 3. Install the plugin (copy `plugin/` from this repo)

An Octop plugin is simply a directory under `~/.octop/plugins/<id>/` containing two files:

- **`plugin.yaml`** — the manifest: `id / version / name / description / icon / kind: tool / entry: main.py`.
- **`main.py`** — the implementation (605 lines): every tool is an **`async def`** (its docstring is the description the model sees; parameters carry defaults); at the bottom, `def setup(ctx)` registers each tool via `ctx.tool("name", fn, description=...)`; configuration is read with `get_tool_config` (per-user layer > global env layer).

**To install**, copy the two files from this repo's `plugin/` into `~/.octop/plugins/browser-lightpanda/`:

```bash
# Assuming you cloned this repo (<repo> = the repo path)
mkdir -p ~/.octop/plugins/browser-lightpanda
cp <repo>/plugin/plugin.yaml ~/.octop/plugins/browser-lightpanda/
cp <repo>/plugin/main.py     ~/.octop/plugins/browser-lightpanda/

# Confirm and syntax-check
ls -l ~/.octop/plugins/browser-lightpanda/
~/.octop/venv/bin/python -m py_compile ~/.octop/plugins/browser-lightpanda/main.py && echo "SYNTAX OK"
```

> No clone? Just use the GitHub web UI to save `plugin/plugin.yaml` and `plugin/main.py` into that directory (**copy them verbatim** — don't drop lines).

**`main.py` structure at a glance** (for understanding and future edits — no need to memorise):

- **Top-level constants**: `DEFAULT_BIN` (binary path, defaults to `Path.home()/".local/bin/lightpanda"`), `BASE_DIR / SESSIONS_DIR / OUT_DIR` (session state and artifact output).
- **Config layer**: `get_tool_config` (per-user > global env) decides `bin_path` and the preferred/fallback engines; `_telemetry_env()` disables telemetry by default.
- **Session/state**: each session gets its own directory; cookies/login state persist across calls (`serve.json`, `page.json`).
- **CDP core**: `_start_serve()` idempotently starts `lightpanda serve --port N` → resolves the websocket (`_cdp_ws()`) → Playwright `connect_over_cdp(ws)` → runs page actions (goto/click/type/screenshot…).
- **Engine routing**: `_engine_order(force_engine)` returns `[preferred, fallback]`; `force_engine` pins a single engine.
- **★ Key robustness (both bug fixes from section 8 live here)**: `_is_blank_target(pg)` detects blank/STARTUP targets; `_get_or_create_page()` matches reused pages on the cheap `pg.url` only (**deliberately avoiding `page.title()`**) and wraps everything in `try`, falling back to creating a fresh real target instead of ever blocking.
- **The 8 public tools** (`lp_status / lp_fetch / lp_navigate / lp_click / lp_type / lp_dom / lp_screenshot / lp_close`) plus the `setup(ctx)` registration block at the bottom.

---

## 4. Write the global routing rules (`~/.octop/env`)

To make this engine routing apply to **every Agent/user on the Octop instance and survive restarts**, write it into the global env file `~/.octop/env` (per-tool config can still override it — that's the layering).

**Append** these 4 lines — **do not overwrite the file** (don't clobber existing lines such as an existing `OCTOP_PRINTER_NAME=<printer>`):

```bash
# Append to ~/.octop/env (keep existing lines)
OCTOP_BROWSER_PREFERRED=lightpanda      # preferred engine
OCTOP_BROWSER_FALLBACK=chrome           # automatic fallback (= existing Playwright Chromium / browser_use)
OCTOP_LIGHTPANDA_BIN=~/.local/bin/lightpanda   # ← use the real absolute path on this host
LIGHTPANDA_DISABLE_TELEMETRY=true       # disable telemetry
```

**Key points:**

- **`OCTOP_LIGHTPANDA_BIN` must be the real absolute path** to the Lightpanda binary on this host (e.g. `~/.local/bin/lightpanda`, expanded). A wrong path means "binary not found".
- The four lines mean: prefer lightpanda, fall back to chrome, point at the binary, disable telemetry.
- Afterwards, `cat ~/.octop/env` to confirm all four lines are present and nothing was lost.

---

## 5. Reload into the runtime

Having the plugin on disk is not enough — the *running server* must pick it up, and the `lp_*` tools must be injected into your Agent. Two reload steps:

```bash
# [1/2] Re-scan plugins on disk → picks up the newly installed browser-lightpanda
octop plugin reload
# Expected: Reloaded N plugin(s)   (N >= 1)

# [2/2] Reload your Agent so the lp_* tools are injected into its toolset
octop agent reload <YOUR_AGENT_ID>
# Expected: ok
```

- Replace `<YOUR_AGENT_ID>` with your Agent's identifier on this instance (see `octop agent list`).
- Both succeeding (`Reloaded N` + `ok`) means `lp_*` is now in your toolset.
- Reminder: `[not loaded]` in `plugin list` is the **CLI process's** view, not the server's. Trust the two commands above.

---

## 6. End-to-end verification (`scripts/lightpanda-verify-all.py`)

After installing and reloading, run this repo's verification script. It **imports the plugin's `main.py` directly and bare-invokes the async tool functions** (proving the engine really works, independent of whether octop injected the tools), covering in order:

**status → Lightpanda (fetch·navigate·screenshot·close) → Chrome fallback (fetch·navigate·close) → cross-call (navigate, then screenshot over a second independent connection)**

Each step prints ✅/❌ with evidence (HTTP status, title, PNG magic bytes, Markdown length, cross-check against a direct fetch). All passing means **✅ N passed · ❌ 0 failed / 🎉 all green** and exit 0.

```bash
# Point the script at this host's real paths (it honours these two env vars)
export OCTOP_LIGHTPANDA_BIN=~/.local/bin/lightpanda
export LP_PLUGIN_DIR=~/.octop/plugins/browser-lightpanda

python3 <repo>/scripts/lightpanda-verify-all.py /tmp/verify-out
# Expected last line: ✅ 18 passed · ❌ 0 failed … 🎉 all green … with exit 0
```

**Reference output (real run, for comparison):**

```text
[load] plugin module loaded from .../browser-lightpanda (3.1s) · budget=100s
  ✅ [ 3.1s] T1 lp_status: config OK  preferred=lightpanda / fallback=chrome / bin=~/.local/bin/lightpanda
  ✅ [ 4.2s] T2 lp_fetch(example.com,markdown): engine=lightpanda / md 960B / cross-checked vs direct fetch
  ✅ [ 6.7s] T3 lp_navigate(example.com): engine=lightpanda / http=200 / title='Example Domain'
  ✅ [ 7.3s] T4 lp_screenshot: engine=lightpanda / PNG 10583B / magic=89504e47
  ✅ [ 7.8s] T5 lp_close
  ✅ [ 9.7s] T6a lp_fetch(force=chrome): engine=chrome / 952B
  ✅ [12.2s] T6b lp_navigate(campfire,force=chrome): engine=chrome / title='Outdoor Odyssey Nomad Backpack' / http=200
  ✅ [13.8s] T7a lp_navigate(xcall) → T7b second connection screenshot (no hang) → T7c close
═══════ verdict ═══════
  ✅ 18 passed · ❌ 0 failed · total 14.8s
  🎉 all green! both engines (Lightpanda preferred + Chrome fallback) and cross-call work
[DONE] PASS · 18 checks · total 14.8s
```

Seeing "🎉 all green!" means both engines (Lightpanda preferred, Chrome fallback) and cross-call all work on your host — **you're ready to use it**.

> Why does verification "bare-invoke functions" instead of waiting for octop injection? Because that hits the real Lightpanda/Playwright/CDP chain directly and cleanly proves *the engine itself* works, decoupled from "did octop put the tools in the conversation". Availability on the octop side is guaranteed by the two reload commands in step 5.

---

## 7. Usage cheat-sheet (`lp_*` tools)

After reloading, the 8 `lp_*` tools are in the Agent's toolset; call them whenever a browser is needed (**lightpanda by default, automatic Chrome fallback, telemetry off**). It is **non-resident**: zero usage when idle, starts on demand, and is closed on request.

| Goal | Tool | Notes |
|---|---|---|
| Open/navigate to a page, keep the session | `lp_navigate(url, session="default")` | Returns final url/title/http + which engine; later click/type/screenshot calls continue in the same session |
| One-shot fetch (runs JS) → content | `lp_fetch(url, out="markdown"｜"html"｜"text"｜"pdf"｜"png")` | No resident process, cheapest; **markdown is the cleanest input for an LLM** |
| Click an element | `lp_click(selector, session=...)` | CSS selector; briefly waits for the DOM to settle |
| Type into a field | `lp_type(selector, text, session=..., fill=False)` | `fill=True` sets the value directly; `False` types character by character (fires input/change) |
| Read structured page content | `lp_dom(mode="html"｜"text"｜"markdown", session=...)` | **markdown preserves headings/lists/quotes/code/links — best for LLMs** |
| Screenshot to PNG | `lp_screenshot(path="", full_page=False, session=...)` | `full_page=True` scrolls and stitches a long image; empty `path` auto-names with a timestamp |
| Close session (and stop its serve) | `lp_close(session="default")` | Frees the port/memory; worth calling after a full task |
| Inspect status/config | `lp_status()` | Returns binary path+version, preferred/fallback engines, telemetry, dirs; opens no browser, very cheap |

- **Sessions**: calls sharing a session share browsing context (cookies/login/current page), which makes "open → fill → submit → screenshot" chains easy; call `lp_close` when done. Different sessions are independent.
- **Engine routing**: usually nothing to do — lightpanda is preferred, and anything it can't handle is **automatically retried on Chrome**, with `engine_used`/`used_fallback` in the result. For special cases, `force_engine="lightpanda"` or `"chrome"` pins one side.

Rule of thumb: open/fetch/screenshot/interact → `lp_navigate`, `lp_fetch`, `lp_screenshot`, `lp_dom` (lightpanda by default); awkward sites get switched to Chrome automatically; call `lp_close` when finished.

---

## 8. Troubleshooting (two core bugs + common pitfalls)

These are the two real problems encountered during installation (symptom → root cause → fix → how to verify), plus general pitfalls. The signature: **`lp_navigate` (the CDP path) hangs or throws repeatedly, while `lp_fetch` (the CLI path) returns in ~1s** — so the problem is **not the binary**, but **CDP target/page management**. (Both fixes are already built into `plugin/main.py`; normally you won't need to change anything.)

### 8.1 Bug ①: the STARTUP target is not navigable (critical — must fix)

- **Symptom**: `lp_navigate` hangs until timeout, or throws `Protocol error (Page.navigate): No page on the STARTUP session; create a real target with Target.createTarget`.
- **Root cause**: after `connect_over_cdp`, Playwright picks an *existing* page — and the only page right after Lightpanda starts is the **STARTUP** placeholder (`about:blank`). If `_get_or_create_page` takes the "reuse an existing page" branch, it can hand that STARTUP page to `goto` — and STARTUP is not a real target you can navigate → hang/error.
- **Fix (built in)**: add the `_is_blank_target(pg)` check; when reuse matching hits a blank/STARTUP target, **skip it** and instead create a real navigable target via `ctx.new_page()` (= `Target.createTarget`) before calling `goto`.
- **How to confirm**: run `scripts/lightpanda-verify-all.py`; **T3 lp_navigate must be ✅ with http=200** (reference host: passed in 1.9s). Still hanging/throwing → the fix isn't in place.

### 8.2 Bug ②: cross-call hang on the "second independent CDP connection"

- **Symptom**: the **second** independent `lp_*` call in the same session (e.g. `lp_screenshot` right after `lp_navigate`) hangs for >72s.
- **Root cause**: `connect_over_cdp` itself is fast (~0.03s) and the serve is reused correctly; what actually stalls is **enumerating/inspecting the already-open pages after connecting, reading url/title per page** — `page.title()` in particular is an expensive CDP query that is most likely to hang in the *second independent connection* context (the first connection is usually fine). In short: **connecting is fine; querying existing page state is what blocks.**
- **Fix (built in)**: match reused pages on the cheap `pg.url` only (**never call `page.title()`**), and wrap the whole block in `try` — any exception gracefully falls back to creating a fresh real target, never blocking.
- **How to confirm**: in `scripts/lightpanda-verify-all.py`, **T7 (cross-call) navigate → screenshot** must be ✅ and must not stall (reference host: T7 completes in ~2.2s). If T7b screenshot never returns, the fix isn't in place.

### 8.3 Other common pitfalls

- **Leftover `lightpanda serve` processes**: repeated test runs/aborts leave several serves around (each holding a port). Clean up first: `pkill -f "lightpanda serve"`, then confirm with `pgrep -af "lightpanda serve"`.
- **The `pkill -f` self-match trap**: if your current shell command line itself contains the string `"lightpanda serve"` (e.g. you typed it inside a grep/echo), `pkill -f` may match your own shell and SIGTERM it (exit -15). Safer: list pids with `pgrep -f "lightpanda serve"`, **drop your own pid (`$$`)**, then kill.
- **~120s tool limit**: `execute`/tools often have a hard limit around **120 seconds**. A single round with too many engine cases (fetch + navigate + screenshot across several sites) can exceed it and get killed (exit 124) — **that is not necessarily a hang**, just cumulative time. **Mitigation**: run in smaller steps, raise the budget (`LP_BUDGET=180`), or split non-essential parts.
- **Cold V8 JIT / slow first run**: Lightpanda runs on V8, so the **first** run of a page type or a freshly started serve may be slower (JIT not warmed up); the same case gets faster afterwards. "Slow first, fast after" is normal — don't panic.
- **Don't hard-code a site's copy into assertions**: the verify script's T2 fetches example.com and asserts on `engine + non-empty + cross-check against a direct fetch`, not on a specific sentence. When switching sites, do the same — **assert structure, length, cross-checks**, not exact punctuation.
- **Network/DNS jitter**: at some times navigation/fetching gets slow or times out; usually **a single retry fixes it**. If it persists, check DNS/proxy, or try another site.
- **Port conflicts**: `_start_serve` picks a free port, but extreme cases can collide. The idempotent logic usually avoids it; if it happens, clear leftover serves and retry.

---

## 9. Rollback / upgrade

- **Rollback (no longer needed)**: delete the directory `~/.octop/plugins/browser-lightpanda/` → `octop plugin reload` + `octop agent reload <ID>` (removes it from the runtime) → optionally `rm ~/.local/bin/lightpanda` → optionally remove those 4 lines from `~/.octop/env`.
- **Upgrade the Lightpanda binary**: re-run the installer / drop a newer build over `~/.local/bin/lightpanda` → check `~/.local/bin/lightpanda version` → re-run `scripts/lightpanda-verify-all.py` to confirm it's still all green. **`main.py` needs no changes** (it points at whatever binary `OCTOP_LIGHTPANDA_BIN` names).
- **After changing plugin code**: always `octop plugin reload` + `octop agent reload` (code changes are not hot-reloaded).

---

## Appendix A: paths cheat-sheet

| Item | Path / value | Notes |
|---|---|---|
| Lightpanda binary | `~/.local/bin/lightpanda` | `lightpanda version` reports the build |
| Plugin directory | `~/.octop/plugins/browser-lightpanda/` | Octop plugin root |
| Plugin manifest | `~/.octop/plugins/browser-lightpanda/plugin.yaml` | 7 lines of metadata |
| Plugin implementation | `~/.octop/plugins/browser-lightpanda/main.py` | 605 lines, the 8 `lp_*` tools |
| Global routing env | `~/.octop/env` | 4 lines: `OCTOP_BROWSER_PREFERRED/FALLBACK/LIGHTPANDA_BIN`, `LIGHTPANDA_DISABLE_TELEMETRY` |
| Session state | `~/.octop/browser-lightpanda/sessions/<session>/` | `serve.json` / `page.json` (cookies, login state) |
| Artifact output | `~/.octop/browser-lightpanda/out/` | screenshots, PDFs, etc. |
| This guide | this repo's `README.md` (+ `README.zh-CN.md` / `README.en.md`) | the file you're reading |
| Verification script | this repo's `scripts/lightpanda-verify-all.py` | the one-shot all-green script from step 6 |
| Plugin source | this repo's `plugin/plugin.yaml`, `plugin/main.py` | the two files you deploy in step 3 |

## Appendix B: one-line smoke test

Not ready for the full suite? Confirm the binary itself runs:

```bash
~/.local/bin/lightpanda version && echo "Lightpanda binary OK"
```

A version string plus `Lightpanda binary OK` means the binary is fine. To confirm the whole plugin (both engines + cross-call), run `scripts/lightpanda-verify-all.py` from step 6.

---

## License & credits

- **Lightpanda** itself is **AGPL-3.0** (see its upstream repository). This guide and plugin code exist for integration purposes; if you distribute the binary to third parties as part of a product, evaluate AGPL's copyleft obligations yourself.
- The plugin code in this repo (`plugin/`, `scripts/`) is free to use in your own Octop instance.
