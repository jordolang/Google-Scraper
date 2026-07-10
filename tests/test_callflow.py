from salescall import callflow
from salescall.models import Business, QueueEntry, Tier
from salescall.playbook import build_playbook


def _entry() -> QueueEntry:
    b = Business(name="Acme Plumbing", category="Plumber", phone="(614) 555-1212")
    return QueueEntry(business=b, tier=Tier.NO_SITE_NO_EMAIL, score=1.0, suggested_minutes=7)


def test_dispositions_are_stable():
    assert "booked" in callflow.DISPOSITIONS
    assert "callback" in callflow.DISPOSITIONS
    assert len(callflow.DISPOSITIONS) == 8


def test_flat_steps_covers_every_stage_step():
    pb = build_playbook(_entry())
    flat = callflow.flat_steps(pb)
    expected = sum(len(stage.steps) for stage in pb.stages)
    assert len(flat) == expected
    assert all(isinstance(name, str) for name, _ in flat)


def test_panels_are_rich_renderables():
    from rich.panel import Panel
    pb = build_playbook(_entry())
    assert isinstance(callflow.brief_panel(_entry(), pb), Panel)
    step = pb.stages[0].steps[0]
    assert isinstance(callflow.step_panel("open", 1, 5, step, 30, 7), Panel)
    assert isinstance(callflow.objection_detail_panel(pb.objections[0]), Panel)


def test_console_still_imports_shared_helpers():
    from salescall import console
    assert console.DISPOSITIONS is callflow.DISPOSITIONS
    assert console.brief_panel is callflow.brief_panel
