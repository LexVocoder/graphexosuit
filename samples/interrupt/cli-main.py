from graphexosuit.layer.cli import CliApp
from liner import InterruptLiner


if __name__ == "__main__":
    cli = CliApp(InterruptLiner())
    try:
        cli()
    except Exception as exc:
        cli.confess(exc)
