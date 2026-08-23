"""Licensing for the terminal: the TUI, the scripts, and packaged CLI runs.

The desktop app has dialogs; everything else has this. Same manager, same
answers, printed instead of shown.

    python app.py --licence status
    python app.py --licence activate LLSP-XXXXX-XXXXX-XXXXX-XXXXX
    python app.py --licence trial
    python app.py --licence deactivate
    python app.py --licence plans

Scripts call :func:`require` at the top of ``main`` and get a clear message and
a non-zero exit instead of a stack trace when the licence does not cover what
they are about to do.
"""

from __future__ import annotations

import sys
from typing import List, Optional

from . import keys, plans
from .errors import LicenseError, ServiceUnreachable, TrialExhausted
from .manager import get_manager

COMMANDS = ("status", "activate", "trial", "deactivate", "plans")


def _out(text: str = "") -> None:
    print(text)


def print_status() -> int:
    manager = get_manager()
    status = manager.status(refresh=True)
    _out(f"Licence   {status.headline()}")
    _out(f"Plan      {status.tier_name}")
    if status.key:
        _out(f"Key       {keys.masked(status.key)}   (seat {status.seat})")
    if status.email:
        _out(f"Owner     {status.email}")
    if status.detail:
        _out(f"Note      {status.detail}")
    _out()
    _out("This licence allows:")
    for line in manager.restrictions():
        _out(f"  - {line}")
    if not status.licensed:
        _out()
        _out("Start the free 72-hour trial with:  python app.py --licence trial")
    return 0


def print_plans() -> int:
    _out("Two ways to pay for the same software.\n")
    _out(f"{'Plan':10} {'Monthly':>10} {'Yearly':>10} {'One-time':>10}  Machines")
    for key in (plans.SOLO, plans.PRO, plans.AGENCY):
        tier = plans.TIERS[key]
        monthly = plans.price_for(f"{key}-subscription-monthly")
        yearly = plans.price_for(f"{key}-subscription-yearly")
        once = plans.price_for(f"{key}-perpetual-once")
        _out(f"{tier.name:10} {monthly.display if monthly else '—':>10} "
             f"{yearly.display if yearly else '—':>10} "
             f"{once.display if once else '—':>10}  {tier.limits.max_machines}")
    _out()
    _out("A subscription renews and always has the newest version.")
    _out("A one-time licence never expires and includes "
         f"{plans.TIERS[plans.PRO].perpetual_update_months} months of updates; "
         f"renewals are {plans.PERPETUAL_RENEWAL_PERCENT}% of the original.")
    _out()
    for key in (plans.SOLO, plans.PRO, plans.AGENCY):
        _out(f"{plans.TIERS[key].name}: {plans.TIERS[key].blurb}")
    return 0


def activate(typed_key: str) -> int:
    if not typed_key:
        _out("Usage: --licence activate LLSP-XXXXX-XXXXX-XXXXX-XXXXX")
        return 2
    try:
        status = get_manager().activate(typed_key)
    except LicenseError as exc:
        _out(f"Activation failed: {exc}")
        return 1
    _out(f"Activated. This computer is on {status.tier_name} (seat {status.seat}).")
    return 0


def start_trial() -> int:
    try:
        status = get_manager().start_trial()
    except TrialExhausted:
        _out("This computer has already used its 72-hour trial.")
        _out("See what a licence costs with:  python app.py --licence plans")
        return 1
    except ServiceUnreachable as exc:
        _out(f"{exc}")
        return 1
    except LicenseError as exc:
        _out(f"Could not start the trial: {exc}")
        return 1
    _out(status.headline())
    return 0


def deactivate() -> int:
    try:
        get_manager().deactivate()
    except LicenseError as exc:
        _out(f"The licence service could not be told ({exc}).")
        _out("Releasing this computer locally; contact support if the seat "
             "still shows as used.")
        get_manager().deactivate(local_only=True)
        return 1
    _out("This computer has been deactivated and its seat released.")
    return 0


def run(argv: Optional[List[str]] = None) -> int:
    """Handle ``--licence <command> [key]``. Returns a process exit code."""
    arguments = list(argv or [])
    command = arguments[0] if arguments else "status"
    if command == "status":
        return print_status()
    if command == "plans":
        return print_plans()
    if command == "trial":
        return start_trial()
    if command == "deactivate":
        return deactivate()
    if command == "activate":
        return activate(arguments[1] if len(arguments) > 1 else "")
    _out(f"Unknown licence command {command!r}. Try: {', '.join(COMMANDS)}")
    return 2


def require(feature: str, *, action: str = "", quiet: bool = False) -> bool:
    """Whether ``feature`` is licensed; prints why not when it is not."""
    manager = get_manager()
    if manager.allows(feature):
        return True
    if quiet:
        return False
    label = action or plans.FEATURE_LABELS.get(feature, feature)
    status = manager.status()
    upgrade = manager.lowest_tier_with(feature)
    print(f"\n{label} is not covered by this licence.", file=sys.stderr)
    print(f"  Current: {status.tier_name} — {status.headline()}", file=sys.stderr)
    if upgrade:
        price = plans.price_for(f"{upgrade}-subscription-monthly")
        print(f"  Included from {plans.tier(upgrade).name}"
              f"{f' ({price.display})' if price else ''}.", file=sys.stderr)
    print("  python app.py --licence plans    to see the options", file=sys.stderr)
    print("  python app.py --licence trial    for a free 72 hours\n", file=sys.stderr)
    return False


def require_or_exit(feature: str, *, action: str = "") -> None:
    """Same as :func:`require`, but ends the process when the answer is no."""
    if not require(feature, action=action):
        raise SystemExit(2)
