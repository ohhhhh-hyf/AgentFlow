"""高中题库检索。给 notes.quiz 用，也可单独调用。

    from tools.exercise_search import ExerciseSearchTool

    tool = ExerciseSearchTool()
    bundle = tool.search_for_notes(
        notes,
        subject="数学",
        difficulty="适中",
        qtype="单选题",
    )
    bundle.questions / bundle.query_label
"""

from .catalog import HighSchoolCatalog, default_catalog, load_catalog
from .client import get_questions
from .match import build_spec, difficulty_code, parse_difficulty, parse_grade
from .tool import (
    BankQuestion,
    ExerciseSearchTool,
    SearchBundle,
    html_to_text,
    search_for_notes,
)

__all__ = [
    "BankQuestion",
    "ExerciseSearchTool",
    "HighSchoolCatalog",
    "SearchBundle",
    "build_spec",
    "default_catalog",
    "get_questions",
    "html_to_text",
    "load_catalog",
    "difficulty_code",
    "parse_difficulty",
    "parse_grade",
    "search_for_notes",
]
