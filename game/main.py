"""Launch the three-stage chip leakage workshop."""
from session import Game
from terminal import Terminal


def main():
    # The callback is evaluated only after the window and game are initialized.
    terminal = Terminal(lambda value: game.submit(value))
    game = Game(terminal)
    terminal.write("CHIP LAB / Side-channel workshop")
    terminal.write("Type help for available commands.")
    terminal.write("Please type your WPI username:")
    terminal.run()


if __name__ == "__main__":
    main()
