"""
AI Video Factory - Core Configuration Module
"""
import os
from pathlib import Path
from typing import Any, Dict, Optional

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings


class AppConfig(BaseModel):
    """Application configuration"""
    name: str = "AI Video Factory"
    version: str = "1.0.0"
    debug: bool = False
    log_level: str = "INFO"


class DatabaseConfig(BaseModel):
    """Database configuration"""
    url: str = "sqlite+aiosqlite:///./database/ai_video_factory.db"
    echo: bool = False


class ServerConfig(BaseModel):
    """Server configuration"""
    host: str = "0.0.0.0"
    port: int = 8000
    workers: int = 1


class StorageConfig(BaseModel):
    """Storage paths configuration"""
    projects_dir: str = "./projects"
    downloads_dir: str = "./downloads"
    output_dir: str = "./output"
    sessions_dir: str = "./sessions"
    logs_dir: str = "./logs"


class DefaultsConfig(BaseModel):
    """Default generation settings"""
    clip_duration: int = 8
    aspect_ratio: str = "16:9"
    resolution: str = "720p"
    language: str = "English"
    output_format: str = "mp4"


class RetryConfig(BaseModel):
    """Retry configuration"""
    max_retries: int = 3
    retry_delay: int = 5
    exponential_backoff: bool = True


class QuotaConfig(BaseModel):
    """Quota check configuration"""
    check_interval: int = 60
    warning_threshold: int = 2


class BrowserConfig(BaseModel):
    """Browser automation configuration"""
    headless: bool = False
    timeout: int = 30000
    slow_mo: int = 100
    user_agent: str = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"


class FFmpegConfig(BaseModel):
    """FFmpeg configuration"""
    path: str = "ffmpeg"
    ffprobe_path: str = "ffprobe"
    threads: int = 4
    preset: str = "medium"
    crf: int = 23


class SecurityConfig(BaseModel):
    """Security configuration"""
    secret_key: str = "CHANGE_ME_IN_PRODUCTION"
    session_expire_minutes: int = 60
    max_upload_size_mb: int = 100


class Config(BaseSettings):
    """Main configuration class"""
    app: AppConfig = Field(default_factory=AppConfig)
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)
    server: ServerConfig = Field(default_factory=ServerConfig)
    storage: StorageConfig = Field(default_factory=StorageConfig)
    defaults: DefaultsConfig = Field(default_factory=DefaultsConfig)
    retry: RetryConfig = Field(default_factory=RetryConfig)
    quota: QuotaConfig = Field(default_factory=QuotaConfig)
    browser: BrowserConfig = Field(default_factory=BrowserConfig)
    ffmpeg: FFmpegConfig = Field(default_factory=FFmpegConfig)
    security: SecurityConfig = Field(default_factory=SecurityConfig)
    
    # Runtime base directory
    base_dir: Path = Field(default_factory=lambda: Path(__file__).parent.parent.parent)
    
    class Config:
        env_prefix = "AIVF_"
        env_file = ".env"
        env_file_encoding = "utf-8"


def load_yaml_config(config_path: str) -> Dict[str, Any]:
    """Load configuration from YAML file"""
    path = Path(config_path)
    if not path.exists():
        return {}
    
    with open(path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f) or {}


def get_config() -> Config:
    """Get application configuration"""
    base_dir = Path(__file__).parent.parent.parent
    
    # Load default config
    default_config_path = base_dir / "config" / "default.yaml"
    default_config = load_yaml_config(str(default_config_path))
    
    # Load environment-specific config if exists
    env = os.getenv("AIVF_ENV", "development")
    env_config_path = base_dir / "config" / f"{env}.yaml"
    env_config = load_yaml_config(str(env_config_path))
    
    # Merge configurations (env overrides default)
    merged = {**default_config, **env_config}
    
    # Create config object
    config = Config(
        base_dir=base_dir,
        app=AppConfig(**merged.get('app', {})),
        database=DatabaseConfig(**merged.get('database', {})),
        server=ServerConfig(**merged.get('server', {})),
        storage=StorageConfig(**merged.get('storage', {})),
        defaults=DefaultsConfig(**merged.get('defaults', {})),
        retry=RetryConfig(**merged.get('retry', {})),
        quota=QuotaConfig(**merged.get('quota', {})),
        browser=BrowserConfig(**merged.get('browser', {})),
        ffmpeg=FFmpegConfig(**merged.get('ffmpeg', {})),
        security=SecurityConfig(**merged.get('security', {})),
    )
    
    # Resolve storage paths relative to base_dir
    config.storage.projects_dir = str(base_dir / config.storage.projects_dir)
    config.storage.downloads_dir = str(base_dir / config.storage.downloads_dir)
    config.storage.output_dir = str(base_dir / config.storage.output_dir)
    config.storage.sessions_dir = str(base_dir / config.storage.sessions_dir)
    config.storage.logs_dir = str(base_dir / config.storage.logs_dir)
    
    return config


# Global config instance
_config: Optional[Config] = None


def get_or_init_config() -> Config:
    """Get or initialize global config instance"""
    global _config
    if _config is None:
        _config = get_config()
    return _config
