"""
AI Video Factory - Database Models

Core database models for projects, scenes, jobs, and quota tracking.
"""
from datetime import datetime
from enum import Enum
from typing import Optional, List, Dict, Any

from sqlalchemy import (
    Column, Integer, String, Float, DateTime, ForeignKey, 
    Text, Boolean, JSON, Enum as SQLEnum
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship

Base = declarative_base()


class JobStatus(str, Enum):
    """Generation job status states"""
    PENDING = "PENDING"
    READY = "READY"
    SUBMITTED = "SUBMITTED"
    GENERATING = "GENERATING"
    COMPLETED = "COMPLETED"
    DOWNLOADING = "DOWNLOADING"
    DOWNLOADED = "DOWNLOADED"
    VALIDATING = "VALIDATING"
    VALID = "VALID"
    FAILED = "FAILED"
    RETRY = "RETRY"
    BLOCKED = "BLOCKED"
    QUOTA_WAIT = "QUOTA_WAIT"


class SceneType(str, Enum):
    """Scene type classifications"""
    HOOK = "HOOK"
    ESTABLISHING = "ESTABLISHING"
    CHARACTER_INTRODUCTION = "CHARACTER_INTRODUCTION"
    DIALOGUE = "DIALOGUE"
    REACTION = "REACTION"
    ACTION = "ACTION"
    TRANSITION = "TRANSITION"
    MONTAGE = "MONTAGE"
    CLIMAX = "CLIMAX"
    RESOLUTION = "RESOLUTION"
    NORMAL_WORLD = "NORMAL_WORLD"
    STRANGE_EVENT = "STRANGE_EVENT"
    INVESTIGATION = "INVESTIGATION"
    ESCALATION = "ESCALATION"
    REVEAL = "REVEAL"
    MEET = "MEET"
    RELATIONSHIP = "RELATIONSHIP"
    CONFLICT = "CONFLICT"
    SEPARATION = "SEPARATION"
    PROBLEM = "PROBLEM"
    EXPLANATION = "EXPLANATION"
    EXAMPLE = "EXAMPLE"
    MISTAKE = "MISTAKE"
    SOLUTION = "SOLUTION"
    CTA = "CTA"
    SETUP = "SETUP"
    ADVENTURE = "ADVENTURE"
    JOURNEY = "JOURNEY"
    TURNING_POINT = "TURNING_POINT"
    LESSON = "LESSON"
    MISUNDERSTANDING = "MISUNDERSTANDING"
    PUNCHLINE = "PUNCHLINE"
    QUESTION = "QUESTION"
    DEMONSTRATION = "DEMONSTRATION"
    SUMMARY = "SUMMARY"
    CONTEXT = "CONTEXT"
    EVENT = "EVENT"
    DEVELOPMENT = "DEVELOPMENT"
    CONSEQUENCE = "CONSEQUENCE"
    CLUES = "CLUES"
    ENDING = "ENDING"
    INTRODUCTION = "INTRODUCTION"


class SceneImportance(str, Enum):
    """Scene importance for retry logic"""
    MANDATORY = "MANDATORY"
    OPTIONAL = "OPTIONAL"


class RiskLevel(str, Enum):
    """Scene complexity risk levels"""
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class Project(Base):
    """Project model"""
    __tablename__ = "projects"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Project configuration
    niche = Column(String(100))
    topic = Column(Text)
    target_duration = Column(Integer)  # in seconds
    language = Column(String(50), default="English")
    aspect_ratio = Column(String(20), default="16:9")
    resolution = Column(String(20), default="720p")
    model = Column(String(100))
    clip_duration = Column(Integer, default=8)
    visual_style = Column(Text)
    voiceover = Column(Boolean, default=True)
    voice_selection = Column(String(100))
    subtitles = Column(Boolean, default=False)
    background_music = Column(Boolean, default=False)
    output_format = Column(String(20), default="mp4")
    generation_priority = Column(String(20), default="balanced")
    
    # Provider settings
    provider_name = Column(String(100))
    account_id = Column(Integer, ForeignKey("accounts.id"))
    
    # Story data (JSON for flexibility)
    story_data = Column(JSON)  # Contains title, logline, synopsis, acts, scenes
    character_bible = Column(JSON)  # Character definitions
    visual_bible = Column(JSON)  # Visual style guide
    
    # Status
    status = Column(String(50), default="draft")  # draft, generating, completed, failed
    progress = Column(Float, default=0.0)  # 0-100
    
    # Output
    final_video_path = Column(String(500))
    final_report = Column(JSON)
    
    # Relationships
    scenes = relationship("Scene", back_populates="project", cascade="all, delete-orphan")
    jobs = relationship("GenerationJob", back_populates="project", cascade="all, delete-orphan")


class Scene(Base):
    """Scene model"""
    __tablename__ = "scenes"
    
    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Scene identification
    scene_number = Column(Integer, nullable=False)
    act_number = Column(Integer, default=1)
    scene_type = Column(SQLEnum(SceneType), nullable=False)
    importance = Column(SQLEnum(SceneImportance), default=SceneImportance.MANDATORY)
    
    # Scene content
    purpose = Column(Text)
    duration = Column(Float)  # in seconds
    location = Column(Text)
    time_of_day = Column(String(50))
    characters = Column(JSON)  # List of character IDs involved
    character_actions = Column(Text)
    emotion = Column(String(100))
    dialogue_narration = Column(Text)
    camera = Column(Text)
    lighting = Column(Text)
    environment = Column(Text)
    props = Column(JSON)
    transition = Column(Text)
    
    # Prompt data
    prompt = Column(Text)
    prompt_repaired = Column(Text)
    
    # Complexity
    risk_level = Column(SQLEnum(RiskLevel), default=RiskLevel.LOW)
    risk_factors = Column(JSON)
    
    # Continuity
    continuity_notes = Column(Text)
    previous_scene_id = Column(Integer, ForeignKey("scenes.id"))
    
    # Generation status
    qa_status = Column(String(50))
    generation_status = Column(String(50), default="pending")
    retry_count = Column(Integer, default=0)
    error_message = Column(Text)
    
    # Output
    video_path = Column(String(500))
    video_checksum = Column(String(64))
    video_metadata = Column(JSON)
    qa_result = Column(JSON)
    
    # Relationships
    project = relationship("Project", back_populates="scenes")
    job = relationship("GenerationJob", back_populates="scene", uselist=False)
    previous_scene = relationship("Scene", remote_side=[id])


class GenerationJob(Base):
    """Generation job queue model"""
    __tablename__ = "generation_jobs"
    
    id = Column(Integer, primary_key=True, index=True)
    scene_id = Column(Integer, ForeignKey("scenes.id"), nullable=False, unique=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Job state
    status = Column(SQLEnum(JobStatus), default=JobStatus.PENDING)
    priority = Column(Integer, default=0)
    
    # Provider info
    provider_name = Column(String(100))
    account_id = Column(Integer, ForeignKey("accounts.id"))
    provider_job_id = Column(String(255))  # ID from the provider
    
    # Timing
    submitted_at = Column(DateTime)
    started_at = Column(DateTime)
    completed_at = Column(DateTime)
    
    # Retry tracking
    retry_count = Column(Integer, default=0)
    max_retries = Column(Integer, default=3)
    last_error = Column(Text)
    
    # Quota tracking
    quota_used = Column(Integer, default=1)
    
    # Relationships
    project = relationship("Project", back_populates="jobs")
    scene = relationship("Scene", back_populates="job")


class Account(Base):
    """Authorized provider account model"""
    __tablename__ = "accounts"
    
    id = Column(Integer, primary_key=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Account info
    provider_name = Column(String(100), nullable=False)
    account_name = Column(String(255), nullable=False)
    email = Column(String(255))
    
    # Status
    is_active = Column(Boolean, default=True)
    is_authorized = Column(Boolean, default=False)
    requires_attention = Column(Boolean, default=False)
    attention_reason = Column(Text)  # CAPTCHA, 2FA, etc.
    
    # Session storage (encrypted)
    session_data = Column(Text)  # Encrypted session cookies/tokens
    session_expires = Column(DateTime)
    
    # Usage tracking
    last_used = Column(DateTime)
    error_count = Column(Integer, default=0)
    cooldown_until = Column(DateTime)
    
    # Permissions
    permissions = Column(JSON)
    
    # Relationships
    jobs = relationship("GenerationJob", back_populates="account")
    quotas = relationship("QuotaTracking", back_populates="account", cascade="all, delete-orphan")


class QuotaTracking(Base):
    """Provider quota tracking model"""
    __tablename__ = "quota_tracking"
    
    id = Column(Integer, primary_key=True, index=True)
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Quota info
    provider_name = Column(String(100), nullable=False)
    quota_type = Column(String(100))  # daily, hourly, etc.
    
    # Limits
    limit_value = Column(Integer)
    used_value = Column(Integer, default=0)
    remaining_value = Column(Integer)
    
    # Reset info
    reset_time = Column(DateTime)
    reset_period = Column(String(50))  # daily, hourly, etc.
    
    # Status
    is_exhausted = Column(Boolean, default=False)
    warning_sent = Column(Boolean, default=False)
    
    # Relationships
    account = relationship("Account", back_populates="quotas")


class QAResult(Base):
    """Video QA result model"""
    __tablename__ = "qa_results"
    
    id = Column(Integer, primary_key=True, index=True)
    scene_id = Column(Integer, ForeignKey("scenes.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Validation results
    file_exists = Column(Boolean)
    duration = Column(Float)
    resolution = Column(String(20))
    aspect_ratio = Column(String(20))
    codec = Column(String(50))
    container = Column(String(20))
    file_size = Column(Integer)
    
    # Quality checks
    has_corruption = Column(Boolean, default=False)
    has_audio = Column(Boolean)
    has_black_frames = Column(Boolean, default=False)
    is_empty = Column(Boolean, default=False)
    
    # Overall status
    status = Column(String(50))  # pass, fail, warning
    severity = Column(String(20))  # critical, major, minor, none
    issues = Column(JSON)  # List of issues found
    recommendations = Column(Text)
    
    # Metadata
    validated_at = Column(DateTime, default=datetime.utcnow)
    validator_version = Column(String(20))


class LogEntry(Base):
    """Application log entry model"""
    __tablename__ = "log_entries"
    
    id = Column(Integer, primary_key=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    
    # Log info
    level = Column(String(20))  # DEBUG, INFO, WARNING, ERROR, CRITICAL
    module = Column(String(100))
    message = Column(Text)
    context = Column(JSON)
    
    # Optional references
    project_id = Column(Integer, ForeignKey("projects.id"))
    job_id = Column(Integer, ForeignKey("generation_jobs.id"))
    scene_id = Column(Integer, ForeignKey("scenes.id"))
