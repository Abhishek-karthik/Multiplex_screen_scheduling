"""App smoke tests (Streamlit AppTest): every page renders, every model solves, nothing raises.

Run from the project root:  python -m pytest -q tests/test_app.py
"""
from pathlib import Path

import pytest

pytest.importorskip('streamlit')
from streamlit.testing.v1 import AppTest  # noqa: E402

APP = str(Path(__file__).resolve().parent.parent / 'app' / 'streamlit_app.py')
PAGES = ['views/overview.py', 'views/data.py', 'views/market_demand.py', 'views/studio_m1.py', 'views/studio_m2.py',
         'views/studio_m3.py', 'views/studio_m4.py', 'views/whatif.py', 'views/compare.py', 'views/sensitivity.py',
         'views/final_plan.py', 'views/under_the_hood.py']


def _app():
    at = AppTest.from_file(APP, default_timeout=180)
    at.run()
    assert not at.exception, at.exception
    return at


def test_every_page_renders_before_solving():
    at = _app()
    for page in PAGES:
        at.switch_page(page).run()
        assert not at.exception, (page, at.exception)


@pytest.mark.parametrize('stage, page', [('m1', 'views/studio_m1.py'), ('m2', 'views/studio_m2.py'),
                                         ('m3', 'views/studio_m3.py'), ('m4', 'views/studio_m4.py')])
def test_each_model_solves_from_its_page(stage, page):
    at = _app()
    at.switch_page(page).run()
    at.button(key=f'solve_{stage}').click().run()
    assert not at.exception, at.exception
    assert any(m.label == 'Solver status' and m.value == 'Optimal' for m in at.metric)


def test_full_chain_then_results_pages():
    at = _app()
    next(b for b in at.sidebar.button if 'Run full chain' in b.label).click().run()
    assert not at.exception, at.exception
    for page in ['views/compare.py', 'views/final_plan.py', 'views/under_the_hood.py', 'views/studio_m4.py']:
        at.switch_page(page).run()
        assert not at.exception, (page, at.exception)
    at.switch_page('views/final_plan.py').run()
    revenue = next(m.value for m in at.metric if m.label == 'Daily ticket revenue')
    assert revenue == '₹416,230'                                    # the report's final plan


def test_infeasible_budget_is_reported_not_raised():
    at = _app()
    at.switch_page('views/studio_m1.py').run()
    at.number_input(key='w_budget').set_value(300_000).run()
    at.button(key='solve_m1').click().run()
    assert not at.exception, at.exception
    assert any('could not be solved' in e.value for e in at.error)


def test_stats_builder_generates_on_demand():
    at = _app()
    at.switch_page('views/data.py').run()
    for analysis in ['Summary statistics', 'Category counts', 'Correlation matrix', 'Group-by aggregate']:
        at.selectbox(key='w_analysis').set_value(analysis).run()
        next(b for b in at.button if b.label == 'Generate').click().run()
        assert not at.exception, (analysis, at.exception)
        assert any(analysis in s.value for s in at.success)
