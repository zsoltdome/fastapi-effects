from fastapi_mergen.cli.main import main


def test_cli_help_is_successful(capsys: object) -> None:
    assert main([]) == 0


def test_reserved_command_fails_safely(capsys: object) -> None:
    assert main(["doctor"]) == 2
