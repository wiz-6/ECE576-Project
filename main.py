import random

from help import help
from chip import Chip, init_chip

# Globals
secret_key = None
chips = []

def exit_game():
    print("Exiting the game...")
    exit()

def process_command(command):
    command_name = command[0]
    match command_name:
        case "exit":
            exit_game() 
        case "help":
            help(command)
        case _:
            print("Unknown command. Type 'help' for a list of commands.")

def main():
    global secret_key, chips

    # Game setup and initialization
    print("Welcome to the game!") #TODO: Add an actual game introduction
    rng_seed = input("Please type your WPI username: ") 
    random.seed(rng_seed)  # Seed the random number generator for reproducibility

    # Init key
    secret_key = random.getrandbits(128)  # Generate a random 128-bit key

    # Init chips
    chip_classifications = random.shuffle(["fixed", "noise", "random", "leaky"])
    for c in chip_classifications:
        chips.append(init_chip(c))

    # Game (terminal) loop
    while True:
        # Prompt user for input
        command = input("> ").split(" ")

        # Run command
        process_command(command)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nKeyboard interrupt received (ctl+C).")
        exit_game()
    except Exception as e:
        print(f"An error occurred: {e}")