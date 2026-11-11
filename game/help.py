"""Player-facing command reference."""
COMMAND_NAMES = {
    "status": "show-game-status", "goal": "show-stage-goal", "trace": "capture-power-traces",
    "threshold": "set-t-threshold", "fixed-trials": "set-num-fixed-traces",
    "random-trials": "set-num-random-traces", "ttest": "run-ttest", "guess": "submit-chip-guess",
    "profile-key": "set-profile-key", "profile-inputs": "set-profile-plaintexts",
    "profile-trials": "set-profile-trials", "profile": "build-profile",
    "attack-inputs": "set-attack-plaintexts", "inspect-trace": "inspect-target-trace",
    "compare-key": "compare-key-candidate", "attack": "run-attack", "keyguess": "submit-key-guess",
    "view": "show-chart", "cancel": "cancel-capture", "report": "export-results", "restart": "restart-game",
}
COMMAND_ALIASES = {
    "set-fixed-trials": "fixed-trials", "set-random-trials": "random-trials",
    "game-status": "status", "capture-traces": "trace", "t-threshold": "threshold",
    "guess-chip": "guess", "guess-key": "keyguess", "view-chart": "view", "export-report": "report",
}

SETTINGS = {
    "t-threshold": "threshold",
    "num-fixed-traces": "fixed-trials",
    "num-random-traces": "random-trials",
    "profile-key": "profile-key",
    "profile-plaintexts": "profile-inputs",
    "profile-trials": "profile-trials",
    "attack-plaintexts": "attack-inputs",
}
for setting, internal in SETTINGS.items():
    COMMAND_ALIASES[COMMAND_NAMES[internal]] = internal
    COMMAND_NAMES[internal] = f"set {setting}"


def setting_names(available):
    return [name for name, internal in SETTINGS.items() if internal in available]


def command_choices(available):
    names = [COMMAND_NAMES.get(name, name) for name in available if name not in SETTINGS.values()]
    if setting_names(available):
        names.append("set")
    return names


def resolve_command(name):
    return {public: internal for internal, public in COMMAND_NAMES.items()}.get(name, COMMAND_ALIASES.get(name, name))


def command_name(name):
    internal = resolve_command(name)
    return COMMAND_NAMES.get(internal, internal)


def update_command_references(text):
    import re
    names = {**COMMAND_ALIASES, **{name: name for name in COMMAND_NAMES if "-" in name}}
    pattern = r"(?<!set )(?<![\w-])(?:" + "|".join(map(re.escape, sorted(names, key=len, reverse=True))) + r")(?![\w-])"
    return re.sub(pattern, lambda match: command_name(match.group()), text)


def public_text(text):
    """Expand command references in help and usage messages."""
    import re
    pattern = r"(?<![\w-])(?:" + "|".join(COMMAND_NAMES) + r")(?![\w-])"
    # Used only for command usage, not general prose describing a profile or trace.
    return update_command_references(re.sub(pattern, lambda match: COMMAND_NAMES[match.group()], text, count=1))


help_texts = {
    "goal": "Show the current stage objective and completion criteria. Usage: show-stage-goal",
    "status": "Show the current stage and recorded results. Usage: status",
    "trace": (
        "Capture one simulated power trace from each chip. Usage: trace [plaintext byte, default 0]. "
        "Each curve is 200 consecutive power samples during one modeled AES S-box operation "
        "on the supplied plaintext byte. X is time as a sample index (0-199), not a trace number "
        "or plaintext value. Y is a relative power signal in arbitrary units (a.u.), not watts. "
        "The signal includes a baseline, measurement noise, and the chip's modeled behavior. "
        "Values can be negative because the signal is relative to a reference level. "
        "All four plots share the same power scale; repeated captures include fresh noise."
    ),
    "threshold": (
        "Define the positive magnitude of the t-test cutoff. Usage: t-threshold <positive value>. "
        "No default. Each test plots +/-threshold and counts samples where |t| exceeds it. "
        "Saved tests retain their settings. Restart clears all experiment settings."
    ),
    "fixed-trials": "Set the number of fixed-plaintext trials. Usage: fixed-trials <2-50000>. No default.",
    "random-trials": "Set the number of random-plaintext trials. Usage: random-trials <2-50000>. No default.",
    "ttest": (
        "Fixed-vs-random Welch test. Usage: run-ttest <chip 1-4> [fixed byte, default 0]. "
        "fixed-trials, random-trials, and t-threshold must all be set explicitly first. "
        "Counts may differ; each group's sample variance is divided by its own trial count. "
        "X is time sample index; Y is the unitless t-statistic, not power. "
        "Dashed lines show the chosen positive and negative threshold."
    ),
    "guess": "Identify both the leaky chip and a time sample inside its leakage window. A completed t-test for that chip is required. Usage: guess-chip <chip 1-4> <sample 0-199>. An accepted sample is retained for profiling and key recovery.",
    "profile-key": "Choose the fixed key on the controlled copy. Usage: profile-key <byte 0-255>. Required, no default. Changing key clears measured profile and attack results.",
    "profile-inputs": "Choose the plaintext bytes to vary under the fixed key. Usage: profile-inputs <bytes/ranges>. Examples: 0-255 or 0,17,42 or 0-15 128-143. Bytes are 0-255, ranges inclusive; duplicates run once per trial. Required, no default. Only selected inputs run; class coverage depends on their S-box Hamming weights.",
    "profile-trials": "Choose repetitions per selected plaintext. Usage: profile-trials <2-5000>. Default 20. Repeat captures add to existing same-key, same-sample statistics.",
    "profile": (
        "Build the profile using the chosen sample, fixed key, and selected plaintexts. "
        "Usage: build-profile [clear]. The chip/sample guess must be accepted and profile-key and profile-inputs defined first. "
        "The key stays fixed while selected plaintexts vary. No other plaintexts are generated. "
        "Each trace is labeled HW(SBOX(plaintext XOR key)). Only observed classes fill the notebook. "
        "All nine classes need at least 20 observations and strictly increasing means for submission. "
        "view-chart profile opens the notebook without collecting. build-profile clear clears measurements. "
        "Changing the key clears measurements; changing inputs changes future captures."
    ),
    "submit-profile": "Submit the measured profile for validation and enter stage 3. Usage: submit-profile. Requires all nine classes, at least 20 observations per class, and strictly increasing means. Building a profile never advances the stage automatically.",
    "attack-inputs": "Choose target plaintext bytes before capturing. Usage: attack-inputs <bytes/ranges 0-255>. No default. Inputs cycle in the chosen set, with every byte used at least once. Changing selection affects future captures only.",
    "inspect-trace": "Inspect one representative full trace per chosen plaintext. Usage: inspect-trace <number>. The screen compares power at the accepted sample against the profile's class means.",
    "compare-key": "Compare a candidate for the unknown secret-key byte to the captured data. Usage: compare-key <byte 0-255>. Predicted HW and profile mean are computed from the candidate, not the hidden true key. The displayed residual is observed power minus predicted mean.",
    "attack": "Capture chosen-input target traces and rank 256 candidates for the unknown secret-key byte. Usage: attack [traces 1-50000, default at least 200]. Requires attack-inputs; count must cover every selected byte",
    "keyguess": "Submit the recovered key byte. Usage: keyguess <byte>",
    "view": "Review a saved chart without collecting traces. Usage: view traces|ttest [chip]|profile|attack",
    "cancel": "Cancel the current experiment, keeping previous results. Usage: cancel",
    "report": "Save session evidence as JSON without overwriting an existing file. Usage: report [filename.json]",
    "restart": "Reset progress and results; keep username unless supplied. Usage: restart [username]",
    "assessment": (
        "Leak assessment: compare fixed-versus-random Welch t-tests across the four chips. "
        "A localized |t| above your chosen threshold suggests data-dependent leakage; raw peaks alone do not. "
        "A fixed byte can yield a mean close to the varying-input mean even on a leaky chip. Try a different "
        "fixed byte if results are inconclusive. More traces reduce noise but cannot separate equal means. Submit a chip with guess."
    ),
    "profiling": (
        "Profiling: the accepted chip/sample guess fixes the measurement index from your t-chart. Build a profile "
        "with a fixed known key on the controlled copy and student-selected plaintext bytes. Measurements are grouped into "
        "nine Hamming-weight classes. Class means should rise steadily with HW(SBOX(p XOR k)). "
        "A flat or unordered profile may indicate a poor sample or insufficient traces. "
        "submit-profile validates the profile and unlocks key recovery."
    ),
    "recovery": (
        "Key recovery: run-attack captures fresh traces using the selected target plaintexts. Each candidate "
        "key predicts a Hamming-weight class; its profile mean is compared to observed power. "
        "Lower mean squared distance is better. One trace can leave several candidates tied; "
        "more traces add evidence. Each attack is independent. Submit a byte with keyguess."
    ),
    "help": "Show commands or explanations. Usage: help [command|assessment|profiling|recovery]",
    "exit": "Exit the game. Usage: exit",
}


STAGE_GOALS = (
    "Identify which of the four chips has power consumption that depends on its input data, "
    "and locate a time sample where that dependence appears. Your evidence is the difference "
    "between fixed-plaintext and varying-plaintext measurements under the same unknown key. "
    "This stage is complete when your chip and leak-sample identification is correct and "
    "supported by a completed t-test of that chip.\n"
    f"Setup: Use {command_name('fixed-trials')} <count> and {command_name('random-trials')} <count> "
    f"to choose the group sizes. Use {command_name('threshold')} <value> to set the cutoff shown on the chart.\n"
    f"Measure: Use {command_name('ttest')} <chip> to compare the two groups.\n"
    f"Submit: Use {command_name('guess')} <chip> <sample> to record your conclusion.",
    "Characterize the identified chip using a controlled copy whose key you choose and hold fixed. "
    "Your profile relates measured power at the accepted sample to the nine possible Hamming "
    "weights of the AES S-box output as plaintexts vary. The goal is a measured profile with "
    "enough observations in every class and consistently increasing means. Completion requires "
    "explicit submission of a valid profile; collecting data alone does not finish the stage.\n"
    f"Setup: Use {command_name('profile-key')} <byte> to hold the copy's key fixed and "
    f"{command_name('profile-inputs')} <bytes or ranges> to choose its inputs. "
    f"Use {command_name('profile-trials')} <count> to adjust repeats per input.\n"
    f"Measure: Use {command_name('profile')} to add measurements to the profile.\n"
    "Submit: Use submit-profile to validate the profile and enter key recovery.",
    "Use your submitted profile to infer one byte of the target chip's fixed, unknown key. "
    "You control the plaintexts but not the target key. Compare new measurements with the "
    "power predicted by candidate keys and assess their fit across multiple inputs. "
    "The goal is to identify and submit the correct key byte using evidence from your captures, "
    "rather than relying on one ambiguous trace.\n"
    f"Setup: Use {command_name('attack-inputs')} <bytes or ranges> to choose target inputs.\n"
    f"Measure: Use {command_name('attack')} [count] to capture traces and rank secret-key byte candidates.\n"
    f"Compare: Use {command_name('inspect-trace')} <number> to review a trace or "
    f"{command_name('compare-key')} <byte> to compare a secret-key candidate's fit with your measurements.\n"
    f"Submit: Use {command_name('keyguess')} <byte> to record your conclusion.",
    "The workshop is complete: you identified data-dependent leakage, measured its relationship "
    "to processed data, and used that profile to recover a secret key byte. Your recorded "
    "measurements and comparisons remain available for review and export.",
)


STAGE_TITLES = ("Leak assessment", "Profiling", "Key recovery", "Complete")
STAGE_COMMANDS = (
    {"trace", "threshold", "fixed-trials", "random-trials", "ttest", "guess"},
    {"profile-key", "profile-inputs", "profile-trials", "profile", "submit-profile"},
    {"attack-inputs", "inspect-trace", "compare-key", "attack", "keyguess"},
    set(),
)
COMMON_COMMANDS = {"goal", "status", "view", "cancel", "report", "restart", "help", "exit"}
TOPICS = ("assessment", "profiling", "recovery")


def print_help_commands(stage=None):
    if stage is None:
        for command in help_texts:
            if command not in TOPICS:
                print(f"- {COMMAND_NAMES.get(command, command)}")
        print("Learning topics: assessment, profiling, recovery")
        return
    print(f"{STAGE_TITLES[stage]}:")
    names = command_choices([name for name in help_texts if name in STAGE_COMMANDS[stage]])
    if names:
        print("Commands: " + " | ".join(names))
    shared = [COMMAND_NAMES.get(name, name) for name in help_texts if name in COMMON_COMMANDS]
    print("Shared: " + " | ".join(shared))
    if stage < 3:
        print(f"Learning topic: help {TOPICS[stage]}")


def help(command, stage=None):
    if len(command) == 1:
        print("Help / use help <command> for details")
        print_help_commands(stage)
    elif command[1] == "set" and len(command) == 2:
        settings = SETTINGS if stage is None else setting_names(STAGE_COMMANDS[stage])
        if settings:
            print("Usage: set <setting> <value>")
            print("Settings: " + " | ".join(settings))
            print("Use help set <setting> for details.")
        else:
            print("No settings are available in this stage.")
    elif resolve_command(" ".join(command[1:])) in help_texts:
        name = resolve_command(" ".join(command[1:]))
        available = (set(help_texts) if stage is None else
                     STAGE_COMMANDS[stage] | COMMON_COMMANDS | ({TOPICS[stage]} if stage < 3 else set()))
        if name not in available:
            print("That command or topic belongs to another stage.")
            return
        text = help_texts[name]
        if name == "help" and stage is not None:
            topic = f"|{TOPICS[stage]}" if stage < 3 else ""
            text = f"Show current-stage commands or explanations. Usage: help [command{topic}]"
        if name == "view" and stage is not None:
            choices = ("traces|ttest [chip]", "profile|ttest [chip]|traces", "attack|profile|ttest [chip]", "traces|ttest [chip]|profile|attack")
            text = f"Review recorded charts. Usage: view-chart {choices[stage]}"
        if "Usage: " in text:
            before, usage = text.split("Usage: ", 1)
            # Only the first word of the usage is a command.
            first, separator, rest = usage.partition(" ")
            text = before + "Usage: " + command_name(first) + separator + rest
        text = text.replace("profile (no arguments)", "build-profile (no arguments)")
        text = text.replace("view profile", "view-chart profile").replace("profile clear", "build-profile clear")
        text = text.replace("Collect measurements: profile ", "Collect measurements: build-profile ")
        text = text.replace("with guess.", "with guess-chip.")
        text = text.replace("then profile ", "then build-profile ").replace("with keyguess.", "with guess-key.")
        print(update_command_references(text))
    else:
        print(f"No help available for '{command[1]}'.")
        print_help_commands(stage)


if __name__ == "__main__":
    print_help_commands()
