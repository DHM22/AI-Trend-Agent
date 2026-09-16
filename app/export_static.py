"""Build the saved dashboard for Netlify, without running a web server."""

import json
import shutil
from pathlib import Path

from app.main import APP_DIR, ROOT, ReportUnavailable, dashboard_context, load_report, templates

OUTPUT_FILES = {
    "index.html", "api/report.json", "health.json", "_redirects",
    "static/style.css", "static/app.js",
}


def static_url(name: str, *, path: str) -> str:
    if name != "static" or path not in {"style.css", "app.js"}:
        raise ValueError("Unknown static asset")
    return f"/static/{path}"


def export(output: Path = ROOT / "dist") -> int:
    # Validate before writing anything: a bad report must fail the deploy rather
    # than replace a working site with an incomplete report.
    report = load_report()
    context = dashboard_context(report)
    html = templates.env.get_template("index.html").render(
        **context, url_for=static_url,
    )

    # Publish only this allowlist, never the repo, local settings, or caches.
    # Refuse unexpected leftovers instead of deleting somebody else's files.
    if output.is_symlink():
        raise ValueError("The build output directory must not be a symbolic link.")
    if output.exists():
        for path in output.rglob("*"):
            if path.is_symlink() or (path.is_file() and path.relative_to(output).as_posix() not in OUTPUT_FILES):
                raise ValueError("The build output contains unexpected files. Use an empty output directory.")

    (output / "static").mkdir(parents=True, exist_ok=True)
    (output / "api").mkdir(exist_ok=True)
    (output / "index.html").write_text(html, encoding="utf-8")
    (output / "api" / "report.json").write_text(
        report.model_dump_json(indent=2), encoding="utf-8",
    )
    (output / "health.json").write_text(json.dumps({"status": "ok"}), encoding="utf-8")
    (output / "_redirects").write_text(
        "/api/report /api/report.json 200\n/health /health.json 200\n",
        encoding="utf-8",
    )
    for filename in ("style.css", "app.js"):
        shutil.copyfile(APP_DIR / "static" / filename, output / "static" / filename)
    return len(context.get("rows") or [])


if __name__ == "__main__":
    try:
        count = export()
    except (ReportUnavailable, OSError, ValueError) as exc:
        raise SystemExit(f"Static build failed: {exc}") from None
    print(f"Built dist/ with {count} recommendations. No API calls or credentials required.")
