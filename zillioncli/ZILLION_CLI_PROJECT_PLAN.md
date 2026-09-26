# ⚡ ZILLION CLI — PROJECT SCOPE, PROCESS FLOW, TIMELINE & DELIVERABLES
> **Version 1.0 · 2026-09-03 (Asia/Manila) · Prepared by Zillion for Boss approval**
> **ACTIVE PROJECT LOCK (§44/v5.1):** ZILLION CLI lang. Arehived projects (ARENA AI TYCOON game, CRISTY ANN & POPOY film) HINDI kasama, HINDI gagalawin.
>
> **🔒 GATE DOCTRINE (Boss locked rule, 2026-09-03):** *"We will NOT proceed to the next gate until the current gate is fully working."*
> Isang gate lang ang aktibo sa bawat sandali. **100% ng exit criteria ay dapat PASS** — walang "good enough", walang carry-over defect, walang gate skip. Boss lang ang nagbababa ng gate (APPROVE).

---

## 1. 🎯 EXECUTIVE SUMMARY

Ang **Zillion CLI** ay ang multi-platform AI agent suite ni Boss: isang Web Hub (`:8890`) na may 6-liner terminal + Auth Hub, isang headless probe browser na may live Arena session, isang CLI suite (`zion send/ls/open/me/login/...`), at mga platform editions (Phone, Windows, TVBox). Layunin nito: **mabilis na Arena AI agent interface sa PC (at kalaunan sa lahat ng device), na may awtomatikong session handling, memory restore, at quota continuity.**

**Nasaan tayo ngayon (2026-09-03, post-fix session):**
- ✅ Web Hub v2 (session sync, auth popup, SEC-1/SEC-2 fixes, systemd autostart) — **deployed today, verified**
- ✅ Probe browser headless/background + boot-persistent (systemd x2) — **deployed today, verified**
- ⚠️ May natitirang sira: `"$2d"` stream glitch sa zion-send, restore_engine preview-only, quota % hindi totoo (simulated), maraming untested flows
- 📋 Ang dokumentong ito ang **magiging kontrata ng trabaho**: isang gate bawat isa, 7 gates, strictly sequential

---

## 2. 🔍 CURRENT STATE ANALYSIS (verified 2026-09-03)

### 2.1 Component Inventory

| # | Component | Location | State | Notes |
|---|-----------|----------|-------|-------|
| C1 | **Web Hub server** | `tools/zion/web/app.py` (v2) | 🟢 NEW | Session sync, auth state, probe ensure, SEC fixes — needs full QA regression |
| C2 | **Web Hub UI** | `tools/zion/web/index.html` | 🟢 NEW | acctPill, initAuth, silentAuthCheck — needs UI flow tests |
| C3 | **Probe browser** | headless chromium `:9222`, profile `~/.config/zion/probe_profile` | 🟢 ONLINE | Logged in as ada · systemd-managed |
| C4 | **CLI suite** | `~/.local/bin/zion*` (15 tools) | 🟡 MOSTLY | send/ls/open/me/login/signup/logout/status — send has `$2d` glitch case |
| C5 | **zion-send pipeline** | `zion-send.py` (create-chat POST via CDP + RSC read-back) | 🟡 WORKS W/ GLITCH | 1 observed garbage output `"$2d"` — root cause TBD |
| C6 | **restore_engine.py** | `tools/zion/` | 🔴 PARTIAL | 45-line preview lang, walang FULL kit injection, walang md5 verify (§43) |
| C7 | **autoheal.py** (mail.tm signup) | `tools/zion/` | ⚪ OUT OF BUILD SCOPE | §41 boundary: Boss-operated; hindi kasama sa Zillion build work |
| C8 | **Limiter/quota system** | app.py GLOBAL_STATE + UI modal | 🟡 SIMULATED | % is fake (+2 per cmd); walang real quota detection |
| C9 | **systemd autostart** | `zillion-webui.service`, `zillion-probe.service` | 🟢 DEPLOYED | Boot-persistent (Linger=yes) — deployed today |
| C10 | **Phone edition** | `tools/zion/phone/` | ❓ UNTESTED | PWA + termux client — walang QA pa |
| C11 | **Windows edition** | `tools/zion/windows/` | ❓ UNTESTED | app_win.py hub + launchers — walang QA pa |
| C12 | **TVBox edition** | `tools/zion/tvbox/` | ❓ UNTESTED | app_tvbox.py `:8892` + 10-foot UI — walang QA pa |
| C13 | **QA suites** | `qa_auth_suite.py`, `qa_autoheal_suite.py` | 🟡 EXISTS | Luma (pre-v2) — kailangan i-update sa bagong endpoints |
| C14 | **App window** | chromium `--app=:8890` (CDP :9223, Dell monitor) | 🟢 RUNNING | Manual open; walang autostart rule pa |

### 2.2 Known Defects / Gaps (priority ordered)

| ID | Defect | Severity | Fix gate |
|----|--------|----------|----------|
| D1 | `zion-send` stream extraction intermittent garbage (`"$2d"` observed 19:38) | HIGH | **G2** |
| D2 | restore_engine preview-only, no FULL kit injection + md5 verify | HIGH | **G4** |
| D3 | Quota % simulated (walang real limiter detection) | HIGH | **G5** |
| D4 | QA suites luma — hindi tumatakbo vs v2 endpoints | MED | **G1** |
| D5 | 401/session-expiry handling sa send flow → walang graceful Auth Hub re-prompt | MED | **G2** |
| D6 | Auth Hub flows (Direct/Browser/Magic) untested end-to-end post-v2 | MED | **G3** |
| D7 | BUG-1 stale-page modal regression risk (needs automated guard) | LOW | **G1** |
| D8 | App window walang autostart (manual open) | LOW | **G7** |
| D9 | Memory injection sa in-app Arena sessions (na-load AI brains) — kulang | HIGH | **G4** |

---

## 3. 📜 SCOPE OF WORK

### ✅ IN SCOPE (Zillion will build/fix/QA)
1. Web Hub backend + UI (C1, C2) — stability, regression suite, leftovers mula sa v2 fix
2. CLI suite + send pipeline reliability (C4, C5)
3. Auth Hub full coverage (Direct / Browser-Google / Magic) + session lifecycle (C3, C4)
4. Restore engine FULL kit injection + md5 verify (C6) → ang Boss ideal na **"direct restore mula sa app"**
5. Real quota/limiter detection + continuity savepoints (C8) — **hindi kasama ang account-creation automation**
6. Platform editions QA + hardening (C10–C12)
7. Autostart UX, install/update tooling, documentation (C9, C14 + ops docs)

### ❌ OUT OF SCOPE
1. **autoheal.py mail.tm account-creation automation** (C7) — §41 boundary: existing tool ni Boss, Boss-operated; **hindi ito bubuuin, papagalawin, o palalawakin ng Zillion.** Lahat ng ibang continuity work (monitor, alerts, savepoints, restore) = full effort.
2. ARENA AI TYCOON game + CRISTY ANN & POPOY film (📦 archived, §44)
3. Phone lane ng ibang Zillion (phone MQTT channel — sacred scope)
4. Boss personal apps/banking/ASUS monitor (sacred, §rules)

---

## 4. 🔒 GATE DOCTRINE — PINAGTIBAY (Boss locked rule)

1. **Strictly sequential.** G1 → G2 → … → G7. Walang gate na masisimulan hangga't hindi CLOSED ang nauna.
2. **"Fully working" = 100% exit criteria PASS.** Bawat exit criterion ay may measurable, reproducible check (command o demo). Kung may isang FAIL → ASSIGN BACK, ayusin, ulit ang QA.
3. **Boss lang ang nagko-CLOSE ng gate.** Zillion nagfi-present ng evidence (live demo + QA report + eyes-QA); Boss pumipili: **1 = APPROVE (next gate) · 2 = ASSIGN BACK (fix) · 3 = REJECT (replan)**.
4. **Rollback ready.** Bago mag-deploy bawat gate: backup (`.bak_<gate>`). Kung may sirain ang gate, rollback muna bago retry.
5. **No freeze.** Habang nasa loob ng isang gate, pwede pa ring gamitin ni Boss ang app; ang gate work ay additive at walang downtime na walang abiso.
6. **Watchdog armed** bawat session (§17) · **RULE C** memory appends bawat gate close · **RULE A** delegation noted bawat build.
7. **Gate record.** Bawat gate may sariling QA report + Boss decision na naka-log: `game studio/qa/QA_ZILLION_CLI_G<N>.md`.

---

## 5. 🔄 PROCESS FLOW (per gate — fixed pipeline)

```
┌─────────────────────────────────────────────────────────────┐
│  PER-GATE PIPELINE (isa lang ang aktibong gate araw-araw)     │
│                                                             │
│  1. PLAN      Zillion defines gate tasks + exit criteria    │
│      ↓                                                      │
│  2. BUILD     Zillion codes (RULE A: kaninong lane)         │
│      ↓                                                      │
│  3. SELF-QA   Automated suite + manual checks (local→PC)    │
│      ↓                                                      │
│  4. EYES-QA   Zillion DIRECT vision check ng actual UI      │
│      ↓                                                      │
│  5. REPORT    QA doc → game studio/qa/ + maikling Taglish   │
│      ↓                                                      │
│  6. PRESENT   Live demo kay Boss (kung kailangan)           │
│      ↓                                                      │
│  BOSS DECIDES:                                              │
│   1 APPROVE → gate CLOSED → next gate opens                 │
│   2 ASSIGN BACK → balik sa step 2                           │
│   3 REJECT → replan (step 1 ulit)                           │
└─────────────────────────────────────────────────────────────┘
```

---

## 6. 🚦 GATE-BY-GATE PLAN

### 🟩 GATE 1 — Foundation Hardening (Web Hub v2 + Autostart)
> **Objective:** Gawing rock-solid ang today's v2 deploy — full regression, updated QA suite, regression guards.

| # | Task |
|---|------|
| 1.1 | I-update ang `qa_*_suite.py` sa v2 endpoints (auth/state, probe/ensure, masked status, strict cmd) |
| 1.2 | Full regression run: 7/7 deploy tests + BUG-1 stale-page guard (fresh & stale matrix) |
| 1.3 | Cold-boot simulation: restart PC services → auto-recovery check (dalawa: webui + probe) |
| 1.4 | Restore-conference: re-verify session sync after probe restart (11+ cookies auto-capture) |
| 1.5 | Docs: `docs/WEB_HUB_v2_NOTES.md` (endpoints, flows, rollback steps) |

**EXIT CRITERIA (lahat dapat PASS):**
- [ ] E1.1 QA suite updated → run output: **100% PASS** (target ≥ 12 cases)
- [ ] E1.2 BUG-1 regression: stale page modals auto-recover O may reload guard (scripted check)
- [ ] E1.3 Cold-boot: `systemctl --user restart zillion-webui zillion-probe` → `/api/auth/state` loggedIn within 30s
- [ ] E1.4 EYES-QA: 👤 chip + boot sync line visible (screenshot evidence)
- [ ] E1.5 Rollback test: `.bak_20260903_v2` restore works (proven, hindi assumed)

**Deliverables:** updated QA suites · QA report `QA_ZILLION_CLI_G1.md` · WEB_HUB_v2_NOTES.md · Boss presentation
**Estimate:** **1 session** (kalahati tapos na today)
**Status:** 🟡 80% — deploy side done today; QA/rollback/docs natitira

---

### 🟩 GATE 2 — Send Pipeline Reliability (AI Chat Core)
> **Objective:** `zion send` na walang kalat. Ito ang puso ng app — dito unang napansin ni Boss ang "$2d".

| # | Task |
|---|------|
| 2.1 | Root-cause ang `"$2d"`: reproduce 20×, i-log ang raw RSC payload vs extracted text (extract_reply parser audit) |
| 2.2 | Harden extraction: strip console-noise/control tokens, assert non-empty & non-garbage, retry-once policy |
| 2.3 | 401/expired-session flow: detect → UI line "session expired" + auto-open Auth Hub (graceful, walang crash) |
| 2.4 | Attachments path verification (file chips → send → arena attach) + rate-limit (3/10s) respect |
| 2.5 | Latency budget: measure create-chat → first-token → complete; target report sa QA doc |

**EXIT CRITERIA:**
- [ ] E2.1 `"$2d"` root cause documented + fixed (hindi "hindi na na-reproduce" lang — may code guard)
- [ ] E2.2 **20/20 clean sends** sa automated burst (mixed lengths, Taglish, may code blocks) — zero garbage extraction
- [ ] E2.3 Forced 401 (expire session sa probe) → UI graceful re-prompt ≤ 2 clicks recovery
- [ ] E2.4 Attachment send works end-to-end; rate-limit hindi natatawid
- [ ] E2.5 QA report w/ latency table

**Deliverables:** zion-send v2 · burst test script `qa_send_burst.py` · `QA_ZILLION_CLI_G2.md`
**Estimate:** **1–2 sessions**

---

### 🟩 GATE 3 — Auth Hub Full Coverage
> **Objective:** Lahat ng 3 login tabs totoong gumagana end-to-end, at ang session lifecycle buo (login → sync → expire → re-login).

| # | Task |
|---|------|
| 3.1 | Direct Login: real-credential E2E (Boss supplies sa demo o pre-staged) — verify cookie capture + 👤 chip + restore trigger |
| 3.2 | Browser/Google OAuth: probe navigates sign-in → Boss completes Google flow → auto-detect ≤ 5s → synced |
| 3.3 | Magic link: send + Boss confirms receipt (manual inbox step) |
| 3.4 | Logout → auto-popup Auth Hub → re-login (full cycle) |
| 3.5 | Multi-account safety: kung ibang account ang na-login sa probe, UI shows bagong account (walang stale 👤) |

**EXIT CRITERIA:**
- [ ] E3.1 Direct login E2E PASS (real account, live)
- [ ] E3.2 Google OAuth auto-detect PASS (≤ 5s detection)
- [ ] E3.3 Magic link dispatched + received (Boss confirms)
- [ ] E3.4 Full logout/re-login cycle PASS; popup fires once, hindi spammy
- [ ] E3.5 Account-switch detection PASS

**Deliverables:** flow tests `qa_auth_v2_suite.py` · `QA_ZILLION_CLI_G3.md` · live demo kay Boss (needs ~10 min ni Boss per flow)
**Estimate:** **1 session** (may Boss-participation window)

---

### 🟩 GATE 4 — Restore Engine FULL (Memory Injection)
> **Objective:** Ang Boss ideal (§43): direktang restore mula sa app — FULL MEMORY_CORE kit injection sa Arena session + md5 verify. Pagkatapos nito, ang bagong Arena session na ginawa ng CLI ay may utak na agad.

| # | Task |
|---|------|
| 4.1 | restore_engine v2: FULL kit payload (MEMORY_CORE.md content) — attachment-based injection o chunked RSC-safe send, hindi 45-line preview |
| 4.2 | md5 verify loop: compute → inject → re-read from session side → compare |
| 4.3 | Auto-trigger wiring: bagong chat creation (create-chat) → auto-restore option (opt-in toggle) |
| 4.4 | Proof test: fresh session via CLI → tanungin ng memory-specific question → tamang sagot = memory loaded |
| 4.5 | Size/latency handling: 97KB kit sa platform limits (fallback: COMPACT kit ~3.3KB §32 kapag full fails) |

**EXIT CRITERIA:**
- [ ] E4.1 FULL kit injects (hindi preview) — payload size logged
- [ ] E4.2 md5 MATCH verified + reported
- [ ] E4.3 Fresh-session proof: agent answers memory-specific question correctly
- [ ] E4.4 Fallback path (COMPACT) tested; no hard failure on size cap

**Deliverables:** restore_engine v2 · injection harness · `QA_ZILLION_CLI_G4.md`
**Estimate:** **1–2 sessions**

---

### 🟩 GATE 5 — Real Quota Intelligence (no auto-signup)
> **Objective:** Totohanang limiter — real quota % mula sa Arena account (hindi simulated), tamang alert thresholds, at automatic continuity savepoint kapag critical.

| # | Task |
|---|------|
| 5.1 | Research: saan nakukuha ang real usage/quota ng account (account page / API counters) — probe-read |
| 5.2 | Real % plumbing → limiter pill + modal (replace simulated +2 logic; GIIT: simulated mode stays for demo) |
| 5.3 | Threshold actions: ≥90% → alert + auto-continuity savepoint (memory + docs → savepoint zip, §17 rules) |
| 5.4 | Accuracy test: UI % vs actual account page — EYES-QA comparison |
| 5.5 | ⚪ Account-creation auto-heal component: **Boss-operated, out of build scope (§41)** — doc note lang |

**EXIT CRITERIA:**
- [ ] E5.1 Real quota source found + integrated (o documented honest limitation kung walang API)
- [ ] E5.2 UI % = actual % (within 5%) — EYES-QA evidence
- [ ] E5.3 Critical threshold → savepoint zip created + verified md5
- [ ] E5.4 Simulated mode toggle works para sa demos

**Deliverables:** quota detector module · `QA_ZILLION_CLI_G5.md`
**Estimate:** **1 session**

---

### 🟩 GATE 6 — Multi-Platform Editions (Phone · Windows · TVBox)
> **Prerequisite check muna:** available ba ang devices (phone reachable, Windows PC on, TVBox on)? Kung hindi available ang isang device sa gate window, i-defer ang sub-gate na iyon (Boss decision) — hindi ito blocker ng ibang platform.

| # | Task |
|---|------|
| 6.1 | Phone: install/update PWA + termux client; smoke: send/ls/me vs hub |
| 6.2 | Windows: installer dry-run (kung maa-access) o manual verification checklist kay Boss |
| 6.3 | TVBox: server :8892 + 10-foot UI smoke |
| 6.4 | Feature parity matrix + per-edition quickstart docs |

**EXIT CRITERIA:**
- [ ] E6.1 Bawat AVAILABLE edition: install OK + send/me/ls smoke PASS
- [ ] E6.2 Parity matrix published; gaps documented with owners
- [ ] E6.3 Per-edition quickstart doc (1 page each)

**Deliverables:** `qa_platform_<edition>.md` ×3 · parity matrix · quickstarts
**Estimate:** **1–2 sessions** (device-dependent)

---

### 🟩 GATE 7 — Polish, Autostart UX & Handover
> **Objective:** Production-grade finish.

| # | Task |
|---|------|
| 7.1 | App window autostart (Hyprland workspace rule → Dell WS4/5, km binding/script) |
| 7.2 | One-command installer/updater (`install_zillion.sh` — deps, services, probe profile, skills symlink) |
| 7.3 | USER_MANUAL (Boss-facing, Taglish) + OPS_RUNBOOK (Zillion-facing: restart, rollback, logs) |
| 7.4 | Legacy cleanup: dedupe stale files sa tools/zion (demo/scratch scripts → `archive/` subfolder, memory RULE C intact) |
| 7.5 | Final full-suite regression (lahat ng QA suites green) + Boss UAT |

**EXIT CRITERIA:**
- [ ] E7.1 Fresh boot → webui + probe + app window (kung naka-rule) — lahat buhay
- [ ] E7.2 Installer dry-run PASS sa clean copy
- [ ] E7.3 Docs complete + reviewed ni Boss
- [ ] E7.4 Full regression: G1 suite + send burst + auth flows — 100% green

**Deliverables:** installer · USER_MANUAL.md · OPS_RUNBOOK.md · final QA `QA_ZILLION_CLI_FINAL.md`
**Estimate:** **1 session**

---

## 7. 📅 TIMELINE

> Sessions = working sessions natin (via Arena, restore-based). Calendar assumes ~1 session/day; kung mas mabilis si Boss mag-approve, mas mabilis din.

| Gate | Sessions est. | Calendar est. | Boss time needed | Depends on |
|------|---------------|---------------|------------------|------------|
| **G1** Foundation Hardening | 1 | Day 1 | ~5 min approval | — (started today) |
| **G2** Send Pipeline Reliability | 1–2 | Day 2–3 | ~5 min approval | G1 closed |
| **G3** Auth Hub Full Coverage | 1 | Day 4 | **~10–15 min** (login demos) | G2 closed |
| **G4** Restore Engine FULL | 1–2 | Day 5–6 | ~5 min approval | G3 closed |
| **G5** Real Quota Intelligence | 1 | Day 7 | ~5 min approval | G4 closed |
| **G6** Multi-Platform Editions | 1–2 | Day 8–9 | device access | G5 closed |
| **G7** Polish & Handover | 1 | Day 10 | ~15 min UAT | G6 closed |
| **TOTAL** | **7–10 sessions** | **~10 working days (≈2 weeks)** | ~1 hour total | strictly sequential |

**Milestone savepoints:** kada gate close → savepoint zip + memory append (§17/RULE C).
**Critical-path risk:** G4 (restore injection) at G2 (stream glitch root-cause) ang may pinaka-maraming unknowns — kaya 1–2 sessions ang estimate nila.

---

## 8. 📦 DELIVERABLES MASTER LIST

| Gate | Deliverable | Path (PC canonical) |
|------|-------------|---------------------|
| G1 | Updated QA suites + QA report + hub notes | `tools/zion/qa_*_suite.py` · `game studio/qa/QA_ZILLION_CLI_G1.md` · `game studio/docs/WEB_HUB_v2_NOTES.md` |
| G2 | zion-send v2 + burst suite + QA report | `~/.local/bin/zion-send` · `tools/zion/qa_send_burst.py` · `game studio/qa/QA_ZILLION_CLI_G2.md` |
| G3 | Auth v2 suite + QA report + demo | `tools/zion/qa_auth_v2_suite.py` · `game studio/qa/QA_ZILLION_CLI_G3.md` |
| G4 | restore_engine v2 + harness + QA report | `tools/zion/restore_engine.py` · `game studio/qa/QA_ZILLION_CLI_G4.md` |
| G5 | quota detector + QA report | `tools/zion/quota_detect.py` · `game studio/qa/QA_ZILLION_CLI_G5.md` |
| G6 | platform QA + parity matrix + quickstarts | `game studio/qa/qa_platform_*.md` · `game studio/docs/PLATFORM_PARITY.md` |
| G7 | installer + manuals + final QA | `tools/zion/install_zillion.sh` · `game studio/docs/USER_MANUAL.md` · `OPS_RUNBOOK.md` · `game studio/qa/QA_ZILLION_CLI_FINAL.md` |
| ALL | This plan (canonical) | `game studio/docs/ZILLION_CLI_PROJECT_PLAN.md` (+ copy sa `tools/zion/`) |

---

## 9. 👥 ROLES & STANDING RULES

- **Boss** — sole gate approver (1/2/3), device/credential provider, final UAT
- **Zillion** — plan, build, self-QA, eyes-QA, report (RULE A routing noted sa reports kung may sub-agent assist via gateway 8090)
- **Approval gates** — deploys at delikadong ops, Boss muna (§1, §33)
- **Memory** — RULE C appends kada gate close; watchdog armed bawat session (§17); savepoint kada milestone (§32)
- **Honesty** — walang pretend PASS; fail = fail, report, fix (§31 honesty rule)
- **Scope** — archived projects hinid ginalaw (§44); §41 boundary sa auto-signup builds

## 10. 🎲 RISKS & MITIGATIONS

| Risk | Likelihood | Mitigation |
|------|-----------|------------|
| Vision-less session (JAXVL) mid-gate | Med | §45 strict rule: new chat + `zillionOM` hanggang DIRECT; gate QA needs EYES |
| zion-send root cause mahirap i-reproduce | Med | burst harness may detailed raw dumps; guard regardless of exact cause |
| Arena platform changes (endpoints/UI) | Med | rsc/DOM extraction may version guards; QA suite catches drift agad |
| Full kit injection too big for platform | Med | COMPACT kit fallback (E4.4) |
| Context exhaustion mid-gate | Med | §17 watchdog + per-gate savepoints; restore picks up sa same gate |
| Device unavailable sa G6 | Med | defer sub-gate only (Boss decision), hindi buong gate |

## 11. ✅ DEFINITION OF "FULLY WORKING" (locked)

Isang gate ay "fully working" LAMANG kung:
1. **100% ng exit criteria ay may PASS evidence** (command output, screenshot, o live demo) — hindi "in theory"
2. Automated suite PASS sa PC (hindi lang sa isang run — 2 consecutive runs)
3. EYES-QA kung may UI component (DIRECT vision evidence)
4. Rollback proven
5. Boss APPROVE na-record sa gate QA doc

---

> **NEXT ACTION (kung i-approve ni Boss ang planong ito):** simulan ang **G1 remaining work** (QA suite update → regression → rollback proof → G1 presentation). Isang utos lang ni Boss — *"go G1"* — tuloy na tayo. 💜
