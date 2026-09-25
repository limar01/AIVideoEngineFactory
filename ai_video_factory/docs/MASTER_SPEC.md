# AI VIDEO FACTORY — UNIFIED MULTI-PROVIDER MASTER PROJECT SPECIFICATION

## SnapGen.ai + Meta AI / Vibes + Google Flow

### Purpose

Build one modular AI Video Factory application that uses a **shared production/orchestration system** and **separate provider-specific video-generation pipelines**.

The user should interact with ONE application.

The user selects a video-generation provider:

- `SnapGen.ai`
- `Meta AI / Vibes`
- `Google Flow`

The system then activates **only the selected provider adapter/pipeline**.

The shared story, character, visual, scene, timeline, QA, audio, persistence, and final-assembly systems remain common unless a provider requires a specific processing path.

---

# 1. CORE DESIGN PRINCIPLE

## ONE APP — ONE PROJECT — MULTIPLE VIDEO ENGINES

The architecture must NOT create three separate applications.

Instead:

```text
USER
  ↓
VIDEO FACTORY UI
  ↓
PROJECT CONFIGURATION
  ↓
SHARED STORY ENGINE
  ↓
CHARACTER BIBLE
  ↓
VISUAL BIBLE
  ↓
SCENE PLANNER
  ↓
SCENE / COMPLEXITY OPTIMIZER
  ↓
REFERENCE IMAGE ENGINE
  ↓
SHARED PROMPT ENGINE
  ↓
PROVIDER ROUTER
  ↓
┌─────────────────────────────────────────────┐
│ USER SELECTS VIDEO PROVIDER                 │
│                                             │
│  SnapGen.ai       → SnapGen Pipeline        │
│  Meta AI/Vibes    → Meta/Vibes Pipeline     │
│  Google Flow      → Google Flow Pipeline    │
└─────────────────────────────────────────────┘
  ↓
PROVIDER-SPECIFIC VIDEO GENERATION
  ↓
COMMON VIDEO QA
  ↓
COMMON AUDIO / TIMELINE SYSTEM
  ↓
LIP-SYNC WHEN REQUIRED
  ↓
SUBTITLES
  ↓
FFMPEG ASSEMBLY
  ↓
FINAL VIDEO
  ↓
FINAL QA / REPORT
```

The provider-specific modules must be isolated.

Adding another provider later must NOT require rewriting the core application.

---

# 2. PROVIDER SELECTION

The project creation UI must include:

```text
Video Generation Provider:

( ) SnapGen.ai
( ) Meta AI / Vibes
( ) Google Flow
```

Optional advanced selection:

```text
Provider Model:
Provider Resolution:
Provider Aspect Ratio:
Provider Clip Duration:
Reference Images:
Native Audio:
External Audio Pipeline:
Lip-Sync:
```

The application must read the provider capabilities before building the generation queue.

Example:

```json
{
  "provider": "google_flow",
  "model": "veo_3_1",
  "clip_duration": 8,
  "reference_images": true,
  "native_audio": true
}
```

The user should not need to manually redesign the project for a provider.

---

# 3. SHARED CORE PIPELINE

All providers use the same high-level production system:

```text
USER REQUEST
↓
PROJECT CONFIG
↓
STORY
↓
CHARACTER BIBLE
↓
VISUAL BIBLE
↓
SCENE PLAN
↓
TIMELINE
↓
REFERENCE ASSETS
↓
PROVIDER PROMPT COMPILATION
↓
SELECTED VIDEO PROVIDER
↓
VIDEO CLIPS
↓
VIDEO QA
↓
AUDIO / DIALOGUE / SFX / BGM
↓
LIP-SYNC IF REQUIRED
↓
SUBTITLES
↓
FINAL ASSEMBLY
↓
FINAL QA
```

The core engine owns the project.

The selected provider owns only the provider-specific generation process.

---

# 4. PROVIDER ROUTER

Create a central provider router:

```text
ProviderRouter
```

Responsibilities:

1. Read selected provider.
2. Load provider configuration.
3. Load provider capabilities.
4. Select correct adapter.
5. Compile provider-specific prompts.
6. Select provider-specific reference-image behavior.
7. Select generation duration strategy.
8. Select audio strategy.
9. Select quota/capacity strategy.
10. Send jobs to the selected provider only.

Example:

```python
provider = ProviderRouter.get_provider(project.provider)

if provider == "snapgen":
    return SnapGenProvider()

if provider == "meta_vibes":
    return MetaVibesProvider()

if provider == "google_flow":
    return GoogleFlowProvider()
```

Never run all providers automatically unless the user explicitly enables multi-provider generation.

---

# 5. PROVIDER ADAPTER INTERFACE

All providers must implement a common interface.

```text
VideoGenerationProvider
```

Required capabilities:

```text
authenticate()
check_session()
get_capabilities()
get_quota()
get_capacity()
get_reference_support()

compile_prompt()
prepare_references()

submit_generation()
get_generation_status()
download_result()

detect_error()
detect_quota()
detect_rate_limit()

close_session()
```

Optional capabilities:

```text
supports_native_audio()
supports_dialogue()
supports_voice_reference()
supports_start_frame()
supports_end_frame()
supports_ingredients()
supports_video_extension()
supports_video_to_video()
supports_scene_builder()
supports_lip_sync()
```

---

# 6. SHARED PROJECT CONFIGURATION

Every project should support:

- Project name
- Niche/category
- Topic
- Target duration
- Language
- Aspect ratio
- Resolution
- Video provider
- Video model
- Clip duration
- Visual style
- Voiceover
- Voice selection
- Voice speed
- Voice pitch
- Dialogue
- SFX
- Ambience
- BGM
- Subtitles
- Lip-sync
- Reference images
- Output format
- Generation priority
- Mandatory/optional scenes

Example:

```json
{
  "project": "My Filipino Horror Story",
  "provider": "snapgen",
  "language": "Filipino",
  "target_duration": 600,
  "aspect_ratio": "16:9",
  "resolution": "720p",
  "clip_duration": 8,
  "reference_images": true,
  "voiceover": true,
  "dialogue": true,
  "sfx": true,
  "bgm": true,
  "lip_sync": true,
  "subtitles": true
}
```

The duration engine must calculate the required generation units based on the selected provider.

Do NOT assume every provider uses the same duration.

---

# 7. STORY ENGINE

The shared Story Engine creates:

1. Title
2. Logline
3. Synopsis
4. Complete story
5. Acts
6. Scenes
7. Narration
8. Dialogue
9. Scene timing
10. Character involvement
11. Environment
12. Emotional progression
13. Visual actions
14. Sound events
15. Ending

The story must be created before provider-specific video prompts.

The system should estimate narration and dialogue duration and build the visual timeline around the actual story.

---

# 8. CHARACTER BIBLE

For every important character generate:

- Name
- Age
- Gender
- Height
- Body type
- Face
- Skin tone
- Hair
- Eyes
- Clothing
- Accessories
- Props
- Personality
- Expression style
- Movement style
- Voice description
- Dialogue behavior
- Continuity rules
- Lip-sync requirements

Character DNA must be available to every provider prompt compiler.

Avoid:

```text
"same character as previous scene"
```

When the provider requires full context, insert the required Character DNA into the compiled prompt.

---

# 9. VISUAL BIBLE

Create a project-wide Visual Bible containing:

- Art direction
- Rendering style
- Color behavior
- Lighting
- Camera language
- Lens behavior
- Environment style
- Texture
- Composition
- Character rendering
- Background rendering
- Motion rules
- Negative constraints
- Continuity rules

The Visual Bible is shared across providers.

The provider adapter converts it into the syntax/format most suitable for that provider.

---

# 10. REFERENCE IMAGE ENGINE

Create reusable project-level reference assets:

1. Main character references
2. Supporting character references
3. Location references
4. Key prop references
5. Visual style references
6. Expression references
7. Pose references
8. Start/end frame references where supported

Each reference asset stores:

- Asset ID
- Character/location ID
- Prompt
- Source
- Resolution
- Aspect ratio
- Version
- QA status

References should be reused whenever possible.

Do not generate a new character reference for every scene unnecessarily.

---

# 11. SCENE PLANNER

Every scene contains:

- Scene ID
- Act
- Sequence
- Purpose
- Duration
- Location
- Time of day
- Characters
- Character actions
- Emotion
- Narration
- Dialogue
- Camera
- Lighting
- Environment
- Props
- SFX events
- BGM state
- Ambience
- References
- Lip-sync required
- Subtitle text
- Provider prompt
- QA status
- Generation status

Supported scene types:

```text
HOOK
ESTABLISHING
CHARACTER_INTRODUCTION
DIALOGUE
REACTION
ACTION
TRANSITION
MONTAGE
CLIMAX
RESOLUTION
```

---

# 12. SCENE COMPLEXITY OPTIMIZER

Short video generation becomes less reliable when too many actions happen simultaneously.

Before generation:

1. Identify the primary action.
2. Identify the primary camera movement.
3. Limit unnecessary character movement.
4. Prefer one primary location.
5. Reduce simultaneous events.
6. Avoid excessive object interaction.
7. Preserve continuity.
8. Split overloaded scenes.

Each scene receives:

```text
LOW
MEDIUM
HIGH
```

risk.

High-risk scenes must be simplified or divided before generation.

---

# 13. PROVIDER-AGNOSTIC PROMPT ENGINE

The shared Prompt Engine creates a normalized scene specification.

The provider adapter then converts that specification into a provider-ready prompt.

Normalized prompt content:

```text
CHARACTER DNA
+
VISUAL DNA
+
REFERENCE INSTRUCTIONS
+
ENVIRONMENT
+
ACTION
+
EMOTION
+
CAMERA
+
LIGHTING
+
COMPOSITION
+
PROPS
+
MOTION
+
CONTINUITY
+
NEGATIVE CONSTRAINTS
```

Do not hard-code provider-specific syntax into the shared story engine.

---

# 14. PROVIDER PIPELINE A — SNAPGEN.AI

## SnapGen Adapter

Provider ID:

```text
snapgen
```

Class:

```text
SnapGenProvider
```

This pipeline is activated ONLY when:

```text
project.provider == "snapgen"
```

Pipeline:

```text
SHARED SCENE
↓
SNAPGEN PROMPT COMPILER
↓
SNAPGEN REFERENCE PREPARATION
↓
SNAPGEN AUTHORIZED SESSION
↓
SNAPGEN GENERATION
↓
DOWNLOAD
↓
VIDEO QA
↓
COMMON AUDIO PIPELINE
↓
LIP-SYNC IF REQUIRED
↓
ASSEMBLY
```

The SnapGen implementation must retain the free-tier safety rules:

- Do not bypass quotas.
- Do not bypass CAPTCHA.
- Do not bypass 2FA.
- Do not bypass anti-bot controls.
- Do not bypass rate limits.
- Do not violate provider restrictions.

Provider configuration must contain:

```text
daily_generation_limit
clip_duration_limits
resolution_limits
model_limits
reset_behavior
concurrent_limit
```

Quota state must be persistent.

When quota is exhausted:

```text
STOP
↓
QUOTA_WAIT
↓
SAVE PROJECT
↓
WAIT FOR RESET
↓
RESUME
```

Completed valid scenes must never be regenerated automatically.

---

# 15. PROVIDER PIPELINE B — META AI / VIBES

## Meta/Vibes Adapter

Provider ID:

```text
meta_vibes
```

Class:

```text
MetaVibesProvider
```

This pipeline is activated ONLY when:

```text
project.provider == "meta_vibes"
```

Provider assumptions from the existing Meta/Vibes specification:

- Base generation unit: 8 seconds
- Generated video is treated as silent in this provider pipeline
- Reference images may be used
- Audio is generated separately
- Voiceover is synchronized separately
- SFX is synchronized separately
- BGM is synchronized separately
- Lip-sync is a separate stage
- No daily quota should be assumed by the core system
- Temporary rate limits and provider capacity must still be monitored

Pipeline:

```text
SHARED SCENE
↓
META/VIBES PROMPT COMPILER
↓
REFERENCE IMAGE PREPARATION
↓
META/VIBES AUTHORIZED SESSION
↓
8-SECOND VIDEO GENERATION
↓
DOWNLOAD
↓
VIDEO QA
↓
VOICEOVER
↓
DIALOGUE
↓
SFX
↓
AMBIENCE
↓
BGM
↓
LIP-SYNC
↓
SUBTITLES
↓
FFMPEG
```

The system should split complex story events into multiple 8-second visual units.

The Meta/Vibes adapter must NOT force audio instructions into the visual prompt when the provider does not generate audio.

---

# 16. PROVIDER PIPELINE C — GOOGLE FLOW

## Google Flow Adapter

Provider ID:

```text
google_flow
```

Class:

```text
GoogleFlowProvider
```

This pipeline is activated ONLY when:

```text
project.provider == "google_flow"
```

Google Flow currently supports video creation from text prompts, ingredients/references, frames, and other video inputs. Current Google documentation also describes Veo 3.1, Gemini Omni, image/reference workflows, video extension, and video-to-video features. Feature availability can vary by model, plan, platform, and region. citeturn0search0turn0search1

The adapter must therefore use a dynamic capability system instead of assuming one fixed Flow configuration.

Possible Flow capabilities include:

```text
TEXT_TO_VIDEO
FRAMES_TO_VIDEO
FIRST_FRAME
FIRST_AND_LAST_FRAME
INGREDIENTS_TO_VIDEO
VIDEO_EXTENSION
VIDEO_TO_VIDEO
NATIVE_AUDIO
VOICE_REFERENCE
CHARACTER_REFERENCE
SCENE_BUILDER
```

Google Flow's current documentation describes using character references and visual "ingredients" to maintain consistent characters and key objects between clips. It also supports start/end frames for controlled transitions where available. citeturn0search0

### Google Flow Pipeline

```text
SHARED SCENE
↓
FLOW CAPABILITY DETECTION
↓
FLOW PROMPT COMPILER
↓
CHARACTER / INGREDIENT PREPARATION
↓
START/END FRAME PREPARATION WHEN NEEDED
↓
FLOW AUTHORIZED SESSION
↓
FLOW VIDEO GENERATION
↓
DOWNLOAD / PROJECT ASSET HANDLING
↓
VIDEO QA
↓
AUDIO MODE DECISION
↓
┌───────────────────────────────────────┐
│ NATIVE AUDIO AVAILABLE / REQUESTED   │
│            ↓                          │
│ Use Flow-generated audio              │
│            OR                         │
│                                       │
│ EXTERNAL AUDIO MODE                   │
│            ↓                          │
│ Shared Voice/SFX/BGM Pipeline         │
└───────────────────────────────────────┘
↓
LIP-SYNC IF REQUIRED
↓
SUBTITLES
↓
FFMPEG
```

### Important Google Flow Audio Rule

Google Flow's current product information states that Veo 3.1 supports native audio. Therefore the unified application must NOT hard-code the Meta/Vibes silent-video assumption onto Google Flow. citeturn0search3

The Flow adapter must expose:

```json
{
  "native_audio": true,
  "external_audio_pipeline": true
}
```

The project may select:

```text
Audio Mode:
( ) Native Provider Audio
( ) External Audio Pipeline
( ) Hybrid
```

If native audio is used, the system still runs audio QA.

If external audio is used, the common audio pipeline creates voiceover/dialogue/SFX/BGM and synchronizes them during final assembly.

### Google Flow Duration Rule

Do not hard-code an 8-second assumption.

Current Google documentation lists multiple supported generation lengths depending on the model and feature. For example, current Veo 3.1 documentation lists 4s, 6s, 8s, and 10s options in supported configurations, while ingredients/reference workflows can have their own restrictions. The adapter must query/configure the active model's capabilities before building generation units. citeturn0search1

Therefore:

```text
Flow generation unit =
provider/model capability
```

not:

```text
always 8 seconds
```

---

# 17. GOOGLE FLOW REFERENCE STRATEGY

The Flow adapter should map the shared Reference Image Engine to the capabilities available in the selected Flow model.

Supported reference concepts can include:

```text
Character references
Visual ingredients
Object references
Location references
Start frame
End frame
Existing video
```

The adapter should prefer reusable project references rather than regenerating references for every scene.

Google documentation specifically describes using ingredients to maintain consistent subjects and key objects across clips. citeturn0search0

The system should store:

```text
flow_reference_asset_id
flow_asset_type
flow_project_reference
source_asset
version
qa_status
```

---

# 18. PROVIDER CAPABILITY MATRIX

The application should maintain a capability registry.

Example:

| Capability | SnapGen.ai | Meta/Vibes | Google Flow |
|---|---|---|---|
| Text-to-video | Configurable | Yes | Yes |
| Reference images | Provider config | Yes | Yes |
| Fixed 8s assumption | No | Yes | No |
| Native audio | Provider config | No in this pipeline | Model-dependent |
| External audio | Yes | Yes | Yes |
| Lip-sync | External stage | External stage | External/optional |
| Start/end frames | Configurable | Configurable | Supported by some Flow models |
| Ingredients | Configurable | Reference images | Yes |
| Video extension | Configurable | Configurable | Supported by some models |
| Video-to-video | Configurable | Configurable | Supported |
| Daily quota | Configurable | None assumed | Credit/capacity configuration |
| Browser automation | If required | If required | If required |
| Mock provider | Yes | Yes | Yes |

This table is configuration-driven.

Do NOT treat it as permanent truth.

Provider capabilities can change.

---

# 19. COMMON AUDIO ENGINE

The audio system is shared.

It must support:

```text
VOICEOVER
DIALOGUE
SFX
AMBIENCE
BGM
SUBTITLES
```

For providers that generate silent video:

```text
VIDEO
+
AUDIO ENGINE
```

For providers that generate native audio:

```text
VIDEO + NATIVE AUDIO
↓
AUDIO QA
↓
OPTIONAL EXTERNAL AUDIO
```

The user must be able to choose whether provider-native audio is retained, replaced, or supplemented.

---

# 20. VOICEOVER ENGINE

For every narration segment store:

- Text
- Speaker
- Start time
- Expected duration
- Actual duration
- Emotion
- Voice
- Pitch
- Speed
- Audio file
- QA status

Actual audio duration must be measured.

If it does not fit:

1. Adjust timing where appropriate.
2. Adjust voice speed within reasonable limits.
3. Split narration.
4. Restructure scene timing.

Do not create unnatural speech simply to force a visual clip duration.

---

# 21. DIALOGUE ENGINE

For each dialogue segment store:

- Character
- Dialogue text
- Start
- End
- Voice
- Emotion
- Speaking intensity
- Lip-sync requirement

Multiple speakers must be represented as separate timeline segments.

---

# 22. SFX ENGINE

Automatically detect sound events from the scene plan.

Examples:

- Door
- Footsteps
- Rain
- Thunder
- Phone
- Explosion
- Impact
- Glass
- Crowd
- Vehicle
- Wind
- Heartbeat

Each SFX stores:

```text
type
start
duration
intensity
source
audio_file
volume
pan
QA
```

---

# 23. AMBIENCE ENGINE

Support:

- Forest
- City
- Classroom
- Office
- Bedroom
- Rain
- Ocean
- Night
- Horror
- Crowd
- Interior room tone

Ambience should loop naturally.

---

# 24. BGM ENGINE

Generate/select BGM based on:

- Genre
- Emotion
- Scene type
- Pacing
- Intensity

Automatically duck BGM beneath speech/dialogue.

---

# 25. LIP-SYNC ENGINE

Lip-sync remains a separate pluggable subsystem.

Pipeline:

```text
CHARACTER VIDEO
+
DIALOGUE AUDIO
↓
LIP-SYNC PROVIDER
↓
LIP-SYNC VIDEO
```

Apply only when:

- Character is visible.
- Character is speaking.
- Mouth is sufficiently visible.
- Dialogue exists.

Do NOT lip-sync:

- Narration over non-speaking characters
- Background characters
- Hidden faces
- Scenes without dialogue

If lip-sync fails:

```text
KEEP ORIGINAL VIDEO
MARK LIP-SYNC FAILED
DO NOT DESTROY SOURCE
```

---

# 26. MASTER TIMELINE

Create one timeline shared by all providers.

Example:

```text
TIME      VIDEO       VOICE       DIALOGUE    SFX       BGM
00:00     Scene 01    Narration   -           Rain      Horror
00:08     Scene 02    -           Character   Door      Tension
00:16     Scene 03    Narration   -           Footstep  Tension
```

Every asset must reference:

```text
scene_id
start_time
end_time
duration
layer_type
sync_status
```

The timeline is provider-independent.

---

# 27. VIDEO + AUDIO SYNCHRONIZATION

After generation:

1. Validate actual clip duration.
2. Update timeline.
3. Align narration.
4. Align dialogue.
5. Align SFX.
6. Align ambience.
7. Align BGM.
8. Generate subtitles.
9. Apply lip-sync.
10. Revalidate.

If provider duration differs from the planned duration, the timeline engine must adapt rather than blindly cutting content.

---

# 28. GENERATION QUEUE

Shared states:

```text
PENDING
READY
SUBMITTED
GENERATING
COMPLETED
DOWNLOADING
DOWNLOADED
VALIDATING
VALID
AUDIO_PENDING
LIPSYNC_PENDING
FINALIZING
FAILED
RETRY
BLOCKED
QUOTA_WAIT
CAPACITY_WAIT
```

Provider-specific jobs must include:

```text
provider
provider_job_id
provider_model
provider_generation_unit
provider_session
```

Jobs survive application restart.

Completed valid assets must never be regenerated automatically.

---

# 29. CAPACITY / QUOTA MANAGER

Use a generic:

```text
ProviderCapacityManager
```

It supports:

```text
daily quota
monthly quota
credits
concurrent generation
rate limits
temporary cooldown
session limits
provider availability
```

Each provider configuration determines which rules are active.

Never bypass:

- Quotas
- CAPTCHA
- 2FA
- Rate limits
- Anti-bot controls
- Account restrictions
- Provider terms

If capacity is exhausted:

```text
STOP
↓
SAVE STATE
↓
WAIT
↓
RESUME WHEN ALLOWED
```

---

# 30. AUTHORIZED ACCOUNT / SESSION MANAGEMENT

If a provider permits multiple accounts, support an authorized account pool.

Store:

- Account ID
- Provider
- Session state
- Permission state
- Capacity/quota state
- Cooldown
- Error count
- Last use

Authentication remains user-controlled.

Do not automate CAPTCHA solving.

Do not bypass 2FA.

Do not store passwords in plaintext.

---

# 31. BROWSER AUTOMATION

Use Playwright where browser automation is required.

Requirements:

- Stable selectors
- Semantic selectors
- Login detection
- Session persistence
- Prompt submission
- Reference upload
- Generation detection
- Error detection
- Quota/rate-limit detection
- Download detection
- Recovery from page reloads

Never use coordinate clicking when a stable selector is available.

Stop and request user intervention when:

- Login is required
- 2FA is required
- CAPTCHA is required
- Human verification is required

Provider browser automation must remain isolated inside its adapter.

---

# 32. DOWNLOAD MANAGER

For every generated video:

1. Download.
2. Verify file exists.
3. Verify file size.
4. Verify readable video stream.
5. Verify duration.
6. Verify metadata.
7. Generate checksum.
8. Associate with scene ID.
9. Mark valid only after QA.

---

# 33. VIDEO QA

Validate:

- File exists
- Duration
- Resolution
- Aspect ratio
- Codec
- Container
- Corruption
- Black frames
- Empty output
- Minimum file size
- Audio presence when expected
- Reference consistency where automated checks are possible

QA result:

```text
status
severity
issue
recommendation
timestamp
```

---

# 34. AUDIO QA

Validate:

- Audio exists when expected
- Duration
- Sample rate
- Channels
- Clipping
- Silence
- Voice intelligibility
- BGM level
- SFX level
- Sync offset

Native provider audio and externally generated audio use the same QA interface.

---

# 35. RETRY / REPAIR ENGINE

Never blindly regenerate.

Analyze the failure.

Visual repairs:

- Simplify action
- Simplify camera
- Reduce characters
- Simplify environment
- Improve references
- Shorten prompt
- Repair continuity

Audio repairs:

- Adjust voice speed
- Split narration
- Lower BGM
- Reposition SFX
- Regenerate voice segment

Lip-sync repairs:

- Improve face crop
- Reduce dialogue length
- Retry
- Switch lip-sync provider

Provider-specific repair rules belong in the provider adapter.

---

# 36. NICHE TEMPLATE SYSTEM

Initial templates:

```text
Drama / Romance
Horror
Finance
Stickman
Kids Stories
Animal Stories
Motivation
Comedy
Educational
History
Mystery
```

Each template can control:

- Story structure
- Pacing
- Visual style
- Audio style
- SFX style
- BGM style
- Narration behavior
- Dialogue behavior
- Lip-sync frequency

New templates must be addable without modifying the core engine.

---

# 37. PROJECT PERSISTENCE

Store:

```text
project.json
story/
characters/
visual_bible/
references/
scenes/
prompts/
jobs/
video/
audio/
lipsync/
subtitles/
timeline/
qa/
provider/
logs/
output/
```

Example:

```text
AI_VIDEO_FACTORY/
├── app/
│   ├── ui/
│   ├── api/
│   ├── core/
│   ├── providers/
│   │   ├── base/
│   │   ├── snapgen/
│   │   ├── meta_vibes/
│   │   └── google_flow/
│   ├── story/
│   ├── scenes/
│   ├── prompts/
│   ├── references/
│   ├── queue/
│   ├── quota/
│   ├── audio/
│   │   ├── voice/
│   │   ├── dialogue/
│   │   ├── sfx/
│   │   ├── ambience/
│   │   ├── bgm/
│   │   └── mixer/
│   ├── lipsync/
│   ├── subtitles/
│   ├── downloader/
│   ├── qa/
│   └── assembly/
├── projects/
├── config/
├── database/
├── logs/
├── tests/
└── README.md
```

---

# 38. PROVIDER CONFIGURATION

Provider-specific configuration must be externalized.

Example:

```yaml
providers:

  snapgen:
    enabled: true
    clip_duration: configurable
    reference_images: configurable
    native_audio: configurable
    quota_mode: configured
    browser_automation: true

  meta_vibes:
    enabled: true
    clip_duration: 8
    reference_images: true
    native_audio: false
    external_audio: true
    quota_mode: none
    browser_automation: true

  google_flow:
    enabled: true
    capability_detection: true
    native_audio: model_dependent
    reference_images: true
    ingredients: true
    frames: true
    quota_mode: credits
    browser_automation: true
```

These values are examples and must be verified against the active provider configuration/capabilities at runtime.

---

# 39. DASHBOARD

The single UI should display:

```text
PROJECTS
CREATE PROJECT
CURRENT PROJECT

STORY
CHARACTERS
VISUAL BIBLE
REFERENCES
SCENES
PROMPTS

VIDEO PROVIDER
MODEL
PROVIDER STATUS

VIDEO GENERATION
VOICEOVER
DIALOGUE
SFX
BGM
AMBIENCE
LIP-SYNC
SUBTITLES

TIMELINE
QUEUE
QUOTA / CAPACITY
QA
FAILED JOBS
RETRY

FINAL OUTPUT
REPORT
LOGS
```

Provider selector:

```text
VIDEO ENGINE

[ SnapGen.ai ▼ ]

Available:
✓ SnapGen.ai
✓ Meta AI / Vibes
✓ Google Flow
```

When the user changes provider, the UI should display that provider's capabilities.

---

# 40. PROVIDER-SPECIFIC PIPELINE VISUALIZATION

The dashboard should make the selected pipeline obvious.

### SnapGen

```text
STORY
 ↓
SCENES
 ↓
SNAPGEN
 ↓
VIDEO
 ↓
AUDIO
 ↓
LIPSYNC
 ↓
ASSEMBLY
```

### Meta AI / Vibes

```text
STORY
 ↓
SCENES
 ↓
REFERENCE IMAGES
 ↓
8s META/VIBES VIDEO
 ↓
VIDEO QA
 ↓
VOICE
 ↓
SFX
 ↓
BGM
 ↓
LIPSYNC
 ↓
ASSEMBLY
```

### Google Flow

```text
STORY
 ↓
SCENES
 ↓
FLOW CAPABILITY CHECK
 ↓
INGREDIENTS / FRAMES / REFERENCES
 ↓
FLOW VIDEO
 ↓
NATIVE AUDIO OR EXTERNAL AUDIO
 ↓
LIPSYNC IF REQUIRED
 ↓
SUBTITLES
 ↓
ASSEMBLY
```

---

# 41. TESTING

Create tests for:

- Story generation
- Character Bible
- Visual Bible
- Scene planning
- Prompt compilation
- Provider routing
- Provider capability detection
- Reference management
- Queue
- Persistence
- Quota/capacity
- Video generation
- Voiceover
- Dialogue
- SFX
- BGM
- Timeline
- Subtitles
- Lip-sync
- Audio mixing
- FFmpeg
- Final QA

Every provider must have a mock provider implementation.

Automated tests must not consume real generation credits.

---

# 42. SECURITY

Never:

- Store passwords in plaintext
- Expose session cookies
- Log secrets
- Commit credentials
- Bypass authentication
- Bypass provider restrictions

Use:

- Environment variables
- Secure session storage
- Secret redaction
- Permission checks
- Safe logging

---

# 43. FINAL ASSEMBLY

The shared assembly engine should:

1. Sort clips by scene order.
2. Select valid video assets.
3. Apply lip-sync outputs when available.
4. Align voiceover.
5. Align dialogue.
6. Add SFX.
7. Add ambience.
8. Add BGM.
9. Duck BGM under speech.
10. Add subtitles.
11. Add transitions where appropriate.
12. Normalize audio.
13. Render final video.
14. Validate final output.

Keep intermediate files.

Never destroy original provider outputs.

---

# 44. FINAL REPORT

Generate:

- Project ID
- Provider used
- Model used
- Target duration
- Actual duration
- Number of scenes
- Number of video units
- Successful generations
- Failed generations
- Retries
- Skipped optional scenes
- Quota/capacity usage
- Reference assets
- Voice segments
- Dialogue segments
- SFX
- BGM
- Lip-sync jobs
- Subtitle status
- Final QA
- Errors
- Warnings
- Final video path

---

# 45. DEVELOPMENT RULES

Before coding:

1. Inspect the existing repository.
2. Identify current architecture.
3. Do not overwrite working code blindly.
4. Create a technical implementation plan.
5. Implement incrementally.
6. Test each module.
7. Integrate only after module tests pass.
8. Keep provider-specific code isolated.
9. Keep shared logic provider-agnostic.
10. Persist all project state.
11. Use mock providers for testing.
12. Do not hard-code provider limits.
13. Query or configure provider capabilities.
14. Never mix provider-specific assumptions into the shared pipeline.
15. Prefer simple reliable implementations over unnecessary complexity.

---

# 46. ACCEPTANCE CRITERIA

The unified system is functional when a user can:

1. Create a project.
2. Enter a topic.
3. Select a niche.
4. Select target duration.
5. Select a video provider.
6. Select a model where supported.
7. Generate a story.
8. Generate Character Bible.
9. Generate Visual Bible.
10. Generate reference assets.
11. Generate scene plan.
12. Generate provider-ready prompts.
13. Route generation to the selected provider.
14. Generate video clips.
15. Track every generation job.
16. Download and validate clips.
17. Generate or retain appropriate audio.
18. Generate voiceover.
19. Generate dialogue.
20. Generate SFX.
21. Add ambience.
22. Add BGM.
23. Apply lip-sync where required.
24. Generate subtitles.
25. Synchronize the master timeline.
26. Assemble the final video.
27. Run final QA.
28. Pause safely on quota/capacity limits.
29. Resume later without regenerating valid completed assets.
30. Export the finished video.
31. Add another provider later without rewriting the core engine.

---

# 47. CRITICAL ARCHITECTURAL RULE

The most important rule of this project:

## DO NOT BUILD THREE SEPARATE VIDEO FACTORIES.

Build:

```text
ONE AI VIDEO FACTORY
        +
ONE SHARED ORCHESTRATION CORE
        +
MULTIPLE PROVIDER ADAPTERS
```

Specifically:

```text
                  AI VIDEO FACTORY
                         │
             ┌───────────┴───────────┐
             │   SHARED CORE         │
             │                       │
             │ Story                 │
             │ Characters            │
             │ Visual Bible          │
             │ Scenes                │
             │ References            │
             │ Timeline              │
             │ Audio                 │
             │ QA                    │
             │ Assembly              │
             └───────────┬───────────┘
                         │
                  PROVIDER ROUTER
                         │
       ┌─────────────────┼─────────────────┐
       │                 │                 │
       ▼                 ▼                 ▼
   SNAPGEN          META/VIBES       GOOGLE FLOW
   ADAPTER            ADAPTER           ADAPTER
       │                 │                 │
       ▼                 ▼                 ▼
   SnapGen            8-sec           Flow/Veo/
   Pipeline            Pipeline        Omni Pipeline
       │                 │                 │
       └─────────────────┼─────────────────┘
                         ▼
                  COMMON VIDEO QA
                         │
                  COMMON AUDIO
                         │
                    LIP-SYNC
                         │
                    SUBTITLES
                         │
                      FFMPEG
                         │
                   FINAL VIDEO
```

The user selects the provider.

The system activates only that provider's generation pipeline.

Everything else remains shared.

---

# 48. FUTURE PROVIDER EXTENSION

A new provider should require only:

```text
providers/
└── new_provider/
    ├── adapter.py
    ├── capabilities.py
    ├── prompt_compiler.py
    ├── reference_handler.py
    ├── browser.py
    ├── downloader.py
    └── config.yaml
```

The core application should not need to be rewritten.

Future providers could include any service that exposes an authorized workflow compatible with the provider interface.

---

# 49. FINAL SYSTEM GOAL

The final product is:

## AI VIDEO FACTORY

A single application where the user can say:

> "Create a 10-minute Filipino horror story."

Then select:

```text
Video Engine:
[ SnapGen.ai ]
[ Meta AI / Vibes ]
[ Google Flow ]
```

The system automatically handles:

```text
STORY
↓
CHARACTERS
↓
VISUAL BIBLE
↓
SCENES
↓
REFERENCE ASSETS
↓
PROVIDER-SPECIFIC PROMPTS
↓
SELECTED VIDEO ENGINE
↓
VIDEO QA
↓
VOICE
↓
DIALOGUE
↓
SFX
↓
AMBIENCE
↓
BGM
↓
LIP-SYNC
↓
SUBTITLES
↓
MASTER TIMELINE
↓
FFMPEG
↓
FINAL VIDEO
↓
FINAL QA
```

The provider is replaceable.

The project is not.

The AI Video Factory remains the orchestration layer, while SnapGen.ai, Meta AI/Vibes, and Google Flow are interchangeable video-generation backends.
