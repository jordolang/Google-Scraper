import importlib


def test_app_module_exposes_main():
    mod = importlib.import_module("app")
    assert hasattr(mod, "main") or hasattr(mod, "__file__")


def test_sales_calls_classic_dispatch(monkeypatch):
    import sales_calls
    called = {}
    monkeypatch.setattr(sales_calls, "cmd_sheet", lambda: called.setdefault("sheet", True))
    sales_calls.main(["--classic", "sheet"])
    assert called.get("sheet") is True


def test_sales_calls_default_launches_unified(monkeypatch):
    import sales_calls
    launched = {}

    # main should route no-arg invocation to the cockpit launcher (the seam
    # sales_calls exposes for launching the unified Textual app), not the
    # Rich _menu().
    monkeypatch.setattr(sales_calls, "_launch_cockpit", lambda screen=None: launched.setdefault("cockpit", screen or "menu"))
    sales_calls.main([])
    assert launched.get("cockpit") == "menu"


def test_sales_calls_screen_arg_launches_cockpit_on_screen(monkeypatch):
    import sales_calls
    launched = {}
    monkeypatch.setattr(sales_calls, "_launch_cockpit", lambda screen=None: launched.setdefault("cockpit", screen or "menu"))
    sales_calls.main(["sheet"])
    assert launched.get("cockpit") == "sheet"
