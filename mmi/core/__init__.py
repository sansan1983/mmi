"""mmi core —— 记忆引擎层，与 UI 无关的核心代码。"""

from mmi.core.classifier import ClassificationResult, classify_session, is_trash
from mmi.core.config import get_default_model, load_config, save_config, set_default_model
from mmi.core.context import (
    LoadedContext,
    LoaderConfig,
    build_context,
    build_context_detailed,
    compose_messages,
    estimate_tokens,
)
from mmi.core.gc import GcReport, gc_all, gc_cold, gc_trash, gc_zombies
from mmi.core.heat import apply_heat_and_state, compute_heat, derive_state, sort_by_heat
from mmi.core.i18n import detect_lang, t
from mmi.core.search import fuzzy_match_scores, search_top_k, tokenize
from mmi.core.session import Session, SessionMeta, SessionState, new_session_id, utcnow_iso
from mmi.core.storage import (
    SessionCorrupt,
    SessionNotFound,
    StorageError,
    append_turn,
    delete_session,
    list_session_ids,
    move_to_trash,
    parse_turns,
    read_meta,
    read_session,
    update_access,
    write_session,
)
from mmi.core.summarizer import schedule_summary_update, should_update_summary, update_summary
from mmi.core.titler import generate_title

__all__ = [
    "Session", "SessionMeta", "SessionState", "new_session_id", "utcnow_iso",
    "SessionNotFound", "SessionCorrupt", "StorageError",
    "append_turn", "delete_session", "list_session_ids", "move_to_trash",
    "parse_turns", "read_meta", "read_session", "update_access", "write_session",
    "apply_heat_and_state", "compute_heat", "derive_state", "sort_by_heat",
    "LoadedContext", "LoaderConfig", "build_context", "build_context_detailed",
    "compose_messages", "estimate_tokens",
    "schedule_summary_update", "should_update_summary", "update_summary",
    "gc_all", "gc_cold", "gc_trash", "gc_zombies", "GcReport",
    "fuzzy_match_scores", "search_top_k", "tokenize",
    "generate_title",
    "ClassificationResult", "classify_session", "is_trash",
    "get_default_model", "load_config", "save_config", "set_default_model",
    "detect_lang", "t",
]
