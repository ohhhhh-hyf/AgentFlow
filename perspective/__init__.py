"""Shared perspective modeling package."""
from .agent import PerspectiveModelingAgent
from .contracts import PERSPECTIVE_MODELING_GENERATION_OUTPUT_CONTRACT
from .models import EMPTY_PERSPECTIVE_MODELING, PerspectiveModeling
from .hits import (
    Hit,
    HitTable,
    build_hit_table,
    foreign_only,
    attribute_to_speaker,
    render_action_groups_block,
    render_hit_block,
    slice_transcript_for_person,
    speaker_blocks,
)
from .preferences import (
    BLOCK_TITLE as PREFERENCE_BLOCK_TITLE,
    CHANNEL_TITLE as USER_CHANNEL_TITLE,
    PREFERENCE_LINES,
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
    "PERSONAL_VIEW_DIRECTIVE",
    "SYNTH_LINES",
    "Hit",
    "HitTable",
    "USER_CHANNEL_TITLE",
    "VIEW_DIRECTIVE_TITLE",
    "address_aliases",
    "build_hit_table",
    "foreign_only",
    "build_preference_block",
    "build_user_channel",
    "attribute_to_speaker",
    "render_action_groups_block",
    "render_hit_block",
    "skip_reason",
    "slice_transcript_for_person",
    "speaker_blocks",
    "synthesize_perspective_profile",
]
