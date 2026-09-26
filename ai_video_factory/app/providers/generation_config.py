"""Generation configuration dataclass.

Holds the production-wide generation settings (aspect ratio, resolution,
output count, model) with defaults from the master prompt:
  - aspect_ratio: "9:16"   (Shorts/Reels vertical)
  - resolution:  "1080p"
  - output_count: 1        (x1 — single output)
  - model:       "Veo 3.1 - Lite"
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class GenerationConfig:
    """Production-wide generation settings.

    Defaults match the master prompt:
      aspect_ratio="9:16", resolution="1080p", output_count=1, model="Veo 3.1 - Lite"
    """

    aspect_ratio: str = "9:16"
    resolution: str = "1080p"
    output_count: int = 1  # x1, x2, x3, x4 — number of variations to generate
    model: str = "Veo 3.1 - Lite"
    clip_seconds: float = 10.0  # duration per clip in seconds

    # Image-specific (Nano Banana 2)
    image_aspect_ratio: str = "9:16"  # crop_9_16 toggle for image gen

    # Extra metadata passthrough
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict for JSON/metadata storage."""
        return {
            "aspect_ratio": self.aspect_ratio,
            "resolution": self.resolution,
            "output_count": self.output_count,
            "model": self.model,
            "clip_seconds": self.clip_seconds,
            "image_aspect_ratio": self.image_aspect_ratio,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> GenerationConfig:
        """Deserialize from dict."""
        return cls(
            aspect_ratio=d.get("aspect_ratio", "9:16"),
            resolution=d.get("resolution", "1080p"),
            output_count=int(d.get("output_count", 1)),
            model=d.get("model", "Veo 3.1 - Lite"),
            clip_seconds=float(d.get("clip_seconds", 10.0)),
            image_aspect_ratio=d.get("image_aspect_ratio", "9:16"),
            extra=d.get("extra", {}),
        )

    @classmethod
    def pinoy_kanto_defaults(cls) -> GenerationConfig:
        """Master prompt defaults for Pinoy Kanto Shorts Drama.

        From the production master prompt §3:
          aspect_ratio: 9:16
          resolution: 1080p
          clip_duration: 8-10s (preferred 8)
          output_count: 1 (x1 — user instruction)
          model: Veo 3.1 - Lite
        """
        return cls(
            aspect_ratio="9:16",
            resolution="1080p",
            output_count=1,  # x1 per user instruction
            model="Veo 3.1 - Lite",
            clip_seconds=10.0,  # max clip duration
            image_aspect_ratio="9:16",
        )
