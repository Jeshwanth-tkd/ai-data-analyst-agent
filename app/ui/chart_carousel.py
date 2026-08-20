"""
Phase 27: UI polish -- a reusable chart carousel + click-to-zoom lightbox.

Before this phase, every chart section (LLM-generated charts, Automatic
EDA, Forecast, chat replies) rendered as a plain vertical stack of
st.image() calls -- functional, but a long scroll for a dataset with
several charts, and no way to see a chart larger than its inline size.

render_chart_carousel() replaces that with one embedded HTML/CSS/JS
component (via streamlit.components.v1.html) per chart group: left/right
arrow navigation, dot indicators, a slide counter, keyboard arrow-key
support, and click-to-zoom into a full-size lightbox overlay (also
keyboard/click-outside dismissible). Every image is embedded as a
base64 data: URI directly in the component's HTML -- no separate image
server or extra file-serving route needed, consistent with how
app/report/report_generator.py already embeds charts into the HTML
report.

Deliberately a hand-written vanilla-JS component, not a pip-installed
Streamlit carousel/lightbox package: this project's own rule is free
tools only, and a ~100-line self-contained component has no external
dependency, no version-compatibility risk with whatever Streamlit
version Community Cloud runs, and is small enough to fully understand
and maintain (an actual advantage for a portfolio project meant to be
explained in an interview) versus pulling in a third-party widget.

st.components.v1.html() renders each call in its OWN <iframe> -- so
multiple carousels on the same page (Charts, Automatic EDA, Forecast)
never collide with each other's element IDs or JS state, with zero
extra namespacing work needed here.
"""

import base64
import html
import json
import os

import streamlit.components.v1 as components

_STYLE = """
<style>
  * { box-sizing: border-box; }
  body { margin: 0; font-family: 'Inter', -apple-system, "Segoe UI", Roboto, sans-serif; }
  .carousel { position: relative; width: 100%; }
  .carousel-viewport {
    position: relative; width: 100%; overflow: hidden; border-radius: 10px;
    border: 1px solid #e3e6ea; background: #fafbfc;
  }
  .carousel-track { display: flex; transition: transform 0.35s ease; }
  .carousel-slide {
    flex: 0 0 100%; display: flex; align-items: center; justify-content: center;
    padding: 14px; cursor: zoom-in;
  }
  .carousel-slide img { max-width: 100%; max-height: 360px; border-radius: 6px; }
  .carousel-nav {
    position: absolute; top: 50%; transform: translateY(-50%);
    background: rgba(255,255,255,0.92); border: 1px solid #d7dbe0; border-radius: 50%;
    width: 36px; height: 36px; display: flex; align-items: center; justify-content: center;
    cursor: pointer; font-size: 18px; color: #2c3e50; user-select: none;
    box-shadow: 0 1px 4px rgba(0,0,0,0.12); transition: background 0.15s ease;
  }
  .carousel-nav:hover { background: #ffffff; }
  .carousel-nav.prev { left: 10px; }
  .carousel-nav.next { right: 10px; }
  .carousel-footer {
    display: flex; align-items: center; justify-content: space-between;
    margin-top: 8px; font-size: 0.85rem; color: #5f6b7a;
  }
  .carousel-caption { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .carousel-dots { display: flex; gap: 6px; }
  .carousel-dot {
    width: 7px; height: 7px; border-radius: 50%; background: #cfd5db; cursor: pointer;
    transition: background 0.15s ease, transform 0.15s ease;
  }
  .carousel-dot.active { background: #4C8BF5; transform: scale(1.3); }
  .carousel-hint { color: #97a2ad; }
  .lightbox {
    display: none; position: fixed; inset: 0; background: rgba(15, 18, 22, 0.88);
    z-index: 9999; align-items: center; justify-content: center; cursor: zoom-out;
  }
  .lightbox.open { display: flex; }
  .lightbox img {
    max-width: 92vw; max-height: 88vh; border-radius: 8px; box-shadow: 0 8px 40px rgba(0,0,0,0.5);
  }
  .lightbox-close {
    position: absolute; top: 18px; right: 26px; color: #fff; font-size: 30px;
    cursor: pointer; line-height: 1; user-select: none;
  }
  .lightbox-nav {
    position: absolute; top: 50%; transform: translateY(-50%); color: #fff;
    font-size: 32px; cursor: pointer; user-select: none; padding: 8px 16px;
  }
  .lightbox-nav.prev { left: 8px; }
  .lightbox-nav.next { right: 8px; }
</style>
"""


def _names_json(names: list) -> str:
    """
    Encodes a list of filenames as a JS array literal for embedding
    inside this component's <script> block. json.dumps() (not Python's
    repr()) is what guarantees valid JS array/string syntax regardless
    of what characters are in a filename (quotes, backslashes, unicode)
    -- repr()'s escaping rules are close to JS's but not a guarantee.
    json.dumps() alone doesn't escape "</", though -- a filename
    containing the literal sequence "</script>" would prematurely close
    the embedded <script> tag and break out into HTML context (this
    can't happen via a real filename on a POSIX filesystem, where "/"
    can't appear in a filename at all, but it's a cheap, correct guard
    either way rather than relying on that filesystem constraint).
    Escaping "</" to "<\\/" is the standard safe fix -- the backslash is
    a no-op inside a JS string literal.
    """
    return json.dumps(names).replace("</", "<\\/")


def _build_carousel_html(chart_paths: list) -> str:
    """
    Pure HTML-string builder, kept separate from render_chart_carousel()
    so it can be unit-tested (and visually spot-checked in a plain
    browser) without needing a running Streamlit script context, which
    components.html() requires. Returns "" if no valid chart files.
    """
    valid_paths = [p for p in chart_paths if os.path.exists(p)]
    if not valid_paths:
        return ""

    slides_html = []
    dots_html = []
    for i, path in enumerate(valid_paths):
        with open(path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode("ascii")
        name = html.escape(os.path.basename(path))
        slides_html.append(
            f'<div class="carousel-slide"><img src="data:image/png;base64,{b64}" '
            f'alt="{name}" data-full="data:image/png;base64,{b64}"></div>'
        )
        active = " active" if i == 0 else ""
        dots_html.append(f'<div class="carousel-dot{active}" data-index="{i}"></div>')

    show_nav = len(valid_paths) > 1
    nav_html = ""
    if show_nav:
        nav_html = (
            '<div class="carousel-nav prev">&#8249;</div>'
            '<div class="carousel-nav next">&#8250;</div>'
        )

    first_name = html.escape(os.path.basename(valid_paths[0]))
    names_json = _names_json([os.path.basename(p) for p in valid_paths])

    component_html = f"""
{_STYLE}
<div class="carousel">
  <div class="carousel-viewport">
    <div class="carousel-track">{"".join(slides_html)}</div>
    {nav_html}
  </div>
  <div class="carousel-footer">
    <span class="carousel-caption" id="caption">{first_name}</span>
    <div class="carousel-dots">{"".join(dots_html) if show_nav else ""}</div>
    <span class="carousel-hint">{"&#8592; &#8594; to browse &middot; " if show_nav else ""}click to zoom</span>
  </div>
</div>
<div class="lightbox" id="lightbox">
  <span class="lightbox-close" id="lightbox-close">&times;</span>
  {'<span class="lightbox-nav prev" id="lightbox-prev">&#8249;</span>' if show_nav else ''}
  <img id="lightbox-img" src="">
  {'<span class="lightbox-nav next" id="lightbox-next">&#8250;</span>' if show_nav else ''}
</div>
<script>
  (function() {{
    const track = document.querySelector('.carousel-track');
    const slides = document.querySelectorAll('.carousel-slide');
    const dots = document.querySelectorAll('.carousel-dot');
    const caption = document.getElementById('caption');
    const lightbox = document.getElementById('lightbox');
    const lightboxImg = document.getElementById('lightbox-img');
    const names = {names_json};
    let index = 0;

    function goTo(i) {{
      index = (i + slides.length) % slides.length;
      track.style.transform = 'translateX(-' + (index * 100) + '%)';
      dots.forEach((d, di) => d.classList.toggle('active', di === index));
      caption.textContent = names[index];
    }}

    document.querySelectorAll('.carousel-nav.prev').forEach(el => el.addEventListener('click', () => goTo(index - 1)));
    document.querySelectorAll('.carousel-nav.next').forEach(el => el.addEventListener('click', () => goTo(index + 1)));
    dots.forEach(d => d.addEventListener('click', () => goTo(parseInt(d.dataset.index))));

    slides.forEach((s, i) => s.addEventListener('click', () => {{
      goTo(i);
      lightboxImg.src = s.querySelector('img').dataset.full;
      lightbox.classList.add('open');
    }}));

    function closeLightbox() {{ lightbox.classList.remove('open'); }}
    document.getElementById('lightbox-close').addEventListener('click', closeLightbox);
    lightbox.addEventListener('click', (e) => {{ if (e.target === lightbox) closeLightbox(); }});

    const lbPrev = document.getElementById('lightbox-prev');
    const lbNext = document.getElementById('lightbox-next');
    if (lbPrev) lbPrev.addEventListener('click', (e) => {{
      e.stopPropagation(); goTo(index - 1); lightboxImg.src = slides[index].querySelector('img').dataset.full;
    }});
    if (lbNext) lbNext.addEventListener('click', (e) => {{
      e.stopPropagation(); goTo(index + 1); lightboxImg.src = slides[index].querySelector('img').dataset.full;
    }});

    document.addEventListener('keydown', (e) => {{
      if (lightbox.classList.contains('open')) {{
        if (e.key === 'Escape') closeLightbox();
        if (e.key === 'ArrowLeft') {{ goTo(index - 1); lightboxImg.src = slides[index].querySelector('img').dataset.full; }}
        if (e.key === 'ArrowRight') {{ goTo(index + 1); lightboxImg.src = slides[index].querySelector('img').dataset.full; }}
      }} else {{
        if (e.key === 'ArrowLeft') goTo(index - 1);
        if (e.key === 'ArrowRight') goTo(index + 1);
      }}
    }});
  }})();
</script>
"""
    return component_html


def render_chart_carousel(chart_paths: list, height: int = 460) -> None:
    """
    Renders one carousel component for a list of chart image file paths.
    Silently renders nothing if chart_paths is empty or none of the
    files actually exist on disk (mirrors how the rest of the UI treats
    "nothing to show" -- no error, section just doesn't appear).
    """
    component_html = _build_carousel_html(chart_paths)
    if not component_html:
        return
    components.html(component_html, height=height, scrolling=False)
