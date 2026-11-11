"""Game progression and terminal commands, independent of Pygame rendering."""
import copy
import json
import math
from pathlib import Path
import random
import shlex

import numpy as np

from analysis import candidate_profile, build_profile, collect_ttest, merge_profiles, recover_key
from chip import LeakyChip, init_chip
from help import COMMAND_NAMES, COMMON_COMMANDS, STAGE_COMMANDS, STAGE_GOALS, TOPICS, SETTINGS, command_choices, setting_names, resolve_command, help as show_help, public_text, update_command_references


class Game:
    stages = ("1 / LEAK ASSESSMENT", "2 / PROFILING", "3 / KEY RECOVERY", "COMPLETE")

    def __init__(self, terminal):
        self.terminal = terminal
        terminal.completion_provider = self.completions
        self.username = None
        self.stage = 0
        self.assessment_result = None
        self.selected = None
        self.sample = None
        self.profile = None
        self.profile_submitted = False
        self.attack = None
        self.last_test = None
        self.attack_history = []
        self.fixed_trials = self.random_trials = None
        self.profile_key = None
        self.profile_inputs = None
        self.attack_inputs = None
        self.profile_trials = 20
        self.threshold = None
        self.tests = {}
        self.guesses = []
        self.key_guesses = []
        self.chips = []

    def initialize(self, username):
        self.username = username
        rng = random.Random(username)
        self.secret_key = rng.getrandbits(128)
        kinds = ["fixed", "noise", "random", "leaky"]
        rng.shuffle(kinds)
        self.chips = [init_chip(kind) for kind in kinds]
        self.stage = 0
        self.selected = self.sample = self.profile = self.attack = None
        self.profile_submitted = False
        self.assessment_result = None
        self.last_test = None
        self.attack_history = []
        self.fixed_trials = self.random_trials = None
        self.profile_key = None
        self.profile_inputs = None
        self.attack_inputs = None
        self.profile_trials = 20
        self.threshold = None
        self.tests = {}
        self.guesses = []
        self.key_guesses = []
        self.terminal.reset_views()
        self.terminal.set_traces([chip.get_trace(0, self.secret_key) for chip in self.chips], 0)
        self.terminal.history.clear()
        self.terminal.history_index = 0
        print(f"Welcome, {username}! Recover one AES key byte through three experiments.")
        self.status()
        self.describe_goal()

    def describe_goal(self):
        print("Goal: " + STAGE_GOALS[self.stage])

    def status(self):
        print(f"Stage {self.stages[self.stage]}")
        if self.selected is not None:
            print(f"Identified chip: {self.selected}")
        if self.sample is not None:
            print(f"Selected sample: {self.sample}")
        if self.stage == 0:
            print(f"T threshold: {self.threshold if self.threshold is not None else 'not set'}")
            print(f"Fixed trials: {self.fixed_trials if self.fixed_trials is not None else 'not set'}")
            print(f"Random trials: {self.random_trials if self.random_trials is not None else 'not set'}")
            print(f"Recorded t-tests: {len(self.tests)}")
        elif self.stage == 1:
            print(f"Profile: {'ready' if self.profile and self.profile['monotonic'] else 'not ready'}")
            print(f"Profile key: {self.profile_key if self.profile_key is not None else 'not set'}")
            print(f"Selected plaintexts: {len(self.profile_inputs) if self.profile_inputs else 'not set'}")
            print(f"Trials per plaintext: {self.profile_trials}")
        else:
            if self.stage == 2:
                print(f"Selected target plaintexts: {len(self.attack_inputs) if self.attack_inputs else 'not set'}")
            print(f"Recorded attacks: {len(self.attack_history)}")

    def require(self, condition, message):
        if not condition:
            raise ValueError(message)

    @staticmethod
    def number(value, low, high):
        try:
            number = int(value, 16) if value.lower().startswith('0x') else int(value)
        except ValueError:
            raise ValueError(f"Expected an integer from {low} to {high} (decimal or 0x hex).") from None
        if not low <= number <= high:
            raise ValueError(f"Value must be from {low} to {high}.")
        return number

    def start(self, title, work, complete):
        self.terminal.start_job(title, work, complete)

    def parse_inputs(self, args):
        self.require(bool(args), "Specify plaintext bytes or ranges from 0 to 255.")
        inputs = set()
        for token in ",".join(args).split(","):
            if "-" in token:
                bounds = token.split("-")
                self.require(len(bounds) == 2, "Invalid plaintext range.")
                low, high = [self.number(value, 0, 255) for value in bounds]
                self.require(low <= high, "Plaintext ranges must be ascending.")
                inputs.update(range(low, high + 1))
            else:
                inputs.add(self.number(token, 0, 255))
        return sorted(inputs)

    def completions(self, text):
        """Return public command/argument names without exposing hidden session data."""
        if self.username is None:
            return []
        words = text.split()
        if not words or text[-1:].isspace():
            words.append("")
        prefix = words[-1]
        available = STAGE_COMMANDS[self.stage] | COMMON_COMMANDS
        if len(words) == 1:
            if self.terminal.analysis_future is not None:
                available = {"help", "status", "cancel", "exit"}
            choices = command_choices(available)
        else:
            name = resolve_command(words[0])
            if name == "set" and len(words) == 2 and self.terminal.analysis_future is None:
                return sorted(option for option in setting_names(available) if option.startswith(prefix))
            if name == "help" and len(words) == 3 and words[1] == "set":
                return sorted(option for option in setting_names(available) if option.startswith(prefix))
            if name not in available:
                return []
            if name == "help" and len(words) == 2:
                choices = command_choices(available)
                if self.stage < 3:
                    choices.append(TOPICS[self.stage])
            elif name == "view" and len(words) == 2:
                choices = list(self.terminal.charts)
                if self.chips:
                    choices.append("traces")
                if self.tests:
                    choices.append("ttest")
            elif name == "view" and len(words) == 3 and words[1] == "ttest":
                choices = [str(chip) for chip in self.tests]
            elif name == "profile" and len(words) == 2:
                choices = ["clear"]
            else:
                return []
        return sorted(set(choice for choice in choices if choice.startswith(prefix)))

    def submit(self, value):
        try:
            command = shlex.split(value)
            if not command:
                if self.username is None:
                    print("Please enter your WPI username.")
                return
            if self.username is None:
                self.initialize(value.strip())
                self.terminal.prompt = "> "
                return
            name, *args = command
            if name == "set":
                self.require(args and args[0] in SETTINGS, "Specify a setting. See help set.")
                name, args = SETTINGS[args[0]], args[1:]
            name = resolve_command(name)
            stage_specific = set().union(*STAGE_COMMANDS)
            self.require(name not in stage_specific or name in STAGE_COMMANDS[self.stage],
                         "That command is unavailable in the current stage.")
            if name in ("exit", "status", "cancel", "goal"):
                self.require(not args, f"Usage: {COMMAND_NAMES.get(name, name)}")
            if name == "help":
                self.require(len(args) <= 1 or (len(args) == 2 and args[0] == "set"),
                             "Usage: help [command or topic] or help set <setting>")
            if name == "exit":
                if self.terminal.analysis_future is not None:
                    self.terminal.cancel_job()
                print("Exiting the game...")
                return False
            if name == "help":
                show_help(command, stage=self.stage)
                return
            if name == "goal":
                self.describe_goal()
                return
            if name == "status":
                self.status()
                return
            if name == "cancel":
                self.terminal.cancel_job()
                return
            if self.terminal.analysis_future is not None:
                print("An experiment is running.")
                return
            match name:
                case "fixed-trials" | "random-trials":
                    self.require(len(args) == 1, f"Usage: {name} <2-50000>")
                    count = self.number(args[0], 2, 50000)
                    if name == "fixed-trials":
                        self.fixed_trials = count
                    else:
                        self.random_trials = count
                    print(f"{COMMAND_NAMES.get(name, name)}: {count}")
                case "threshold":
                    self.require(len(args) == 1, "Usage: threshold <positive t-value>")
                    try:
                        threshold = float(args[0])
                    except ValueError:
                        raise ValueError("Threshold must be a finite positive number.") from None
                    self.require(math.isfinite(threshold) and threshold > 0,
                                 "Threshold must be a finite positive number.")
                    self.threshold = threshold
                    print(f"T threshold set to +/-{threshold:g} for future tests.")
                case "ttest":
                    self.ttest(args)
                case "trace":
                    self.require(len(args) <= 1, "Usage: trace [plaintext byte]")
                    plaintext = self.number(args[0], 0, 255) if args else 0
                    self.terminal.set_traces([chip.get_trace(plaintext, self.secret_key)
                                              for chip in self.chips], plaintext)
                    print(f"Captured four chip traces for plaintext {plaintext}.")
                case "guess":
                    self.guess(args)
                case "profile-key":
                    self.require(self.stage == 1, "Profile configuration is unavailable in this stage.")
                    self.require(len(args) == 1, "Usage: profile-key <byte 0-255>")
                    key = self.number(args[0], 0, 255)
                    if self.profile_key != key:
                        self.profile_key = key
                        self.clear_profile()
                    self.show_profile()
                    print(f"Fixed profile key: 0x{key:02X}.")
                case "profile-inputs":
                    self.require(self.stage == 1, "Profile configuration is unavailable in this stage.")
                    self.require(bool(args), "Usage: profile-inputs <bytes and/or ranges, e.g. 0-255>")
                    self.profile_inputs = self.parse_inputs(args)
                    self.show_profile()
                    print(f"Selected {len(self.profile_inputs)} plaintext bytes. Fixed key unchanged.")
                case "profile-trials":
                    self.require(self.stage == 1, "Profile configuration is unavailable in this stage.")
                    self.require(len(args) == 1, "Usage: profile-trials <2-5000>")
                    self.profile_trials = self.number(args[0], 2, 5000)
                    self.show_profile()
                    print(f"Trials per selected plaintext: {self.profile_trials}.")
                case "profile":
                    self.profiling(args)
                case "submit-profile":
                    self.require(not args, "Usage: submit-profile")
                    self.require_assessment()
                    self.require(self.profile is not None and self.profile["monotonic"]
                                 and all(n >= 20 for n in self.profile["counts"]),
                                 "Profile submission rejected: nine increasing class means and at least 20 observations per class are required.")
                    self.profile_submitted = True
                    self.stage = 2
                    self.show_attack()
                    print("Stage 2 complete! Profile submitted.")
                    self.describe_goal()
                case "attack-inputs":
                    self.attack_inputs = self.parse_inputs(args)
                    print(f"Selected {len(self.attack_inputs)} target plaintext bytes for future captures.")
                    if self.attack is None:
                        self.show_attack()
                case "inspect-trace":
                    self.require(self.attack is not None, "No target traces recorded.")
                    self.require(len(args) == 1, "Usage: inspect-trace <number>")
                    index = self.number(args[0], 1, len(self.attack["display_traces"])) - 1
                    candidate = self.terminal.charts["attack"]["candidate"]
                    self.show_attack(index=index, candidate=candidate)
                case "compare-key":
                    self.require(self.attack is not None, "No target traces recorded.")
                    self.require(len(args) == 1, "Usage: compare-key <byte>")
                    candidate = self.number(args[0], 0, 255)
                    index = self.terminal.charts["attack"].get("index", 0)
                    self.show_attack(index=index, candidate=candidate)
                case "attack":
                    self.attacking(args)
                case "keyguess":
                    self.keyguess(args)
                case "view":
                    self.view(args)
                case "report":
                    self.report(args)
                case "restart":
                    self.require(len(args) <= 1, "Usage: restart [username]")
                    self.initialize(args[0] if args else self.username)
                case _:
                    print("Unknown command. Type 'help' for available commands.")
        except (ValueError, OSError) as error:
            message = str(error)
            print(public_text(message) if message.startswith("Usage:") else update_command_references(message))
        finally:
            self.terminal.stage_text = self.stages[self.stage]
            self.terminal.stage_index = self.stage

    def ttest(self, args):
        self.require(self.threshold is not None, "No t threshold defined. See help t-threshold.")
        self.require(self.fixed_trials is not None and self.random_trials is not None,
                     "Fixed and random trial counts must both be defined. See help run-ttest.")
        threshold = self.threshold
        fixed_count, random_count = self.fixed_trials, self.random_trials
        self.require(1 <= len(args) <= 2, "Usage: run-ttest <chip 1-4> [fixed byte]")
        chip = self.number(args[0], 1, 4)
        plaintext = self.number(args[1], 0, 255) if len(args) == 2 else 0

        def complete(values):
            peak = int(np.argmax(np.abs(values)))
            result = {"chip": chip, "fixed_count": fixed_count, "random_count": random_count, "plaintext": plaintext,
                      "peak_sample": peak, "peak_t": float(values[peak]),
                      "threshold": threshold, "crossings": int(np.sum(np.abs(values) > threshold)), "values": values.tolist()}
            self.tests[chip] = result
            self.last_test = chip
            self.terminal.analysis = (chip, fixed_count, random_count, plaintext, values, threshold)
            self.terminal.plot = None
            print(f"Chip {chip}: peak |t|={abs(values[peak]):.2f} at sample {peak}; "
                  f"{result['crossings']} samples exceed |t| > {threshold:g}.")
            if not result["crossings"]:
                print(f"Inconclusive for fixed plaintext 0x{plaintext:02X}. "
                      "A first-order t-test compares means, which can be similar even when leakage exists.")
                print(f"Try another fixed byte with run-ttest {chip} {(plaintext + 1) % 256}. "
                      "Use more traces if measurement noise is limiting the comparison.")
        self.start(f"T-test chip {chip}: {fixed_count} fixed + {random_count} random traces",
                   lambda cancel, progress: collect_ttest(self.chips[chip - 1], self.secret_key,
                                                         fixed_count, random_count, plaintext, cancel, progress), complete)

    def guess(self, args):
        self.require(len(args) == 2, "Usage: guess-chip <chip 1-4> <sample 0-199>")
        chip = self.number(args[0], 1, 4)
        sample = self.number(args[1], 0, 199)
        self.require(self.stage == 0, "The leaky chip is already identified.")
        self.require(chip in self.tests and self.tests[chip]["chip"] == chip,
                     "No completed t-test is recorded for that chip.")
        target = self.chips[chip - 1]
        correct = isinstance(target, LeakyChip) and target.leak_index <= sample < target.leak_index + 5
        self.guesses.append({"chip": chip, "sample": sample, "correct": correct})
        if not correct:
            print("Chip and sample guess is incorrect. Try again!")
            return
        self.selected = chip
        self.sample = sample
        self.assessment_result = copy.deepcopy(self.tests[chip])
        self.stage = 1
        self.show_profile()
        print(f"You win Stage 1! Chip {chip}, sample {sample}, correctly identifies the leak. Congratulations!")
        self.status()
        self.describe_goal()

    def show_profile(self):
        profile = self.profile
        self.terminal.show_chart("profile", {
            "kind": "profile", "sample": self.sample,
            "key": self.profile_key, "inputs": self.profile_inputs, "trials": self.profile_trials,
            "counts": profile["counts"] if profile else [0] * 9,
            "values": profile["means"] if profile else [None] * 9,
            "stddev": profile["stddev"] if profile else [None] * 9,
            "accepted": self.profile_submitted,
            "ready": bool(profile and profile["monotonic"]),
        })

    def clear_profile(self):
        self.profile = self.attack = None
        self.profile_submitted = False
        self.terminal.charts.pop("attack", None)
        self.stage = 1

    def require_assessment(self):
        self.require(self.selected is not None and self.assessment_result is not None
                     and self.assessment_result["chip"] == self.selected
                     and self.sample is not None
                     and self.chips[self.selected - 1].leak_index <= self.sample < self.chips[self.selected - 1].leak_index + 5
                     and isinstance(self.chips[self.selected - 1], LeakyChip),
                     "No completed assessment is recorded for the identified leaky chip.")

    def profiling(self, args):
        self.require(self.stage == 1, "Profiling is unavailable in this stage.")
        self.require_assessment()
        if args == ["clear"]:
            self.clear_profile()
            self.show_profile()
            print("Profile measurements cleared.")
            return
        self.require(not args, "Usage: build-profile [clear]")
        self.require(self.sample is not None, "No sample selected.")
        self.require(self.profile_key is not None, "No fixed profile key defined.")
        self.require(self.profile_inputs is not None, "No profile plaintexts selected.")
        key, count = self.profile_key, self.profile_trials
        plaintexts = list(self.profile_inputs)
        controlled_chip = copy.copy(self.chips[self.selected - 1])

        def complete(result):
            self.profile = merge_profiles(self.profile, result)
            self.profile_submitted = False
            self.attack = None
            self.terminal.charts.pop("attack", None)
            print(f"Profile at sample {self.sample} (known key 0x{key:02X}):")
            print(" HW    count     mean      stddev")
            for hw, n in enumerate(self.profile["counts"]):
                if n:
                    print(f" {hw:2}    {n:5}    {self.profile['means'][hw]:7.3f}    "
                          f"{self.profile['stddev'][hw]:7.3f}")
            self.show_profile()
            filled = sum(n > 0 for n in self.profile["counts"])
            if self.profile["monotonic"]:
                print("Profile ready; not submitted.")
            else:
                self.stage = 1
                if filled < 9:
                    print(f"Profile recorded: {filled}/9 classes measured.")
                elif any(n < 20 for n in self.profile["counts"]):
                    print("Profile not accepted: fewer than 20 observations in a class.")
                else:
                    print("Profile not accepted: class means are not strictly increasing.")
            self.terminal.stage_text = self.stages[self.stage]
            self.terminal.stage_index = self.stage
        total = count * len(plaintexts)
        self.start(f"Profiling chip copy: {total} traces / fixed key 0x{key:02X} / {len(plaintexts)} plaintexts",
                   lambda cancel, progress: build_profile(controlled_chip, key, self.sample,
                                                         plaintexts, count, cancel, progress), complete)

    def show_attack(self, index=0, candidate=None):
        result = self.attack
        if candidate is None and result is not None:
            candidate = result["ranking"][0]
        fit = None
        if result is not None:
            fit = (result["candidate_fit"] if candidate == result["ranking"][0] else
                   candidate_profile(result["plaintexts"], result["observations"], candidate))
        self.terminal.show_chart("attack", {"kind": "recovery", "sample": self.sample, "fit": fit,
            "profile": self.profile, "result": result, "inputs": self.attack_inputs,
            "index": index, "candidate": candidate})

    def attacking(self, args):
        self.require(len(args) <= 1, "Usage: attack [trace count 1-50000]")
        self.require(self.stage == 2 and self.profile_submitted and self.profile is not None and self.profile["monotonic"],
                     "No accepted profile is available in the current stage.")
        self.require_assessment()
        self.require(self.attack_inputs is not None, "No target plaintexts selected. See help attack-inputs.")
        inputs = list(self.attack_inputs)
        count = self.number(args[0], 1, 50000) if args else max(200, len(inputs))
        self.require(count >= len(inputs), "Trace count must cover every selected plaintext at least once.")

        def complete(result):
            result["profile"] = copy.deepcopy(self.profile)
            self.attack = result
            self.attack_history.append(result)
            print(f"Ranked secret-key candidates from {count} new traces (mean squared distance):")
            for rank, candidate in enumerate(result["ranking"][:5], 1):
                print(f" {rank}. 0x{candidate:02X} ({candidate})  distance={result['scores'][candidate]:.4f}")
            self.show_attack()
        self.start(f"Attacking chip {self.selected}: {count} unknown-key traces",
                   lambda cancel, progress: recover_key(self.chips[self.selected - 1], self.secret_key,
                                                       self.profile, count, cancel, progress, inputs), complete)

    def keyguess(self, args):
        self.require(len(args) == 1, "Usage: keyguess <byte 0-255 or 0x00-0xff>")
        key = self.number(args[0], 0, 255)
        self.require(self.stage == 2 and self.attack is not None,
                     "Key submission is unavailable without a recorded Stage 3 attack.")
        correct = key == (self.secret_key & 255)
        self.key_guesses.append({"key": key, "correct": correct})
        if correct:
            self.stage = 3
            print(f"You win! Recovered secret AES key byte 0x{key:02X}. All three stages complete!")
            print("You identified data-dependent leakage, built a profile, and recovered the key byte.")
        else:
            print("That is not the secret key byte.")

    def view(self, args):
        self.require(1 <= len(args) <= 2, "Usage: view traces|ttest [chip]|profile|attack")
        self.require(len(args) == 1 or args[0] == "ttest", "Only view ttest accepts a chip number.")
        name = args[0]
        if name == "traces":
            self.terminal.analysis = None
            self.terminal.plot = None
        elif name == "ttest":
            self.require(bool(self.tests), "No t-test is recorded.")
            chip = self.number(args[1], 1, 4) if len(args) == 2 else (self.selected or self.last_test)
            self.require(chip in self.tests, "No t-test is recorded for that chip.")
            result = self.tests[chip]
            self.terminal.analysis = (result["chip"], result["fixed_count"], result["random_count"], result["plaintext"],
                                      result["values"], result["threshold"])
            self.terminal.plot = None
        else:
            self.require(name in self.terminal.charts, "That chart is not available yet.")
            self.terminal.plot = self.terminal.charts[name]
            self.terminal.analysis = None

    def report(self, args):
        self.require(len(args) <= 1, 'Usage: report [filename.json]')
        path = Path(args[0] if args else 'chip-lab-results.json')
        self.require(not path.exists(), "Report already exists. Choose another filename to keep the previous report.")
        data = {"username": self.username, "stage": self.stages[self.stage],
                "identified_chip": self.selected, "assessment": self.assessment_result,
                "selected_sample": self.sample, "profile_submitted": self.profile_submitted,
                "threshold": self.threshold, "fixed_trials": self.fixed_trials,
                "random_trials": self.random_trials, "profile_key": self.profile_key,
                "profile_inputs": self.profile_inputs, "attack_inputs": self.attack_inputs, "profile_trials": self.profile_trials, "ttests": list(self.tests.values()), "profile": self.profile,
                "attack": self.attack, "attack_history": self.attack_history,
                "chip_guesses": self.guesses, "key_guesses": self.key_guesses,
                "completed": self.stage == 3}
        # Secret key and hidden chip identities are never included in the report.
        with path.open('x') as stream:
            json.dump(data, stream, indent=2)
        print(f"Saved evidence to {path}.")
