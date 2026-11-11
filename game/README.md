# ECE 576 Leakage Assesment, Profiling, and Key Recovery.

Explore how simulated power measurements can reveal information about a chip's computations.

## Run the game

From the project folder, create a Python virtual environment.

```bash
python -m venv .venv
```

Activate it with `source .venv/bin/activate` on macOS or Linux, or
`.venv\Scripts\activate.bat` in Windows Command Prompt. Then install the
dependencies and start the game.

```bash
python -m pip install -r requirements.txt
python main.py
```

Enter your WPI username when prompted.

## Play

1. **Leak assessment.** Investigate the four chips and decide where the evidence points.
2. **Profiling.** Use the controlled copy to build a model from your measurements.
3. **Key recovery.** Evaluate your model against new observations and submit a key-byte guess.

Use `show-stage-goal` to review the current objective, `help` to see available
commands, and `help <command>` for syntax. Use the plots, your own experiments,
and outside research to decide what the results mean.

Press Tab to complete a command, Enter to submit it, and Up or Down to recall
previous commands. Scroll through output with the mouse wheel or Page Up and
Page Down. Use `export-results` to save your evidence and `exit` to quit.
