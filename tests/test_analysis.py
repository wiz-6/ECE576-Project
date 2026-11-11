import unittest
from unittest.mock import patch

import numpy as np

from analysis import candidate_profile, build_profile, collect_ttest, merge_profiles, recover_key, welch_t


class AnalysisTests(unittest.TestCase):
    def test_fixed_plaintext_can_hide_leakage_from_mean_comparison(self):
        from chip import FixedChip, LeakyChip, NoiseChip, RandomChip, SBOX

        key = next(byte for byte in range(256) if SBOX[byte].bit_count() == 4)
        alternative = next(byte for byte in range(256) if SBOX[byte ^ key] == 0)
        with patch("chip.rng", np.random.default_rng(20)), patch(
            "analysis.np.random.default_rng",
            side_effect=lambda: np.random.Generator(np.random.PCG64(21)),
        ):
            for model in (FixedChip, NoiseChip, RandomChip, LeakyChip):
                values = collect_ttest(model(73), key, 1000, 1000, 0)
                self.assertLess(np.max(np.abs(values)), 4.5, model.__name__)
            values = collect_ttest(LeakyChip(73), key, 1000, 1000, alternative)
            self.assertGreater(np.max(np.abs(values[73:78])), 4.5)
            self.assertIn(int(np.argmax(np.abs(values))), range(73, 78))

    def test_collection_matches_direct_sample_statistics(self):
        class RecordingChip:
            def __init__(self):
                self.groups = [[], []]
                self.inputs = []

            def get_trace(self, plaintext, key):
                index = len(self.inputs)
                self.inputs.append((plaintext, key))
                trace = np.arange(200, dtype=float) * (index + 1) + plaintext
                self.groups[index % 2].append(trace)
                return trace

        chip = RecordingChip()
        result = collect_ttest(chip, 123, 20, 20, 42)
        fixed, random = map(np.array, chip.groups)
        expected = (fixed.mean(axis=0) - random.mean(axis=0)) / np.sqrt(
            fixed.var(axis=0, ddof=1) / 20 + random.var(axis=0, ddof=1) / 20)
        np.testing.assert_allclose(result, expected)
        self.assertTrue(all(value == 42 for value, _ in chip.inputs[::2]))
        self.assertTrue(all(0 <= value <= 255 for value, _ in chip.inputs[1::2]))
        self.assertTrue(all(key == 123 for _, key in chip.inputs))

    def test_unequal_group_counts_match_direct_welch_formula(self):
        class Recorder:
            def __init__(self):
                self.traces = []
            def get_trace(self, plaintext, key):
                trace = np.arange(200) * .05 + len(self.traces) ** 2 + plaintext
                self.traces.append(trace)
                return trace
        for fixed_count, random_count in ((3, 7), (8, 2)):
            chip = Recorder()
            progress = []
            result = collect_ttest(chip, 0, fixed_count, random_count, 42,
                                   progress=lambda done, total: progress.append((done, total)))
            groups = [[], []]
            index = 0
            for trial in range(max(fixed_count, random_count)):
                for group, count in enumerate((fixed_count, random_count)):
                    if trial < count:
                        groups[group].append(chip.traces[index])
                        index += 1
            fixed, random = map(np.asarray, groups)
            expected = (fixed.mean(0) - random.mean(0)) / np.sqrt(
                fixed.var(0, ddof=1) / fixed_count + random.var(0, ddof=1) / random_count)
            np.testing.assert_allclose(result, expected)
            self.assertEqual(len(chip.traces), fixed_count + random_count)
            self.assertEqual(progress[-1], (fixed_count + random_count,) * 2)
        for fixed_count, random_count in ((1, 20), (20, 1), (50001, 20), (20, 50001)):
            with self.assertRaises(ValueError):
                collect_ttest(None, 0, fixed_count, random_count)

    def test_pooled_class_statistics_match_raw_samples(self):
        def batch(values):
            return {"key": 42, "sample": 73, "counts": [len(values)] + [0] * 8,
                    "means": [float(np.mean(values))] + [None] * 8,
                    "stddev": [float(np.std(values, ddof=1))] + [None] * 8,
                    "monotonic": False}
        first, second = np.arange(20.), np.arange(30.) * 2
        previous, incoming = batch(first), batch(second)
        result = merge_profiles(previous, incoming)
        expected = np.concatenate((first, second))
        self.assertEqual(result['counts'][0], 50)
        self.assertAlmostEqual(result['means'][0], np.mean(expected))
        self.assertAlmostEqual(result['stddev'][0], np.std(expected, ddof=1))
        self.assertEqual(previous['counts'][0], 20)
        self.assertIsNone(result['means'][1])
        self.assertFalse(result['monotonic'])
        incoming['key'] = 43
        with self.assertRaises(ValueError):
            merge_profiles(previous, incoming)

    def test_profile_only_measures_selected_inputs_under_fixed_key(self):
        from chip import SBOX
        class Recorder:
            def __init__(self):
                self.calls = []
                self.groups = [[] for _ in range(9)]
            def get_trace(self, plaintext, key):
                self.calls.append((plaintext, key))
                value = plaintext + len(self.calls) * .01
                self.groups[SBOX[plaintext ^ key].bit_count()].append(value)
                return np.full(200, value)
        recorder = Recorder()
        result = build_profile(recorder, 42, 73, [0, 17, 255], 20)
        self.assertEqual(recorder.calls, [(p, 42) for _ in range(20) for p in (0, 17, 255)])
        self.assertEqual(sum(result['counts']), 60)
        for hw, observations in enumerate(recorder.groups):
            self.assertEqual(result['counts'][hw], len(observations))
            if observations:
                self.assertAlmostEqual(result['means'][hw], np.mean(observations))
                self.assertAlmostEqual(result['stddev'][hw], np.std(observations, ddof=1))
            else:
                self.assertIsNone(result['means'][hw])
        self.assertFalse(result['monotonic'])

    def test_attack_captures_only_selected_inputs_and_retains_real_traces(self):
        class Recorder:
            def __init__(self):
                self.calls = []
            def get_trace(self, plaintext, key):
                self.calls.append((plaintext, key))
                return np.arange(200, dtype=float) + plaintext
        target = Recorder()
        profile = {"sample": 73, "means": list(range(9))}
        result = recover_key(target, 42, profile, 8, plaintexts=[0, 17, 255])
        self.assertEqual(target.calls, [(p, 42) for p in (0, 17, 255, 0, 17, 255, 0, 17)])
        self.assertEqual(len(result['display_traces']), 3)
        for item in result['display_traces']:
            self.assertEqual(item['values'][73], item['observation'])
            self.assertEqual(item['observation'], result['observations'][item['index']])
        with self.assertRaises(ValueError):
            recover_key(target, 42, profile, 2, plaintexts=[0, 1, 2])
        with self.assertRaises(ValueError):
            recover_key(target, 42, profile, 8)

    def test_candidate_overlay_groups_observations_without_secret_key(self):
        from chip import SBOX
        plaintexts = list(range(256))
        observations = [float(SBOX[p ^ 42].bit_count()) for p in plaintexts]
        fit = candidate_profile(plaintexts, observations, 42)
        self.assertEqual(fit['means'], list(range(9)))
        self.assertEqual(sum(fit['counts']), 256)
        incomplete = candidate_profile([0], [2.5], 42)
        self.assertEqual(sum(value is not None for value in incomplete['means']), 1)
        self.assertEqual(incomplete['means'][SBOX[42].bit_count()], 2.5)

    def test_zero_variance(self):
        result = welch_t(np.array([0., 1., -1.]), np.zeros(3), np.zeros(3), np.zeros(3), 2, 2)
        np.testing.assert_array_equal(result, [0, np.inf, -np.inf])

    def test_invalid_parameters(self):
        for count, plaintext in [(1, 0), (50001, 0), (2, -1), (2, 256)]:
            with self.assertRaises(ValueError):
                collect_ttest(None, 0, count, count, plaintext)


if __name__ == '__main__':
    unittest.main()
