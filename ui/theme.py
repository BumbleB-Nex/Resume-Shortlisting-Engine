"""
Theme layer — all custom CSS, the WebGL hero banner and plotly styling.

Everything here is presentation only: no scoring logic, no external assets
(fonts and scripts are local/system so the app keeps working fully offline).
"""
from __future__ import annotations

import streamlit as st
import streamlit.components.v1 as components

# ── palette (mirrors .streamlit/config.toml) ───────────────────────
BG = "#0b0c0f"
BG_2 = "#12141a"
CARD = "#0f1116"
BORDER = "#262a33"
BORDER_HI = "#3a3f4b"
TEXT = "#e8e6e1"
MUTED = "#9096a1"
ACCENT = "#c9b27c"
ACCENT_RGB = "201,178,124"

SERIF = '"Cormorant Garamond", "Playfair Display", Georgia, "Times New Roman", serif'
SANS = 'Inter, "Segoe UI", system-ui, -apple-system, sans-serif'
EASE = "cubic-bezier(.77,0,.18,1)"

TAG_COLOR = {"STRONG": "#16a34a", "PRESENT": "#2563eb", "WEAK": "#b45309", "MISSING": "#b91c1c"}
CONF_COLOR = {"HIGH": "#4ade80", "MEDIUM": "#fbbf24", "LOW": "#f87171"}

_CSS = f"""
<style>
/* ── layout: extreme whitespace, centred column ─────────────────── */
html, body, [data-testid="stAppViewContainer"] {{ font-family: {SANS}; }}
.block-container {{ max-width: 1200px; padding: 3.2rem 2.5rem 5rem 2.5rem; }}
header[data-testid="stHeader"] {{ background: transparent; }}
[data-testid="stSidebar"] {{ background: #0d0f13; border-right: 1px solid {BORDER}; }}
[data-testid="stSidebar"] .block-container {{ padding-top: 2rem; }}
hr {{ border-color: {BORDER} !important; margin: 1.2rem 0 1.6rem 0; }}
[data-testid="stElementContainer"] {{ font-variant-numeric: tabular-nums; }}

/* ── typography: serif display, tight tracking, clip reveal ─────── */
@keyframes reveal {{ from {{ clip-path: inset(0 100% 0 0); }} to {{ clip-path: inset(0 0 0 0); }} }}
@keyframes rise   {{ from {{ opacity: 0; transform: translateY(12px); }} to {{ opacity: 1; transform: none; }} }}
h1, h2, h3, h4, .serif, [data-testid="stMetricValue"] {{
  font-family: {SERIF} !important; letter-spacing: -0.015em; font-weight: 600;
}}
h1, h2, h3 {{ animation: reveal .9s {EASE} both; }}
h2 {{ animation-delay: .08s; }}  h3 {{ animation-delay: .16s; }}  h4 {{ animation: rise .7s {EASE} both; animation-delay: .22s; }}
[data-testid="stMarkdownContainer"] h2 {{ font-size: 1.75rem; margin: .2rem 0 .6rem 0; }}
[data-testid="stMarkdownContainer"] h3 {{ font-size: 1.35rem; margin: .1rem 0 .5rem 0; }}
[data-testid="stMarkdownContainer"] h4 {{ font-size: 1.15rem; margin: 0 0 .35rem 0; }}
[data-testid="stCaptionContainer"] {{ color: {MUTED}; letter-spacing: .01em; }}
.eyebrow {{ font-size: .68rem; letter-spacing: .18em; text-transform: uppercase; color: {MUTED}; margin: 0 0 .25rem 0; }}
.big-num {{ font-family: {SERIF}; font-size: 2.1rem; font-weight: 600; line-height: 1; color: {TEXT}; }}
.big-num small {{ font-family: {SANS}; font-size: .8rem; color: {MUTED}; margin-left: .35rem; font-weight: 400; }}

/* ── cards: sharp 1px borders, ambient glow on hover ───────────── */
[data-testid="stVerticalBlockBorderWrapper"] {{
  border: 1px solid {BORDER} !important; border-radius: 4px !important; background: {CARD};
  transition: box-shadow .45s {EASE}, border-color .45s {EASE}, transform .45s {EASE};
}}
[data-testid="stVerticalBlockBorderWrapper"]:hover {{
  border-color: {BORDER_HI} !important; box-shadow: 0 0 40px rgba({ACCENT_RGB},0.08);
}}
[data-testid="stVerticalBlockBorderWrapper"] > div {{ padding: 1.05rem 1.2rem !important; }}
.sse-obs {{ opacity: 0; transform: translateY(12px); transition: opacity .8s {EASE}, transform .8s {EASE}; }}
.sse-obs.in-view {{ opacity: 1; transform: none; }}

/* ── buttons: transparent, tracked uppercase, liquid sweep, magnetic ── */
.stButton > button, .stDownloadButton > button, [data-testid="stFormSubmitButton"] > button {{
  position: relative; overflow: hidden; background: transparent; color: {TEXT};
  border: 1px solid {BORDER_HI}; border-radius: 3px; font-family: {SANS};
  text-transform: uppercase; letter-spacing: .09em; font-size: .72rem; font-weight: 600;
  padding: .55rem 1rem; min-height: 2.35rem;
  transform: translate(var(--mx, 0px), var(--my, 0px));
  transition: transform .25s {EASE}, box-shadow .25s {EASE}, background .35s {EASE}, border-color .25s, color .25s;
}}
.stButton > button::before, .stDownloadButton > button::before {{
  content: ""; position: absolute; inset: 0; pointer-events: none;
  background: linear-gradient(105deg, transparent 32%, rgba({ACCENT_RGB},.22) 50%, transparent 68%);
  background-size: 260% 100%; background-position: 130% 0;
  transition: background-position .7s {EASE};
}}
.stButton > button:hover, .stDownloadButton > button:hover {{
  border-color: {ACCENT}; color: {ACCENT}; box-shadow: 0 0 26px rgba({ACCENT_RGB},.18);
  transform: translate(var(--mx, 0px), calc(var(--my, 0px) - 2px));
}}
.stButton > button:hover::before, .stDownloadButton > button:hover::before {{ background-position: -30% 0; }}
.stButton > button:active, .stDownloadButton > button:active {{ transform: scale(.98); }}
.stButton > button:focus:not(:active) {{ border-color: {ACCENT}; box-shadow: none; }}
.stButton > button[kind="primary"] {{ background: {ACCENT}; color: {BG}; border-color: {ACCENT}; }}
.stButton > button[kind="primary"]:hover {{ color: {BG}; box-shadow: 0 0 34px rgba({ACCENT_RGB},.35); }}
.stButton > button p, .stDownloadButton > button p {{ font-size: inherit; letter-spacing: inherit; }}

/* ── navigation: underline indicator, grows from the left ───────── */
[data-testid="stButtonGroup"] [role="radiogroup"] {{
  gap: .15rem; border: none !important; border-bottom: 1px solid {BORDER} !important; border-radius: 0 !important;
  width: 100%; padding: 0; background: transparent !important; box-shadow: none !important;
}}
button[data-variant="segmented_control"] {{
  position: relative; background: transparent !important; border: none !important; border-radius: 0 !important;
  box-shadow: none !important; outline: none !important; margin: 0 !important;
  padding: .75rem 1.1rem .85rem 1.1rem !important; color: {MUTED} !important;
  font-family: {SANS}; transition: color .3s {EASE};
}}
button[data-variant="segmented_control"] p {{
  font-size: .72rem !important; letter-spacing: .13em; text-transform: uppercase; font-weight: 600;
}}
button[data-variant="segmented_control"]::after {{
  content: ""; position: absolute; left: 1.1rem; bottom: -1px; height: 1px; width: 0;
  background: {ACCENT}; transition: width .38s {EASE};
}}
button[data-variant="segmented_control"]:hover {{ color: {TEXT} !important; }}
button[data-variant="segmented_control"]:hover::after {{ width: calc(100% - 2.2rem); }}
button[data-variant="segmented_control"][aria-checked="true"] {{ color: {ACCENT} !important; }}
button[data-variant="segmented_control"][aria-checked="true"]::after {{ width: calc(100% - 2.2rem); }}

/* ── inputs / tables / charts ───────────────────────────────────── */
[data-testid="stSelectbox"] > div > div, [data-testid="stTextInput"] input, [data-testid="stFileUploader"] section {{
  background: {BG_2}; border-color: {BORDER} !important; border-radius: 3px;
}}
[data-testid="stDataFrame"] {{ border: 1px solid {BORDER}; border-radius: 4px; overflow: hidden; }}
[data-testid="stDataFrame"] * {{ font-variant-numeric: tabular-nums; }}
[data-testid="stExpander"] details {{ border: 1px solid {BORDER}; border-radius: 4px; background: {CARD}; }}
[data-testid="stExpander"] summary {{ font-family: {SANS}; letter-spacing: .04em; }}
[data-testid="stMetric"] {{ padding: 0; }}
[data-testid="stMetricLabel"] {{ color: {MUTED}; font-size: .72rem; letter-spacing: .12em; text-transform: uppercase; }}
[data-testid="stMetricValue"] {{ font-size: 2rem; }}
[data-testid="stAlert"] {{ border-radius: 3px; }}
code, pre {{ font-variant-numeric: tabular-nums; }}
[data-testid="stCode"] pre {{ background: {BG_2} !important; border: 1px solid {BORDER}; border-radius: 3px; }}

/* ── chips + evidence quotes ────────────────────────────────────── */
.chip {{ display: inline-block; padding: 2px 10px; margin: 2px 6px 4px 0; border-radius: 2px; border: 1px solid transparent;
         font-size: .74rem; font-weight: 600; letter-spacing: .03em; line-height: 1.6; white-space: nowrap; }}
.chip-green {{ background: rgba(34,197,94,.12); color: #86efac; border-color: rgba(34,197,94,.25); }}
.chip-red   {{ background: rgba(239,68,68,.12); color: #fca5a5; border-color: rgba(239,68,68,.25); }}
.chip-grey  {{ background: rgba(148,163,184,.10); color: #b6bcc7; border-color: rgba(148,163,184,.22); }}
.chip-gold  {{ background: rgba({ACCENT_RGB},.12); color: {ACCENT}; border-color: rgba({ACCENT_RGB},.3); }}
.evi {{ border-left: 1px solid rgba({ACCENT_RGB},.55); padding: .15rem .9rem; margin: .15rem 0 .8rem .15rem;
        color: #b6bcc7; font-family: {SERIF}; font-style: italic; font-size: .98rem; line-height: 1.45; }}
.evi-head {{ font-size: .84rem; color: {TEXT}; margin: .45rem 0 .1rem 0; }}
.evi-head .mt {{ font-size: .66rem; letter-spacing: .12em; text-transform: uppercase; color: {MUTED}; margin-left: .5rem; }}
.evi-head .mt.miss {{ color: #f87171; }}
.kv {{ display: flex; justify-content: space-between; font-size: .84rem; padding: .3rem 0; border-bottom: 1px solid {BORDER}; }}
.kv:last-child {{ border-bottom: none; }}
.kv span:last-child {{ color: {TEXT}; font-weight: 600; }}
.kv span:first-child {{ color: {MUTED}; }}
</style>
"""


def inject_css() -> None:
    """Inject the global stylesheet once per run (call at the top of app.py)."""
    st.markdown(_CSS, unsafe_allow_html=True)


def style_fig(fig, height: int | None = None):
    """Apply the dark, transparent plotly look."""
    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family=SANS, color=TEXT, size=12),
        colorway=[ACCENT, "#8b93a7", "#4ade80", "#f87171"],
        margin=dict(l=10, r=20, t=10, b=10),
    )
    fig.update_xaxes(gridcolor=BORDER, zerolinecolor=BORDER, linecolor=BORDER)
    fig.update_yaxes(gridcolor=BORDER, zerolinecolor=BORDER, linecolor=BORDER)
    if height:
        fig.update_layout(height=height)
    return fig


# ── WebGL hero ─────────────────────────────────────────────────────
_HERO_HTML = """
<!doctype html><html><head><meta charset="utf-8"><style>
  html,body{margin:0;padding:0;background:__BG__;overflow:hidden;height:100%;}
  #wrap{position:relative;width:100%;height:__H__px;}
  canvas{position:absolute;inset:0;width:100%;height:100%;display:block;}
  .ov{position:absolute;left:0;top:0;height:100%;display:flex;flex-direction:column;justify-content:center;padding:0 .4rem;pointer-events:none;}
  .t{font-family:__SERIF__;font-weight:600;font-size:2.55rem;letter-spacing:-.02em;line-height:1.05;color:__TEXT__;margin:0;
     animation:reveal 1.1s cubic-bezier(.77,0,.18,1) .15s both;}
  .s{font-family:__SANS__;font-size:.78rem;letter-spacing:.2em;text-transform:uppercase;color:__MUTED__;margin:.7rem 0 0 .1rem;
     animation:reveal 1.1s cubic-bezier(.77,0,.18,1) .55s both;}
  .s b{color:__ACCENT__;font-weight:600;}
  @keyframes reveal{from{clip-path:inset(0 100% 0 0)}to{clip-path:inset(0 0 0 0)}}
</style></head><body><div id="wrap"><canvas id="c"></canvas>
<div class="ov"><h1 class="t">Smart Shortlisting Engine</h1>
<div class="s">Local &middot; semantic <b>+</b> keyword matching &middot; evidence-backed ranking</div></div></div>
<script>
(function(){
  var cv=document.getElementById('c'), DPR=Math.min(1.5, window.devicePixelRatio||1);
  var W=0,H=0, t0=performance.now(), mouse={x:0,y:0}, target={x:0,y:0}, hidden=false;
  var NX=100, NZ=54, N=NX*NZ, ACC=[__ACC_R__,__ACC_G__,__ACC_B__];
  function resize(){ W=cv.clientWidth; H=cv.clientHeight; cv.width=W*DPR; cv.height=H*DPR; }
  window.addEventListener('resize', resize); resize();
  function onMove(e, el){ var r=cv.getBoundingClientRect(); var x=(e.clientX-r.left)/Math.max(1,r.width), y=(e.clientY-r.top)/Math.max(1,r.height);
    target.x=Math.max(-1,Math.min(1,x*2-1)); target.y=Math.max(-1,Math.min(1,y*2-1)); }
  window.addEventListener('mousemove', function(e){ onMove(e); });
  window.addEventListener('mouseleave', function(){ target.x=0; target.y=0; });
  var pd=null; try{ pd=window.parent.document; }catch(err){ pd=null; }
  if(pd){ pd.addEventListener('mousemove', function(e){ var r=window.frameElement?window.frameElement.getBoundingClientRect():{left:0,top:0,width:pd.body.clientWidth,height:400};
      var x=(e.clientX-r.left)/Math.max(1,r.width), y=(e.clientY-r.top)/Math.max(1,r.height*2.5);
      target.x=Math.max(-1,Math.min(1,x*2-1)); target.y=Math.max(-1,Math.min(1,y*2-1)); }, {passive:true}); }
  document.addEventListener('visibilitychange', function(){ hidden=document.hidden; if(!hidden) raf(); });

  // ---- WebGL path ------------------------------------------------
  var gl=cv.getContext('webgl',{alpha:true,antialias:false,premultipliedAlpha:true}) || cv.getContext('experimental-webgl');
  var useGL=!!gl;
  var prog, aPos, uT, uM, uAsp, uDpr, buf;
  if(useGL){
    var vs='attribute vec2 a;uniform float t;uniform vec2 m;uniform float asp;uniform float dpr;varying float d;'+
      'void main(){float x=a.x,z=a.y;float y=sin(x*1.5+t)*0.22+sin(z*1.2-t*0.8)*0.18+sin((x+z)*0.7+t*0.45)*0.14+cos(x*0.6-z*0.9+t*0.3)*0.1;'+
      'float yaw=m.x*0.22;float cy=cos(yaw),sy=sin(yaw);vec3 p=vec3(x*cy-z*sy,y,x*sy+z*cy);'+
      'float pitch=-1.02+m.y*0.08;float cp=cos(pitch),sp=sin(pitch);p=vec3(p.x,p.y*cp-p.z*sp,p.y*sp+p.z*cp);'+
      'p.z-=3.6;p.y+=0.25;float w=-p.z;d=clamp(1.0-(w-1.8)/4.5,0.0,1.0);'+
      'gl_Position=vec4(p.x*1.15,p.y*1.5,p.z*0.2,w);gl_PointSize=(1.8+3.0*d)*dpr;}';
    var fs='precision mediump float;varying float d;uniform vec3 c;'+
      'void main(){float r=length(gl_PointCoord-0.5);float a=smoothstep(0.5,0.1,r)*mix(0.10,0.85,d);'+
      'gl_FragColor=vec4(mix(c,vec3(1.0),0.25*d)*a,a);}';
    function sh(type,src){var s=gl.createShader(type);gl.shaderSource(s,src);gl.compileShader(s);
      if(!gl.getShaderParameter(s,gl.COMPILE_STATUS)){console.warn(gl.getShaderInfoLog(s));return null;}return s;}
    var v=sh(gl.VERTEX_SHADER,vs), f=sh(gl.FRAGMENT_SHADER,fs);
    if(v&&f){ prog=gl.createProgram();gl.attachShader(prog,v);gl.attachShader(prog,f);gl.linkProgram(prog);gl.useProgram(prog);
      var pts=new Float32Array(N*2), k=0;
      for(var i=0;i<NX;i++)for(var j=0;j<NZ;j++){pts[k++]=(i/(NX-1)-0.5)*7.0;pts[k++]=(j/(NZ-1)-0.5)*3.6;}
      buf=gl.createBuffer();gl.bindBuffer(gl.ARRAY_BUFFER,buf);gl.bufferData(gl.ARRAY_BUFFER,pts,gl.STATIC_DRAW);
      aPos=gl.getAttribLocation(prog,'a');gl.enableVertexAttribArray(aPos);gl.vertexAttribPointer(aPos,2,gl.FLOAT,false,0,0);
      uT=gl.getUniformLocation(prog,'t');uM=gl.getUniformLocation(prog,'m');uAsp=gl.getUniformLocation(prog,'asp');uDpr=gl.getUniformLocation(prog,'dpr');
      gl.uniform3f(gl.getUniformLocation(prog,'c'),ACC[0]/255,ACC[1]/255,ACC[2]/255);
      gl.enable(gl.BLEND);gl.blendFunc(gl.ONE,gl.ONE_MINUS_SRC_ALPHA);gl.clearColor(0,0,0,0);
    } else useGL=false;
  }
  // ---- Canvas2D fallback --------------------------------------------
  var ctx2=null, pts2=null;
  if(!useGL){ ctx2=cv.getContext('2d'); pts2=[]; for(var i=0;i<60;i++)for(var j=0;j<34;j++)pts2.push([(i/59-0.5)*7,(j/33-0.5)*3.6]); }

  function frame(now){
    var t=(now-t0)/1000; mouse.x+=(target.x-mouse.x)*0.06; mouse.y+=(target.y-mouse.y)*0.06;
    if(useGL){ gl.viewport(0,0,cv.width,cv.height); gl.clear(gl.COLOR_BUFFER_BIT);
      gl.uniform1f(uT,t*0.9); gl.uniform2f(uM,mouse.x,mouse.y); gl.uniform1f(uAsp,W/Math.max(1,H)); gl.uniform1f(uDpr,DPR);
      gl.drawArrays(gl.POINTS,0,N);
    } else if(ctx2){ ctx2.setTransform(DPR,0,0,DPR,0,0); ctx2.clearRect(0,0,W,H);
      var yaw=mouse.x*0.22,cy=Math.cos(yaw),sy=Math.sin(yaw),pitch=-1.02+mouse.y*0.08,cp=Math.cos(pitch),sp=Math.sin(pitch);
      for(var q=0;q<pts2.length;q++){var x=pts2[q][0],z=pts2[q][1];
        var y=Math.sin(x*1.5+t)*0.22+Math.sin(z*1.2-t*0.8)*0.18+Math.sin((x+z)*0.7+t*0.45)*0.14;
        var px=x*cy-z*sy,pz=x*sy+z*cy,py=y; var py2=py*cp-pz*sp,pz2=py*sp+pz*cp; pz2-=3.6;py2+=0.25; var w=-pz2;
        var d=Math.max(0,Math.min(1,1-(w-1.8)/4.5)); var sx=(px*1.15/w*0.5+0.5)*W, syy=(0.5-py2*1.5/w*0.5)*H;
        ctx2.fillStyle='rgba('+ACC[0]+','+ACC[1]+','+ACC[2]+','+(0.1+0.7*d)+')'; ctx2.beginPath(); ctx2.arc(sx,syy,0.6+1.3*d,0,6.283); ctx2.fill(); }
    }
    if(!hidden) requestAnimationFrame(frame);
  }
  function raf(){ requestAnimationFrame(frame); }
  raf();

  // ---- parent-DOM enhancements (scroll reveal + magnetic buttons) ----
  if(pd){
    try{
      var io=new IntersectionObserver(function(es){es.forEach(function(e){ if(e.isIntersecting){ e.target.classList.add('in-view'); io.unobserve(e.target);} });},{threshold:0.06});
      var SEL='[data-testid="stVerticalBlockBorderWrapper"]:not(.sse-obs), [data-testid="stDataFrame"]:not(.sse-obs), [data-testid="stPlotlyChart"]:not(.sse-obs), [data-testid="stExpander"]:not(.sse-obs)';
      function magnet(b){ if(b.__mag) return; b.__mag=true;
        b.addEventListener('mousemove',function(e){var r=b.getBoundingClientRect();var dx=(e.clientX-(r.left+r.width/2))/r.width, dy=(e.clientY-(r.top+r.height/2))/r.height;
          b.style.setProperty('--mx',(dx*8).toFixed(1)+'px'); b.style.setProperty('--my',(dy*6).toFixed(1)+'px');});
        b.addEventListener('mouseleave',function(){ b.style.setProperty('--mx','0px'); b.style.setProperty('--my','0px'); }); }
      function scan(){ pd.querySelectorAll(SEL).forEach(function(el){ el.classList.add('sse-obs'); io.observe(el); });
        pd.querySelectorAll('.stButton > button, .stDownloadButton > button').forEach(magnet); }
      scan(); new MutationObserver(function(){ clearTimeout(window.__sseT); window.__sseT=setTimeout(scan,80); }).observe(pd.body,{childList:true,subtree:true});
      window.__sseParent=true;
    }catch(err){ console.warn('parent DOM enhancements unavailable', err); }
  }
})();
</script></body></html>
"""


def hero_canvas(height: int = 240) -> None:
    """Render the WebGL particle-wave header with the app title overlaid."""
    r, g, b = (int(ACCENT[i:i + 2], 16) for i in (1, 3, 5))
    html = (_HERO_HTML.replace("__BG__", BG).replace("__H__", str(height)).replace("__SERIF__", SERIF)
            .replace("__SANS__", SANS).replace("__TEXT__", TEXT).replace("__MUTED__", MUTED)
            .replace("__ACCENT__", ACCENT).replace("__ACC_R__", str(r)).replace("__ACC_G__", str(g)).replace("__ACC_B__", str(b)))
    components.html(html, height=height, scrolling=False)
