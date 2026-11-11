"""The llm_execution gate. Any internal failure lets the call through: a budget plugin must never
be the reason an agent stops working."""
from __future__ import annotations

import logging
import time
import uuid
from types import SimpleNamespace
from typing import Any, Callable, Optional

from .core import Ledger, load_config, model_counts, window_bounds

logger = logging.getLogger(__name__)
BLOCKABLE_API_MODES = {"chat_completions", None, ""}


def synthetic_response(text: str, model: Optional[str]) -> SimpleNamespace:
    """An OpenAI-shaped final answer: the turn ends here and the provider is never called."""
    message = SimpleNamespace(role="assistant", content=text, tool_calls=None)
    choice = SimpleNamespace(index=0, message=message, finish_reason="stop")
    return SimpleNamespace(id=f"cron-budget-{uuid.uuid4().hex}", object="chat.completion",
                           model=model or "cron-budget", choices=[choice], usage=None)


def notice_text(job_name: str, reason: str, decision: Any, resets_at: Any) -> str:
    if reason == "job_limit":
        detail = f"this job used {decision.job_used} requests in the current window"
    else:
        detail = (f"{decision.used} requests are used and the rest is reserved for chat "
                  f"(cron cap {decision.cron_cap})")
    return (f"⏸️ cron-budget held \"{job_name}\": {detail}. "
            f"Runs make no model calls until the window resets at {resets_at:%H:%M %Z}. "
            "Check with `hermes cron-budget status`.")


class Gate:
    def __init__(self, ctx: Any, ledger_factory: Callable[[], Ledger] = Ledger) -> None:
        self.ctx = ctx
        self._ledger_factory = ledger_factory
        self._ledger: Optional[Ledger] = None

    @property
    def ledger(self) -> Ledger:
        if self._ledger is None:
            self._ledger = self._ledger_factory()
        return self._ledger

    def _cron(self) -> Any:
        return self.ctx.current_cron_execution()

    def llm_execution(self, request: Any = None, next_call: Optional[Callable] = None,
                      model: Optional[str] = None, provider: Optional[str] = None,
                      api_mode: Optional[str] = None, **_: Any) -> Any:
        try:
            blocked = self._account(model, provider, api_mode)
        except Exception:
            logger.warning("cron-budget: accounting failed; allowing the call", exc_info=True)
            self._note_failure()
            blocked = None
        return blocked if blocked is not None else next_call(request)

    def _account(self, model: Optional[str], provider: Optional[str],
                 api_mode: Optional[str]) -> Optional[Any]:
        config = load_config(self.ledger.directory)
        counted = model_counts(model, config)
        cron = self._cron()
        fields = {"kind": "cron" if cron else "chat", "counted": counted, "provider": provider,
                  "model": model, "profile": cron.profile if cron else self._profile(),
                  "job_id": cron.job_id if cron else None,
                  "job_name": cron.job_name if cron else None}
        if not cron or not counted:
            self.ledger.record(verdict="allowed", **fields)
            return None

        decision = self.ledger.decide(config, cron.job_id)
        if not decision.block:
            self.ledger.record(verdict="allowed", **fields)
            return None
        if config["mode"] != "enforce" or api_mode not in BLOCKABLE_API_MODES:
            self.ledger.record(verdict="would_block", **fields)
            return None

        self.ledger.record(verdict="blocked", **fields)
        if self.ledger.first_notice(config, cron.job_id, decision.reason):
            _, end = window_bounds(config)
            return synthetic_response(notice_text(cron.job_name, decision.reason, decision, end), model)
        return synthetic_response("[SILENT]", model)

    def _note_failure(self) -> None:
        """Failing open must stay visible: `status` warns when calls went through uncounted."""
        try:
            (self.ledger.directory / "last_failure").write_text(f"{time.time():.3f}")
        except Exception:
            logger.debug("cron-budget: could not record the failure", exc_info=True)

    def pre_auxiliary_call(self, model: Optional[str] = None, provider: Optional[str] = None,
                           **_: Any) -> None:
        """Titling, compression and the like spend quota too. Counted; never blocked."""
        try:
            config = load_config(self.ledger.directory)
            cron = self._cron()
            self.ledger.record(
                kind="aux", verdict="allowed", counted=model_counts(model, config),
                provider=provider, model=model, profile=cron.profile if cron else self._profile(),
                job_id=cron.job_id if cron else None, job_name=cron.job_name if cron else None)
        except Exception:
            logger.debug("cron-budget: aux accounting failed", exc_info=True)

    def _profile(self) -> str:
        try:
            return str(self.ctx.profile_name)
        except Exception:
            return "default"
