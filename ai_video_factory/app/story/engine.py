"""Story Engine adapter layer — Pinoy reek drama engine with Taglish dialogue.

Defines the ``StoryEngine`` ABC and the default ``HermesStoryEngine`` plus
``PinoyDramaStoryEngine`` that produces Pinoy reek drama stories with:
- 4 characters (Aling Nena, Kiko, Mia, Apo Lola) with locked outfits/props
- Taglish (Tagalog-English) dialogue per scene
- Background per scene from Filipino household/neighborhood settings
- 1 scene per 8 seconds (9:16 vertical, narrations baked into prompt)
- Continuity DNA: character names, outfits, props, background per scene
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

import yaml

from app.story.models import Act, Character, CharacterBible, Scene, StoryDoc, VisualBible

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Adapter interface (the seam)
# ---------------------------------------------------------------------------


class StoryEngine(ABC):
    @abstractmethod
    def generate_story(self, topic: str, niche: str, target_seconds: int) -> StoryDoc:
        """Produce a fully-structured story (acts + scenes + narration)."""

    @abstractmethod
    def generate_character_bible(self, story: StoryDoc) -> CharacterBible:
        """Produce the character bible (appearance/clothing/props)."""

    @abstractmethod
    def generate_visual_bible(
        self, story: StoryDoc, character_bible: CharacterBible,
    ) -> VisualBible:
        """Produce visual bible (color/lighting/camera style/aspect ratio)."""


# ---------------------------------------------------------------------------
# Pinoy Drama Story Engine — 4 characters, Taglish, 1 scene per 8s
# ---------------------------------------------------------------------------


class PinoyDramaStoryEngine(StoryEngine):
    """Free-tier story engine for Pinoy drama shorts.

    Produces:
    - 4 characters with locked outfits/props for consistency
    - Taglish (Tagalog-English) dialogue per scene
    - Background per scene from Filipino household/neighborhood
    - 1 scene per 8 seconds (scene_count = ceil(target_seconds / 8))
    - Continuity DNA: character_names, background, outfit, props per scene
    """

    CLIP_SECONDS = 8.0
    ASPECT_RATIO = "9:16"

    # 4 characters with locked outfits/props for consistency
    _CHARACTERS = CharacterBible(
        characters=[
            Character(
                name="Aling Nena",
                appearance=(
                    "Matang woman, warm face with natural makeup, sweat on forehead "
                    "from market work. Friendly but concerned expression."
                ),
                clothing=(
                    "White work blouse with floral print, dark blue skirt, "
                    "simple gold necklace, hair in neat bun with loose strands."
                ),
                props=["Oblong plastic bag with market goods", "Worn slippers"],
            ),
            Character(
                name="Kiko",
                appearance=(
                    "Lanky young man, tired eyes, stubble on chin, slouched posture. "
                    "Restless energy, avoids eye contact."
                ),
                clothing=(
                    "Faded black band t-shirt (slightly oversized), grey joggers, "
                    "scuffed canvas shoes, silver ring on right hand."
                ),
                props=["Cellphone with cracked screen", "Ballpoint pen"],
            ),
            Character(
                name="Mia",
                appearance=(
                    "Petite girl, long dark hair in ponytail, bright observant eyes. "
                    "Wears modified school uniform. Bright, hopeful expression."
                ),
                clothing=(
                    "White blouse with school emblem, grey pleated skirt, "
                    "black ribbon in hair, simple stud earrings."
                ),
                props=["Small notebook", "Pencil case"],
            ),
            Character(
                name="Apo Lola",
                appearance=(
                    "Elderly woman, kind wrinkled face, silver hair in braid, calm "
                    "presence. Sits quietly, observes everything with gentle smile."
                ),
                clothing=(
                    "Traditional Filipino terno dress in subdued colors, "
                    "knit shawl over shoulders, simple earrings."
                ),
                props=["Rosary beads", "Small hand fan"],
            ),
        ],
        notes=(
            "4 characters in same household. Outfits, props, and gestures locked "
            "across all scenes for consistency. Continuity DNA: character name + "
            "outfit + props + background per scene."
        ),
    )

    # Filipino household/neighborhood backgrounds — 12 settings
    _BACKGROUNDS = [
        "Interior of modest Filipino house living room, afternoon light through window, "
        "family photos on wall, ceiling fan slowly turning, simple wooden furniture",

        "Kitchen area of Filipino home, small gas stove, plate of leftover food on table, "
        "cup of coffee, afternoon light through curtains, family calendar on wall",

        "Street scene outside Filipino neighborhood, narrow road, jeepney in distance, "
        "tricycle passing, sari-sari store with goods outside, children playing",

        "Market area, crowded stalls with goods, vendors calling out, "
        "baskets of vegetables and fruits, sunlight through awning, people with bags",

        "Bedroom of Filipino home, small room with bunk bed, "
        "fan overhead, family pictures on wall, notebook on bedside table",

        "Front yard of Filipino house, concrete ground, small garden with "
        "ornamental plants, wooden gate, afternoon shadows, quiet street",

        "Prayer corner in Filipino home, religious images on wall, candle, bench, "
        "soft light, calm spiritual atmosphere",

        "Neighborhood basketball court, cemented court, makeshift hoops, "
        "afternoon sun, teenagers playing in background",

        "Sari-sari store porch, goods neatly arranged, owner sitting, "
        "afternoon light, neighborhood activity passing",

        "Concrete stairs in Filipino neighborhood, wall with faded paint, "
        "vine growing on wall, afternoon atmosphere",

        "Inside Filipino home at dusk, dim light, ceiling fan, "
        "family gathered, television in background, calm evening",

        "Outdoor area at sunset, golden light, silhouettes of houses, "
        "distant church bell, peaceful ending atmosphere",
    ]

    # Taglish dialogue per scene index
    _DIALOGUE = [
        # Scene 0
        ("Aling Nena", "Anak, kailangan mo na yang pera para sa school supplies ni Mia?"),
        ("Kiko", "Ay nako, tatay, wala na akong pambili. Hindi ko alam kung paano ko sasabihin 'to."),
        # Scene 1
        ("Aling Nena", "Nakakainis talaga ang buhay no? Parang lahat ng plano, nagka-unti-unti ang natitira."),
        ("Mia", "Tay, hindi ka na dapat mag-alala. May bagian din tayo sa Diyos."),
        # Scene 2
        ("Kiko", "Grabe, akala ko kaya ko 'to, pero parang nalulungkot na ako. Parang wala nang pag-asa."),
        ("Apo Lola", "Huwag kang mag-alala, apo. May plano ang Diyos — hindi mo kailangan intindihin lahat."),
        # Scene 3
        ("Aling Nena", "Tingnan mo, Mia. Kung makikita mo ang mga bagay na nasa paligid mo, may halaga ang lahat. Kahit maliit."),
        ("Mia", "Tama si Lola, Tay. Basta tayo magtulungan, kaya nating overcome ang lahat."),
        # Scene 4
        ("Kiko", "Akala ko kasi ayoko na, pero when I see you, nananatili pa rin ang hope sa puso ko."),
        ("Aling Nena", "Love ko 'yan sa iyo, anak. Kahit anong mangyari, kayo ang pangarap ko."),
        # Scene 5
        ("Mia", "Tay, next week may scholarship opportunity ako. Pwede kitang tulungan doon."),
        ("Kiko", "Grabe, Mio? Talagang may pag-asa pa? Salamat, anak. Ibibigay ko lahat ng makakaya ko."),
        # Scene 6
        ("Apo Lola", "Remember, sa bawat pagsubok, may aral. Hindi tayo nag-iisa sa pagsubok na 'to."),
        ("Aling Nena", "Tama si Lola. Handa tayong harapin ang lahat, sama-sama."),
        # Scene 7
        ("Kiko", "Promise ko sa inyo, hiharap ko ang lahat. Gamitin ko ang lahat ng natutunan ko."),
        ("Mia", "We're in this together, Tay. Kaya mo 'yan. We believe in you."),
        # Scene 8 — climax
        ("Aling Nena", "Sabi ni Apo Lola, may pag-asa pa. Let's trust the process. Kaya nating harapin ang lahat."),
        ("Kiko", "Promise. From now on, I won't give up. Para sa pamilya ko."),
        # Scene 9 — resolution
        ("Mia", "Look at us now, Tay. Stronger than ever. We did it together."),
        ("Apo Lola", "And that is how family should be. Mahalaga ang unity."),
    ]

    # Narration (voiceover) per scene — drives audio in Veo prompt
    _NARRATION = [
        "A family gathering in a modest Filipino home. The air thick with unspoken words.",
        "Another day in the life of a family trying to make ends meet.",
        "Shadows of doubt begin to creep into their hearts.",
        "A moment of truth emerges amidst everyday struggles.",
        "Hope flickers in the darkness like a candle in the wind.",
        "The family faces their fears together, hand in hand.",
        "A glimmer of light at the end of the tunnel.",
        "Love and unity bind them through the storm.",
        "A promise made, a promise kept. The family stands strong.",
        "The journey continues, but they are not alone.",
    ]

    # Scene titles
    _TITLES = [
        "The Gathering", "Morning Light", "Whispers in the Kitchen",
        "At the Market", "The Bedroom Confession", "In the Front Yard",
        "Prayer Time", "Basketball Court Drama", "Sari-Sari Store Stories",
        "Stairway to Hope", "Dusk Falls", "Sunset Promise",
    ]

    def generate_story(self, topic: str, niche: str, target_seconds: int) -> StoryDoc:
        n_scenes = max(2, -(-int(target_seconds) // int(self.CLIP_SECONDS)))
        n_scenes = min(n_scenes, 60)  # cap at 60 scenes (8 min)

        scenes: list[Scene] = []
        for i in range(n_scenes):
            bg = self._BACKGROUNDS[i % len(self._BACKGROUNDS)]
            chars = self._characters_for_scene(i, n_scenes)
            outfit = self._outfit_for_scene(chars)
            props = self._props_for_scene(chars)
            dialogue = self._dialogue_for_scene(i)
            narration = self._NARRATION[i % len(self._NARRATION)]

            dialogue_text = " ".join(
                f"{speaker}: \"{line}\"" for speaker, line in dialogue
            )

            continuity = {
                "characters": chars,
                "outfits": {name: self._outfit_for_character(name) for name in chars},
                "background": bg,
                "dialogue_language": "Taglish (Tagalog-English)",
                "aspect_ratio": self.ASPECT_RATIO,
            }

            scenes.append(
                Scene(
                    scene_number=i + 1,
                    act_number=self._act_number(i, n_scenes),
                    title=self._TITLES[i % len(self._TITLES)],
                    description=f"Pinoy drama scene {i+1}: {bg[:80]}...",
                    narration_text=f"[VOICEOVER]: {narration}\n\n[DIALOGUE]: {dialogue_text}",
                    narration_seconds=self.CLIP_SECONDS,
                    target_clip_seconds=self.CLIP_SECONDS,
                    characters=chars,
                    background_scene=bg,
                    outfit_description=outfit,
                    props_list=props,
                    dialogue_lines=dialogue,
                    continuity_dna=continuity,
                )
            )

        acts = self._build_acts(scenes, topic, niche)
        return StoryDoc(
            topic=topic,
            niche=niche,
            target_seconds=target_seconds,
            title=f"Pinoy Drama: {topic.replace('_', ' ').title()}",
            logline=f"Isang maikling kwento ng pamilyang Pinoy — {topic}.",
            acts=acts,
        )

    def _characters_for_scene(self, idx: int, total: int) -> list[str]:
        if total <= 2:
            return ["Aling Nena", "Kiko"]
        if idx < total * 0.3:
            return ["Aling Nena", "Kiko"]
        if idx < total * 0.6:
            return ["Aling Nena", "Kiko", "Mia"]
        if idx < total * 0.85:
            return ["Aling Nena", "Kiko", "Mia", "Apo Lola"]
        return ["Aling Nena", "Kiko", "Mia"]

    def _outfit_for_character(self, name: str) -> str:
        char = next((c for c in self._CHARACTERS.characters if c.name == name), None)
        if char:
            return f"{name}: {char.clothing}. Carrying: {', '.join(char.props)}."
        return f"{name}: no specific outfit."

    def _outfit_for_scene(self, chars: list[str]) -> str:
        return " | ".join(self._outfit_for_character(c) for c in chars) + " |"

    def _props_for_scene(self, chars: list[str]) -> list[str]:
        props = []
        for name in chars:
            char = next((c for c in self._CHARACTERS.characters if c.name == name), None)
            if char:
                props.extend(char.props)
        return list(dict.fromkeys(props))

    def _dialogue_for_scene(self, idx: int) -> list[tuple[str, str]]:
        start = (idx * 2) % len(self._DIALOGUE)
        lines = []
        for i in range(2):
            s = start + i
            if s < len(self._DIALOGUE):
                lines.append(self._DIALOGUE[s])
        return lines

    def _act_number(self, idx: int, total: int) -> int:
        if total <= 3:
            return 1
        if idx < total * 0.4:
            return 1
        if idx < total * 0.75:
            return 2
        return 3

    def _build_acts(self, scenes: list[Scene], topic: str, niche: str) -> list[Act]:
        acts_map: dict[int, list[Scene]] = {}
        for s in scenes:
            acts_map.setdefault(s.act_number, []).append(s)
        return [
            Act(
                act_number=num,
                title=f"Act {num}",
                summary=f"Pinoy drama — {topic}.",
                scenes=members,
            )
            for num, members in sorted(acts_map.items())
        ]

    def generate_character_bible(self, story: StoryDoc) -> CharacterBible:
        return self._CHARACTERS

    def generate_visual_bible(
        self, story: StoryDoc, character_bible: CharacterBible,
    ) -> VisualBible:
        return VisualBible(
            color_palette=["warm_golden_hour", "indoor_natural", "subtle_shadows"],
            lighting="natural_indoor_afternoon_light_with_soft_shadows",
            camera_style="continuous_shot_cinematic_vertical_9x16",
            notes=(
                "Pinoy drama: warm natural light, continuous shots, 9:16 vertical. "
                "Character consistency: same outfit/props/background per scene. "
                "8-second clips. Taglish dialogue in prompt. SFX: ambient Filipino street sounds, "
                "household sounds, emotional BGM."
            ),
            aspect_ratio=self.ASPECT_RATIO,
        )


# ---------------------------------------------------------------------------
# Generic HermesStoryEngine (existing stub, kept for compatibility)
# ---------------------------------------------------------------------------


class HermesStoryEngine(StoryEngine):
    """Default free-tier engine — delegates to Hermes subagent (stubbed for now)."""

    DEFAULT_TEMPLATE_DIR = "config/templates"
    DEFAULT_MODEL = "poolside/laguna-s-2.1:free"

    def __init__(
        self,
        template_dir: str | Path = DEFAULT_TEMPLATE_DIR,
        model: str = DEFAULT_MODEL,
        config: dict[str, Any] | None = None,
    ) -> None:
        self.template_dir = Path(template_dir)
        self.model = model
        self._template_cache: dict[str, dict[str, Any]] = {}
        self._hermes_config: dict[str, Any] = (
            config if config is not None else self._load_story_yaml()
        )

    @staticmethod
    def _load_story_yaml(path: str | Path = "config/story.yaml") -> dict[str, Any]:
        story_yaml = Path(path)
        if not story_yaml.exists():
            return {}
        with open(story_yaml) as f:
            data = yaml.safe_load(f) or {}
        return data.get("hermes", {})

    def load_template(self, niche: str) -> dict[str, Any]:
        if niche in self._template_cache:
            return self._template_cache[niche]
        template_path = self.template_dir / f"{niche}.yaml"
        if not template_path.exists():
            raise FileNotFoundError(f"Template not found for niche '{niche}': {template_path}")
        with open(template_path) as f:
            data = yaml.safe_load(f)
        if not isinstance(data, dict):
            raise TypeError(f"Template {template_path} did not parse to a dict")
        self._template_cache[niche] = data
        return data

    def _model_preferences(self, niche: str) -> str:
        prefs = self._hermes_config.get("model_preferences", {})
        return str(prefs.get(niche, prefs.get("default", self.DEFAULT_MODEL)))

    def generate_story(self, topic: str, niche: str, target_seconds: int) -> StoryDoc:
        template = self.load_template(niche)
        logger.info(
            "HermesStoryEngine.generate_story [STUB] — topic=%r, niche=%r, "
            "target=%ds, model=%s",
            topic, niche, target_seconds, self._model_preferences(niche),
        )

        pacing = str(template.get("story_structure", {}).get("pacing", "moderate"))
        mood = str(template.get("visual_guidance", {}).get("mood", "tense"))
        beats = template.get("scene_types") or ["exposition", "climax"]
        structure = template.get("story_structure", {})
        n_acts = max(1, int(structure.get("acts", 1) or 1))
        clip_s = 8.0
        n_scenes = min(15, max(2, -(-int(target_seconds) // int(clip_s))))

        narr_templates = {
            "exposition": f"In a {pacing} tale of {niche}, something stirs around {topic}.",
            "rising_tension": "The air grows cooler. Something is watching.",
            "jump_scare": "A sudden sound breaks the silence.",
            "revelation": "The truth reveals itself in the shadows.",
            "climax": "Everything converges. There is no escape.",
        }

        scenes: list[Scene] = []
        for i in range(n_scenes):
            st = str(beats[i % len(beats)])
            label = st.replace("_", " ")
            scenes.append(
                Scene(
                    scene_number=i + 1,
                    act_number=min(n_acts, 1 + (i * n_acts) // n_scenes),
                    title=label.title(),
                    description=f"{label}: a {mood} moment around {topic}.",
                    narration_text=narr_templates.get(st, f"The {label} deepens around {topic}."),
                    narration_seconds=5.0,
                    target_clip_seconds=clip_s,
                )
            )

        acts: list[Act] = []
        for a in range(1, n_acts + 1):
            members = [s for s in scenes if s.act_number == a]
            if members:
                acts.append(
                    Act(
                        act_number=a,
                        title=f"Act {a}",
                        summary=f"A {niche} story about {topic} — act {a}.",
                        scenes=members,
                    )
                )

        return StoryDoc(
            topic=topic,
            niche=niche,
            target_seconds=target_seconds,
            title=f"The {topic.replace('_', ' ').title()}",
            logline=f"A {niche} story where {topic} awakens a darkness.",
            acts=acts,
        )

    def generate_character_bible(self, story: StoryDoc) -> CharacterBible:
        template = self.load_template(story.niche)
        mood = str(template.get("visual_guidance", {}).get("mood", "unsettling"))
        return CharacterBible(
            characters=[
                Character(
                    name="The Protagonist",
                    appearance="Unseen silhouette, ordinary clothing, cautious demeanor.",
                    clothing="Casual dark clothing suitable for nighttime",
                    props=["Flashlight", "Phone (dead battery)"],
                )
            ],
            notes=f"Visual style: {mood}.",
        )

    def generate_visual_bible(
        self, story: StoryDoc, character_bible: CharacterBible,
    ) -> VisualBible:
        template = self.load_template(story.niche)
        vg = template.get("visual_guidance", {})
        return VisualBible(
            color_palette=list(vg.get("color_palette", ["black", "deep_red"])),
            lighting=str(vg.get("lighting", "low_contrast")),
            camera_style=str(vg.get("camera_style", "tight_closeups")),
            notes=str(vg.get("mood")) if vg.get("mood") else None,
            aspect_ratio=str(vg.get("recommended_aspect_ratio"))
            if vg.get("recommended_aspect_ratio")
            else None,
        )


# ---------------------------------------------------------------------------
# Factory / registry
# ---------------------------------------------------------------------------

_ENGINE_REGISTRY: dict[str, type[StoryEngine]] = {
    "hermes": HermesStoryEngine,
    "pinoy_drama": PinoyDramaStoryEngine,
}


def register_engine(name: str, cls: type[StoryEngine]) -> None:
    _ENGINE_REGISTRY[name] = cls


def get_story_engine(
    engine_name: str | None = None,
    config_path: str | Path = "config/story.yaml",
) -> StoryEngine:
    resolved: str
    if engine_name is None:
        cfg_path = Path(config_path)
        if cfg_path.exists():
            with open(cfg_path) as f:
                data = yaml.safe_load(f) or {}
            resolved = str(data.get("engine", "hermes"))
        else:
            resolved = "hermes"
    else:
        resolved = engine_name

    cls = _ENGINE_REGISTRY.get(resolved)
    if cls is None:
        raise ValueError(
            f"Unknown story engine '{resolved}'. Registered: {sorted(_ENGINE_REGISTRY)}"
        )
    return cls()
