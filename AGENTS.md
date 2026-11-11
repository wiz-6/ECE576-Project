# Repository guidance

Keep game/README.md student-facing. Include setup, launch instructions, basic controls,
and a broad description of the three stages. Keep test commands, implementation
details, and strategies for solving the lab out of the README. Detailed command
syntax and conceptual guidance belong in the game's stage-specific help.

## Code map

All runtime files and the student README live in `game/`. Distribute that
folder to students. Keep contributor guidance, the proposal, and tests at
the repository root. The paths below are relative to `game/`.

- `main.py` launches the Pygame application.
- `session.py` owns game state, command dispatch, progression, and result exports.
- `help.py` defines public command names, aliases, stage permissions, and student-facing goals.
- `terminal.py` handles input, completion, rendering, and background capture jobs.
- `chip.py` models the simulated chips. `analysis.py` processes their measurements.

Keep dispatch, help, and completion aligned when changing commands. The public
stages are numbered 1–3. Profiling requires a completed t-test for the correctly
identified chip and a valid leak sample. That sample carries forward. A valid
profile remains editable until `submit-profile` succeeds. Key recovery requires
explicit target plaintext selection. Preserve completed results when a capture
is cancelled, and keep the hidden key and chip classifications out of exports.

## Verification

Use the project virtual environment with the dependencies in `game/requirements.txt`. Run from the repository root.

```bash
PYTHONPATH=game .venv/bin/python -m unittest discover -s tests -v
```

The suite covers statistics, candidate scoring, a seeded playthrough, stage
permissions, input validation, exports, cancellation, and headless Pygame
rendering. For visual changes, exercise the affected screen at the default size
and after resizing.
