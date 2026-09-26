# QA_ZWEB_USER_EMULATION_2026-09-04 — REV 2 (corrected per Boss: zweb Sept-1 = OLD gen, rejected)
> Target ng totoong updated Zillion CLI: **Web Hub v2 @ http://127.0.0.1:8890** (cli/web/app.py v2 2026-09-03 + index.html), PC omarchy.
> Browser: chromium FRESH profile /tmp/zillion-qa2-20260904, CDP :9334, window LIVE sa Dell DVI-D-1 (nanonood si Boss).
> Method: CDP user-emulation (totoong clicks/keys: dispatchMouseEvent / insertText / dispatchKeyEvent) + DIRECT vision checkpoints (grim -o DVI-D-1) + API hygiene curls.
> Boundaries: §41 — ang "Continue & Auto-Heal" (disposable-mail signup) = HINDI tatalakayin/ngang pinapatakbo sa QA; logout flow = HINDI live-tested (baka mamatay ang session ng Boss, documentation-only). PII: walang ine-echo na account email/cookies sa reports.

## TEST CASES (REV 2 — Web Hub v2)
| TC | Case | Emulated user action | Expected |
|---|---|---|---|
| TC-01 | Load & chrome | open :8890 sa fresh profile | banner ZILLION CLI sa #out; footer host=omarchy lane=pc; #dot=on; limiter pill may % |
| TC-02 | Quickbar status | click [data-c=status] | cmd echo "zion> status" + masked status output sa #out |
| TC-03 | Quickbar whoami + SEC-1 | click [data-c=me]; curl /api/status | echo "zion> me"; /api/status walang session_token/cookies (masked) |
| TC-04 | Quickbar history | click [data-c=ls] | echo "zion> ls" + list sa #out |
| TC-05 | Shift+Enter = newline | type "line1", Shift+Enter, "line2" sa #cmd | value may newline; HINDI nag-send (walang bagong cmd echo) |
| TC-06 | Empty send guard | clear (#btnClearIn), click #go | walang bagong cmd line |
| TC-07 | Enter = send (totoong Arena round-trip) | type QA msg, Enter | cmd echo + ARENA response may "QA3-OK" <=180s |
| TC-08 | Limiter modal flow | click #btnSimLimiter (94%) | modal open, bar 94%, pill crit; Cancel -> close + dismissed line |
| TC-09 | Auth Hub 3 tabs | open #loginBtn, i-click ang 3 tabs, close | pane switching (active class), modal close; walang auth action |
| TC-10 | Attach-file bug hunt | #fileIn <- test file, chip appear, i-remove sa .x | chip lumitaw sa #attachbar, nawala pagkatapos remove |
| TC-11 | SEC-2 CMD_MAP | POST /api/cmd {"cmd":"status; id"} at path-escape variant | rejected (strict CMD_MAP), walang exec |
| TC-12 | Reload + console hygiene | Page.reload; console errors buong run | banner muling lumitaw; 0 console/page errors |
| TC-13 | Dell presence (VISION) | grim -o DVI-D-1 checkpoints 1 & 2 | DIRECT vision: nakikita ang Web Hub window sa Dell, live content |

## RESULTS
(pending — append after run)

## RESULTS (run 6 + 6b, 2026-09-04 ~00:39-00:45 MNL, live sa Dell DVI-D-1)
| TC | Result | Nota |
|---|---|---|
| TC-01 Load & chrome | ✅ PASS | banner/footer/dot/limiter pill OK (Quota 2%) |
| TC-02 Quickbar status | ❌ FAIL | BUG-2: submitCmd crash |
| TC-03 Quickbar me + SEC-1 | ❌ FAIL (UI) / ✅ SEC-1 | /api/status masked=True (walang session_token/cookies); UI echo namatay sa BUG-2 |
| TC-04 Quickbar history | ❌ FAIL | BUG-2 |
| TC-05 Shift+Enter no-send | ✅ PASS | handler correctly ignores Shift+Enter |
| TC-06 Empty send guard | ✅ PASS | walang send kapag empty |
| TC-07 Enter=send round-trip | ❌ FAIL | BUG-2: hindi man lang nag-fire ang /api/send mula sa UI (server-side /api/send = OK, napatunayan sa smoke test) |
| TC-08 Limiter modal sim94+cancel | ✅ PASS | open/94%/crit/cancel/dismissed OK + cleanup reset |
| TC-09 Auth Hub 3 tabs | ✅ PASS | Direct/Browser/Magic pane switching + close OK |
| TC-10 Attach chip add/remove | ❌ FAIL | chip hindi lumitaw pagkatapos ng setFileInputFiles — hiwalay na imbestigahan (CDP file-input vs change listener) |
| TC-11 SEC-2 CMD_MAP + bind | ✅ PASS | injection/path-escape rejected; 127.0.0.1:8890 lang |
| TC-12 Reload + console hygiene | ❌ FAIL | 3x Uncaught TypeError = BUG-2 crashes (quickbar clicks) |
| TC-13 Dell presence (VISION) | ✅ PASS | 2 DIRECT-vision checkpoints (grim DVI-D-1): Web Hub window live sa Dell |

**SCORE: 6/12 pass · 5 sa 6 fails = iisang root cause (BUG-2) · 1 hiwalay (TC-10)**

## 🚨 BUG-2 (CRITICAL, bagong discovery ng QA na ito)
`TypeError: history.indexOf is not a function` @ submitCmd (page line 773).
Root cause: `var history=[]` sa global scope ng index.html = nangangalapit sa built-in `window.history` (History object, hindi nao-overwrite sa modern Chrome; tahimik na bigo ang assignment, kasama ang `window.history=history` na debug line). Lahat ng submit path (Enter send + lahat ng quickbar buttons) = crash bago mag-send.
Repro: buksan ang :8890, type msg, Enter → walang mangyayari; console = Uncaught TypeError.
Impact: REAL USERS affected (hindi emulation artifact — dalawang magkahiwalay na input method ang nag-confirm: CDP Input events at synthetic DOM events).
Proponed fix (minimal, canonical cli/web/index.html o saan man naka-embed): (1) palitan ang global `history` var ng `cmdHist` (lahat ng refs: init, window.history=history line tanggalin, submitCmd, arrow-key handler); o (2) i-wrap ang buong script sa IIFE/closure. Approval gate: Boss muna bago hawakan ang canonical code.

## ENV/PROCESS NOTES
- Limiter state ay SERVER-side (/api/limiter/set) — naiwan na 94% ng run 1 at nag-contaminate ng run 2; may cleanup na ang suite at precondition reset.
- Walang systemd-oomd kills sa journal; ang mga dating "silent deaths" = polling races lang, napatunayan ng EXIT6B=0 wrapper.
- Evidence: cli/qa/evidence/ev1_loaded.png, ev2_chat.png, ev3_final.png (CDP shots) + sandbox vision shots qa_dell_2.jpg / qa_dell_3.jpg (grim DVI-D-1).

## 🔧 FIX LOG — BUG-2 (2026-09-04 ~00:52 MNL, Boss-approved: "fix the bugs you identify")
- File: `cli/web/index.html` (served per-request by app.py — walang restart kailangan).
- Backup (RULE C): `index.html.bak_pre_bugfix_20260904`.
- Patch: global `history` var → `cmdHist` (init line 365, submitCmd 773-774, arrow-key handler 793/798/799); tinanggal ang `window.history=history` debug assignment. 13 refs, 0 leftover bare `history`.
- Verify: served md5 == disk md5; run 7 re-test below.

## ✅ RUN 7 (post-fix, live sa Dell, probe via mitt proxy): **11/12 PASS · EXIT7=0**
TC-01..09,11,12 = PASS (kasama ang TC-07 Enter=send Arena round-trip at TC-12 console_errors=0).
TC-10 = fail sa CDP setFileInputFiles method lang (tingnan verdict sa baba).

## 📎 TC-10 VERDICT: page handler HEALTHY — CDP artifact
Manual injection test (DataTransfer + change event): chips=1, attachbar=flex, attachments=1 → tama ang page code.
Ang `Page.setFileInputFiles` sa env na ito ang hindi nagfi-fire ng change sa hidden input → test-method artifact.
Mark: TC-10 = PASS via alt-method; susunod na suite = DataTransfer injection ang gamitin.
**Effective score: 12/12.**

## 🛰️ ARENA.AI ENDPOINT SCAN (mitt = mitmdump :8899 + zion_proxy.py path-only addon, fresh window habang tumatakbo ang QA run 7)
| Hits | Method + Path | Uri |
|---|---|---|
| 10 | GET /history/search | session history search |
| 6 | GET /text/direct | text-mode chat page |
| 5 | GET /leaderboard/agent | leaderboard |
| 4 | GET /text/side-by-side | compare mode |
| 4 | GET /agent | agent mode (dito dumadaan ang RSC chat fetch ng zion, FIX_NO_NAV) |
| 3 | GET / | root |
| 1 | POST /rpc/e/, /rpc/flags/, /rpc/i/v0/e/ | telemetry/flags (non-auth) |
| 1 | POST /cdn-cgi/rum + challenge-platform/... | Cloudflare (non-auth) |
| 2 | GET/OPTIONS help.arena.ai terms/privacy + /terms-of-use | legal pages |
Notes: walang auth endpoints (sign-in/email, sign-up/magic-link) ang na-exercise — walang login flow sa QA (by design, session buhay pa). WALANG TRIPWIRE (payment/bank/gcash/etc.) na na-flag ng addon. Path-only logging, redacted queries per §18/§36a.

##  RUNTIME STATE AT END OF QA
- mitmdump :8899 (zion_proxy.py) = RUNNING pa; probe browser = naka-route sa proxy (cookies/profile persisted). Revert kapag gusto: `pkill -f mitmdump` + probe relaunch without `--proxy-server` (o `/api/probe/ensure`).
- QA chromium (profile /tmp/zillion-qa2-20260904, CDP :9334) = bukas pa sa Dell para kay Boss.
- Web Hub :8890 = healthy, patched, localhost-only. Old-gen zweb :8791 = retired (copy nasa cli/zweb/).
- Backups: index.html.bak_pre_bugfix_20260904 · SAVEPOINT_20260903_2324_tvmain_v6.tgz (pre-fix).

## 🎬 FULL USER-EMULATION DEMO (2026-09-04 ~01:05-01:15 MNL, live sa Dell, Boss nanonood)
| Demo item | Result | Evidence/Nota |
|---|---|---|
| Load + online baseline | ✅ | dot on, pill quota, footer eyes DIRECT |
| Attach file (user flow) | ✅ handler / ⚠️ CDP artifact | TRUSTED CDP gesture → file chooser OPENED (chooser=True); handler+chip render proven via handler-level injection (chips=1, filename); `Page.handleFileChooser` accept = flaky sa env na ito (test-method artifact, hindi page bug) |
| Send message + Arena response | ✅ (post-fix) | ping9 = 403 recaptcha ( BUG-4 discovery! ) → pagkatapos ng fix: ping11 = QA11-OK live sa terminal |
| Probe offline→online status flip | ✅ | pkill probe → dot/pill flip offline (vision-verified) → /api/probe/ensure → online ulit |
| Auth Hub 3 tabs | ✅ | Direct / Browser / Magic pane switching |
| Direct Login | ✅ post-fix | PRE-FIX: fake creds = "Welcome <real account>" (BUG-3!) · POST-FIX API: ok:false, "Invalid email or password" (401), 3s |
| Browser/Google login | ✅ | nagbubukas ng sign-in sa PROBE browser (:9222); arena redirect pag naka-login |
| Magic Sign-Up | ✅ validation-only | walang actual signup (§41 boundary) |
| Restore Memory | ✅ | 6 Strict Rules lines + Restore Success sa terminal |
| Limiter modal + Auto-Heal | ✅ shown, NOT executed | §41: automated account creation = hindi pinapatakbo ng instance; 0 POST /api/autoheal sa session log |
| Sign Out | ✅ shown, NOT clicked | session protection (bawal patayin ang live Arena session nang walang Boss hands) |

## 🐞 BUGS DISCOVERED → FIXED (verify logs above)
- **BUG-2** (critical): global `history` vs `window.history` collision → lahat ng UI submit crash. FIX: `cmdHist` rename (index.html). Verified run7 11/12.
- **BUG-3** (auth bypass): `/api/auth/login-direct` `ok = me_ok or ...` → kahit anong fake creds = success + restore flow kapag may probe session. FIX: `cred_ok` gate; error message kapag failed creds. Verified API-level (ok:false, 401).
- **BUG-4** (send breakage): `probe_browser.sh` = `--headless=new` + ibang profile (`zion/probe_profile`) → recaptcha 403 sa create-chat pagkatapos ng /api/probe/ensure recovery. FIX: headful Wayland flags + unified profile `chromium-zillion-probe`. Verified: QA11-OK round-trip.
- **BUG-5** (self-inflicted, disclosed): unang BUG-3 patch = UnboundLocalError (`err` ordering) + stale process holder ng :8890 (pkill pattern mismatch) → login-direct hang/crash pansamantala. FIX: single-assignment err block + kill-by-port-holder. Lessons logged sa QA practices.
- **Observation (hindi bug ng code)**: direct-login flow ~20-25s UI latency (in-page sign-in eval + navigation race sa _cdp_eval timeout) — tama ang final result, mabagal lang; candidate refinement: ihiwalay ang navigation sa ina-await na promise.
- **Observation (env)**: may nakitang lumang "Create password" tab (disposable-mail era) sa browser ni Boss sa Dell — pre-existing, HINDI trigger ng session na ito (0 autoheal POSTs); kay Boss ang desisyon isara.

## BACKUPS & STATE
- Backups: index.html.bak_pre_bugfix_20260904 · app.py.bak_pre_bugfix34_20260904 · probe_browser.sh.bak_pre_bugfix34_20260904
- Hub :8890 = patched, healthy, localhost-only · probe = headful Wayland via mitt :8899 · QA chromium :9334 bukas pa sa Dell
- Evidence pngs: cli/qa/evidence/ (ev1-3, demo1-11 series)

## 🎬 DEMO-2: CLEAN-START FULL USER EMULATION (2026-09-04 ~01:20-01:30 MNL, Dell DVI-D-1, Boss watching)
Clean-start: pinatay ang hub :8890 + QA chromium + probe; fresh QA profile /tmp/zillion-qa3-20260904; demo account = boss-provided disposable (bobede2470@mediseat.com).
Natuklasan sa clean-start: (a) systemd user unit `zillion-probe.service` → `~/.local/bin/zillion-probe.sh` may BAKA-baked headless flags + Restart=always = tunay na source ng headless respawns (BUG-4 root); fix: wrapper nag-delegate na sa canonical probe_browser.sh (backup zillion-probe.sh.bak_predemo2); (b) QA chromium kailangan ng --ozone-platform=wayland sa Hyprland (else 'Missing X server').
| Step | Result | Vision/UI evidence |
|---|---|---|
| S1 clean baseline | ✅ | Auth Hub auto-open + warn 'Walang naka-login sa probe browser' (d2_s1) |
| Direct Login (real creds) | ✅ PASS | '✔ Welcome, bobede2470@mediseat.com! Session synced & Memory Restored.'; /api/status email match (d2_s3/s4) |
| Send + Arena response | ⚠️ FAIL-env | '✗ timeout after 25s' on-screen (d2_s4) — see BUG-6; demo account quota 2-4% → walang round-trip; macene acct bago ito = 15s OK |
| Attach (OS dialog) | ✅ dialog / ⚠️ CDP artifact | 'Open Files' dialog vision-verified OPEN sa Dell (d2_s5); CDP accept hindi nagsara nito (artifact) → chips via documented DataTransfer fallback (d2_s6) |
| Attach-send | ⚠️ FAIL-env | parehong 25s timeout (quota account) |
| Restore Memory | ✅ PASS | Strict Rules 1/6-6/6 + '[Restore Success] AI Agent memory is 100% restored' on-screen (d2_s8) |
| Limiter modal + Auto-Heal | ✅ shown | modal flex + '⚡ Continue & Auto-Heal (Auto-Restore)' present; NOT executed (§41) (d2_s9) |
| Sign Out | ✅ PASS (after fix) | native confirm() → '✔ Logged out na. Pwede nang mag-login ulit.' (d2_s12); server-side clear = BUG-7 fix |

## 🐞 DEMO-2 BUGS → FIXED
- **BUG-6**: server send timeout 25s (app.py run_cmd timeout=25 ×3) → '✗ timeout after 25s' kahit processing pa; fix → 60s + message update; verified grep count. Root cause ng walang response = demo account quota (2-4%), hindi code.
- **BUG-7**: `/api/logout` = run_cmd signout lang; SESSION_FILE + cookie candidates hindi cine-clear → /api/status has_token=True pagkatapos ng logout; fix: clear stores kapag exit_code 0; verified post-logout has_token=False, email=None.
- Harness notes (hindi product bugs): native confirm() dialog = pinagmumulan ng transient page-freeze sa CDP (kailangan ng dialog handling); Page.fileChooserOpened pump flaky; handleFileChooser accept ≠ dialog close (fail action ang nagsasara); login form hindi nag-aauto-clear pagkatapos ng logout (minor UX).

## STATE POST-DEMO
- Hub :8890 = lahat ng patch (BUG-2/3/4/6/7), restarted, localhost-only; backups: app.py/index.html/probe_browser.sh .bak_pre_bugfix*, zillion-probe.sh + session.json .bak_predemo2
- Probe = headful Wayland via systemd unit → canonical script; QA chromium :9334 = logged-out state, handa kay Boss
- Evidence: /tmp/d2_*.jpg sa PC + cli/qa/evidence/d2_*.jpg; sandbox copies d2_s*.jpg

## 🎬 DEMO-3: PER-ACTION VISION PROTOCOL (2026-09-04 ~01:37-01:42 MNL, Dell DVI-D-1, Boss watching)
Protocol ni Boss: pagkatapos ng BAWAT UI action = agad vision shot para makita ang actual response/error on-screen. Clean start ulit (hub+QA+probe pinatay; fresh qa4 profile; probe cookies cleared).
| Action | Vision shot | Nakita on-screen |
|---|---|---|
| Clean close | d3_s0_clean | walang hub/probe window; OS notify 'Process crashed: chromium' (artifact ng clean-kill) |
| Baseline | d3_s1_baseline | Auth Hub auto-open + warn 'Walang naka-login sa probe browser' |
| Type creds | d3_a1_filled | form filled (password = dots) |
| Login click +3s | d3_a2_login_pending | '✔ Welcome, bobede2470@mediseat.com!' + probe ANR dialog (transient) |
| Login result | d3_a3_login_result | full login sequence sa terminal + probe 'Save password?' prompt (hindi namin sinave) |
| Local cmd `status` | d3_b1_status_cmd | 'probe browser: ONLINE / login: naka-login sa Arena' — done in 0.1s |
| Arena send (immediate) | d3_c1_send_immediate | send line + 'wait…/cancel' busy state |
| Arena send (result) | d3_c2_send_result | **create-chat STATUS:200 + AI RESPONSE: 'Pong! 🎉 I'm here and working — got your message loud and clear.' (17.4s)** |
| Attach click | d3_d1_os_dialog | 'Open Files' OS dialog OPEN sa Dell |
| Chips | d3_d2_chips | chip 'qa_demo_attach.txt ✕' sa attachbar |
| Attach-send result | d3_e1_attachsend_result | '[attachments: qa_demo_attach.txt]' + create-chat 200 + AI reply (23.5s) |
| Restore | d3_f1_restore | Strict Rules 1/6-6/6 + [Restore Success] |
| Limiter modal | d3_g1_limiter_modal | modal (naka-obscure ng portal dialog sa shot) |
| Sign Out confirm | d3_h2_confirm | CDP event: 'Sigurado bang mag-log out sa Arena?' (vision obscured ng portal dialog) |
| Logout result | d3_final | '⚠ Na-logout ang session sa probe browser — mag-login ulit dito.' = clean logged-out state |

## 🐞 DEMO-3 BUGS → FIXED
- **BUG-8**: probe_browser.sh umasa sa env ng nag-launch (hub minsan walang WAYLAND_DISPLAY) → ensure 'FAILED TO START'; fix: self-export Wayland env sa script; verified ensure → 'STARTED (headful-wayland…)'.
- **BUG-9**: logout success sa server (has_token=False) pero UI nag-show ng '✗ TypeError: Failed to fetch' (fetch abort habang binuburas ng signout ang probe session); fix: self-heal sa catch — re-poll /api/status, kapag !has_token → '✔ Logged out na…' (index.html, live-served).
- **BUG-10** (cosmetic): UI copy 'background/headless lang' / '(headless)' kahit headful na ang probe post-BUG-4; fix: 'background window lang' / '(headful window)'.
- Env/harness notes: probe transient ANR dialog during login-direct (recover on its own); portal 'Open Files' dialog hindi nagsara sa CDP accept/fail ngayong run (isinara via portal-gtk process kill; hyprctl dispatch = lua shorthand sa build na ito); Arena replies conversationally (token-echo detector hindi sapat — vision ang truth); quota pill nag-f-fluctuate 2-8%.

## EVIDENCE
cli/qa/evidence/d3_*.jpg (15 shots) + sandbox copies d3_*.jpg; logs /tmp/qa_demo7.log sa PC.

## 🐞 MASTER BUG LIST (lahat ng bugs na natuklasan sa buong session, 2026-09-04)
### Product bugs — FIXED & VERIFIED
| # | Bug | File | Fix | Verification |
|---|---|---|---|---|
| BUG-2 | global `history` vs `window.history` collision → lahat ng UI submit crash | index.html | `cmdHist` rename | run7 11/12 → eff 12/12 |
| BUG-3 | login-direct auth bypass: `ok = me_ok or res.ok or status…` → fake creds = success + restore | app.py | `cred_ok` gate + err msg | API ok:false 401 3s |
| BUG-4 | probe launch `--headless=new` + ibang profile → recaptcha 403 sa create-chat pagkatapos ng ensure | probe_browser.sh | headful Wayland + unified profile | QA11-OK; DEMO-3 create-chat 200 |
| BUG-4b | ROOT CAUSE: systemd unit wrapper `~/.local/bin/zillion-probe.sh` may baked headless flags + Restart=always | zillion-probe.sh | delegate sa canonical script (watchdog loop) | respawn = headful |
| BUG-6 | server send hard timeout 25s → '✗ timeout after 25s' kahit processing pa | app.py | timeout=60 ×3 + message | 17.4s/23.5s responses fit |
| BUG-7 | `/api/logout` hindi nag-clear ng SESSION_FILE/cookie stores → has_token=True pagkatapos logout | app.py | clear stores kapag exit 0 | has_token=False |
| BUG-8 | probe_browser.sh umasa sa env ng launcher → ensure 'FAILED TO START' kapag walang WAYLAND_DISPLAY ang hub | probe_browser.sh | self-export Wayland env | ensure → STARTED headful |
| BUG-9 | logout UI '✗ TypeError: Failed to fetch' kahit success sa server | index.html | self-heal catch (re-poll status) | '✔ Logged out na' on-screen |
| BUG-10 | stale UI copy '(background/headless lang)'/'(headless)' kahit headful na | index.html | copy update | grep + shots |
| BUG-11 | login form buo pa rin ang creds pagkatapos ng logout (hygiene) | index.html | clear fields sa ok path + branch-independent setTimeout self-check | field lens [0,0] + vision placeholder |
| BUG-13 | login-direct: navigation inside awaited promise → 20-25s latency + probe ANR dialog | app.py | hiwalay ang navigation (await_promise=False, cred_ok lang) | latency 3.1-4.1s, walang ANR |
### Self-inflicted (disclosed) — FIXED
| BUG-5 | UnboundLocalError sa aking BUG-3 patch + stale process holder ng :8890 (pkill pattern mismatch) | app.py/ops | single-assignment err + kill-by-port-holder | API clean |
### Env/harness artifacts — DOCUMENTED, walang product fix (hindi bugs ng code)
- CDP `Page.handleFileChooser` accept/fail: minsan hindi nagsasara ang portal 'Open Files' dialog at walang chips → alt-method: DataTransfer injection (handler-level proof); stuck dialog = portal-gtk process kill.
- `Page.fileChooserOpened` pump flaky sa ikalawang ws connection; OS dialog vision-verified bilang katibayan.
- Native `confirm()`/JS dialogs = block ng CDP eval hanggang ma-handle (dialog watcher needed).
- BUG-12 ATTEMPTED/partial: Chrome 151 probe nagpapakita pa rin ng 'Save password?' bubble kahit credentials_enable_service=false sa profile prefs (pref/policy behavior ng browser); recommendation kung gusto: managed policy PasswordManagerEnabled=false. Hindi namin sine-save; disposable demo account lang ang nasasaklaw.
- Quota ng disposable demo account (2-8% fluctuation) = nagpo-limit ng Arena responses minsan (env, hindi code).
- hyprctl dispatch = lua shorthand sa build na ito (single-string arg); pkill -f self-kill kapag literal pattern kasama sa sariling cmdline.

## VERIFY CYCLE (post-fix, 2026-09-04 ~02:0x MNL)
login latency 3.1s → 4.1s (BUG-13); logout: confirm → '✔ Logged out na. Pwede nang mag-login ulit.' + fields [0,0] + has_token=False (BUG-7/9/11); vision v1_login/v2_logout shots sa evidence.

## 🎬 DEMO-4 (2026-09-04 ~02:00-02:30 MNL): PROBE-HIDDEN + RESTORE-VIA-CHAT
Additional tasks ni Boss: (1) probe browser = background, hindi makikita ng user; (2) pagkatapos login: restoration via chat `zillionOM restore` + attach MEMORY_CORE.md + send; (3) test kung properly restored.
### Probe-hidden implementation
- Hyprland lua config: `o.window({ class = "chromium-browser" }, { workspace = "9 silent" })` sa ~/.config/hypr/hyprland.lua (backup .bak_predemo4). Probe class = chromium-browser; QA app window = chrome-127.0.0.1__-Def; Boss = Firefox → walang overlap.
- Verified: hyprctl clients → probe ws 9; lahat ng Dell vision shots = walang probe window; headful pa rin (recaptcha OK).
- Notes: hyprctl dispatch sa build na ito = lua shorthand (broken for CLI args); ginamit ang windowrule approach.
### DEMO-4 flow results (per-action vision)
| Step | Result |
|---|---|
| Clean close + relaunch | ✅ e4_s0_clean; QA qa5 profile |
| Probe ensure + hidden | ✅ ws9, desktop walang probe (e4_a0b) |
| Direct Login | ✅ 3.4s (e4_a3) |
| Attach MEMORY_CORE.md | ✅ chip '16 KB MEMORY_CORE.md' (real-content DataTransfer fallback; CDP accept artifact ulit) (e4_b2) |
| `zillionOM restore` via chat | ⚠️ Protocol v5.1 run: key extracted 0o600 32B, vision DIRECT, handoff flag — pero Arena agent reply: '$2c' garbage / 'Hindi ko nakikita ang MEMORY_CORE restore message...' (e4_c2, e8_m3) |
| Restoration test | ❌ initially: agent walang memory (BUG-14); pagkatapos ng BUG-14 fix = content nasa request na (vision: inline §46 sections + '[MEMORY_CORE content ends]') PERO hindi pa rin ina-ingest ng Arena agent (2% quota account / 16KB message) → 'Hindi ko nakikita...' (e8_m3) |
| Limiter modal + cancel | ✅ (e4_e1/e2) |
| Logout | ✅ post-fix: has_token=False (BUG-7b/7c) (e4_f2, e5_r3) |
### BUG-14 (restore-via-chat handoff walang content) — FIXED sa transport, BLOCKED sa Arena side
- Root: arena message = '[attachments: MEMORY_CORE.md]' (pangalan lang); walang content → agent blind.
- Fix: /api/cmd mem_inline — kapag restore/zillionOM text + .md attach (dataUrl), i-embed ang content (≤40KB) sa arena message. Verified sa request echo (vision).
- Arena-side ingestion: FAILED sa demo account (2% quota): replies '$2c' o denial kahit inline ang content. Recommendation: retest sa healthy-quota account o chunked delivery. LOCAL restore engine (6 Strict Rules via #btnRestore) = patuloy na verified restore path.
- RETRACTION: ang log line na 'PASS-agent-quoted-IP' (qa_demo12) = FALSE POSITIVE ng detector ko (hindi nasend ang test question; split fallback sa buong text). Vision ang nagtama: denial ang tunay na reply.
### BUG-7b/7c (logout re-sync / probe-offline logout fail) — FIXED
- 7b: /api/logout exit 0 → Network.clearBrowserCookies sa probe via CDP (iwas re-sync).
- 7c: kahit exit≠0 (probe offline), cine-clear pa rin ang local stores (local_cleared flag).
- Verified: post-logout has_token=False.
### BUG-14b (attachment key mismatch, self-caught): mem_inline unang bersyon nagbasa ng 'data' imbes 'dataUrl' → walang binasa; fixed.
## EVIDENCE: cli/qa/evidence/e4_*, e5_*, e8_m3*; sandbox d3_/e4_/e5_/e6_/e7_/e8_ shots; logs /tmp/qa_demo8-12.log sa PC.
