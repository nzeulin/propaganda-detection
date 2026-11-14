"""Per-execution provider accounting; never record credentials or hidden reasoning."""

from contextvars import ContextVar

usage_context: ContextVar[list | None] = ContextVar("provider_usage", default=None)


def record_usage(model, usage, operation):
    ledger = usage_context.get()
    if ledger is None:
        return
    if hasattr(usage, "model_dump"):
        usage = usage.model_dump(exclude_none=True)
    ledger.append(
        {
            "model": model,
            "operation": operation,
            "usage": usage or {},
            "billing_note": "Reported token usage; actual cost depends on provider pricing.",
        }
    )
