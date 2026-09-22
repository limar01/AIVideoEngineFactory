# PROVIDER-000: SnapGen Browser Recon Report

**Task ID:** PROVIDER-000 (Spike)  
**Title:** SnapGen AI Browser Recon  
**Owner:** Browser Automation Agent  
**Status:** Complete  
**Date:** 2026-09-22  
**Source:** Master Spec §18 (Provider Abstraction)

---

## 1. Provider Overview

| Field | Value |
|-------|-------|
| **Name** | SnapGen AI |
| **URL** | https://snapgen.ai |
| **App URL** | https://snapgen.ai/app |
| **Video Gen URL** | https://snapgen.ai/app/video-gen |
| **Status Page** | https://snapgen.ai/status |
| **Pricing** | https://snapgen.ai/pricing |
| **Terms** | https://snapgen.ai/terms |
| **Auth Method** | Google OAuth (Google account sign-in only — no email/password) |
| **Underlying Model** | Google Veo 3.1, Grok (xAI), Vela AI, ByteDance Seedance |
| **Output Format** | MP4 video (resolution varies by model) |

## 2. Free Tier Analysis

### Free Tier: Veo 3.1 Fast Model

- **Cost:** 0 credits (confirmed via UI: "This generation will cost: 0 Credits")
- **Limitation:** Only Veo 3.1 Fast is free on text-to-video; image-to-video requires paid plan
- **Daily cap:** Not explicitly stated; described as "free unlimited" on the free tier
- **Rate limits:** Unknown — "human verification" (CAPTCHA) may trigger after multiple generations
- **Watermark:** None on free tier (per user YouTube reference)
- **Resolution:** 720p
- **Duration:** 8 seconds (fixed on free tier)
- **Aspect ratios:** 16:9 default; 9:16 and 4:3 available (per UI controls)

### Paid Tier (for reference only — not used by default)

- $10 = 2,000 credits (with 100% bonus = 4,000 effective)
- Credits work across video + image + canvas editing
- Premium unlocks: Grok, Seedance, Vela, image-to-video, extend video, aspect ratio selection, API access
- $20/month unlimited plan also available (flat subscription)

**Conclusion:** The free Veo 3.1 Fast model has no explicit daily quota, but the Browser Automation Agent must detect implicit rate limits via:
1. CAPTCHA/human verification triggers
2. "Under Maintenance" model states (Seed, Kling, etc. are currently under maintenance)
3. Generation queueing delays

## 3. Authentication Flow

1. User navigates to https://snapgen.ai or https://snapgen.ai/app
2. Click "Login" or "Sign Up" in the header (top-right)
3. Redirected to Google OAuth consent screen
4. After Google auth, redirected back to https://snapgen.ai/app
5. Session stored as cookies (no localStorage API keys visible)

**Key constraint (spec §2, §5):** Authentication, 2FA, and CAPTCHA must remain **user-controlled**. The Browser Automation Agent must NOT attempt to bypass these. If CAPTCHA/human verification appears, the provider must return an error that triggers `BLOCKED` state (§4 of PROVIDER_INTERFACE.md error classification).

## 4. Generation UI Mapping

### Homepage (`/`)
- Large textarea at viewport position (x:48, y:713), 689×132px
- Placeholder: "Describe the video you want to generate with Grok..." (note: UI shows Grok placeholder even when Veo is selected)
- Model selector buttons: "First Frame", "Veo 3.1 Fast", "16:9", "720p", "8s", "Pro Studio"
- Generate button: "Generate with Grok" at (x:647, y:1393)
- Special offer banner: "🔥 Special Offer: Unlimited Video Generation - Only $20/month!"

### App (`/app/video-gen`)
- Tabbed interface: "Create New", "New Grok 30s", "Extend Video"
- Model selection grid: Veo (Google AI), Grok (xAI), Vela AI, ByteDance Seed (Under Maintenance), Kling (Under Maintenance), etc.
- Settings: Basic/Advanced tabs
- First Frame / Last Frame image upload controls
- Aspect ratio, resolution, duration dropdowns
- Text prompt textarea
- "Generate with Grok" button (text changes based on selected model)

### Login state:
- Header shows "Login" / "Sign Up" when not authenticated
- When authenticated: shows user avatar or name (not visible when logged out)
- No credit/quota display on the free Veo 3.1 Fast model (0 credits shown as "This generation will cost: 0 Credits")

## 5. Generation Workflow (mapped to VideoGenerationProvider interface)

### submit_generation(prompt, scene_metadata)
1. Navigate to https://snapgen.ai/app/video-gen
2. Select "Veo 3.1 Fast" model (free tier)
3. Set duration to 8s (fixed for free tier)
4. Set aspect ratio per scene needs (16:9, 9:16, or 4:3)
5. Set resolution to 720p (free tier max)
6. Fill textarea with prompt text
7. Click "Generate with Veo" button
8. Capture the generation ID from the URL or "History" page

### get_generation_status(result_id)
1. Navigate to https://snapgen.ai/app/history or monitor the generation page
2. Poll for completion status
3. Status indicators visible: "Generating...", "Processing", "Completed", or error messages
4. Check for CAPTCHA/human verification prompts (triggers BLOCKED state)

### download_result(result_id)
1. From History page, find the completed generation
2. Click the download button on the result thumbnail
3. File is MP4 format
4. Capture file and move to clips directory

### get_quota()
- Free Veo 3.1 Fast: 0 credits per generation, no explicit daily limit
- No quota display element found on UI for free tier
- Quota detection strategy: 
  1. No credit counter on free model → assume unlimited but watch for CAPTCHA/rate-limit triggers
  2. If CAPTCHA appears → treat as implicit rate limit → QUOTA_WAIT with conservative backoff
  3. If any credit prompt appears → parse credit balance from DOM

### detect_error(raw_response)
Error strings to watch for in the page DOM/text:
- "human verification" / CAPTCHA prompts
- "Under Maintenance" (model-specific)
- "rate limit" / "too many requests"
- "generation failed" / "try again"
- "session expired" / "sign in"

### detect_quota_exhaustion(raw_response)
- CAPTCHA/human verification appearing after multiple successful generations
- "Credits remaining: 0" text (if switching to paid models)
- HTTP 429 or rate-limit error responses
- "Please wait" cooldown timers

## 6. Browser Automation Strategy (Playwright)

```python
class SnapGenProvider(VideoGenerationProvider):
    BASE_URL = "https://snapgen.ai"
    APP_URL = "https://snapgen.ai/app/video-gen"
    
    def authenticate(self):
        # Navigate to /app — check if Google OAuth session is active
        # If not, we CANNOT auto-login (no API keys per user constraint)
        # Must signal to user: return False → BLOCKED state
        # User must manually log in via browser
        pass
    
    def submit_generation(self, prompt, scene_metadata):
        # 1. Select Veo 3.1 Fast model
        # 2. Fill textarea: page.fill('textarea[placeholder*="Describe"]', prompt)
        # 3. Set duration: page.click('button:text("8s")')
        # 4. Set aspect ratio: page.click('button:text("16:9")')
        # 5. Click Generate: page.click('button:has-text("Generate")')
        # 6. Extract generation ID from URL or wait for History entry
        pass
    
    def get_generation_status(self, result_id):
        # Poll History page or generation page
        # Check for: "Completed", "Generating", "Failed", CAPTCHA
        pass
```

## 7. Risks & Mitigations

| Risk | Likelihood | Mitigation |
|------|-----------|------------|
| CAPTCHA/human verification on free tier | High | Detect and set state to BLOCKED; escalate to user |
| Google OAuth only — no programmatic login | High | Session cookies captured via browser automation after user logs in manually; CDP auth (spec user constraint) |
| Veo 3.1 Fast always 0 credits but rate-limited | Medium | Detect CAPTCHA as rate limit signal; implement conservative backoff |
| Model "Under Maintenance" states | Medium | Check model status before submitting; fall back to available models |
| Download URL expires | Low | Download immediately upon completion detection |

## 8. Session Management

- Session is cookie-based (Google OAuth)
- No API key required for free tier
- Session expiry unknown — check via `check_session()` by navigating to `/app` and verifying user avatar/header presence
- Credentials stored encrypted in `Account` table per SECURITY-001 (not hard-coded)

## 9. Quota Detection Strategy

Since the free Veo 3.1 Fast model shows "0 Credits" and no daily cap:

1. **Primary signal:** CAPTCHA/human verification appearing during generation submission or polling
2. **Secondary signal:** "rate limit" or "too many requests" error messages
3. **Tertiary signal:** If user switches to a paid model, parse credit counter from DOM
4. **Fallback:** Conservative fixed limit (configurable in `config/quota.yaml::policy::fallback_daily_limit`)

**The QuotaManager must NOT assume 10 generations per day** (spec §2). Default to detecting real signals and falling back to a configurable conservative limit.

## 10. Testability

- `MockVideoProvider` handles all automated testing (spec §27)
- SnapGen integration tests require a real authenticated session
- Provider is completely isolated under `app/providers/snapgen/` (spec §18.2)
- Can be toggled via `config/providers.yaml::provider: snapgen` / `mock`
