"""Capture runtime errors a static fetch can't see: JS console errors and
failed API/network calls. Uses headless Chrome via Selenium.

If Chrome/Selenium is unavailable the function returns a single 'info' finding
explaining that, never raising — the rest of the intel still works.
"""

from __future__ import annotations

import json

from ..models import Finding


def _make_driver():
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options

    opts = Options()
    opts.add_argument("--headless=new")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--window-size=1366,900")
    opts.set_capability("goog:loggingPrefs", {"browser": "ALL", "performance": "ALL"})
    return webdriver.Chrome(options=opts)


def _failed_requests(perf_logs: list[dict]) -> list[tuple[str, int]]:
    """Pull HTTP responses with status >= 400 from CDP performance logs."""
    failures: list[tuple[str, int]] = []
    for entry in perf_logs:
        try:
            msg = json.loads(entry["message"])["message"]
        except (KeyError, ValueError, TypeError):
            continue
        if msg.get("method") == "Network.responseReceived":
            resp = msg.get("params", {}).get("response", {})
            status = resp.get("status", 0)
            if isinstance(status, int) and status >= 400:
                failures.append((resp.get("url", "")[:120], status))
    return failures


def capture_runtime_errors(url: str, wait_seconds: int = 4) -> list[Finding]:
    import time

    try:
        driver = _make_driver()
    except Exception as exc:  # noqa: BLE001 - environment/driver issues are expected
        return [Finding(
            key="errors_unavailable", severity="info",
            headline="Live error scan skipped",
            detail=f"Headless Chrome unavailable: {type(exc).__name__}: {exc}",
            pitch="",
        )]

    findings: list[Finding] = []
    try:
        driver.set_page_load_timeout(30)
        driver.get(url)
        time.sleep(wait_seconds)

        console = driver.get_log("browser")
        js_errors = [e for e in console if e.get("level") == "SEVERE"]
        perf = driver.get_log("performance")
        failures = _failed_requests(perf)
    except Exception as exc:  # noqa: BLE001
        driver.quit()
        return [Finding(
            key="errors_scan_failed", severity="info",
            headline="Live error scan failed",
            detail=f"{type(exc).__name__}: {exc}", pitch="",
        )]
    finally:
        try:
            driver.quit()
        except Exception:  # noqa: BLE001
            pass

    if js_errors:
        sample = js_errors[0].get("message", "")[:140]
        findings.append(Finding(
            key="js_console_errors", severity="critical",
            headline=f"{len(js_errors)} JavaScript error(s) in console",
            detail=f"e.g. {sample}",
            pitch="Your site is throwing live errors in the browser right now — "
                  "that means buttons, forms, or your quote request can silently "
                  "break for customers and you'd never know. Leads vanish into thin air.",
        ))

    if failures:
        sample_url, sample_status = failures[0]
        findings.append(Finding(
            key="failed_requests", severity="critical",
            headline=f"{len(failures)} failed network/API request(s)",
            detail=f"e.g. {sample_status} {sample_url}",
            pitch="Parts of your site are failing to load — images, scripts, or "
                  "an API call coming back as errors. Visitors see a broken, "
                  "half-loaded page and assume you're out of business.",
        ))

    if not findings:
        findings.append(Finding(
            key="no_runtime_errors", severity="good",
            headline="No console/network errors detected",
            detail="Clean load in headless Chrome.",
            pitch="Credit where due — the site loads cleanly with no errors. The "
                  "angle here isn't 'it's broken,' it's 'it's dated / slow / "
                  "not converting.'",
        ))
    return findings
