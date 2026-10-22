"""Build site/index.html, a single-file page with the README's content.

site/page.html is the Jinja page shell, site/site.toml its text and tabs, and
site/content/<tab>.md each tab's prose. The Markdown is a Jinja template too, with
{{ diagram("NAME") }} for docs/diagrams/NAME.svg, {{ results("EXPERIMENT") }} and
{{ conditions("EXPERIMENT") }} for what results/EXPERIMENT/ contains, and
{{ icon("NAME") }}. The Mozilla design system is inlined from site/vendor/ (tokens,
components, icons and logo, from the mozilla-html skill of
github.com/mozilla/aidev-plugins).

  uv run python tools/build_site.py [results directory]
"""
import functools
import html
import json
import re
import sys
import tomllib
from pathlib import Path

import markdown
from jinja2 import Environment, FileSystemLoader, select_autoescape
from markupsafe import Markup

from repro.experiments import PHASES, Arm
from repro.timestamps import trial_name

ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / "site"
BROWSERS = {"firefox": "Firefox", "chrome": "Chrome", "safari": "Safari"}
STATES = {"pass": ("checkmark", "Passed", "Check passed in every trial"),
          "partial": ("warning-fill", "Failed in some trials", "Check failed in some trials"),
          "fail": ("error-fill", "Failed", "Check failed in every trial")}


def icon(name, label=None):
    """An Acorn icon from site/vendor/icons/, as inline SVG; announced only if labelled."""
    svg = (SITE / "vendor" / "icons" / f"{name}-16.svg").read_text().strip()
    return Markup(svg.replace('aria-hidden="true"', f'role="img" aria-label="{label}"', 1) if label else svg)


def logo(name):
    """A logo from site/vendor/, as inline SVG."""
    return Markup((SITE / "vendor" / f"{name}.svg").read_text().strip().replace("<svg ", '<svg class="moz-logo" ', 1))


def conjunction(items):
    """['a', 'b', 'c'] -> 'a, b and c'."""
    items = [str(i) for i in items]
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]


def number(text):
    """Typographic minus signs in numbers."""
    return re.sub(r"(?<![\w.])-(?=\d)", "\N{MINUS SIGN}", text)


def ppm(value):
    return number(f"{value:+d}") if value else "0"


def arms(plan):
    """One dict per arm: summary row name, browser, path cell, and the varying settings."""
    if "trials" in plan:
        return [{"name": trial_name(t), "browser": t["browser"], "path": f"<code>{t['path']}</code>",
                 "Video clock, ppm": ppm(t["videoPpm"])}
                for t in sorted(plan["trials"], key=lambda t: (list(BROWSERS).index(t["browser"]), -t["videoPpm"]))]
    rows = []
    for arm in sorted((Arm(**a) for a in plan["arms"]), key=lambda a: list(BROWSERS).index(a.browser)):
        path = f"<code>{arm.path}</code>"
        if not arm.realtime:
            path += ' <span class="moz-badge">Control*</span>'
        rows.append({"name": arm.label, "browser": arm.browser, "path": path,
                     "Render quantum, frames": str(arm.quantum)})
    return rows


def conditions(plan, constant):
    """One line describing what every trial of an experiment did."""
    duration = plan.get("duration") or plan["durationSeconds"]
    parts = [f"{duration} s {'recordings' if 'trials' in plan else 'calls'}"]
    if stalls := plan["stalls"]:
        parts.append(f"{conjunction(s['durationMs'] for s in stalls)} ms stall{'s' * (len(stalls) > 1)}"
                     f" at {conjunction(s['atSeconds'] for s in stalls)} s")
    if dsp := plan.get("dsp"):
        parts.append("block copy" if dsp["mode"] == "copy" else f"{dsp['taps']}-tap FIR")
    if load := plan.get("load"):
        parts.append(f"{load['workers']} stress-ng workers from {load['atSeconds']} to "
                     f"{load['atSeconds'] + load['seconds']} s")
    if quantum := constant.get("Render quantum, frames"):
        parts.append(f"{quantum}-frame render quantum")
    if "trials" in plan:
        parts.append(f"video clock {conjunction(ppm(c) for c in sorted({t['videoPpm'] for t in plan['trials']}, reverse=True))} ppm")
    if "rounds" in plan:
        parts.append(f"{plan['rounds']} trials per arm")
    return " · ".join(parts)


def status(column, value):
    """'pass', 'partial' or 'fail' for cells that are checks; None for measurements."""
    if m := re.fullmatch(r"(\d+)/(\d+)", value):
        passed, total = map(int, m.groups())
        return "pass" if passed == total else "fail" if passed == 0 else "partial"
    if column == "Audio exact":
        return "pass" if value == "yes" else "fail"
    if "never" in value:
        return "fail" if set(value.split(", ")) == {"never"} else "partial"
    if column == "Failed trials" and value != "0":
        return "fail"
    return None


def cell(column, value, rowspan=1):
    value = str(value)
    span = f' rowspan="{rowspan}"' if rowspan > 1 else ""
    if not (state := status(column, value)):
        return f'<td class="num"{span}>{html.escape(number(value))}</td>'
    name, label, _ = STATES[state]
    return f'<td class="num {state}"{span}>{icon(name, label)}{html.escape(number(value))}</td>'


def heading(column):
    """'Backlog p95, ms (before / load / after)' -> 'Backlog p95' with unit 'ms'."""
    name, _, unit = re.sub(r" \(.*\)$", "", column).partition(", ")
    return html.escape(name) + (f'<span class="unit">{unit}</span>' if unit else "")


def table(experiment, results):
    """The experiment's results table, and its conditions line."""
    directory = results / experiment
    summary = json.loads((directory / "summary.json").read_text())
    if "rows" in summary:
        plan, rows = summary["plan"], summary["rows"]
    else:  # The timestamps summary is the rows alone.
        plan, rows = json.loads((directory / "plan.json").read_text()), summary
    ordered = arms(plan)
    settings = [k for k in ordered[0] if k not in ("name", "browser", "path")]
    varying = [k for k in settings if len({a[k] for a in ordered}) > 1]
    constant = {k: ordered[0][k] for k in settings if k not in varying}
    columns = list(next(iter(rows.values())))
    if all(str(row.get("Failed trials", 0)) == "0" for row in rows.values()):
        columns = [c for c in columns if c != "Failed trials"]
    # Contention metrics hold one value per phase, joined by " / ": one row per phase.
    phased = [c for c in columns if any(" / " in str(row[c]) for row in rows.values())]
    phases = PHASES if phased else ("",)

    keys = ["Browser", "Path", *varying] + (["Phase"] if phased else [])
    head = [f'<th scope="col">{heading(k)}</th>' for k in keys]
    head += [f'<th scope="col" class="num">{heading(c)}</th>' for c in columns]

    body = []
    for i, arm in enumerate(ordered):
        row, split = rows[arm["name"]], {c: str(rows[arm["name"]][c]).split(" / ") for c in phased}
        first_of_browser = i == 0 or ordered[i - 1]["browser"] != arm["browser"]
        for p, phase in enumerate(phases):
            cells = []
            if p == 0:
                if first_of_browser:
                    count = sum(a["browser"] == arm["browser"] for a in ordered) * len(phases)
                    cells.append(f'<th scope="rowgroup" rowspan="{count}">{BROWSERS[arm["browser"]]}</th>')
                span = f' rowspan="{len(phases)}"' if phased else ""
                cells += [f"<td{span}>{arm['path']}</td>"] + [f'<td class="num"{span}>{arm[k]}</td>' for k in varying]
            if phased:
                cells.append(f'<td class="phase">{phase}</td>')
            for c in columns:
                if c in phased:
                    cells.append(cell(c, split[c][p]))
                elif p == 0:
                    cells.append(cell(c, row[c], len(phases)))
            group = "group-start" if p == 0 and first_of_browser else "arm-start" if p == 0 else ""
            body.append((f'<tr class="{group}">' if group else "<tr>") + "".join(cells) + "</tr>")

    markup = "\n".join(['<div class="moz-table-wrapper">', '<table class="moz-table compact results">',
                        "<thead>", "<tr>" + "".join(head) + "</tr>", "</thead>", "<tbody>", *body, "</tbody>",
                        "</table>", "</div>"])
    return markup + "\n", conditions(plan, constant)


def legend():
    items = "".join(f'<li><span class="{state}">{icon(name)}</span>{text}</li>'
                    for state, (name, _, text) in STATES.items())
    return f'<ul class="legend">{items}</ul>\n'


def diagram(name):
    """docs/diagrams/NAME.svg, tagged with its width so CSS never enlarges it."""
    svg = (ROOT / "docs" / "diagrams" / f"{name}.svg").read_text().split("?>", 1)[1]
    width = re.search(r'viewBox="0 0 ([\d.]+) ', svg).group(1)
    return Markup('<figure class="diagram moz-card">' + svg.replace("<svg ", f'<svg style="--diagram-width: {width}" ', 1)
                  + "</figure>")


def panel(env, name):
    """site/content/NAME.md, its Jinja calls expanded, as HTML."""
    body = markdown.markdown(env.get_template(f"content/{name}.md").render(), extensions=["tables", "fenced_code"])
    # Markdown's own tables; results() tables come styled.
    return Markup(re.sub(r"<table>(.*?)</table>",
                         r'<div class="moz-table-wrapper"><table class="moz-table compact">\1</table></div>', body, flags=re.S))


def build(results):
    site = tomllib.loads((SITE / "site.toml").read_text())
    tables = functools.cache(lambda experiment: table(experiment, results))
    env = Environment(loader=FileSystemLoader(SITE), autoescape=select_autoescape(["html"]),
                      trim_blocks=True, lstrip_blocks=True, keep_trailing_newline=True)
    env.globals.update(
        icon=icon, logo=logo, diagram=diagram,
        results=lambda experiment: Markup(legend() + tables(experiment)[0]),
        conditions=lambda experiment: Markup(f'<p class="meta"><code>{experiment}</code> · {tables(experiment)[1]}</p>'))
    panels = [{"id": tab["id"], "html": panel(env, tab["id"])}
              for group in site["groups"] for tab in group if "id" in tab]
    (SITE / "index.html").write_text(env.get_template("page.html").render(site, panels=panels))


if __name__ == "__main__":
    build(Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "results")
