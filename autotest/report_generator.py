from __future__ import annotations

from pathlib import Path
from typing import Any

from jinja2 import BaseLoader, Environment, select_autoescape

REPORT = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<title>LLM-AutoTest - {{ project.project_id }}</title><style>
body{font:14px system-ui,sans-serif;max-width:1200px;margin:2rem auto;padding:0 1rem;color:#1f2937}
.PASSED{color:#15803d}.FAILED,.BUILD_FAILED,.CRASHED,.INFRA_ERROR{color:#b91c1c}.TIMEOUT{color:#b45309}
table{border-collapse:collapse;width:100%}th,td{border:1px solid #d1d5db;padding:.55rem;text-align:left;vertical-align:top}
th{background:#f3f4f6}pre{white-space:pre-wrap;background:#111827;color:#e5e7eb;padding:1rem;overflow:auto}
</style></head><body><h1>{{ project.project_id }}</h1>
<p>Overall status: <strong class="{{ result.status }}">{{ result.status }}</strong> · Duration: {{ '%.3f'|format(result.duration_seconds or 0) }} s</p>
<p>Sources: {{ project.source_files|map('string')|join(', ') }}</p>
<p>Passed {{ result.counts.PASSED }}, failed {{ result.counts.FAILED }}, not run {{ result.counts.NOT_RUN }}</p>
<h2>Test cases</h2><table><thead><tr><th>ID</th><th>Requirement</th><th>Description</th><th>Input</th><th>Expected</th><th>Actual</th></tr></thead><tbody>
{% for c in result.testcases %}<tr><td>{{ c.testcase_id }}</td><td>{{ c.requirement_id }}</td><td>{{ c.description }}</td>
<td><code>{{ c.inputs|tojson }}</code></td><td><code>{{ c.expected|tojson }}</code></td><td class="{{ c.actual_status }}">{{ c.actual_status }} {{ c.actual_detail }}</td></tr>{% endfor %}</tbody></table>
<h2>Build log</h2><pre>{{ result.build_log }}</pre><h2>Execution log</h2><pre>{{ result.execution_log }}</pre></body></html>"""

SUMMARY = """<!doctype html><html><head><meta charset="utf-8"><title>LLM-AutoTest summary</title>
<style>body{font:15px system-ui;max-width:900px;margin:2rem auto}table{border-collapse:collapse;width:100%}td,th{border:1px solid #ccc;padding:.6rem}</style></head>
<body><h1>Run {{ run_id }}</h1><table><tr><th>Project</th><th>Status</th><th>Passed</th><th>Failed</th><th>Not run</th></tr>
{% for x in items %}<tr><td><a href="{{ x.relative_report }}">{{ x.project_id }}</a></td><td>{{ x.result.status }}</td><td>{{ x.result.counts.PASSED }}</td><td>{{ x.result.counts.FAILED }}</td><td>{{ x.result.counts.NOT_RUN }}</td></tr>{% endfor %}
</table></body></html>"""


class ReportGenerator:
    def __init__(self):
        self.environment = Environment(loader=BaseLoader(), autoescape=select_autoescape(["html", "xml"]))

    def project_report(self, project: Any, result: dict[str, Any], output_dir: str | Path) -> Path:
        destination = Path(output_dir) / "report.html"
        destination.write_text(self.environment.from_string(REPORT).render(project=project, result=result), encoding="utf-8")
        return destination

    def summary_report(self, run_id: str, items: list[dict[str, Any]], run_dir: str | Path) -> Path:
        destination = Path(run_dir) / "summary.html"
        destination.write_text(self.environment.from_string(SUMMARY).render(run_id=run_id, items=items), encoding="utf-8")
        return destination

