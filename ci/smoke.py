"""Smoke test for the ukuetis_site image, run against a live container.

It is fed to the container over stdin (`docker exec -i <name> python - < ci/smoke.py`),
so it never has to be copied into the image, and it can be run by hand the same way
against any locally started container of this image.

It is pure stdlib on purpose: the image installs only flask and loguru, so anything
else imported here would fail at the gate instead of at the thing being gated.

It talks HTTP to the server the image's own CMD started (not Flask's test client),
so it proves the container actually comes up. Failures leave through SystemExit,
never `assert`, which vanishes under PYTHONOPTIMIZE=1. Every target is checked
before reporting.
"""

import urllib.error
import urllib.request

# The app reads PORT from the environment and defaults to 8000; nothing in the
# image or in the CI run sets PORT, so 8000 is what the container listens on.
BASE_URL = "http://127.0.0.1:8000"
TIMEOUT = 5

# app.py has one route, `/` (templates/index.html on top of templates/base.html).
# Status alone is not enough, so the page must carry markers from both halves of
# the render: `class="footer-content"` exists only in base.html (the layout),
# `id="hero"` and `id="products"` only inside index.html's `{% block content %}`
# (the page body). The body markers are ids, not classes, because a class list
# grows tokens in everyday CSS edits; both ids are referenced by the page's nav
# and style.css. Attributes, not prose: the visible copy gets reworded.
HTML_ROUTES = [
    ("/", ['class="footer-content"', 'id="hero"', 'id="products"']),
]

# Served by Flask from inside the image, so a broken `COPY static/` in the
# Dockerfile shows up here and nowhere else: the HTML route above renders
# perfectly well with not a single file under static/, and the page would reach
# production stripped of its styling, scripts and favicon.
STATIC_ASSETS = [
    "/static/css/style.css",
    "/static/js/main.js",
    "/static/favicon.svg",
]


def fetch(route):
    """GET the route; return (body_bytes, None) on 200, else (None, reason)."""
    try:
        with urllib.request.urlopen(BASE_URL + route, timeout=TIMEOUT) as response:
            status = response.status
            body = response.read()
    except urllib.error.HTTPError as error:
        # A 4xx/5xx is an answer, not a transport problem: report the code as is.
        return None, "HTTP {}".format(error.code)
    except Exception as error:
        # Connection refused, timeout, DNS — anything that kept us from an answer.
        return None, "{}: {}".format(type(error).__name__, error)
    if status != 200:
        return None, "HTTP {}".format(status)
    return body, None


def check_html(route, markers):
    """Return None when the route answers 200 AND contains every marker."""
    body, reason = fetch(route)
    if reason is not None:
        return reason
    try:
        # Decoded explicitly as UTF-8 rather than compared as bytes: the page is
        # Russian, so matching a str marker against a bytes body would be a
        # guaranteed false failure.
        text = body.decode("utf-8")
    except UnicodeDecodeError as error:
        return "200 but body is not valid UTF-8: {}".format(error)
    # EVERY missing marker is reported, not just the first one: which ones are
    # gone is the diagnosis — layout only, body only, or the whole render.
    missing = [marker for marker in markers if marker not in text]
    if missing:
        return "200 but {}/{} markers missing from {} bytes of body: {}".format(
            len(missing), len(markers), len(body),
            ", ".join(repr(marker) for marker in missing))
    return None


def check_asset(route):
    """Return None when the asset answers 200 with a non-empty body."""
    body, reason = fetch(route)
    if reason is not None:
        return reason
    # Status alone would not catch it: a style.css truncated to zero bytes (a
    # botched build step, a half-written file) answers a perfectly good 200 and
    # the site ships unstyled. Emptiness is the honest check — what the CSS or
    # the JS should *contain* is not this gate's business.
    if not body:
        return "200 but the body is empty (0 bytes)"
    return None


def main():
    results = []
    for route, markers in HTML_ROUTES:
        results.append((route, check_html(route, markers)))
    for route in STATIC_ASSETS:
        results.append((route, check_asset(route)))

    failures = []
    for route, reason in results:
        if reason is None:
            print("ok   {}".format(route))
        else:
            print("FAIL {} -> {}".format(route, reason))
            failures.append("{} ({})".format(route, reason))

    if failures:
        print("smoke FAILED: {}/{} targets broken: {}".format(
            len(failures), len(results), ", ".join(failures)))
        raise SystemExit(1)

    print("smoke ok: {}/{} targets".format(len(results), len(results)))


if __name__ == "__main__":
    main()
