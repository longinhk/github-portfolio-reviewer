"""Small rendering smoke test for the Streamlit entry point."""

from pathlib import Path

from streamlit.testing.v1 import AppTest


def test_initial_page_renders_without_exceptions() -> None:
    entry_point = Path(__file__).parents[1] / "streamlit_app.py"

    app = AppTest.from_file(str(entry_point)).run(timeout=10)

    assert not app.exception
    assert app.title[0].value == "GitHub Portfolio Reviewer"
    assert any(button.label == "Analyze repository" for button in app.button)
