"""Entrypoint for the coworking bot (systemd runs: python -m coworkingbot.working_bot_fixed)."""

from coworkingbot.working_bot_app import run


def main() -> None:
    run()


if __name__ == "__main__":
    main()
