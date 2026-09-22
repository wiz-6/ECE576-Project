"""Pure-Python toy cipher, synthetic acquisition, and measured-profile inference."""
from dataclasses import dataclass, field
import math
import random
import statistics

# A fixed nonlinear permutation (a seeded shuffle), NOT AES or a secure cipher.
_order = list(range(256))
random.Random(576).shuffle(_order)
SBOX = tuple(_order)
SAMPLES = 64
WINDOWS = {'power': range(18, 26), 'em': range(40, 48)}


def byte(text):
    try:
        value = int(text, 16)
    except ValueError:
        raise ValueError('Enter a hexadecimal byte (00-FF).') from None
    if not 0 <= value <= 255:
        raise ValueError('Enter a hexadecimal byte (00-FF).')
    return value


def encrypt(plaintext, key):
    if not 0 <= plaintext < 256 or not 0 <= key < 256:
        raise ValueError('Plaintext and key must be bytes.')
    return SBOX[plaintext ^ key]


@dataclass(frozen=True)
class Chip:
    name: str
    power_gain: float
    em_gain: float


CHIPS = (Chip('Chip A', 0, 0), Chip('Chip B', .13, .10),
         Chip('Chip C', 1.0, .12), Chip('Chip D', .12, 1.0))


@dataclass(frozen=True)
class Trace:
    plaintext: int
    ciphertext: int
    power: tuple
    em: tuple


def capture(chip, key, plaintext, rng):
    intermediate = encrypt(plaintext, key)
    hw = intermediate.bit_count()
    signals = []
    for name, gain in [('power', chip.power_gain), ('em', chip.em_gain)]:
        signals.append(tuple(.3 * math.sin(i / 5) +
                             (gain * hw if i in WINDOWS[name] else 0) +
                             rng.gauss(0, 1) for i in range(SAMPLES)))
    return Trace(plaintext, intermediate, *signals)


def average(traces, signal):
    if not traces:
        return ()
    return tuple(statistics.fmean(getattr(t, signal)[i] for t in traces)
                 for i in range(SAMPLES))


def welch(fixed, random_group, signal):
    """None: equal constant groups (0/0); signed infinity: unequal constants."""
    if min(len(fixed), len(random_group)) < 2:
        raise ValueError('Welch testing requires at least two trials per group.')
    result = []
    for i in range(SAMPLES):
        a = [getattr(t, signal)[i] for t in fixed]
        b = [getattr(t, signal)[i] for t in random_group]
        delta = statistics.fmean(a) - statistics.fmean(b)
        se2 = statistics.variance(a) / len(a) + statistics.variance(b) / len(b)
        result.append(delta / math.sqrt(se2) if se2 else
                      (math.copysign(math.inf, delta) if delta else None))
    return tuple(result)


def feature(trace, signal):
    return statistics.fmean(getattr(trace, signal)[i] for i in WINDOWS[signal])


class Profile:
    def __init__(self):
        self.values = {s: [[] for _ in range(9)] for s in WINDOWS}
        self.version = 0

    def add(self, trace, copy_key):
        label = encrypt(trace.plaintext, copy_key).bit_count()
        for s in WINDOWS:
            self.values[s][label].append(feature(trace, s))
        self.version += 1

    @property
    def counts(self):
        return [len(v) for v in self.values['power']]

    @property
    def ready(self):
        return min(self.counts) >= 2

    def fingerprints(self):
        if not self.ready:
            raise ValueError('Build a profile with at least two measurements in every class.')
        # Explicit floor prevents singular Gaussian densities for constant samples.
        return {s: [(statistics.fmean(v), max(statistics.variance(v), 1e-6))
                    for v in classes] for s, classes in self.values.items()}


def score_trace(trace, fingerprints):
    """Uses public plaintext and measured features only, never ciphertext or target key."""
    observed = {s: feature(trace, s) for s in WINDOWS}
    result = {s: [] for s in WINDOWS}
    for key in range(256):
        label = encrypt(trace.plaintext, key).bit_count()
        for s in WINDOWS:
            mean, variance = fingerprints[s][label]
            result[s].append(-.5 * (math.log(2 * math.pi * variance) +
                                   (observed[s] - mean) ** 2 / variance))
    return result


def ranking(scores, mode='combined'):
    signals = WINDOWS if mode == 'combined' else [mode]
    return sorted(((k, sum(scores[s][k] for s in signals)) for k in range(256)),
                  key=lambda item: item[1], reverse=True)


@dataclass
class Experiment:
    chip: Chip
    _key: int = field(repr=False)
    observed: list = field(default_factory=list)
    fixed: list = field(default_factory=list)
    random_group: list = field(default_factory=list)
    profile: Profile = field(default_factory=Profile)
    target: list = field(default_factory=list)
    scores: dict = field(default_factory=lambda: {s: [0.] * 256 for s in WINDOWS})
    settings: dict = field(default_factory=lambda: dict(plaintext='00', copy_key='00',
                         copy_plaintext='00', guess='00', threshold='4.5', trials=100,
                         repetitions=4, random=False, mode='combined', individual=False, index=0))
    message: str = 'Ready.'

    def measure(self, plaintext, rng):
        return capture(self.chip, self._key, plaintext, rng)

    def check_guess(self, guess):
        return guess == self._key

    def clear_recovery(self):
        self.target.clear()
        self.scores = {s: [0.] * 256 for s in WINDOWS}

    def add_target(self, trace, fingerprints):
        delta = score_trace(trace, fingerprints)
        for s in WINDOWS:
            self.scores[s] = [a + b for a, b in zip(self.scores[s], delta[s])]
        self.target.append(trace)


def experiments(rng):
    return [Experiment(chip, rng.randrange(256)) for chip in CHIPS]
