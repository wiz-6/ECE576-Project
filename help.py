'''
    Commands for helping users.
'''

help_texts = {
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