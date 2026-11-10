"""cron-budget: keep scheduled jobs from spending the requests people need for chat."""
from __future__ import annotations


def register(ctx) -> None:
    from .cron_budget import cli
    from .cron_budget.gate import Gate

    gate = Gate(ctx)
    ctx.register_middleware("llm_execution", gate.llm_execution)
    ctx.register_hook("pre_auxiliary_call", gate.pre_auxiliary_call)
    ctx.register_cli_command("cron-budget", help=cli.HELP, setup_fn=cli.setup,
                             handler_fn=cli.handle, description=cli.HELP)
    ctx.register_command("cron-budget", cli.slash, description="Show cron request budget")
