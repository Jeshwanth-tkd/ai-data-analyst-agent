"""
Phase 27: tests for app/ui/chart_carousel.py's pure HTML builder.

render_chart_carousel() itself calls streamlit.components.v1.html(),
which needs a live Streamlit script context and can't run under plain
pytest -- so these tests exercise _build_carousel_html(), the pure
string-building function it wraps, directly. (Visual behavior --
navigation, click-to-zoom, keyboard/escape dismissal -- was verified
separately with a headless-browser screenshot pass before shipping; see
the README's Phase 27 entry.)
"""

import os

from app.ui.chart_carousel import _build_carousel_html, _names_json


def _make_png(tmp_path, name="chart.png"):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    path = str(tmp_path / name)
    fig, ax = plt.subplots()
    ax.plot([1, 2, 3], [1, 4, 9])
    fig.savefig(path)
    plt.close(fig)
    return path


def test_returns_empty_string_for_no_charts():
    assert _build_carousel_html([]) == ""


def test_returns_empty_string_when_no_files_exist():
    assert _build_carousel_html(["/tmp/does_not_exist_abc123.png"]) == ""


def test_embeds_chart_as_base64_data_uri_not_file_path(tmp_path):
    path = _make_png(tmp_path)
    html_str = _build_carousel_html([path])
    assert "data:image/png;base64," in html_str
    assert path not in html_str  # the raw file path must never leak into the component


def test_single_chart_hides_navigation_controls(tmp_path):
    path = _make_png(tmp_path)
    html_str = _build_carousel_html([path])
    assert "carousel-nav prev" not in html_str
    assert "carousel-nav next" not in html_str
    assert "to browse" not in html_str  # keyboard hint only shown with >1 slide


def test_multiple_charts_show_navigation_and_dots(tmp_path):
    paths = [_make_png(tmp_path, f"chart_{i}.png") for i in range(3)]
    html_str = _build_carousel_html(paths)
    assert "carousel-nav prev" in html_str
    assert "carousel-nav next" in html_str
    assert html_str.count("carousel-dot") >= 3
    assert "lightbox-prev" in html_str
    assert "lightbox-next" in html_str


def test_skips_nonexistent_files_but_keeps_valid_ones(tmp_path):
    valid_path = _make_png(tmp_path)
    html_str = _build_carousel_html([valid_path, "/tmp/nope_xyz.png"])
    assert "data:image/png;base64," in html_str
    assert html_str.count('class="carousel-slide"') == 1


def test_filenames_are_html_escaped_in_the_caption_and_alt_attribute(tmp_path):
    path = _make_png(tmp_path, "weird<name>&.png")
    html_str = _build_carousel_html([path])
    # The HTML-context uses (alt attribute, initial caption span) must be
    # escaped -- the JS-context use (inside <script>, a JSON string
    # literal) legitimately contains the raw "<" since that's a
    # different parsing context (see the "</script>" test below for the
    # one JS-context character sequence that DOES need escaping).
    assert 'alt="weird&lt;name&gt;&amp;.png"' in html_str
    assert '>weird&lt;name&gt;&amp;.png<' in html_str


def test_names_json_escapes_script_tag_breakout_sequence():
    # A real filename can never contain "/" on a POSIX filesystem, so
    # this can't be triggered end-to-end via _build_carousel_html() with
    # a real file -- but _names_json() itself must still be safe against
    # it, since it's the function actually responsible for embedding
    # names inside a <script> block.
    malicious_name = "weird</script><script>alert(1)</script>.png"
    result = _names_json([malicious_name])
    assert "</script><script>alert(1)" not in result
    assert "<\\/script>" in result
