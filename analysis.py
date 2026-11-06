"""Fixed-versus-random first-order TVLA for a single simulated chip."""
import numpy as np


def welch_t(fixed_mean, fixed_variance, random_mean, random_variance, count):
    """Welch statistic using unbiased sample variances and equal group sizes."""
    difference = fixed_mean - random_mean
    standard_error = np.sqrt((fixed_variance + random_variance) / count)
    result = np.zeros_like(difference, dtype=float)
    np.divide(difference, standard_error, out=result, where=standard_error > 0)
    result[(standard_error == 0) & (difference != 0)] = np.sign(
        difference[(standard_error == 0) & (difference != 0)]) * np.inf
    return result


def collect_ttest(chip, key, count=1000, plaintext=0):
    """Collect interleaved groups with online statistics, without retaining all traces."""
    if not 2 <= count <= 50000 or not 0 <= plaintext <= 255:
        raise ValueError("Use 2-50000 traces per group and a plaintext byte from 0 to 255")
    rng = np.random.default_rng()
    means = np.zeros((2, 200))
    m2 = np.zeros_like(means)
    for trial in range(1, count + 1):
        for group, value in enumerate((plaintext, int(rng.integers(0, 256)))):
            trace = chip.get_trace(value, key)
            delta = trace - means[group]
            means[group] += delta / trial
            m2[group] += delta * (trace - means[group])
    variances = m2 / (count - 1)
    return welch_t(means[0], variances[0], means[1], variances[1], count)
