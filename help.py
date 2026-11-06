'''
    Commands for helping users.
'''

help_texts = {
    "guess": "Guess which chip is leaky. Usage: guess <chip 1-4>",
    "ttest": "Fixed-vs-random Welch t-test. Usage: ttest <chip 1-4> [traces per group 2-50000, default 1000] [fixed plaintext 0-255, default 0]. Displays t-values and +/-4.5 thresholds.",
    "trace": "Capture all four chip traces. Usage: trace [plaintext byte from 0 to 255]",
    "help": "Show help for a command. Usage: help [command]",
    "exit": "Exit the game. Usage: exit"
}

def print_help_commands():
    for command in help_texts:
        print(f"- {command}")


def help(command):
    if len(command) == 1:
        print("Help command usage: help [command]")
        print("Available commands:")
        print_help_commands()
        
    else:
        command_name = command[1]
        if command_name in help_texts:
            print(help_texts[command_name])
        else:
            print(f"No help available for '{command_name}'.")
            print("Available commands:")
            print_help_commands()

if __name__ == "__main__":
    print_help_commands()
