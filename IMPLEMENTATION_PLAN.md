# AI Video Factory - Technical Implementation Plan

## Phase 1: Core Infrastructure (Week 1)
### 1.1 Project Structure Setup
- Create directory structure as per spec
- Initialize Python backend with FastAPI
- Initialize React frontend with TypeScript
- Set up SQLite database schema
- Configure logging and environment management

### 1.2 Configuration System
- JSON/YAML configuration loader
- Provider configuration templates
- Quota configuration storage
- Environment variable management

### 1.3 Database Layer
- Project model
- Scene model
- Job model
- Account model
- Quota tracking model
- Migration system

## Phase 2: Story & Bible Engines (Week 2)
### 2.1 Story Engine
- LLM provider abstraction
- Story generation pipeline
- Act/scene breakdown
- Narration timing calculation

### 2.2 Character Bible
- Character DNA generation
- Continuity rules
- Provider-specific formatting

### 2.3 Visual Bible
- Art direction generation
- Style consistency rules
- Camera language definition

## Phase 3: Scene Planning & Optimization (Week 3)
### 3.1 Scene Planner
- Scene template system
- Niche-specific templates
- Scene type classification

### 3.2 Scene Complexity Optimizer
- Risk scoring algorithm
- Scene simplification logic
- Scene splitting when needed

### 3.3 Prompt Compiler
- Provider adapter interface
- Prompt assembly logic
- Provider-specific formatting
- Prompt QA validation

### 3.4 Continuity Engine
- State tracking
- Conflict detection
- Resolution suggestions

## Phase 4: Generation Queue & Quota Management (Week 4)
### 4.1 Generation Queue
- Job state machine
- Persistence layer
- Priority handling
- Retry logic

### 4.2 Free-Tier Quota Manager
- Quota tracking
- Reset time calculation
- Account rotation (when permitted)
- Pause/resume logic

### 4.3 Authorized Account Pool
- Secure session storage
- Account status tracking
- Permission management

## Phase 5: Provider Integration (Week 5)
### 5.1 Provider Interface
- Abstract base class
- Required operations definition
- Error handling patterns

### 5.2 Mock Provider
- Testing support
- Simulated delays
- Configurable success/failure

### 5.3 SnapGen Provider (Example)
- Playwright browser automation
- Session management
- Generation submission
- Status polling
- Result download

## Phase 6: Browser Automation (Week 6)
### 6.1 Playwright Integration
- Browser session management
- Selector strategies
- State detection

### 6.2 Authentication Flow
- Login detection
- 2FA handling (user intervention)
- CAPTCHA detection (user intervention)
- Session persistence

### 6.3 Generation Monitoring
- Progress detection
- Error detection
- Quota exhaustion detection
- Recovery strategies

## Phase 7: Download & QA (Week 7)
### 7.1 Download Manager
- File download
- Integrity verification
- Metadata storage

### 7.2 Video QA
- FFprobe integration
- Validation rules
- Quality scoring
- Issue reporting

### 7.3 Retry/Repair Engine
- Failure analysis
- Prompt repair strategies
- Retry limits
- Optional vs mandatory handling

## Phase 8: Video Assembly (Week 8)
### 8.1 FFmpeg Integration
- Clip sorting
- Format normalization
- Concatenation
- Audio mixing
- Subtitle burning

### 8.2 Final Output
- Rendering pipeline
- Quality validation
- Export options

## Phase 9: Frontend Dashboard (Week 9-10)
### 9.1 Project Management
- Create/edit projects
- Configuration UI
- Template selection

### 9.2 Story & Bible Viewer
- Story display
- Character bible
- Visual bible

### 9.3 Scene Management
- Scene list
- Prompt editing
- Status tracking

### 9.4 Generation Dashboard
- Queue visualization
- Progress tracking
- Quota display
- Account status

### 9.5 Results & Reports
- Video preview
- QA results
- Final report
- Download links

## Phase 10: Testing & Polish (Week 11-12)
### 10.1 Unit Tests
- All core modules
- Provider mocks
- Edge cases

### 10.2 Integration Tests
- Full pipeline tests
- Error recovery
- Persistence tests

### 10.3 Documentation
- API documentation
- User guide
- Provider integration guide

---

## Implementation Priority

### Sprint 1: Foundation
1. Project structure
2. Configuration system
3. Database models
4. Basic API endpoints

### Sprint 2: Story Generation
1. LLM abstraction
2. Story engine
3. Character bible
4. Visual bible

### Sprint 3: Scene Pipeline
1. Scene planner
2. Complexity optimizer
3. Prompt compiler
4. Continuity engine

### Sprint 4: Queue & Quota
1. Job queue
2. Quota manager
3. Account pool

### Sprint 5: Provider Layer
1. Provider interface
2. Mock provider
3. SnapGen provider

### Sprint 6: Browser & Download
1. Playwright setup
2. Download manager
3. Video QA

### Sprint 7: Assembly & Frontend
1. FFmpeg assembly
2. React dashboard
3. Integration

### Sprint 8: Testing & Polish
1. Comprehensive tests
2. Bug fixes
3. Documentation
