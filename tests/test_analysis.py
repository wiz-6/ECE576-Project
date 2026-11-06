import unittest

import numpy as np

from analysis import collect_ttest, welch_t


class AnalysisTests(unittest.TestCase):
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
        result = collect_ttest(chip, 123, 20, 42)
        fixed, random = map(np.array, chip.groups)
        expected = (fixed.mean(axis=0) - random.mean(axis=0)) / np.sqrt(
            fixed.var(axis=0, ddof=1) / 20 + random.var(axis=0, ddof=1) / 20)
        np.testing.assert_allclose(result, expected)
        self.assertTrue(all(value == 42 for value, _ in chip.inputs[::2]))
        self.assertTrue(all(0 <= value <= 255 for value, _ in chip.inputs[1::2]))
        self.assertTrue(all(key == 123 for _, key in chip.inputs))

    def test_zero_variance(self):
        result = welch_t(np.array([0., 1., -1.]), np.zeros(3), np.zeros(3), np.zeros(3), 2)
        np.testing.assert_array_equal(result, [0, np.inf, -np.inf])

    def test_invalid_parameters(self):
        for count, plaintext in [(1, 0), (50001, 0), (2, -1), (2, 256)]:
            with self.assertRaises(ValueError):
                collect_ttest(None, 0, count, plaintext)


if __name__ == '__main__':
    unittest.main()
