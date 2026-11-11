import contextlib
import io
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

import numpy as np

import chip
from analysis import CaptureCancelled, build_profile, collect_ttest, rank_keys, recover_key
from session import Game
from help import command_name


class FakeTerminal:
    """Run work immediately so game state transitions are independently testable."""
    def __init__(self):
        self.analysis_future = None
        self.history = []
        self.history_index = 0
        self.charts = {}
        self.plot = None
        self.analysis = None

    def reset_views(self):
        self.charts.clear()
        self.analysis = self.plot = None

    def set_traces(self, traces, plaintext):
        self.traces = traces
        self.analysis = self.plot = None

    def start_job(self, title, work, complete):
        complete(work(threading.Event(), lambda done, total: None))

    def show_chart(self, name, chart):
        self.charts[name] = self.plot = chart
        self.analysis = None

    def cancel_job(self):
        pass


class GameTests(unittest.TestCase):
    def setUp(self):
        self.old_rng = chip.rng
        chip.rng = np.random.default_rng(100)
        generator = np.random.default_rng(200)
        self.patch = patch('analysis.np.random.default_rng', return_value=generator)
        self.patch.start()
        self.terminal = FakeTerminal()
        self.game = Game(self.terminal)
        self.send('student')

    def tearDown(self):
        self.patch.stop()
        chip.rng = self.old_rng

    def send(self, command):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.game.submit(command)
        return output.getvalue()

    def profile_capture(self, key, count, weight=None):
        self.send(f'profile-key {key}')
        classes = range(9) if weight is None else [weight]
        inputs = [next(p for p in range(256) if chip.SBOX[p ^ key].bit_count() == hw) for hw in classes]
        self.send('profile-inputs ' + ','.join(map(str, inputs)))
        self.send(f'profile-trials {count}')
        output = self.send('build-profile')
        if self.game.profile and self.game.profile['monotonic']:
            output += self.send('submit-profile')
        if self.game.stage == 2:
            self.send('attack-inputs 0-31')
        return output

    def identify(self):
        number = next(i for i, c in enumerate(self.game.chips, 1) if isinstance(c, chip.LeakyChip))
        # This fixture selects a fixed byte with strong separation, not a game shortcut.
        key = self.game.secret_key & 255
        plaintext = next(p for p in range(256) if chip.SBOX[p ^ key] == 0)
        self.send("t-threshold 4.5")
        self.send("fixed-trials 1000")
        self.send("random-trials 1000")
        self.send(f'run-ttest {number} {plaintext}')
        self.assertIn('You win Stage 1', self.send(f"guess {number} {self.game.tests[number]['peak_sample']}"))
        self.assertEqual(self.game.sample, self.game.tests[number]["peak_sample"])
        return number

    def test_complete_workshop_and_report(self):
        number = self.identify()
        self.assertEqual(self.game.stage, 1)
        self.assertIn(self.game.sample, range(self.game.chips[number - 1].leak_index,
                                            self.game.chips[number - 1].leak_index + 5))
        self.assertIn('Stage 2 complete', self.profile_capture(0x2b, 300))
        self.assertEqual(self.game.stage, 2)
        self.assertEqual(len(self.game.profile['means']), 9)
        self.send('attack-inputs 0')
        self.send('attack 1')
        scores = self.game.attack['scores']
        self.assertGreater(sum(np.isclose(score, min(scores)) for score in scores), 1)
        self.send('attack-inputs 0-31')
        self.send('attack 300')
        self.assertEqual(self.game.attack['profile'], self.game.profile)
        self.assertIsNot(self.game.attack['profile'], self.game.profile)
        best = self.game.attack['ranking'][0]
        self.assertEqual(best, self.game.secret_key & 255)
        self.assertIn('not the secret', self.send(f'keyguess {(best + 1) % 256}'))
        self.assertEqual(self.game.stage, 2)
        self.assertIn('All three stages complete', self.send(f'keyguess 0x{best:02x}'))
        self.assertEqual(self.game.stage, 3)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'evidence.json'
            self.send(f'report "{path}"')
            data = json.loads(path.read_text())
            self.assertTrue(data['completed'])
            self.assertEqual(len(data['attack_history']), 2)
            self.assertNotIn('secret_key', data)
            self.assertNotIn('chips', data)
            before = path.read_text()
            self.assertIn('already exists', self.send(f'report "{path}"'))
            self.assertEqual(path.read_text(), before)
        self.send('view profile')
        self.assertEqual(self.terminal.plot, self.terminal.charts['profile'])
        self.send('restart')
        self.assertEqual(self.game.stage, 0)
        self.assertIsNone(self.game.profile)
        self.assertFalse(self.game.tests)
        self.assertFalse(self.terminal.charts)
        self.assertFalse(self.game.attack_history)

    def test_gating_and_invalid_commands(self):
        for command in ('profile 0', 'sample 0', 'attack', 'keyguess 0'):
            self.send(command)
            self.assertEqual(self.game.stage, 0)
        for command in ('guess', 'guess 0', 'guess 5', 'guess no', 'guess 1 2',
                        'ttest 1 1', 'ttest 1 20 256', 'trace -1', 'trace no', 'view profile', '"'):
            self.assertNotIn('You win', self.send(command))
            self.assertEqual(self.game.stage, 0)
        wrong = next(i for i, c in enumerate(self.game.chips, 1) if not isinstance(c, chip.LeakyChip))
        self.assertIn('No completed t-test', self.send(f'guess {wrong} 0'))
        self.send('t-threshold 4.5')
        self.send('fixed-trials 2')
        self.send('random-trials 2')
        self.send(f'run-ttest {wrong}')
        self.assertIn('Try again', self.send(f'guess {wrong} 0'))
        self.assertIsNone(self.game.selected)
        self.identify()
        self.send('profile 256')
        self.assertIsNone(self.game.profile)
        self.send('profile 0 1')
        self.assertIsNone(self.game.profile)
        previous_sample = self.game.sample
        self.assertIn('Unknown command', self.send('select-sample 199'))
        self.assertEqual(self.game.sample, previous_sample)

    def test_busy_commands_and_latest_test_view(self):
        self.terminal.analysis_future = object()
        self.assertIn('experiment is running', self.send('restart'))
        self.assertIn('Stage 1', self.send('status'))
        self.terminal.analysis_future = None
        self.send("t-threshold 4.5")
        self.send("fixed-trials 1000")
        self.send("random-trials 1000")
        for number in (1, 2, 1):
            self.send('fixed-trials 2')
            self.send('random-trials 2')
            self.send(f'run-ttest {number}')
        self.send('view ttest')
        self.assertEqual(self.terminal.analysis[0], 1)
        self.send('view ttest 2')
        self.assertEqual(self.terminal.analysis[0], 2)

    def test_incremental_profile_and_reset(self):
        self.identify()
        self.assertEqual(self.terminal.plot['counts'], [0] * 9)
        self.send('profile')
        self.assertIsNone(self.game.profile)
        self.profile_capture(0x2b, 300, 3)
        self.assertEqual(self.game.profile['counts'][3], 300)
        self.assertEqual(sum(n > 0 for n in self.game.profile['counts']), 1)
        self.assertIsNone(self.game.profile['means'][4])
        self.assertEqual(self.game.stage, 1)
        self.send('attack 10')
        self.assertIsNone(self.game.attack)
        before = self.game.profile['means'][3]
        self.profile_capture(0x2b, 300, 3)
        self.assertEqual(self.game.profile['counts'][3], 600)
        self.assertLess(abs(self.game.profile['means'][3] - before), .5)
        for command in ('profile 0x2b 20 9', 'profile 0x2b 20 -1', 'profile 0x2b 20 nope',
                        'profile 0 300 4'):
            self.send(command)
            self.assertEqual(self.game.profile['counts'][3], 600)
            self.assertIsNone(self.game.profile['means'][4])
        for hw in (0, 1, 2, 4, 5, 6, 7, 8):
            self.profile_capture(0x2b, 300, hw)
        self.assertTrue(self.game.profile['monotonic'])
        self.assertEqual(self.game.stage, 2)
        self.assertEqual(self.terminal.charts['profile']['counts'], [300, 300, 300, 600, 300, 300, 300, 300, 300])
        self.send('attack 100')
        profile, attack = self.game.profile, self.game.attack
        for command in ('profile clear', 'profile-key 0', 'run-ttest 1', 'trace'):
            self.assertIn('unavailable in the current stage', self.send(command))
            self.assertEqual(self.game.stage, 2)
            self.assertIs(self.game.profile, profile)
            self.assertIs(self.game.attack, attack)
        self.send('restart-game')
        self.identify()
        self.profile_capture(0, 100, 0)
        self.send('profile clear')
        self.assertIsNone(self.game.profile)
        self.assertIsNone(self.game.attack)
        self.assertEqual(self.terminal.plot['values'], [None] * 9)
        self.profile_capture(0, 100, 0)
        self.send('profile clear')
        self.assertIsNone(self.game.profile)
        self.assertEqual(self.terminal.plot['counts'], [0] * 9)

    def test_profile_requires_explicit_key_sample_and_plaintexts(self):
        self.identify()
        self.send('build-profile')
        self.assertIsNone(self.game.profile)
        self.send('profile-key 42')
        self.send('build-profile')
        self.assertIsNone(self.game.profile)
        for invalid in ('-1', '256', '20-10', '0-256', '0,,1', 'no'):
            self.send('profile-inputs ' + invalid)
            self.assertIsNone(self.game.profile_inputs)
        self.send('profile-inputs 0-2 2,17,255')
        self.assertEqual(self.game.profile_inputs, [0, 1, 2, 17, 255])
        self.send('profile-trials 20')
        self.send('build-profile')
        self.assertEqual(sum(self.game.profile['counts']), 100)
        self.assertEqual(self.game.profile['key'], 42)
        self.assertEqual(self.game.profile['plaintexts'], [0, 1, 2, 17, 255])
        self.assertEqual(self.game.assessment_result['chip'], self.game.selected)
        self.send('profile-inputs 3')
        self.assertEqual(sum(self.game.profile['counts']), 100)
        self.send('build-profile')
        self.assertEqual(sum(self.game.profile['counts']), 120)
        self.send('profile-key 43')
        self.assertIsNone(self.game.profile)
        self.assertIsNone(self.game.attack)
        self.send('restart-game')
        self.assertIsNone(self.game.profile_key)
        self.assertIsNone(self.game.profile_inputs)

    def test_experiment_settings_are_required_and_saved_per_test(self):
        self.assertIsNone(self.game.threshold)
        self.assertIn('No t threshold defined', self.send('run-ttest 1'))
        for value in ('', '0', '-1', 'nan', 'inf', '-inf', 'no', '2 3'):
            self.send(f't-threshold {value}')
            self.assertIsNone(self.game.threshold)
        self.send('t-threshold 3.25')
        self.assertIn('counts must both be defined', self.send('run-ttest 1'))
        self.send('fixed-trials 20')
        self.assertIn('counts must both be defined', self.send('run-ttest 1'))
        self.assertFalse(self.game.tests)
        for command in ('random-trials 1', 'random-trials 50001', 'random-trials 2.5',
                        'random-trials nope', 'random-trials', 'random-trials 2 3'):
            self.send(command)
            self.assertIsNone(self.game.random_trials)
        self.send('random-trials 35')
        self.send('run-ttest 1')
        first = self.game.tests[1]
        self.assertEqual((first['fixed_count'], first['random_count']), (20, 35))
        self.assertEqual(first['threshold'], 3.25)
        self.assertEqual(first['crossings'], sum(abs(v) > 3.25 for v in first['values']))
        self.send('t-threshold 7')
        self.send('fixed-trials 10')
        self.send('run-ttest 2')
        self.assertEqual(self.game.tests[2]['threshold'], 7)
        self.send('view-chart ttest 1')
        self.assertEqual(self.terminal.analysis[1:3], (20, 35))
        self.assertEqual(self.terminal.analysis[5], 3.25)
        self.send('restart-game')
        self.assertIsNone(self.game.threshold)
        self.assertIsNone(self.game.fixed_trials)
        self.assertIsNone(self.game.random_trials)
        self.assertIn('No t threshold defined', self.send('run-ttest 1'))

    def test_guidance_is_only_in_help(self):
        startup = self.send('restart')
        self.assertNotIn('Compare chips', startup)
        status = self.send('status')
        self.assertNotIn('then', status)
        self.assertNotIn('Use ', status)
        self.assertIn('Unknown command', self.send('hint'))
        self.assertIn('fixed-versus-random', self.send('help assessment'))
        self.assertIn('another stage', self.send('help profiling'))
        self.assertIn('another stage', self.send('help recovery'))
        self.identify()
        self.assertIn('t-chart', self.send('help profiling'))
        self.assertNotIn('attack 200', self.profile_capture(0, 300))
        output = self.send('attack 10')
        self.assertNotIn('Submit your answer', output)
        self.assertNotIn('More traces', output)

    def test_progression_requires_a_test_of_the_guessed_leaky_chip(self):
        leaky = next(i for i, c in enumerate(self.game.chips, 1) if isinstance(c, chip.LeakyChip))
        other = next(i for i in range(1, 5) if i != leaky)
        self.assertIn('No completed t-test', self.send(f'guess-chip {leaky} {self.game.chips[leaky - 1].leak_index}'))
        self.assertEqual(self.game.stage, 0)
        self.assertIsNone(self.game.selected)
        self.assertFalse(self.game.guesses)
        self.send('t-threshold 4.5')
        self.send('fixed-trials 20')
        self.send('random-trials 30')
        self.send(f'run-ttest {other}')
        self.assertIn('No completed t-test', self.send(f'guess-chip {leaky} {self.game.chips[leaky - 1].leak_index}'))
        self.assertEqual(self.game.stage, 0)
        self.send(f'run-ttest {leaky}')
        # The latest chart can be for a different chip; the matched evidence must be used.
        self.send(f'run-ttest {other}')
        self.send(f'guess-chip {leaky} {self.game.chips[leaky - 1].leak_index}')
        self.assertEqual(self.game.stage, 1)
        self.assertEqual(self.game.assessment_result['chip'], leaky)
        self.assertEqual(self.game.assessment_result['chip'], leaky)
        self.send('view-chart ttest')
        self.assertEqual(self.terminal.analysis[0], leaky)
        self.send('restart-game')
        self.assertIsNone(self.game.assessment_result)
        self.assertIn('No completed t-test', self.send(f'guess-chip {leaky} {self.game.chips[leaky - 1].leak_index}'))

    def test_chip_guess_requires_a_valid_leak_sample(self):
        number = next(i for i, c in enumerate(self.game.chips, 1) if isinstance(c, chip.LeakyChip))
        self.send('t-threshold 4.5')
        self.send('fixed-trials 20')
        self.send('random-trials 20')
        for start in (0, 195):
            self.game.stage = 0
            self.game.chips[number - 1] = chip.LeakyChip(start)
            self.game.selected = self.game.sample = None
            self.send(f'run-ttest {number}')
            for args in (str(number), f'{number} -1', f'{number} 200', f'{number} no', f'{number} 0 extra'):
                self.send('guess-chip ' + args)
                self.assertEqual(self.game.stage, 0)
                self.assertIsNone(self.game.sample)
            wrong = 199 if start == 0 else 0
            self.assertIn('incorrect', self.send(f'guess-chip {number} {wrong}'))
            self.assertEqual(self.game.stage, 0)
            self.assertIsNone(self.game.selected)
            self.assertIsNone(self.game.sample)
            for sample in (start, start + 4):
                self.game.stage = 0
                self.send(f'guess-chip {number} {sample}')
                self.assertEqual(self.game.stage, 1)
                self.assertEqual(self.game.sample, sample)
                self.assertEqual(self.terminal.plot['sample'], sample)
                self.assertNotIn('reference', self.terminal.plot)
                self.assertEqual(self.game.guesses[-1]['sample'], sample)

    def test_profile_requires_explicit_submission(self):
        self.identify()
        self.assertIn('submission rejected', self.send('submit-profile'))
        self.assertEqual(self.game.stage, 1)
        self.send('profile-key 0')
        inputs = [next(p for p in range(256) if chip.SBOX[p].bit_count() == hw) for hw in range(9)]
        self.send('profile-inputs ' + ','.join(map(str, inputs)))
        self.send('profile-trials 300')
        output = self.send('build-profile')
        self.assertTrue(self.game.profile['monotonic'])
        self.assertEqual(self.game.stage, 1)
        self.assertFalse(self.game.profile_submitted)
        self.assertEqual(self.terminal.plot['kind'], 'profile')
        self.assertTrue(self.terminal.plot['ready'])
        self.assertFalse(self.terminal.plot['accepted'])
        self.assertNotIn('complete', output)
        self.assertIn('unavailable', self.send('run-attack'))
        self.send('submit-profile extra')
        self.assertEqual(self.game.stage, 1)
        self.assertIn('Stage 2 complete', self.send('submit-profile'))
        self.assertTrue(self.game.profile_submitted)
        self.assertEqual(self.game.stage, 2)
        self.assertEqual(self.game.stages[self.game.stage], '3 / KEY RECOVERY')
        self.send('restart-game')
        self.assertFalse(self.game.profile_submitted)
        self.assertIn('Stage 1 /', self.send('game-status'))

    def test_recovery_inputs_and_comparison_screen(self):
        self.identify()
        self.profile_capture(0, 300)
        self.assertEqual(self.terminal.plot['kind'], 'recovery')
        self.assertIsNone(self.terminal.plot['result'])
        self.game.attack_inputs = None
        self.assertIn('No target plaintexts', self.send('run-attack 20'))
        for value in ('-1', '256', '10-0', 'no', '0,,1'):
            self.send('attack-inputs ' + value)
            self.assertIsNone(self.game.attack_inputs)
        self.send('attack-inputs 0,17,255')
        self.send('run-attack 2')
        self.assertIsNone(self.game.attack)
        self.send('run-attack 20')
        result = self.game.attack
        self.assertEqual(set(result['plaintexts']), {0, 17, 255})
        self.assertEqual(self.terminal.plot['kind'], 'recovery')
        self.assertEqual(self.terminal.plot['fit'], result['candidate_fit'])
        self.send('compare-key 0x2b')
        self.assertEqual(self.terminal.plot['fit']['candidate'], 43)
        self.send('inspect-trace 2')
        self.assertEqual(self.terminal.plot['index'], 1)
        self.assertEqual(self.terminal.plot['candidate'], 43)
        self.send('inspect-trace 4')
        self.assertEqual(self.terminal.plot['index'], 1)
        self.send('attack-inputs 99')
        self.assertIs(self.game.attack, result)
        self.assertEqual(set(result['plaintexts']), {0, 17, 255})
        self.send('view-chart attack')
        self.assertEqual(self.terminal.plot['result'], result)

    def test_stage_command_matrix_including_aliases(self):
        from help import STAGE_COMMANDS, COMMAND_NAMES
        commands = set().union(*STAGE_COMMANDS)
        for stage in range(4):
            self.game.stage = stage
            for command in commands - STAGE_COMMANDS[stage]:
                for name in {command, COMMAND_NAMES.get(command, command)}:
                    self.assertIn('unavailable in the current stage', self.send(name))
                    self.assertEqual(self.game.stage, stage)
                    self.assertIsNone(self.game.profile)
                    self.assertFalse(self.game.tests)
        self.game.stage = 0
        for command in ('game-status extra', 'cancel-capture extra', 'exit extra', 'help a b'):
            self.assertIn('Usage:', self.send(command))

    def test_help_is_scoped_to_stage(self):
        for stage, expected, hidden in (
            (0, ('run-ttest', 'guess-chip', 'fixed-trials'), ('build-profile', 'run-attack', 'guess-key')),
            (1, ('profile-key', 'build-profile'), ('run-ttest', 'run-attack', 'guess-chip')),
            (2, ('run-attack', 'guess-key'), ('build-profile', 'fixed-trials', 'guess-chip')),
            (3, (), ('build-profile', 'run-attack', 'run-ttest')),
        ):
            self.game.stage = stage
            output = self.send('help')
            for name in expected:
                self.assertIn(command_name(name).split()[0], output)
            for name in hidden:
                self.assertNotIn(command_name(name), output)
            for name in ('game-status', 'view-chart', 'export-report', 'exit'):
                self.assertIn(command_name(name).split()[0], output)
            self.assertEqual(self.terminal.stage_index, stage)
        self.game.stage = 2
        self.assertIn('Lower mean squared distance', self.send('help recovery'))

    def test_stage_goals_and_descriptive_names(self):
        from help import STAGE_GOALS, STAGE_COMMANDS, COMMAND_NAMES
        for stage in range(4):
            self.game.stage = stage
            self.assertIn(STAGE_GOALS[stage], self.send('show-stage-goal'))
            self.assertNotIn('Goal:', self.send('help'))
            self.assertGreater(len(STAGE_GOALS[stage].split()), 30)
            for internal in STAGE_COMMANDS[stage]:
                public = COMMAND_NAMES.get(internal, internal)
                self.assertIn(public.split()[0], self.send('help'))
                self.assertNotIn('No help available', self.send('help ' + public))
        self.game.stage = 0
        self.send('set num-fixed-traces 20')
        self.send('set num-random-traces 30')
        self.send('set t-threshold 3.5')
        self.send('run-ttest 1')
        self.assertEqual(self.game.tests[1]['fixed_count'], 20)
        self.assertEqual(self.game.tests[1]['random_count'], 30)
        self.assertEqual(self.game.tests[1]['threshold'], 3.5)

    def test_cancellation_and_distance_math(self):
        cancel = threading.Event()
        cancel.set()
        target = chip.LeakyChip(30)
        profile = {'sample': 30, 'means': list(range(9))}
        for operation in (lambda: collect_ttest(target, 0, 20, 30, cancel=cancel),
                          lambda: build_profile(target, 0, 30, [0], cancel=cancel),
                          lambda: recover_key(target, 0, profile, cancel=cancel, plaintexts=[0])):
            with self.assertRaises(CaptureCancelled):
                operation()
        means = np.arange(9) * 0.8
        plaintexts = np.arange(256)
        values = [means[chip.SBOX[int(p) ^ 77].bit_count()] for p in plaintexts]
        scores = rank_keys(plaintexts, values, means)
        self.assertEqual(np.argmin(scores), 77)
        self.assertEqual(scores[77], 0)
        for key in (0, 77, 255):
            expected = np.mean([(v - means[chip.SBOX[int(p) ^ key].bit_count()]) ** 2
                                for p, v in zip(plaintexts, values)])
            self.assertAlmostEqual(scores[key], expected)


if __name__ == '__main__':
    unittest.main()
