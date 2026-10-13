"""Self-contained HTML dashboard (open output/dashboard.html in any browser)."""
from __future__ import annotations

from datetime import datetime
from html import escape

from .config import settings
from .insights import Action, act_today, meeting_prep, overdue_by_owner, waiting_on_me
from .store import OPEN_APPROVAL, OPEN_COMMITMENT, Store
from . import sync_status

CSS = """
:root{--bg:#f6f5f2;--card:#fff;--ink:#1d2430;--mute:#6b7280;--line:#e5e2dc;
--accent:#1f3a5f;--red:#b42318;--amber:#b54708;--green:#067647;--chip:#eef1f5}
@media (prefers-color-scheme:dark){:root{--bg:#121417;--card:#1b1e23;--ink:#e8eaed;
--mute:#9aa1ab;--line:#2b2f36;--accent:#8fb3e0;--red:#f97066;--amber:#fdb022;--green:#47cd89;--chip:#252a31}}
*{box-sizing:border-box}html,body{overflow-x:hidden}body{margin:0;background:var(--bg);color:var(--ink);
font:15px/1.45 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
main{max-width:1180px;margin:0 auto;padding:24px 16px 48px}
header{display:flex;flex-wrap:wrap;justify-content:space-between;align-items:baseline;gap:8px}
h1{font-size:22px;margin:0}h2{font-size:15px;margin:0 0 12px;text-transform:uppercase;
letter-spacing:.06em;color:var(--mute)}.sub{color:var(--mute);font-size:13px}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(140px,100%),1fr));gap:12px;margin:20px 0}
.kpi{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px}
.kpi b{display:block;font-size:26px}.kpi span{color:var(--mute);font-size:13px}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:16px}@media(max-width:820px){.grid{grid-template-columns:1fr}}
section{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:16px;min-width:0}
.wide{grid-column:1/-1}ul{list-style:none;margin:0;padding:0}
li{padding:10px 0;border-top:1px solid var(--line)}li:first-child{border-top:0}
.row{display:flex;gap:8px;align-items:flex-start;justify-content:space-between}
.t{font-weight:600;overflow-wrap:anywhere}.m{color:var(--mute);font-size:13px;margin-top:2px}
.flag{white-space:nowrap;font-size:12px;padding:2px 8px;border-radius:999px;background:var(--chip)}
.Overdue,.red{color:var(--red)}.Due{color:var(--amber)}.Risk{color:var(--red)}
.owner{font-weight:600;margin:12px 0 4px}.owner:first-child{margin-top:0}
a{color:var(--accent)}.empty{color:var(--mute);font-style:italic}
.time{font-variant-numeric:tabular-nums;color:var(--accent);margin-right:4px}
.prep{font-size:13px;margin-top:4px;color:var(--ink);opacity:.85}.past{opacity:.5}
"""


def _flag_class(flag: str) -> str:
    return flag.split()[0].replace("·", "")


def _actions(items: list[Action], empty: str) -> str:
    if not items:
        return f'<p class="empty">{escape(empty)}</p>'
    lis = []
    for a in items:
        link = f' · <a href="{escape(a.link)}" target="_blank">source</a>' if a.link else ""
        meta = " · ".join(x for x in [a.kind, a.who, a.project, f"due {a.due}" if a.due else ""] if x)
        lis.append(
            f'<li><div class="row"><div class="t">{escape(a.text)}</div>'
            f'<span class="flag {_flag_class(a.flag)}">{escape(a.flag)}</span></div>'
            f'<div class="m">{escape(a.id)} · {escape(meta)}{link}</div></li>'
        )
    return "<ul>" + "".join(lis) + "</ul>"


def _meetings(store: Store, meetings, now: datetime) -> str:
    if meetings is None:
        return '<p class="empty">Calendar unavailable this run (see log).</p>'
    if not meetings:
        return '<p class="empty">No meetings in the next 7 days.</p>'
    out, day = [], None
    for m in meetings:
        if m.start.date() != day:
            if day is not None:
                out.append("</ul>")
            day = m.start.date()
            label = "Today" if day == now.date() else f"{m.start:%A}"
            out.append(f'<div class="owner">{label} <span class="sub">{m.start:%d %b}</span></div><ul>')
        when = "All day" if m.all_day else f"{m.start:%H:%M}–{m.end:%H:%M}"
        past = not m.all_day and m.end < now
        who = ", ".join(a.name.split("@")[0] for a in m.others[:4])
        if len(m.others) > 4:
            who += f" +{len(m.others) - 4}"
        links = []
        if m.join_link:
            links.append(f'<a href="{escape(m.join_link)}" target="_blank">join</a>')
        if m.link:
            links.append(f'<a href="{escape(m.link)}" target="_blank">event</a>')
        flag = ""
        if m.my_response in ("needsAction", "tentative"):
            flag = f'<span class="flag Due">{"Not responded" if m.my_response == "needsAction" else "Tentative"}</span>'
        meta = " · ".join(x for x in [escape(who), escape(m.location), " · ".join(links)] if x)
        prep = meeting_prep(store, m.others)
        prep_html = (
            '<div class="prep">' + "".join(f"<div>↳ {escape(p)}</div>" for p in prep[:4])
            + (f"<div>↳ +{len(prep) - 4} more</div>" if len(prep) > 4 else "") + "</div>"
            if prep else ""
        )
        out.append(
            f'<li class="{"past" if past else ""}"><div class="row"><div class="t">'
            f'<span class="time">{when}</span> {escape(m.title)}</div>{flag}</div>'
            f'<div class="m">{meta}</div>{prep_html}</li>'
        )
    out.append("</ul>")
    return "".join(out)


def render(store: Store, now: datetime, meetings=None, sync: dict | None = None) -> str:
    today = now.date()
    act = act_today(store, now)
    waiting = waiting_on_me(store, today)
    overdue = overdue_by_owner(store, today)
    open_c = sum(1 for r in store.rows["Commitments"] if r.get("Status") in OPEN_COMMITMENT)
    pending = sum(1 for r in store.rows["Approvals"] if r.get("Status") in OPEN_APPROVAL)
    high = sum(1 for r in store.rows["Risks"]
               if r.get("Status", "Open") == "Open" and r.get("Severity") == "High")
    n_overdue = sum(len(v) for v in overdue.values())

    od_html = []
    for owner, rows in overdue.items():
        od_html.append(f'<div class="owner">{escape(owner)} <span class="sub">({len(rows)})</span></div><ul>')
        for r in rows:
            link = f' · <a href="{escape(r["Source Link"])}" target="_blank">source</a>' if r.get("Source Link") else ""
            od_html.append(
                f'<li><div class="row"><div class="t">{escape(str(r.get("Item", "")))}</div>'
                f'<span class="flag Overdue">{r["_late"]}d late</span></div>'
                f'<div class="m">{escape(r["ID"])} · due {escape(str(r.get("Due")))}'
                f'{" · " + escape(str(r["Project"])) if r.get("Project") else ""}{link}</div></li>'
            )
        od_html.append("</ul>")

    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Second Brain</title><style>{CSS}{sync_status.CSS}</style></head><body><main>
<header><h1>{"Good morning" if now.hour < 12 else "Good afternoon" if now.hour < 17 else "Good evening"}, {escape(settings.me_name.split()[0])}</h1>
<span class="sub">{now:%A, %d %b %Y · %H:%M} {escape(settings.tz.key)}</span></header>
{sync_status.html_box(sync, now) if sync is not None else ""}
<div class="kpis">
<div class="kpi"><b>{len(act)}</b><span>Act today</span></div>
<div class="kpi"><b>{"–" if meetings is None else sum(1 for m in meetings if m.start.date() == today)}</b><span>Meetings today</span></div>
<div class="kpi"><b>{pending}</b><span>Approvals waiting on you</span></div>
<div class="kpi"><b class="{'red' if n_overdue else ''}">{n_overdue}</b><span>Overdue commitments</span></div>
<div class="kpi"><b>{open_c}</b><span>Open commitments</span></div>
<div class="kpi"><b class="{'red' if high else ''}">{high}</b><span>Open high risks</span></div>
</div>
<div class="grid">
<section><h2>Act today</h2>{_actions(act, "Nothing urgent. Clear runway.")}</section>
<section><h2>Waiting on me</h2>{_actions(waiting, "Nobody is waiting on you.")}</section>
<section><h2>Overdue by owner</h2>{"".join(od_html) or '<p class="empty">Nothing overdue.</p>'}</section>
<section><h2>This week's meetings</h2>{_meetings(store, meetings, now)}</section>
</div></main></body></html>"""


def render_markdown(store: Store, now: datetime, meetings=None, sync: dict | None = None) -> str:
    """Same four sections as the HTML, as Markdown for the online Claude Doc."""
    today = now.date()

    def acts(items: list[Action], empty: str) -> list[str]:
        if not items:
            return [f"_{empty}_"]
        out = []
        for a in items:
            meta = " · ".join(x for x in [a.kind, a.who, a.project, f"due {a.due}" if a.due else ""] if x)
            link = f" · [source]({a.link})" if a.link else ""
            out.append(f"- **{a.text}** — {a.flag}  \n  {a.id} · {meta}{link}")
        return out

    act = act_today(store, now)
    waiting = waiting_on_me(store, today)
    overdue = overdue_by_owner(store, today)
    pending = sum(1 for r in store.rows["Approvals"] if r.get("Status") in OPEN_APPROVAL)
    n_overdue = sum(len(v) for v in overdue.values())
    md = [
        f"Updated {now:%A %d %b %Y, %H:%M} {settings.tz.key}",
        "",
        *(sync_status.markdown_box(sync, now) + [""] if sync is not None else []),
        f"**{len(act)}** act today · **{pending}** approvals waiting · **{n_overdue}** overdue commitments",
        "", "## Act today", *acts(act, "Nothing urgent."),
        "", "## Waiting on me", *acts(waiting, "Nobody is waiting on you."),
        "", "## Overdue by owner",
    ]
    if not overdue:
        md.append("_Nothing overdue._")
    for owner, rows in overdue.items():
        md.append(f"**{owner}** ({len(rows)})")
        md += [f"- {r.get('Item')} — {r['_late']}d late (due {r.get('Due')}) · {r['ID']}" for r in rows]
    md += ["", "## This week's meetings"]
    if meetings is None:
        md.append("_Calendar unavailable this run._")
    elif not meetings:
        md.append("_No meetings in the next 7 days._")
    day = None
    for m in meetings or []:
        if m.start.date() != day:
            day = m.start.date()
            md.append(f"**{'Today' if day == today else f'{m.start:%A}'} {m.start:%d %b}**")
        when = "All day" if m.all_day else f"{m.start:%H:%M}–{m.end:%H:%M}"
        who = ", ".join(a.name for a in m.others[:4]) + (f" +{len(m.others) - 4}" if len(m.others) > 4 else "")
        flag = " · ⚠ not responded" if m.my_response == "needsAction" else ""
        md.append(f"- {when} **{m.title}**{' · ' + who if who else ''}{flag}")
        md += [f"  - ↳ {p}" for p in meeting_prep(store, m.others)[:4]]
    return "\n".join(md)


def write(store: Store, now: datetime, meetings=None, sync: dict | None = None):
    path = settings.dashboard_html
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render(store, now, meetings, sync), encoding="utf-8")
    return path
