from help import help

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
    # Game setup and initialization
    print("Welcome to the game!")

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