import pytest

from eye.tui.app import main


def test_main_runs_without_error(capsys: pytest.CaptureFixture[str]) -> None:
    main()

    assert capsys.readouterr().out
