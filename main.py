import random

from help import help
from chip import LeakyChip, init_chip
from analysis import collect_ttest

secret_key = None
chips = []


def exit_game():
    print("Exiting the game...")
    return False


def process_command(command):
    if not command:
        return
    match command[0]:
        case "exit":
            return exit_game()
        case "help":
            help(command)
        case "guess":
            try:
                if len(command) != 2:
                    raise ValueError
                chip_number = int(command[1])
                if not 1 <= chip_number <= 4:
                    raise ValueError
            except ValueError:
                print("Usage: guess <chip 1-4>")
                return
            if not chips:
                print("Initialize the game before making a guess.")
                return
            if isinstance(chips[chip_number - 1], LeakyChip):
                print(f"You win! Chip {chip_number} is the leaky chip. Congratulations!")
            else:
                print(f"Chip {chip_number} is not the leaky chip. Try again!")
        case _:
            print("Unknown command. Type 'help' for a list of commands.")


def initialize_game(username):
    global secret_key, chips
    random.seed(username)
    secret_key = random.getrandbits(128)
    classifications = ["fixed", "noise", "random", "leaky"]
    random.shuffle(classifications)
    chips = [init_chip(classification) for classification in classifications]


def main():
    from terminal import Terminal

    initialized = False

    def submit(value):
        nonlocal initialized
        if not initialized:
            username = value.strip()
            if not username:
                print("Please enter your WPI username.")
                return
            initialize_game(username)
            terminal.set_traces([chip.get_trace(0, secret_key) for chip in chips], 0)
            initialized = True
            terminal.prompt = "> "
            terminal.history.clear()
            terminal.history_index = 0
            print(f"Welcome, {username}! Type 'help' for a list of commands.")
            return
        command = value.split()
        if command and command[0] == "ttest":
            try:
                if not 2 <= len(command) <= 4:
                    raise ValueError
                chip_number = int(command[1])
                count = int(command[2]) if len(command) >= 3 else 1000
                plaintext = int(command[3]) if len(command) == 4 else 0
                if not (1 <= chip_number <= 4 and 2 <= count <= 50000 and 0 <= plaintext <= 255):
                    raise ValueError
            except ValueError:
                print("Usage: ttest <chip 1-4> [traces per group 2-50000] [fixed plaintext 0-255]")
                return
            selected_chip = chips[chip_number - 1]
            terminal.start_ttest(lambda: collect_ttest(selected_chip, secret_key, count, plaintext),
                                 chip_number, count, plaintext)
            return
        if command and command[0] == "trace":
            if terminal.analysis_future is not None:
                print("Please wait for the t-test to finish before capturing more traces.")
                return
            try:
                if len(command) > 2:
                    raise ValueError
                plaintext = int(command[1]) if len(command) == 2 else 0
                if not 0 <= plaintext <= 255:
                    raise ValueError
            except ValueError:
                print("Usage: trace [plaintext byte from 0 to 255]")
                return
            terminal.set_traces([chip.get_trace(plaintext, secret_key) for chip in chips], plaintext)
            print(f"Captured all four chips with plaintext {plaintext}.")
            return
        return process_command(command)

    terminal = Terminal(submit)
    terminal.write("Welcome to the game!")
    terminal.write("Please type your WPI username:")
    terminal.run()


if __name__ == "__main__":
    main()
