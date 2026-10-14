"""Shared perspective modeling package."""
from .agent import PerspectiveModelingAgent
from .contracts import PERSPECTIVE_MODELING_GENERATION_OUTPUT_CONTRACT
from .models import EMPTY_PERSPECTIVE_MODELING, PerspectiveModeling
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
    PERSONAL_TEMPLATE_VIEW_DIRECTIVE,
    PERSONAL_VIEW_DIRECTIVE,
    VIEW_DIRECTIVE_TITLE,
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
    "PREFERENCE_BLOCK_TITLE",
    "PREFERENCE_LINES",
    "PERSONAL_TEMPLATE_VIEW_DIRECTIVE",
    "PERSONAL_VIEW_DIRECTIVE",
    "SYNTH_LINES",
    "DialogueBlock",
    "Hit",
    "HitTable",
    "USER_CHANNEL_TITLE",
    "VIEW_DIRECTIVE_TITLE",
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
