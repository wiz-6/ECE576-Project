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
        "Saved tests retain their settings. Restart clears all experiment settings. It's the cutoff for "
        "'too big to be chance'. Pure noise still produces nonzero t. Low cutoffs give false positives; "
        "high ones can miss weak effects. "
        "See help welch-t-test for how often noise alone produces a given |t|."
    ),
    "fixed-trials": (
        "Set the number of fixed-plaintext trials. Usage: fixed-trials <2-50000>. No default. "
        "Every trace in this group repeats the same plaintext and key, so only noise varies. "
        "More traces give a more precise average (uncertainty shrinks like 1/√n), but tests take longer."
    ),
    "random-trials": (
        "Set the number of random-plaintext trials. Usage: random-trials <2-50000>. No default. "
        "Each trace uses a new random plaintext, so the average blends all inputs. "
        "This group naturally scatters more on a data-dependent chip."
    ),
    "ttest": (
        "Fixed-vs-random Welch test. Usage: run-ttest <chip 1-4> [fixed byte, default 0]. "
        "fixed-trials, random-trials, and t-threshold must all be set explicitly first.\n"
        "What it does: collects two groups of traces from one chip under the same unknown key. "
        "The fixed group uses the same plaintext byte in every trace; the random group uses a new "
        "random plaintext byte in every trace. The groups are captured interleaved. Welch's "
        "t-statistic is then computed separately at each of the 200 time samples, comparing the "
        "two groups' average power at that moment. See help welch-t-test for the formula.\n"
        "Fixed byte: the plaintext repeated in every fixed-group trace. The test asks whether the "
        "chip's average power while processing this one input differs from its average power "
        "across all inputs.\n"
        "Group sizes: counts may differ; each group's sample variance is divided by its own trial "
        "count. More traces make each group's average more precise, so a real difference stands "
        "out more clearly, but the test takes longer.\n"
        "Chart: X is the time sample index (0-199), the same axis as the raw traces. Y is the "
        "unitless t-statistic, not power. Dashed lines show the chosen positive and negative threshold.\n"
        "Output: peak |t| is the largest magnitude of t and the sample where it occurs. "
        "'samples exceed' counts how many of the 200 samples have |t| above the threshold."
    ),
    "welch-t-test": (
        "Welch's t-test\n"
        "Purpose: decide whether two groups of measurements have different average values, or "
        "whether the observed difference could easily be produced by noise. run-ttest applies it "
        "independently at each of the 200 time samples.\n"
        "Formula: t = (mean_F - mean_R) / sqrt(s_F^2 / n_F + s_R^2 / n_R)\n"
        "  mean_F, mean_R: average power of the fixed and random groups at that sample.\n"
        "  s_F^2, s_R^2: sample variances, the average squared distance of each group's "
        "measurements from its own mean (dividing by n - 1). They describe how much individual "
        "measurements scatter.\n"
        "  n_F, n_R: the number of traces in each group, chosen with set num-fixed-traces and "
        "set num-random-traces.\n"
        "Numerator: the observed difference between the two averages, in power units.\n"
        "Denominator: the standard error, the typical size of that difference if the true averages "
        "were equal and only noise were present. It shrinks as the groups grow.\n"
        "Meaning: t is the difference measured in units of its own uncertainty. t = 5 means the "
        "averages differ by five standard errors.\n"
        "Why Welch: unlike Student's t-test, it does not assume the two groups have equal variance "
        "or equal size; each group's variance is divided by its own count.\n"
        "Sign: positive t means the fixed group drew more power at that sample; negative means less. "
        "When looking for any difference, the magnitude |t| is what matters.\n"
        "Traces and t: when a real difference exists, |t| grows roughly with the square root of the "
        "number of traces, so four times as many traces roughly doubles it. When no real difference "
        "exists, |t| stays in the noise range however many traces you collect.\n"
        "Chance values: with no real difference, t at each sample behaves roughly like a standard "
        "normal value, so |t| > 2 occurs at about 5% of samples by chance alone. Testing 200 samples "
        "at once makes some moderate values likely; the threshold sets how large |t| must be before "
        "you treat it as evidence."
    ),
    "guess": "Identify both the leaky chip and a time sample inside its leakage window. A completed t-test for that chip is required. Usage: guess-chip <chip 1-4> <sample 0-199>. An accepted sample is retained for profiling and key recovery.",
    "profile-key": (
        "Choose the fixed key on the controlled copy. Usage: profile-key <byte 0-255>. Required, no default. "
        "Changing key clears measured profile and attack results.\n"
        "Controlled copy: a second chip identical to the target that you own, so you can set its key. "
        "On the target the key is secret; on the copy you choose it.\n"
        "Why it matters: with a known key you can compute the value the chip processed in every trace, "
        "SBOX(plaintext XOR key), and label the measurement with that value's Hamming weight (see help "
        "hamming-weight). Those labels are what turn raw measurements into a profile. Changing the key "
        "makes earlier labels wrong, which is why measurements are cleared."
    ),
    "profile-inputs": (
        "Choose the plaintext bytes to vary under the fixed key. Usage: profile-inputs <bytes/ranges>. "
        "Examples: 0-255 or 0,17,42 or 0-15 128-143. Bytes are 0-255, ranges inclusive; duplicates run once "
        "per trial. Required, no default.\n"
        "What it is: the plaintexts sent to the controlled copy while its key stays fixed. Each plaintext p "
        "produces one value SBOX(p XOR key), so a given plaintext always lands in the same one of the nine "
        "Hamming-weight classes.\n"
        "Why it matters: only selected inputs run, so the profile only fills the classes your plaintexts "
        "reach. Classes are not equally common, so the selection decides which classes get measured and how "
        "quickly they collect observations."
    ),
    "profile-trials": (
        "Choose repetitions per selected plaintext. Usage: profile-trials <2-5000>. Default 20. "
        "Repeat captures add to existing same-key, same-sample statistics.\n"
        "What it is: how many times each selected plaintext is measured in one build-profile run. "
        "Total traces per run = trials x number of selected plaintexts.\n"
        "Why it matters: every measurement includes noise. A class's count is trials x the number of "
        "selected plaintexts in that class, and the more observations a class has, the more precisely its "
        "mean is known (uncertainty shrinks roughly like stddev / sqrt(count))."
    ),
    "profile": (
        "Build the profile using the chosen sample, fixed key, and selected plaintexts. "
        "Usage: build-profile [clear]. The chip/sample guess must be accepted and profile-key and profile-inputs defined first. "
        "The key stays fixed while selected plaintexts vary. No other plaintexts are generated. "
        "Each trace is labeled HW(SBOX(plaintext XOR key)). Only observed classes fill the notebook. "
        "All nine classes need at least 20 observations and strictly increasing means for submission. "
        "view-chart profile opens the notebook without collecting. build-profile clear clears measurements. "
        "Changing the key clears measurements; changing inputs changes future captures.\n"
        "Output table: HW is the Hamming-weight class (0-8). count (Traces in the notebook) is how many "
        "measurements fell in that class. mean is their average power in a.u.; it becomes the profile's "
        "predicted power for that class. stddev is their spread, mostly measurement noise: how far a single "
        "measurement typically lands from its class mean."
    ),
    "submit-profile": "Submit the measured profile for validation and enter stage 3. Usage: submit-profile. Requires all nine classes, at least 20 observations per class, and strictly increasing means. Building a profile never advances the stage automatically.",
    "attack-inputs": (
        "Choose target plaintext bytes before capturing. Usage: attack-inputs <bytes/ranges 0-255>. No default. "
        "Inputs cycle in the chosen set, with every byte used at least once. Changing selection affects "
        "future captures only.\n"
        "What it is: the plaintexts sent to the target chip, whose key you do not know.\n"
        "Why it matters: each candidate key predicts a Hamming-weight class for each plaintext. One "
        "plaintext can only sort the 256 candidates into nine classes, so many wrong candidates predict "
        "the same class as the true key and tie with it. Each additional distinct plaintext splits the "
        "candidates differently, so fewer wrong candidates keep matching."
    ),
    "inspect-trace": "Inspect one representative full trace per chosen plaintext. Usage: inspect-trace <number>. The screen compares power at the accepted sample against the profile's class means.",
    "compare-key": (
        "Compare a candidate for the unknown secret-key byte to the captured data. Usage: compare-key <byte 0-255>. "
        "Predicted HW and profile mean are computed from the candidate, not the hidden true key. "
        "The displayed residual is observed power minus predicted mean.\n"
        "Reading it: for the correct key, the predicted classes match the real ones, so residuals are just "
        "noise centered on zero and the observed class averages (blue) follow the profile (green). For a "
        "wrong key, many traces are assigned to the wrong class: residuals are larger and the blue averages "
        "look flat or out of order."
    ),
    "attack": (
        "Capture chosen-input target traces and rank 256 candidates for the unknown secret-key byte. "
        "Usage: attack [traces 1-50000]. Default: 200, or the number of selected plaintexts if larger. "
        "Requires attack-inputs; count must cover every selected byte.\n"
        "Output: the five best candidates, in hex and decimal, with their distance. Distance is the average "
        "over all traces of (observed power - profile mean of the class the candidate predicts)^2, in a.u. "
        "squared. Lower is better. A clear gap between the first and second candidates indicates a decisive "
        "result; nearly equal distances mean the evidence cannot yet separate them."
    ),
    "keyguess": "Submit the recovered key byte. Usage: keyguess <byte>",
    "view": "Review a saved chart without collecting traces. Usage: view traces|ttest [chip]|profile|attack",
    "cancel": "Cancel the current experiment, keeping previous results. Usage: cancel",
    "report": "Save session evidence as JSON without overwriting an existing file. Usage: report [filename.json]",
    "restart": "Reset progress and results; keep username unless supplied. Usage: restart [username]",
    "assessment": (
        "Leak assessment: compare fixed-versus-random Welch t-tests across the four chips. "
        "A localized |t| above your chosen threshold suggests data-dependent leakage; raw peaks alone do not. "
        "A fixed byte can yield a mean close to the varying-input mean even on a leaky chip. Try a different "
        "fixed byte if results are inconclusive. More traces reduce noise but cannot separate equal means. "
        "See help welch-t-test for how t is computed and interpreted. Submit a chip with submit-chip-guess."
    ),
    "profiling": (
        "Profiling: the accepted chip/sample guess fixes the measurement index from your t-chart. Build a profile "
        "with a fixed known key on the controlled copy and student-selected plaintext bytes. Measurements are grouped into "
        "nine Hamming-weight classes. Class means should rise steadily with HW(SBOX(p XOR k)). "
        "A flat or unordered profile may indicate a poor sample or insufficient traces. "
        "submit-profile validates the profile and unlocks key recovery. "
        "See help hamming-weight for what the classes mean."
    ),
    "hamming-weight": (
        "Hamming weight and the S-box\n"
        "Hamming weight (HW): the number of 1 bits in a byte, from 0 to 8. Examples: 0x00 = 00000000 has "
        "HW 0; 0x5A = 01011010 has HW 4; 0xFF = 11111111 has HW 8.\n"
        "Why it predicts power: CMOS logic draws current when it charges wires and registers to 1. A common "
        "first approximation is that the power drawn while a value is handled grows with its number of 1 "
        "bits. Values with the same HW are predicted to draw the same power, which gives nine classes, "
        "HW 0 through HW 8.\n"
        "The S-box: AES's SubBytes step replaces each byte using a fixed 256-entry lookup table called the "
        "S-box. It is deliberately non-linear: similar inputs produce unrelated outputs.\n"
        "Why SBOX(p XOR k): this intermediate value depends on a byte you know (the plaintext p) and the "
        "byte you want (the key k). For any guess of k you can predict the HW for every plaintext. Because "
        "the S-box scrambles its input, a wrong guess predicts classes unrelated to the real ones, so its "
        "predictions fit the measurements poorly.\n"
        "In this lab: profiling learns the average power of each HW class; key recovery checks which key's "
        "predicted classes best match new measurements."
    ),
    "recovery": (
        "Key recovery: run-attack captures fresh traces using the selected target plaintexts. Each candidate "
        "key predicts a Hamming-weight class; its profile mean is compared to observed power. "
        "Lower mean squared distance is better. One trace can leave several candidates tied; "
        "more traces add evidence. Each attack is independent. Submit a byte with submit-key-guess."
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
    f"Submit: Use {command_name('guess')} <chip> <sample> to record your conclusion.\n"
    "Learn: help assessment explains the method; help welch-t-test explains the t-statistic.",
    "Characterize the identified chip using a controlled copy whose key you choose and hold fixed. "
    "Your profile relates measured power at the accepted sample to the nine possible Hamming "
    "weights of the AES S-box output as plaintexts vary. The goal is a measured profile with "
    "enough observations in every class and consistently increasing means. Completion requires "
    "explicit submission of a valid profile; collecting data alone does not finish the stage.\n"
    f"Setup: Use {command_name('profile-key')} <byte> to hold the copy's key fixed and "
    f"{command_name('profile-inputs')} <bytes or ranges> to choose its inputs. "
    f"Use {command_name('profile-trials')} <count> to adjust repeats per input.\n"
    f"Measure: Use {command_name('profile')} to add measurements to the profile.\n"
    "Submit: Use submit-profile to validate the profile and enter key recovery.\n"
    "Learn: help profiling explains the method; help hamming-weight explains the classes.",
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
# Reference topics stay available from their first stage onward.
REFERENCE_TOPICS = {"welch-t-test": 0, "hamming-weight": 1}
ALL_TOPICS = TOPICS + tuple(REFERENCE_TOPICS)


def stage_topics(stage):
    return (([TOPICS[stage]] if stage < 3 else [])
            + [topic for topic, first in REFERENCE_TOPICS.items() if stage >= first])


def print_help_commands(stage=None):
    if stage is None:
        for command in help_texts:
            if command not in ALL_TOPICS:
                print(f"- {COMMAND_NAMES.get(command, command)}")
        print("Learning topics: " + ", ".join(ALL_TOPICS))
        return
    print(f"{STAGE_TITLES[stage]}:")
    names = command_choices([name for name in help_texts if name in STAGE_COMMANDS[stage]])
    if names:
        print("Commands: " + " | ".join(names))
    shared = [COMMAND_NAMES.get(name, name) for name in help_texts if name in COMMON_COMMANDS]
    print("Shared: " + " | ".join(shared))
    print("Learning topics: " + " | ".join(f"help {topic}" for topic in stage_topics(stage)))


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
                     STAGE_COMMANDS[stage] | COMMON_COMMANDS | set(stage_topics(stage)))
        if name not in available:
            print("That command or topic belongs to another stage.")
            return
        text = help_texts[name]
        if name == "help" and stage is not None:
            topics = "".join(f"|{topic}" for topic in stage_topics(stage))
            text = f"Show current-stage commands or explanations. Usage: help [command{topics}]"
        if name == "view" and stage is not None:
            choices = ("traces|ttest [chip]", "profile|ttest [chip]|traces", "attack|profile|ttest [chip]", "traces|ttest [chip]|profile|attack")
            text = f"Review recorded charts. Usage: view-chart {choices[stage]}"
        if "Usage: " in text:
            before, usage = text.split("Usage: ", 1)
            # Only the first word of the usage is a command.
            first, separator, rest = usage.partition(" ")
            text = before + "Usage: " + command_name(first) + separator + rest
        print(update_command_references(text))
    else:
        print(f"No help available for '{command[1]}'.")
        print_help_commands(stage)


if __name__ == "__main__":
    print_help_commands()
