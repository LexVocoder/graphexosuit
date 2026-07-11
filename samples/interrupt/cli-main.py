from graphexosuit.layer.cli import CliApp
from liner import build_graph, get_checkpointer_cm


if __name__ == "__main__":
    cli = CliApp(graph=build_graph(), checkpointer_cm=get_checkpointer_cm())
    try:
        cli()
    except Exception as exc:
        cli.confess(exc)
