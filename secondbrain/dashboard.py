"""Self-contained HTML dashboard (open output/dashboard.html in any browser)."""
from __future__ import annotations

import json
from datetime import datetime
from html import escape

from .config import settings
from .insights import Action, act_today, meeting_prep, overdue_by_owner, waiting_on_me
from .store import OPEN_APPROVAL, OPEN_COMMITMENT, Store
from . import profiles, sync_status
from .sync_status import clock

CSS = """
:root{--bg:#f6f5f2;--card:#fff;--ink:#1d2430;--mute:#6b7280;--line:#e5e2dc;
--accent:#1f3a5f;--red:#b42318;--amber:#b54708;--green:#067647;--chip:#eef1f5}
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


THEMES = [  # key, label, swatch (picker dot)
    ("navy", "Navy & Gold", "linear-gradient(135deg,#0f2343 50%,#c9a227 50%)"),
    ("emerald", "Emerald", "linear-gradient(135deg,#065f46 50%,#14b8a6 50%)"),
    ("royal", "Royal Purple", "linear-gradient(135deg,#3b1f8f 50%,#e64980 50%)"),
    ("sunset", "Sunset", "linear-gradient(135deg,#9a3412 50%,#f59e0b 50%)"),
    ("midnight", "Midnight (dark)", "linear-gradient(135deg,#0e1320 50%,#7aa2ff 50%)"),
]
DEFAULT_THEME = "navy"

THEME_CSS = """
:root,:root[data-theme=navy]{--bg:#f3f5f9;--card:#fff;--ink:#14213d;--mute:#5c677d;--line:#e3e8f0;--chip:#eef2f7;
--accent:#1d3557;--accent-soft:#e7edf6;--gold:#c9a227;--hero1:#0f2343;--hero2:#24467d}
:root[data-theme=emerald]{--bg:#f0f7f4;--card:#fff;--ink:#0f2e25;--mute:#55706a;--line:#d9ebe4;--chip:#e8f3ee;
--accent:#0b7a5b;--accent-soft:#e1f3ec;--gold:#2dd4bf;--hero1:#064e3b;--hero2:#0d9488}
:root[data-theme=royal]{--bg:#f6f4fb;--card:#fff;--ink:#241a3a;--mute:#6b6385;--line:#e7e2f3;--chip:#efebf8;
--accent:#5b3cc4;--accent-soft:#ede8fb;--gold:#f472b6;--hero1:#2e1a78;--hero2:#7c3aed}
:root[data-theme=sunset]{--bg:#fbf6f2;--card:#fff;--ink:#3a2418;--mute:#7c6457;--line:#f0e3d9;--chip:#f8ece3;
--accent:#c2410c;--accent-soft:#fdeee4;--gold:#fbbf24;--hero1:#7c2d12;--hero2:#ea580c}
:root[data-theme=midnight]{--bg:#0e1320;--card:#161d2e;--ink:#e6e9f2;--mute:#97a0b8;--line:#26304a;--chip:#1f2740;
--accent:#8fb0ff;--accent-soft:#1f2a45;--gold:#ffc861;--hero1:#131c38;--hero2:#33449a;
--red:#ff8787;--red-soft:#3a1d24;--amber:#ffc078;--amber-soft:#3a2c17;--blue:#8fb0ff;--blue-soft:#1d2a4a;
--green:#69db7c;--green-soft:#183323;--shadow:0 1px 2px rgba(0,0,0,.4),0 6px 18px rgba(0,0,0,.25)}
:root{--red:#c92a2a;--red-soft:#fff0f0;--amber:#b35c00;--amber-soft:#fff4e5;--blue:#1c64d1;--blue-soft:#eaf1fe;
--green:#2b8a3e;--green-soft:#ebf8ef;--shadow:0 1px 2px rgba(16,24,40,.05),0 6px 18px rgba(16,24,40,.06)}
body{background:var(--bg)}
/* banner */
.hero{background:linear-gradient(135deg,var(--hero1),var(--hero2));color:#fff;border-radius:18px;padding:22px 22px 16px;
box-shadow:0 14px 34px -12px var(--hero1);position:relative;overflow:hidden}
.hero::after{content:"";position:absolute;right:-60px;top:-60px;width:220px;height:220px;border-radius:50%;
background:radial-gradient(circle,rgba(255,255,255,.16),transparent 70%);pointer-events:none}
.hero header{align-items:center}.hero h1{color:#fff;font-size:25px;letter-spacing:-.01em}
.hero .sub{color:rgba(255,255,255,.78)}
.hero .sync{background:rgba(255,255,255,.1);border:1px solid rgba(255,255,255,.18);color:#fff;margin-top:16px}
.hero .sync .when{color:rgba(255,255,255,.78)}.hero .sync .ok i{color:var(--gold)}
.hero .sync .failed i{color:#ffb3b3}.hero .sync .stale i{color:#ffd8a8}
.theme-pick{display:flex;gap:7px;align-items:center;font-size:12px;color:rgba(255,255,255,.8)}
.theme-pick button{width:22px;height:22px;border-radius:50%;border:2px solid rgba(255,255,255,.55);padding:0;cursor:pointer}
.theme-pick button.on{border-color:#fff;box-shadow:0 0 0 2px rgba(255,255,255,.35)}
/* tabs with a colour per profile */
.tabs{margin-top:16px}.tab{box-shadow:var(--shadow);border-color:transparent;font-weight:500}
.tab::before{content:"";display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:7px;background:var(--pc,var(--mute))}
.tab[data-tab=all]::before{display:none}
.tab[data-tab=triveni]{--pc:#f76707}.tab[data-tab=sangam]{--pc:#1c7ed6}.tab[data-tab=sundarban]{--pc:#37b24d}
.tab[data-tab=adllp]{--pc:#7048e8}.tab[data-tab=caliber]{--pc:#d6336c}.tab[data-tab=personal]{--pc:#f59f00}
.tab.on{background:var(--accent);color:#fff}.tab.on::before{background:#fff}
:root[data-theme=midnight] .tab.on{color:#0e1320}
/* number cards: own colour + icon each */
.kpi{border:0;border-top:4px solid var(--kc);border-radius:14px;box-shadow:var(--shadow);padding:14px 16px}
.kpi b{color:var(--kc);font-size:30px;letter-spacing:-.02em}
.kpi span::before{margin-right:6px}
.kpis .kpi:nth-child(1){--kc:var(--accent)}.kpis .kpi:nth-child(1) span::before{content:"\u26a1"}
.kpis .kpi:nth-child(2){--kc:var(--blue)}.kpis .kpi:nth-child(2) span::before{content:"\U0001F4C5"}
.kpis .kpi:nth-child(3){--kc:var(--amber)}.kpis .kpi:nth-child(3) span::before{content:"\u270d\ufe0f"}
.kpis .kpi:nth-child(4){--kc:var(--red)}.kpis .kpi:nth-child(4) span::before{content:"\u23f0"}
.kpis .kpi:nth-child(5){--kc:var(--green)}.kpis .kpi:nth-child(5) span::before{content:"\U0001F4CC"}
.kpis .kpi:nth-child(6){--kc:var(--red)}.kpis .kpi:nth-child(6) span::before{content:"\u26a0\ufe0f"}
.kpi b.red{color:var(--red)}
/* sections */
section{border:0;border-radius:16px;box-shadow:var(--shadow);padding:18px}
section h2{color:var(--accent);font-size:14px;display:flex;align-items:center;gap:8px;padding-bottom:10px;
border-bottom:2px solid var(--accent-soft);margin-bottom:6px}
section li{border-radius:10px;padding:11px 8px;margin:0 -8px;border-top-color:var(--line)}
section li:hover{background:var(--accent-soft)}
.owner{color:var(--accent)}
/* status pills */
.flag{font-weight:600;background:var(--chip);color:var(--mute)}
.flag.Overdue{background:var(--red-soft);color:var(--red)}.flag.Due{background:var(--amber-soft);color:var(--amber)}
.flag.New{background:var(--blue-soft);color:var(--blue)}.flag.Follow{background:var(--accent-soft);color:var(--accent)}
.flag.Waiting{background:var(--amber-soft);color:var(--amber)}
/* item buttons */
.acts button{background:var(--card)}
.acts button[data-a=done]:hover{border-color:var(--green);color:var(--green);background:var(--green-soft)}
.acts button[data-a=wa]{color:#128c4b;border-color:#b2e5c7;background:#effaf3}
.acts button[data-a=wa]:hover{background:#dcf5e6;border-color:#25d366;color:#0b6e3a}
.acts button[data-a=mail]{color:var(--blue);border-color:var(--blue-soft);background:var(--blue-soft)}
:root[data-theme=midnight] .acts button[data-a=wa]{background:#14301f;border-color:#1f5c37;color:#7ee2a8}
.act-form .go,.fwd .go{background:var(--accent);border-color:var(--accent);color:#fff}
.pop-in{border:0;box-shadow:0 18px 40px -10px rgba(16,24,40,.35)}
a{color:var(--accent)}
"""

THEME_BOOT = ("<script>try{document.documentElement.dataset.theme=localStorage.getItem('sb-theme')||'%s';}"
              "catch(e){document.documentElement.dataset.theme='%s';}</script>" % (DEFAULT_THEME, DEFAULT_THEME))

THEME_JS = """
(function(){
  var btns=[].slice.call(document.querySelectorAll('.theme-pick button'));
  function mark(){var t=document.documentElement.dataset.theme;btns.forEach(function(b){b.classList.toggle('on',b.dataset.theme===t);});}
  btns.forEach(function(b){b.addEventListener('click',function(){document.documentElement.dataset.theme=b.dataset.theme;
    try{localStorage.setItem('sb-theme',b.dataset.theme);}catch(e){}mark();});});
  mark();
})();
"""


def _theme_picker() -> str:
    dots = "".join(f'<button type="button" data-theme="{k}" title="{escape(label)}" aria-label="{escape(label)} theme" '
                   f'style="background:{sw}"></button>' for k, label, sw in THEMES)
    return f'<div class="theme-pick"><span>Theme</span>{dots}</div>'


def _flag_class(flag: str) -> str:
    return flag.split()[0].replace("·", "")


def _pk(profile: str | None) -> str:
    return profiles.key(profile)


def _actions(items: list[Action], empty: str) -> str:
    if not items:
        return f'<p class="empty">{escape(empty)}</p>'
    lis = []
    for a in items:
        link = f' · <a href="{escape(a.link)}" target="_blank">source</a>' if a.link else ""
        meta = " · ".join(x for x in [a.kind, a.who, a.project, f"due {a.due}" if a.due else ""] if x)
        lis.append(
            f'<li data-p="{_pk(a.profile)}" data-id="{escape(a.id)}"><div class="row"><div class="t">{escape(a.text)}</div>'
            f'<span class="flag {_flag_class(a.flag)}">{escape(a.flag)}</span></div>'
            f'<div class="m">{escape(a.id)} · {escape(meta)}{link}</div></li>'
        )
    return f'<ul>{"".join(lis)}</ul><p class="empty none-here" hidden>{escape(empty)}</p>'


def _meeting_profile(store: Store, m) -> str:
    """Tag a meeting from its title, else from its attendees' open items. "" = All tab only."""
    name = profiles.guess(m.title, m.location)
    if name == profiles.OTHER:
        name = profiles.guess(" ".join(meeting_prep(store, m.others)))
    return "" if name == profiles.OTHER else _pk(name)


def _meetings(store: Store, meetings, now: datetime) -> str:
    if meetings is None:
        return '<p class="empty">Calendar unavailable this run (see log).</p>'
    if not meetings:
        return '<p class="empty">No meetings in the next 7 days.</p>'
    out, day = [], None
    for m in meetings:
        if m.start.date() != day:
            if day is not None:
                out.append("</ul></div>")
            day = m.start.date()
            label = "Today" if day == now.date() else f"{m.start:%A}"
            out.append(f'<div class="grp"><div class="owner">{label} <span class="sub">{m.start:%d %b}</span></div><ul>')
        when = "All day" if m.all_day else f"{clock(m.start)}–{clock(m.end)}"
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
            f'<li data-p="{_meeting_profile(store, m)}" class="{"past" if past else ""}"><div class="row"><div class="t">'
            f'<span class="time">{when}</span> {escape(m.title)}</div>{flag}</div>'
            f'<div class="m">{meta}</div>{prep_html}</li>'
        )
    out.append("</ul></div>")
    out.append('<p class="empty none-here" hidden>No meetings for this profile this week.</p>')
    return "".join(out)


def _messages(msgs: list[dict]) -> str:
    if not msgs:
        return '<p class="empty">No mail or WhatsApp in the last 24 hours.</p>'
    lis = []
    for m in msgs:
        icon = "✉" if m["source"] == "gmail" else "💬"
        title = escape(m["title"])
        if m.get("link"):
            title = f'<a href="{escape(m["link"])}" target="_blank">{title}</a>'
        about = f'<div class="m">{escape(m["summary"])}</div>' if m.get("summary") else ""
        lis.append(f'<li data-p="{_pk(m.get("profile"))}"><div class="t"><span class="ic">{icon}</span> {title}</div>{about}</li>')
    return (f'<ul>{"".join(lis)}</ul>'
            '<p class="empty none-here" hidden>No mail or WhatsApp for this profile in the last 24 hours.</p>')


TABS_CSS = """
.tabs{display:flex;gap:6px;overflow-x:auto;margin:14px 0 0;padding-bottom:2px;scrollbar-width:none}
.tabs::-webkit-scrollbar{display:none}
.tab{flex:0 0 auto;border:1px solid var(--line);background:var(--card);color:var(--ink);border-radius:999px;
padding:6px 12px;font:inherit;font-size:14px;cursor:pointer}
.tab .n{color:var(--mute);margin-left:5px;font-size:12px}
.tab.on{background:var(--accent);border-color:var(--accent);color:var(--card)}.tab.on .n{color:var(--card);opacity:.85}
.ic{margin-right:2px}
.kpi{position:relative;cursor:default}.kpi:focus{outline:2px solid var(--accent);outline-offset:2px}
.pop{display:none;position:absolute;top:100%;left:0;z-index:30;padding-top:6px;width:min(380px,calc(100vw - 32px))}
.pop.r{left:auto;right:0}
.kpi:hover .pop,.kpi.open .pop{display:block}
.pop-in{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:10px 14px;
max-height:min(380px,60vh);overflow:auto;box-shadow:0 10px 30px rgba(0,0,0,.18)}
.pop-h{font-weight:600;font-size:13px;color:var(--mute);text-transform:uppercase;letter-spacing:.05em;margin-bottom:4px}
.pop li{padding:7px 0}.pt{font-size:14px;font-weight:500;overflow-wrap:anywhere}
.acts{display:flex;gap:6px;flex-wrap:wrap;margin-top:7px}
.acts button,.act-form button{font:inherit;font-size:12px;padding:3px 10px;border-radius:999px;border:1px solid var(--line);
background:var(--card);color:var(--ink);cursor:pointer}
.acts button:hover,.act-form button:hover{border-color:var(--accent);color:var(--accent)}
.act-form{display:flex;gap:6px;flex-wrap:wrap;align-items:center;margin-top:7px;font-size:13px}
.act-form select,.act-form input{font:inherit;font-size:13px;padding:3px 6px;border:1px solid var(--line);border-radius:6px;
background:var(--card);color:var(--ink)}
.act-form .go{background:var(--accent);border-color:var(--accent);color:var(--card)}
li.closed{opacity:.35;text-decoration:line-through;transition:opacity .5s}
.fwd{display:flex;flex-direction:column;gap:6px;width:100%}
.person{border:1px solid var(--line);border-radius:12px;padding:10px 14px;margin:10px 0}
.person-h{display:flex;align-items:center;gap:10px;flex-wrap:wrap}
.person-h .avatar{width:30px;height:30px;border-radius:50%;display:grid;place-items:center;font-weight:700;
background:var(--accent-soft,#e7edf6);color:var(--accent)}
.person-h .cnt{color:var(--mute);font-size:13px}
.person-h .remind{margin-left:auto;font:inherit;font-size:12px;padding:4px 11px;border-radius:999px;cursor:pointer;
color:#128c4b;border:1px solid #b2e5c7;background:#effaf3}
#team .person ul{margin-top:4px}
.fwd label{display:flex;gap:6px;align-items:center;flex-wrap:wrap}.fwd .to{flex:1;min-width:160px}
.fwd textarea{font:inherit;font-size:13px;padding:6px 8px;border:1px solid var(--line);border-radius:6px;
background:var(--card);color:var(--ink);width:100%;resize:vertical}
.fwd .who{color:var(--mute);font-size:12px}.fwd .go{align-self:flex-start}
.chip-note{color:var(--accent);font-weight:600}.flag.Follow{color:var(--accent)}
.toast{position:fixed;left:50%;bottom:20px;transform:translateX(-50%);background:var(--ink);color:var(--bg);
padding:9px 16px;border-radius:8px;font-size:14px;z-index:60;max-width:calc(100vw - 32px)}
"""

ACTIONS_JS = """
(function(){
  var SB=window.SB||{}, base=SB.base||'', PROFS=__PROFILES__, CONTACTS=__CONTACTS__, TEAM=__TEAM__;
  function esc(t){return String(t).replace(/[&<>"]/g,function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c];});}
  // Contact pickers (shared <datalist>s): type a name, pick from the list.
  (function(){var w=document.createElement('datalist');w.id='sb-wa';var m=document.createElement('datalist');m.id='sb-mail';
    CONTACTS.forEach(function(c){
      if(c.p){var o=document.createElement('option');o.value=c.n;o.label=(c.r?c.r+' \u00b7 ':'')+'+'+c.p;w.appendChild(o);}
      if(c.e){var o2=document.createElement('option');o2.value=c.n;o2.label=(c.r?c.r+' \u00b7 ':'')+c.e;m.appendChild(o2);}
    });document.body.appendChild(w);document.body.appendChild(m);})();
  function findContact(q,need){q=(q||'').trim().toLowerCase();if(!q)return null;
    var list=CONTACTS.filter(function(c){return c[need];});
    return list.filter(function(c){return c.n.toLowerCase()===q;})[0]||
      (function(){var m=list.filter(function(c){return c.n.toLowerCase().indexOf(q)>=0;});return m.length===1?m[0]:null;})();}
  function draft(li){var t=li.querySelector('.t'),m=li.querySelector('.m');
    var item=t?t.textContent.trim():'',meta=m?m.textContent.split(' \u00b7 source')[0].trim():'';
    return 'please follow up on this and update me:\\n\u2022 '+item+'\\n\u2022 '+meta;}
  function iso(d){var z=new Date(d.getTime()-d.getTimezoneOffset()*60000);return z.toISOString().slice(0,10);}
  function plus(n){var d=new Date();d.setDate(d.getDate()+n);return iso(d);}
  function nice(v){var d=new Date(v+'T00:00:00');return d.toLocaleDateString('en-GB',{day:'numeric',month:'short'});}
  var tt;function toast(msg){var t=document.querySelector('.toast');if(!t){t=document.createElement('div');t.className='toast';document.body.appendChild(t);}
    t.textContent=msg;t.hidden=false;clearTimeout(tt);tt=setTimeout(function(){t.hidden=true;},3500);}
  function note(li,text){var m=li.querySelector('.m');if(!m)return;var c=li.querySelector('.chip-note');
    if(!c){c=document.createElement('span');c.className='chip-note';m.appendChild(c);}c.textContent=' · '+text;}
  function effect(id,a,v,quiet){
    document.querySelectorAll('li[data-id="'+id+'"]').forEach(function(li){
      if(a==='done'){li.dataset.gone='1';if(quiet){li.hidden=true;}else{li.classList.add('closed');setTimeout(function(){li.hidden=true;},700);}}
      else if(a==='followup'){note(li,'Follow up '+nice(v));}
      else if(a==='move'){var p=PROFS.filter(function(x){return x.name===v;})[0];if(p){li.dataset.p=p.key;}note(li,'Moved to '+v);}
      else if(a==='shift'){note(li,'Due '+nice(v));}
    });
    if(window.SBrefresh&&(a==='move'||quiet))window.SBrefresh();
  }
  function today(){return iso(new Date());}
  function ago(d){if(!d)return '';var n=Math.round((new Date(today())-new Date(d))/864e5);
    return n<=0?'sent today':n===1?'sent yesterday':'sent '+n+' days ago';}
  function renderTeam(){
    var box=document.getElementById('team');if(!box)return;
    var by={};TEAM.forEach(function(x){(by[x.to]=by[x.to]||[]).push(x);});
    var names=Object.keys(by).sort(function(a,b){return by[b].length-by[a].length||a.localeCompare(b);});
    if(!names.length){box.innerHTML='<p class="empty">Nothing pushed to anyone yet. Use \U0001F4AC WhatsApp or \u2709 Email on an item and it shows up here under that person.</p>';return;}
    box.innerHTML=names.map(function(n){
      var items=by[n].slice().sort(function(a,b){return (a.on||'').localeCompare(b.on||'');});
      var c=findContact(n,'p');
      return '<div class="grp person"><div class="person-h"><span class="avatar">'+esc(n.charAt(0).toUpperCase())+'</span>'+
        '<b>'+esc(n)+'</b><span class="cnt">'+items.length+' pending</span>'+
        (c?'<button class="remind" data-to="'+esc(n)+'">\U0001F4AC Remind all</button>':'')+'</div><ul>'+
        items.map(function(x){var old=x.on&&(new Date(today())-new Date(x.on))/864e5>=3;
          return '<li data-p="'+x.p+'" data-id="'+esc(x.id)+'"><div class="row"><div class="t">'+esc(x.t)+'</div>'+
            '<span class="flag '+(old?'Overdue':'Follow')+'">'+esc(ago(x.on))+'</span></div><div class="m">'+esc(x.m)+'</div></li>';}).join('')+
        '</ul></div>';}).join('')+'<p class="empty none-here" hidden>Nothing pending with the team for this profile.</p>';
    box.querySelectorAll('li[data-id]').forEach(function(li){if(!li.querySelector('.acts'))bar(li);});
    if(window.SBrefresh)window.SBrefresh();
  }
  function addTeam(id,who){
    var src=document.querySelector('section:not(.team) li[data-id="'+id+'"]');
    var have=TEAM.filter(function(x){return x.id===id;})[0];
    if(have){if(have.to!==who){have.to=who;have.on=today();}}
    else if(src){TEAM.push({id:id,t:(src.querySelector('.t')||{}).textContent||id,
      m:((src.querySelector('.m')||{}).textContent||'').split(' \u00b7 source')[0],p:src.dataset.p,to:who,on:today()});}
    renderTeam();
  }
  var _effect=effect;
  effect=function(id,a,v,quiet){
    if(a==='nudge'&&v.indexOf(' to ')>0){addTeam(id,v.split(' to ').slice(1).join(' to ').trim());return;}
    if(a==='done'){TEAM=TEAM.filter(function(x){return x.id!==id;});setTimeout(renderTeam,quiet?0:750);}
    _effect(id,a,v,quiet);
  };
  (SB.pending||[]).forEach(function(x){effect(x.item,x.action,x.value,true);});
  document.addEventListener('click',function(e){
    var r=e.target.closest('button.remind');if(!r)return;
    var n=r.dataset.to,c=findContact(n,'p');if(!c)return;
    var items=TEAM.filter(function(x){return x.to===n;});
    var text='Hi '+n.split(' ')[0]+', a quick reminder on these pending items. Please update me:'+
      items.map(function(x,i){return '\\n'+(i+1)+'. '+x.t+' ('+x.id+')';}).join('');
    window.open('https://wa.me/'+c.p+'?text='+encodeURIComponent(text),'_blank','noopener');
    items.forEach(function(x){send(x.id,'nudge','reminder on WhatsApp to '+n,'Reminder opened for '+n);});
  });
  function send(id,a,v,label){
    return fetch(base+'/api/item-action',{method:'POST',credentials:'same-origin',
      headers:{'Content-Type':'application/json','X-Second-Brain':'1'},body:JSON.stringify({item:id,action:a,value:v})})
    .then(function(r){if(!r.ok)throw new Error(r.status);effect(id,a,v,false);toast(label+'. The Excel updates at the next sync.');})
    .catch(function(){toast('Could not save. Open the dashboard website and try again.');});
  }
  function bar(li){
    if(li.querySelector('.acts'))return;
    var id=li.dataset.id, risk=id.charAt(0)==='R';
    var b=document.createElement('div');b.className='acts';
    b.innerHTML='<button data-a="done">\u2713 Close</button><button data-a="followup">\u21bb Follow up</button>'+
      '<button data-a="move">\u21c4 Move</button>'+(risk?'':'<button data-a="shift">\U0001F4C5 Shift</button>')+
      '<button data-a="wa">\U0001F4AC WhatsApp</button><button data-a="mail">\u2709 Email</button>';
    li.appendChild(b);
  }
  document.querySelectorAll('section li[data-id]').forEach(bar);
  setTimeout(renderTeam,0);
  function form(li,html){var f=li.querySelector('.act-form');if(f){f.remove();}f=document.createElement('div');
    f.className='act-form';f.innerHTML=html+'<button data-cancel>Cancel</button>';li.appendChild(f);return f;}
  function forward(li,f,kind){
    var wa=kind==='wa',id=li.dataset.id,raw=f.querySelector('.to').value.trim(),msg=f.querySelector('textarea').value;
    var c=findContact(raw,wa?'p':'e'),name,addr;
    if(c){name=c.n;addr=wa?c.p:c.e;}
    else if(wa&&/\\d{10,}/.test(raw.replace(/\\D/g,''))){addr=raw.replace(/\\D/g,'');if(addr.length===10)addr='91'+addr;name=f.querySelector('.nm').value.trim()||'+'+addr;}
    else if(!wa&&/@/.test(raw)){addr=raw;name=f.querySelector('.nm').value.trim()||raw;}
    else{toast(wa?'Pick a name from the list, or type a mobile number.':'Pick a name from the list, or type an email address.');return;}
    var first=name.charAt(0)==='+'?'':name.split(' ')[0];
    var text=(first?'Hi '+first+', ':'Hi, ')+msg;
    if(wa){window.open('https://wa.me/'+addr+'?text='+encodeURIComponent(text),'_blank','noopener');}
    else{var subj='Follow up: '+(li.querySelector('.t')||{}).textContent;
      window.location.href='mailto:'+encodeURIComponent(addr)+'?subject='+encodeURIComponent(subj.slice(0,120))+'&body='+encodeURIComponent(text);}
    var save=f.querySelector('.save');
    if(!c&&!save.hidden&&save.querySelector('input[type=checkbox]').checked&&f.querySelector('.nm').value.trim()){
      fetch(base+'/api/item-action',{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json','X-Second-Brain':'1'},
        body:JSON.stringify({item:'',action:'contact',value:f.querySelector('.nm').value.trim()+'|'+(wa?addr:'')+'|'+(wa?'':addr)})})
        .then(function(r){if(r.ok){CONTACTS.push({n:f.querySelector('.nm').value.trim(),p:wa?addr:'',e:wa?'':addr,r:''});}});}
    send(id,'nudge',(wa?'on WhatsApp':'by email')+' to '+name,(wa?'WhatsApp':'Email')+' opened for '+name);
    f.remove();
  }
  document.addEventListener('click',function(e){
    var btn=e.target.closest('.acts button, .act-form button');if(!btn)return;
    var li=btn.closest('li[data-id]'),id=li.dataset.id;
    if(btn.hasAttribute('data-cancel')){btn.parentNode.remove();return;}
    if(btn.dataset.when){send(id,'followup',btn.dataset.when,'Follow-up set for '+nice(btn.dataset.when));btn.parentNode.remove();return;}
    if(btn.dataset.fwd){forward(li,btn.parentNode,btn.dataset.fwd);return;}
    if(btn.dataset.save){var f=btn.parentNode,el=f.querySelector('select,input');if(!el.value)return;
      var a=btn.dataset.save;send(id,a,el.value,a==='move'?'Moved to '+el.value:a==='shift'?'Due date set to '+nice(el.value):'Follow-up set for '+nice(el.value));f.remove();return;}
    var a=btn.dataset.a;
    if(a==='done'){if(confirm('Close this item? It will be marked done and leave the dashboard.'))send(id,'done','','Closed');}
    else if(a==='followup'){form(li,'Follow up: <button data-when="'+plus(1)+'">Tomorrow</button><button data-when="'+plus(3)+'">In 3 days</button>'+
      '<button data-when="'+plus(7)+'">Next week</button><input type="date" min="'+plus(0)+'"><button class="go" data-save="followup">Set</button>');}
    else if(a==='move'){var cur=li.dataset.p;form(li,'Move to: <select>'+PROFS.filter(function(x){return x.key!==cur;}).map(function(x){
      return '<option>'+x.name+'</option>';}).join('')+'</select><button class="go" data-save="move">Move</button>');}
    else if(a==='shift'){form(li,'New due date: <input type="date" min="'+plus(0)+'"><button class="go" data-save="shift">Save</button>');}
    else if(a==='wa'||a==='mail'){var wa=a==='wa';
      var f=form(li,'<div class="fwd"><label>'+(wa?'WhatsApp to':'Email to')+' <input class="to" list="'+(wa?'sb-wa':'sb-mail')+
        '" placeholder="Type a name'+(wa?' or number':' or email')+'" autocomplete="off"></label><span class="who"></span>'+
        '<textarea rows="4">'+esc(draft(li))+'</textarea>'+
        '<label class="save" hidden><input type="checkbox" checked> Save as contact: <input class="nm" placeholder="Name"></label>'+
        '<button class="go" data-fwd="'+a+'">'+(wa?'Open WhatsApp':'Open email')+'</button></div>');
      var to=f.querySelector('.to');to.focus();
      to.addEventListener('input',function(){var c=findContact(to.value,wa?'p':'e'),who=f.querySelector('.who'),sv=f.querySelector('.save');
        if(c){who.textContent=' '+(wa?'+'+c.p:c.e);sv.hidden=true;}
        else{who.textContent='';var raw=to.value.trim();sv.hidden=!(wa?/\\d{10,}/.test(raw.replace(/\\D/g,'')):/@/.test(raw));}});}
  });
})();
"""

TABS_JS = """
(function(){
  var tabs=[].slice.call(document.querySelectorAll('.tab'));
  var cur='all';
  function show(p){
    cur=p;
    tabs.forEach(function(t){t.classList.toggle('on',t.dataset.tab===p);});
    document.querySelectorAll('[data-p]').forEach(function(el){
      el.hidden = el.dataset.gone==='1' || (p!=='all' && el.dataset.p!==p);
    });
    document.querySelectorAll('.grp').forEach(function(g){
      g.hidden = !g.querySelector('li:not([hidden])');
    });
    document.querySelectorAll('section, .pop').forEach(function(sec){
      var none=sec.querySelector('.none-here'); if(!none) return;
      none.hidden = !!sec.querySelector('li:not([hidden])') || !sec.querySelector('li');
    });
    document.querySelectorAll('[data-v]').forEach(function(b){
      var n=JSON.parse(b.dataset.v)[p]||0; b.textContent=n;
      if(b.dataset.alert){b.classList.toggle('red',n>0);}
    });
    try{ history.replaceState(null,'',p==='all'?location.pathname+location.search:'#'+p); }catch(e){}
  }
  window.SBrefresh=function(){show(cur);};
  tabs.forEach(function(t){t.addEventListener('click',function(){show(t.dataset.tab);});});
  var kpis=[].slice.call(document.querySelectorAll('.kpi'));
  function place(k){var p=k.querySelector('.pop'); if(!p) return; p.classList.remove('r');
    var r=k.getBoundingClientRect(); if(r.left+p.offsetWidth>window.innerWidth-8||r.left+380>window.innerWidth){p.classList.add('r');}}
  kpis.forEach(function(k){
    k.addEventListener('mouseenter',function(){place(k);});
    k.addEventListener('click',function(e){
      if(e.target.closest('.pop')) return;
      var was=k.classList.contains('open');
      kpis.forEach(function(o){o.classList.remove('open');});
      if(!was){place(k);k.classList.add('open');}
    });
  });
  document.addEventListener('click',function(e){ if(!e.target.closest('.kpi')) kpis.forEach(function(o){o.classList.remove('open');}); });
  document.addEventListener('keydown',function(e){ if(e.key==='Escape') kpis.forEach(function(o){o.classList.remove('open');}); });
  var start=(location.hash||'').slice(1);
  show(tabs.some(function(t){return t.dataset.tab===start;})?start:'all');
})();
"""


def _contacts(store: Store) -> list[dict]:
    """People with a phone or email, for the forward pickers. Assistants first."""
    import re as _re
    out = []
    for r in store.rows["People"]:
        phone = _re.sub(r"\D", "", str(r.get("Phone") or "").split(",")[0])
        if len(phone) == 10:
            phone = "91" + phone
        email = str(r.get("Email") or "").strip()
        if not (phone or email) or not r.get("Name"):
            continue
        role = " · ".join(str(x) for x in (r.get("Role"), r.get("Organisation")) if x)
        out.append({"n": str(r["Name"]), "p": phone, "e": email, "r": role})
    pin = lambda c: 0 if _re.search(r"assistant|\bea\b|secretary", c["r"], _re.I) and "manager" not in c["r"].lower() else 1  # noqa: E731
    return sorted(out, key=lambda c: (pin(c), c["n"].lower()))


def _team(store: Store) -> list[dict]:
    """Open items the CEO pushed to someone (WhatsApp/email from the dashboard)."""
    out = []
    sheets = (("Commitments", "Item", OPEN_COMMITMENT, "Commitment"),
              ("Approvals", "Item", OPEN_APPROVAL, "Approval"),
              ("Risks", "Risk", {"Open"}, "Risk"))
    for sheet, col, open_states, kind in sheets:
        for r in store.rows[sheet]:
            if r.get("Pushed To") and r.get("Status", "Open") in open_states:
                meta = " \u00b7 ".join(str(x) for x in (r["ID"], kind, r.get("Project"),
                                                          f"due {r['Due']}" if r.get("Due") else "") if x)
                out.append({"id": r["ID"], "t": str(r.get(col) or ""), "m": meta, "p": _pk(r.get("Profile")),
                            "to": str(r["Pushed To"]), "on": str(r.get("Pushed On") or "")[:10]})
    return out


def _per_profile(rows, key_of) -> dict:
    """{'all': n, '<profile key>': n, ...} for numbers that change with the tab."""
    out = {"all": 0, **{p["key"]: 0 for p in profiles.PROFILES}}
    for r in rows:
        out["all"] += 1
        k = key_of(r)
        out[k] = out.get(k, 0) + 1
    return out


POP_MAX = 15


def _pop(title: str, items: list[tuple[str, str, str]]) -> str:
    """Hover/tap panel for a KPI card. items = (profile key, main text, detail line)."""
    if not items:
        body = '<p class="empty">Nothing here.</p>'
    else:
        lis = "".join(
            '<li data-p="%s"><div class="pt">%s</div>%s</li>'
            % (k, escape(t), '<div class="m">%s</div>' % escape(m) if m else "")
            for k, t, m in items
        )
        body = f'<ul>{lis}</ul><p class="empty none-here" hidden>Nothing for this profile.</p>'
    return f'<div class="pop" role="tooltip"><div class="pop-in"><div class="pop-h">{escape(title)}</div>{body}</div></div>'


def _kpi(label: str, counts: dict, alert: bool = False, items: list | None = None) -> str:
    n = counts["all"]
    cls = "red" if alert and n else ""
    data = escape(json.dumps(counts), quote=True)
    pop = _pop(label, items) if items is not None else ""
    return (f'<div class="kpi" tabindex="0"><b class="{cls}" data-v="{data}"'
            f'{" data-alert=1" if alert else ""}>{n}</b><span>{escape(label)}</span>{pop}</div>')


def _row_items(rows, text_col: str, meta) -> list[tuple[str, str, str]]:
    return [(_pk(r.get("Profile")), str(r.get(text_col) or ""), meta(r)) for r in rows]


def _dot(*parts) -> str:
    return " · ".join(str(x) for x in parts if x)


def render(store: Store, now: datetime, meetings=None, sync: dict | None = None,
           msgs: list[dict] | None = None) -> str:
    today = now.date()
    act = act_today(store, now)
    waiting = waiting_on_me(store, today)
    overdue = overdue_by_owner(store, today)
    row_pk = lambda r: _pk(r.get("Profile"))  # noqa: E731
    open_c = [r for r in store.rows["Commitments"] if r.get("Status") in OPEN_COMMITMENT]
    pending = [r for r in store.rows["Approvals"] if r.get("Status") in OPEN_APPROVAL]
    open_r = [r for r in store.rows["Risks"] if r.get("Status", "Open") == "Open"]
    high = [r for r in open_r if r.get("Severity") == "High"]
    od_rows = [r for rows in overdue.values() for r in rows]
    todays = [m for m in (meetings or []) if m.start.date() == today]

    # Tab badge = open things in that profile (commitments + approvals + open risks).
    badge = _per_profile(open_c + pending + open_r, row_pk)
    tabs = ['<button class="tab" data-tab="all">All</button>'] + [
        f'<button class="tab" data-tab="{p["key"]}">{escape(p["name"])}'
        f'<span class="n">{badge.get(p["key"], 0)}</span></button>'
        for p in profiles.PROFILES if p["key"] != "other" or badge.get("other")
    ]

    od_html = []
    for owner, rows in overdue.items():
        od_html.append(f'<div class="grp"><div class="owner">{escape(owner)} <span class="sub">({len(rows)})</span></div><ul>')
        for r in rows:
            link = f' · <a href="{escape(r["Source Link"])}" target="_blank">source</a>' if r.get("Source Link") else ""
            od_html.append(
                f'<li data-p="{row_pk(r)}" data-id="{escape(r["ID"])}"><div class="row"><div class="t">{escape(str(r.get("Item", "")))}</div>'
                f'<span class="flag Overdue">{r["_late"]}d late</span></div>'
                f'<div class="m">{escape(r["ID"])} · due {escape(str(r.get("Due")))}'
                f'{" · " + escape(str(r["Project"])) if r.get("Project") else ""}{link}</div></li>'
            )
        od_html.append("</ul></div>")
    if od_html:
        od_html.append('<p class="empty none-here" hidden>Nothing overdue for this profile.</p>')

    meet_items = [(_meeting_profile(store, m), m.title,
                   "All day" if m.all_day else f"{clock(m.start)}–{clock(m.end)}") for m in todays]
    meet_kpi = (_kpi("Meetings today", _per_profile(todays, lambda m: _meeting_profile(store, m) or "none"),
                     items=meet_items)
                if meetings is not None else '<div class="kpi"><b>–</b><span>Meetings today</span></div>')
    act_items = [(_pk(a.profile), a.text, _dot(a.id, a.kind, a.flag)) for a in act]
    appr_items = _row_items(pending, "Item", lambda r: _dot(r.get("ID"), r.get("Requested By"),
                                                             r.get("Amount"), f"due {r['Due']}" if r.get("Due") else ""))
    od_items = _row_items(od_rows, "Item", lambda r: _dot(r.get("ID"), r.get("Owner"), f"{r['_late']}d late"))
    oc_items = _row_items(sorted(open_c, key=lambda r: str(r.get("Due") or "9999")), "Item",
                          lambda r: _dot(r.get("ID"), r.get("Owner"), f"due {r['Due']}" if r.get("Due") else ""))
    hr_items = _row_items(high, "Risk", lambda r: _dot(r.get("ID"), r.get("Project"), r.get("Owner")))
    greet = "Good morning" if now.hour < 12 else "Good afternoon" if now.hour < 17 else "Good evening"
    contacts_js = json.dumps(_contacts(store), ensure_ascii=False).replace("</", "<\\/")
    team_js = json.dumps(_team(store), ensure_ascii=False).replace("</", "<\\/")
    profiles_js = json.dumps([{"key": p["key"], "name": p["name"]} for p in profiles.PROFILES]).replace("</", "<\\/")
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Second Brain</title>{THEME_BOOT}<style>{CSS}{sync_status.CSS}{TABS_CSS}{THEME_CSS}</style></head><body><main>
<div class="hero"><header><div><h1>{greet}, {escape(settings.me_name.split()[0])}</h1>
<span class="sub">{now:%A, %d %b %Y} · {clock(now)}</span></div>{_theme_picker()}</header>
{sync_status.html_box(sync, now) if sync is not None else ""}</div>
<nav class="tabs" aria-label="Profiles">{"".join(tabs)}</nav>
<div class="kpis">
{_kpi("Act today", _per_profile(act, lambda a: _pk(a.profile)), items=act_items)}
{meet_kpi}
{_kpi("Approvals waiting on you", _per_profile(pending, row_pk), items=appr_items)}
{_kpi("Overdue commitments", _per_profile(od_rows, row_pk), alert=True, items=od_items)}
{_kpi("Open commitments", _per_profile(open_c, row_pk), items=oc_items)}
{_kpi("Open high risks", _per_profile(high, row_pk), alert=True, items=hr_items)}
</div>
<div class="grid">
<section><h2>\u26a1 Act today</h2>{_actions(act, "Nothing urgent. Clear runway.")}</section>
<section><h2>\u270b Waiting on me</h2>{_actions(waiting, "Nobody is waiting on you.")}</section>
<section><h2>\u23f0 Overdue by owner</h2>{"".join(od_html) or '<p class="empty">Nothing overdue.</p>'}</section>
<section><h2>\U0001F4C5 This week's meetings</h2>{_meetings(store, meetings, now)}</section>
<section class="wide team"><h2>\U0001F465 Pending with team</h2><div id="team"></div></section>
<section class="wide"><h2>\U0001F4AC Mail &amp; WhatsApp · last 24h</h2>{_messages(msgs or [])}</section>
</div></main><script>{THEME_JS}{TABS_JS}{ACTIONS_JS.replace("__PROFILES__", profiles_js).replace("__CONTACTS__", contacts_js).replace("__TEAM__", team_js)}</script></body></html>"""


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
        f"Updated {now:%A %d %b %Y}, {clock(now)}",
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
        when = "All day" if m.all_day else f"{clock(m.start)}–{clock(m.end)}"
        who = ", ".join(a.name for a in m.others[:4]) + (f" +{len(m.others) - 4}" if len(m.others) > 4 else "")
        flag = " · ⚠ not responded" if m.my_response == "needsAction" else ""
        md.append(f"- {when} **{m.title}**{' · ' + who if who else ''}{flag}")
        md += [f"  - ↳ {p}" for p in meeting_prep(store, m.others)[:4]]
    return "\n".join(md)


def write(store: Store, now: datetime, meetings=None, sync: dict | None = None,
          msgs: list[dict] | None = None):
    path = settings.dashboard_html
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render(store, now, meetings, sync, msgs), encoding="utf-8")
    return path
