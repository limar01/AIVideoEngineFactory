# AI Video Factory

A modular, free-tier-oriented AI Video Factory that converts high-level user requests into complete video production pipelines.

## Overview

The AI Video Factory takes user inputs such as "Create a 10-minute horror story" and automatically:

1. Generates the story with acts and scenes
2. Creates Character and Visual Bibles for consistency
3. Optimizes scenes for AI video generation
4. Manages provider quotas and accounts
5. Generates video clips through authorized provider sessions
6. Downloads, validates, and assembles clips into final video

## Architecture

```
USER → VIDEO FACTORY UI → PROJECT CONFIG → STORY ENGINE → CHARACTER BIBLE → VISUAL BIBLE
    ↓
SCENE PLANNER → SCENE OPTIMIZER → PROMPT COMPILER → QUOTA MANAGER → GENERATION QUEUE
    ↓
VIDEO PROVIDER → DOWNLOAD MANAGER → VIDEO QA → RETRY/REPAIR → FFMPEG ASSEMBLY → FINAL VIDEO
```

## Project Structure

```
AI_VIDEO_FACTORY/
├── app/
│   ├── ui/              # Frontend components (React)
│   ├── api/             # FastAPI routes and schemas
│   ├── core/            # Configuration, database, logging
│   ├── providers/       # Video provider adapters
│   │   ├── base/        # Provider interface
│   │   ├── mock/        # Mock provider for testing
│   │   └── snapgen/     # SnapGen provider (example)
│   ├── story/           # Story, character, visual bible engines
│   ├── scenes/          # Scene planning and optimization
│   ├── prompts/         # Prompt compilation and QA
│   ├── queue/           # Generation queue management
│   ├── accounts/        # Account pool management
│   ├── quota/           # Quota tracking
│   ├── downloader/      # Download manager
│   ├── qa/              # Video quality assurance
│   └── assembly/        # FFmpeg assembly
├── projects/            # Project data storage
├── config/              # Configuration files
├── database/            # SQLite database
├── logs/                # Application logs
├── tests/               # Test suites
└── README.md
```

## Features

### Core Features
- **Project Configuration**: Flexible project setup with niche, duration, language, aspect ratio, and more
- **Story Engine**: Automatic story generation with acts, scenes, and narration timing
- **Character Bible**: Detailed character definitions for visual consistency
- **Visual Bible**: Art direction and style guidelines
- **Scene Planner**: Break stories into optimized scenes
- **Scene Complexity Optimizer**: Reduce risk by simplifying complex scenes
- **Prompt Compiler**: Generate provider-ready prompts with full context
- **Continuity Engine**: Track and maintain visual continuity

### Free-Tier Management
- **Quota Manager**: Track and respect provider limits
- **Account Pool**: Manage multiple authorized accounts (when permitted)
- **Pause/Resume**: Safely pause on quota exhaustion, resume later
- **No Regeneration**: Never regenerate valid completed clips

### Generation Pipeline
- **Provider Adapters**: Modular provider interface
- **Job Queue**: Persistent job management with retry logic
- **Download Manager**: Verify and validate downloads
- **Video QA**: Check duration, resolution, corruption, etc.
- **Retry/Repair**: Intelligently repair failed prompts
- **FFmpeg Assembly**: Concatenate clips with audio/subtitles

### Niche Templates
Pre-built templates for:
- Drama/Romance
- Horror
- Finance/Business
- Stickman Animation
- Kids Stories
- Animal Stories
- Motivation/Inspiration
- Comedy
- Educational
- History/Documentary
- Mystery/Thriller

## Installation

### Prerequisites
- Python 3.10+
- Node.js 18+ (for frontend)
- FFmpeg
- Playwright browsers

### Backend Setup

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Install Playwright browsers
playwright install

# Configure environment
cp .env.example .env
# Edit .env with your settings

# Run database migrations
# (Auto-runs on first start)

# Start server
python -m app.main
```

### Frontend Setup

```bash
cd frontend  # (To be created)
npm install
npm run dev
```

## Configuration

### Main Config (`config/default.yaml`)

```yaml
app:
  name: "AI Video Factory"
  version: "1.0.0"
  debug: false

database:
  url: "sqlite+aiosqlite:///./database/ai_video_factory.db"

server:
  host: "0.0.0.0"
  port: 8000

storage:
  projects_dir: "./projects"
  downloads_dir: "./downloads"
  output_dir: "./output"

defaults:
  clip_duration: 8
  aspect_ratio: "16:9"
  resolution: "720p"
```

### Provider Config (`config/providers.yaml`)

Configure provider-specific limits and settings:

```yaml
mock:
  enabled: true
  max_daily_generations: 1000
  clip_duration_limits:
    min: 2
    max: 30

snapgen:
  enabled: false
  max_daily_generations: 10
  clip_duration_limits:
    min: 3
    max: 10
```

## Usage

### API Endpoints (to be implemented)

- `POST /api/projects` - Create new project
- `GET /api/projects/{id}` - Get project details
- `POST /api/projects/{id}/generate-story` - Generate story
- `POST /api/projects/{id}/generate-scenes` - Generate scenes
- `POST /api/projects/{id}/start-generation` - Start video generation
- `GET /api/projects/{id}/status` - Get generation status
- `GET /api/jobs` - List generation jobs
- `POST /api/jobs/{id}/retry` - Retry failed job

### Example Project Creation

```json
{
  "name": "My Horror Story",
  "niche": "horror",
  "topic": "Abandoned hospital at night",
  "target_duration": 600,
  "language": "English",
  "aspect_ratio": "16:9",
  "resolution": "720p",
  "model": "veo3.1-fast",
  "clip_duration": 8,
  "voiceover": true,
  "subtitles": false,
  "provider_name": "mock"
}
```

## Development

### Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=app

# Run specific test module
pytest tests/unit/test_queue.py
```

### Code Style

```bash
# Format code
black app/ tests/

# Lint code
flake8 app/ tests/

# Type checking
mypy app/
```

## Important Notes

### Free-Tier Compliance

This system is designed to **respect** provider limitations:

- ❌ Does NOT bypass quotas, CAPTCHAs, or rate limits
- ❌ Does NOT automate 2FA or human verification
- ❌ Does NOT circumvent terms of service
- ✅ Tracks quota usage accurately
- ✅ Pauses when limits are reached
- ✅ Resumes when quota resets
- ✅ Supports multiple accounts only when permitted

### Security

- Session data is encrypted
- Passwords are never stored in plaintext
- Secrets are managed via environment variables
- Sensitive data is redacted from logs

## Roadmap

### Phase 1: Core Infrastructure ✅
- [x] Project structure
- [x] Configuration system
- [x] Database models
- [x] Provider interface
- [x] Mock provider
- [x] Queue manager

### Phase 2: Story & Bible Engines
- [ ] Story generation engine
- [ ] Character Bible generator
- [ ] Visual Bible generator

### Phase 3: Scene Pipeline
- [ ] Scene planner with templates
- [ ] Scene complexity optimizer
- [ ] Prompt compiler
- [ ] Continuity engine

### Phase 4: Provider Integration
- [ ] SnapGen provider implementation
- [ ] Browser automation with Playwright
- [ ] Session management

### Phase 5: Download & QA
- [ ] Download manager
- [ ] Video QA with FFprobe
- [ ] Retry/repair engine

### Phase 6: Assembly
- [ ] FFmpeg integration
- [ ] Audio mixing
- [ ] Subtitle burning

### Phase 7: Frontend
- [ ] React dashboard
- [ ] Project management UI
- [ ] Generation monitoring

### Phase 8: Testing & Polish
- [ ] Comprehensive test suite
- [ ] Documentation
- [ ] Performance optimization

## License

MIT License - See LICENSE file for details

## Contributing

Contributions welcome! Please read CONTRIBUTING.md for guidelines.
