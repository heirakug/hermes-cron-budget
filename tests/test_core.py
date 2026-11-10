import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from cron_budget.core import DEFAULTS, Ledger, load_config, model_counts, save_config, window_bounds  # noqa: E402
from cron_budget.gate import Gate  # noqa: E402

JST = ZoneInfo("Asia/Tokyo")


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)
        self.ledger = Ledger(self.dir)

    def config(self, **values):
        config = dict(DEFAULTS, timezone="Asia/Tokyo", reset="09:00", **values)
        save_config(config, self.dir)
        return config


class WindowTests(Base):
    def test_before_reset_belongs_to_yesterday(self):
        start, end = window_bounds(self.config(), datetime(2026, 11, 5, 8, 59, tzinfo=JST))
        self.assertEqual((start.day, start.hour, end.day), (4, 9, 5))

    def test_at_reset_opens_new_window(self):
        start, _ = window_bounds(self.config(), datetime(2026, 11, 5, 9, 0, tzinfo=JST))
        self.assertEqual((start.day, start.hour), (5, 9))

    def test_utc_input_is_converted(self):
        start, _ = window_bounds(self.config(), datetime(2026, 11, 5, 0, 30, tzinfo=timezone.utc))
        self.assertEqual((start.day, start.hour), (5, 9))


class DecisionTests(Base):
    def add(self, count, verdict="allowed", job="a", counted=True, kind="cron", ts=None):
        for _ in range(count):
            self.ledger.record(kind=kind, verdict=verdict, counted=counted, job_id=job, ts=ts)

    def test_stops_at_limit_minus_reserve(self):
        config = self.config(daily_limit=10, chat_reserve=3)
        self.add(6)
        self.assertFalse(self.ledger.decide(config, "a").block)
        self.add(1)
        decision = self.ledger.decide(config, "a")
        self.assertEqual((decision.block, decision.reason, decision.cron_cap), (True, "chat_reserve", 7))

    def test_chat_counts_against_cron(self):
        config = self.config(daily_limit=10, chat_reserve=3)
        self.add(7, job=None, kind="chat")
        self.assertTrue(self.ledger.decide(config, "a").block)

    def test_blocked_calls_cost_nothing(self):
        config = self.config(daily_limit=10, chat_reserve=3)
        self.add(50, verdict="blocked")
        self.assertFalse(self.ledger.decide(config, "a").block)

    def test_job_limit_is_per_job(self):
        config = self.config(job_limit=2)
        self.add(2, job="noisy")
        self.assertEqual(self.ledger.decide(config, "noisy").reason, "job_limit")
        self.assertFalse(self.ledger.decide(config, "quiet").block)

    def test_old_window_is_ignored(self):
        config = self.config(daily_limit=10, chat_reserve=3)
        self.add(9, ts=(datetime.now(JST) - timedelta(days=2)).timestamp())
        self.assertFalse(self.ledger.decide(config, "a").block)

    def test_uncounted_models_are_ignored(self):
        config = self.config(daily_limit=10, chat_reserve=3)
        self.add(9, counted=False)
        self.assertFalse(self.ledger.decide(config, "a").block)

    def test_reserve_above_limit_blocks_cron_not_crash(self):
        self.assertTrue(self.ledger.decide(self.config(daily_limit=5, chat_reserve=9), "a").block)

    def test_model_glob(self):
        config = dict(DEFAULTS, models=["*:free"])
        self.assertTrue(model_counts("nvidia/x:free", config))
        self.assertFalse(model_counts("gpt-5", config))

    def test_notice_once_per_window(self):
        config = self.config()
        self.assertTrue(self.ledger.first_notice(config, "a", "chat_reserve"))
        self.assertFalse(self.ledger.first_notice(config, "a", "chat_reserve"))
        self.assertTrue(self.ledger.first_notice(config, "b", "chat_reserve"))

    def test_missing_config_uses_defaults(self):
        self.assertEqual(load_config(self.dir)["mode"], "observe")


class GateTests(Base):
    def gate(self, cron=True):
        execution = SimpleNamespace(job_id="j", job_name="noisy", profile="p") if cron else None
        ctx = SimpleNamespace(current_cron_execution=lambda: execution, profile_name="p")
        return Gate(ctx, ledger_factory=lambda: self.ledger)

    def call(self, gate, api_mode="chat_completions"):
        self.sent = []
        return gate.llm_execution(request={}, next_call=lambda r: self.sent.append(r) or "real",
                                  model="m", provider="x", api_mode=api_mode)

    def text(self, response):
        return response.choices[0].message.content

    def test_enforce_blocks_then_goes_silent(self):
        self.config(mode="enforce", daily_limit=1, chat_reserve=0)
        gate = self.gate()
        self.assertEqual(self.call(gate), "real")
        first = self.call(gate)
        self.assertEqual(self.sent, [])
        self.assertIn("noisy", self.text(first))
        self.assertEqual(self.text(self.call(gate)), "[SILENT]")
        self.assertEqual(self.sent, [])

    def test_observe_never_blocks(self):
        self.config(mode="observe", daily_limit=1, chat_reserve=1)
        self.assertEqual(self.call(self.gate()), "real")
        self.assertEqual(self.ledger.summary(load_config(self.dir))["jobs"][0][4], 1)

    def test_chat_is_never_blocked(self):
        self.config(mode="enforce", daily_limit=1, chat_reserve=1)
        self.assertEqual(self.call(self.gate(cron=False)), "real")

    def test_unsupported_api_mode_is_not_blocked(self):
        self.config(mode="enforce", daily_limit=1, chat_reserve=1)
        self.assertEqual(self.call(self.gate(), api_mode="codex_responses"), "real")

    def test_internal_failure_allows_the_call(self):
        (self.dir / "budget.json").write_text('{"reset": "nonsense", "mode": "enforce", "daily_limit": 1, "chat_reserve": 1}')
        self.assertEqual(self.call(self.gate()), "real")


if __name__ == "__main__":
    unittest.main()
