"""Shared perspective modeling package."""
from .agent import PerspectiveModelingAgent
from .contracts import PERSPECTIVE_MODELING_GENERATION_OUTPUT_CONTRACT
from .models import EMPTY_PERSPECTIVE_MODELING, PerspectiveModeling
from .personal_contracts import (
    PERSONAL_DRAFT_UNDERSTANDING_FIELDS,
    PERSONAL_PERSPECTIVE_GENERATION_OUTPUT_CONTRACT,
    PERSONAL_PROFILE_FIELDS,
    PERSONAL_UNDERSTANDING_FIELDS,
    PersonalPerspectiveGenerationContract,
)
from .personal_models import (
    EMPTY_PERSONAL_PERSPECTIVE,
    PERSONAL_PERSPECTIVE_FIELDS,
    PersonalPerspective,
)
from .personal_prompts import (
    PERSONAL_PERSPECTIVE_MODELING_SYSTEM_PROMPT,
    PERSONAL_PERSPECTIVE_PROMPT_VERSION,
)
from .personal_evidence import (
    PERSONAL_EVIDENCE_FULL_LIMIT,
    build_personal_evidence_pack,
)
from .hits import (
    DialogueBlock,
    Hit,
    HitTable,
    build_hit_table,
    detect_personal_perspective_track,
    foreign_only,
    is_anonymous_speaker,
    parse_speaker_dialogue_blocks,
    attribute_to_speaker,
    render_action_groups_block,
    render_hit_block,
    render_radar_block,
    resolve_anonymous_speakers_by_handshake,
    slice_transcript_for_person,
    speaker_blocks,
)
from .preferences import (
    BLOCK_TITLE as PREFERENCE_BLOCK_TITLE,
    CHANNEL_TITLE as USER_CHANNEL_TITLE,
    PREFERENCE_LINES,
    address_aliases,
    build_preference_block,
    build_user_channel,
)
from .prompts import PERSPECTIVE_MODELING_SYSTEM_PROMPT
from .synth import SYNTH_LINES, skip_reason, synthesize_perspective_profile

__all__ = [
    "PerspectiveModelingAgent",
    "PerspectiveModeling",
    "EMPTY_PERSPECTIVE_MODELING",
    "PERSPECTIVE_MODELING_GENERATION_OUTPUT_CONTRACT",
    "PERSPECTIVE_MODELING_SYSTEM_PROMPT",
    "PersonalPerspective",
    "EMPTY_PERSONAL_PERSPECTIVE",
    "PERSONAL_PERSPECTIVE_FIELDS",
    "PersonalPerspectiveGenerationContract",
    "PERSONAL_PERSPECTIVE_GENERATION_OUTPUT_CONTRACT",
    "PERSONAL_PROFILE_FIELDS",
    "PERSONAL_UNDERSTANDING_FIELDS",
    "PERSONAL_DRAFT_UNDERSTANDING_FIELDS",
    "PERSONAL_PERSPECTIVE_MODELING_SYSTEM_PROMPT",
    "PERSONAL_PERSPECTIVE_PROMPT_VERSION",
    "PERSONAL_EVIDENCE_FULL_LIMIT",
    "build_personal_evidence_pack",
    "PREFERENCE_BLOCK_TITLE",
    "PREFERENCE_LINES",
    "SYNTH_LINES",
    "DialogueBlock",
    "Hit",
    "HitTable",
    "USER_CHANNEL_TITLE",
    "address_aliases",
    "build_hit_table",
    "detect_personal_perspective_track",
    "foreign_only",
    "is_anonymous_speaker",
    "parse_speaker_dialogue_blocks",
    "build_preference_block",
    "build_user_channel",
    "attribute_to_speaker",
    "render_action_groups_block",
    "render_hit_block",
    "render_radar_block",
    "resolve_anonymous_speakers_by_handshake",
    "skip_reason",
    "slice_transcript_for_person",
    "speaker_blocks",
    "synthesize_perspective_profile",
]
