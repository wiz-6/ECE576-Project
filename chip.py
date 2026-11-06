'''
Class for the chip object. This class is used to represent virtual running AES-128.
    It can be Leaky, Random, Noise, or Fixed.

    Basic
'''

import numpy as np
rng = np.random.default_rng(123)

from abc import ABC, abstractmethod

baseline_samples = np.arange(200)
baseline_trace = np.sin(2 * np.pi * baseline_samples / 50)

# Standard AES S-box, indexed by plaintext XOR key.
SBOX = bytes.fromhex(
    "637c777bf26b6fc53001672bfed7ab76"
    "ca82c97dfa5947f0add4a2af9ca472c0"
    "b7fd9326363ff7cc34a5e5f171d83115"
    "04c723c31896059a071280e2eb27b275"
    "09832c1a1b6e5aa0523bd6b329e32f84"
    "53d100ed20fcb15b6acbbe394a4c58cf"
    "d0efaafb434d338545f9027f503c9fa8"
    "51a3408f929d38f5bcb6da2110fff3d2"
    "cd0c13ec5f974417c4a77e3d645d1973"
    "60814fdc222a908846eeb814de5e0bdb"
    "e0323a0a4906245cc2d3ac629195e479"
    "e7c8376d8dd54ea96c56f4ea657aae08"
    "ba78252e1ca6b4c6e8dd741f4bbd8b8a"
    "703eb5664803f60e613557b986c11d9e"
    "e1f8981169d98e949b1e87e9ce5528df"
    "8ca1890dbfe6426841992d0fb054bb16"
)

def init_chip(classification, leak_index=None):
    if classification == "fixed":
        return FixedChip(leak_index)
    elif classification == "noise":
        return NoiseChip(leak_index)
    elif classification == "random":
        return RandomChip(leak_index)
    elif classification == "leaky":
        return LeakyChip(leak_index)
    else:
        raise ValueError(f"Unknown chip classification: {classification}")

class Chip(ABC):
    def __init__(self, leak_index=None):
        # Keep the five-sample window in bounds and fixed across captures.
        if leak_index is None:
            leak_index = int(rng.integers(0, len(baseline_trace) - 4))
        if not isinstance(leak_index, (int, np.integer)) or not 0 <= leak_index <= 195:
            raise ValueError("leak_index must be an integer from 0 through 195")
        self.leak_index = leak_index

    def _base_trace(self):
        # Fresh measurement noise for every capture, including fixed-pattern chips.
        return baseline_trace + rng.normal(0, 1.0, size=200)

    @abstractmethod
    def get_trace(self, plaintext, key):
        pass

class FixedChip(Chip):
    def get_trace(self, plaintext, key):
        trace = self._base_trace()
        trace[30:35] += 4
        trace[90:95] += 6
        trace[150:155] += 3
        return trace

class NoiseChip(Chip):
    def get_trace(self, plaintext, key):
        return self._base_trace()

class RandomChip(Chip):
    def get_trace(self, plaintext, key):
        trace = self._base_trace()
        # A fresh mask makes the leaked byte independent of plaintext and key.
        value = SBOX[int(plaintext) ^ (int(key) & 0xff)] ^ int(rng.integers(0, 256))
        trace[self.leak_index:self.leak_index + 5] += 0.8 * value.bit_count()
        return trace

class LeakyChip(Chip):
    def get_trace(self, plaintext, key):
        trace = self._base_trace()
        # Only the lowest key byte is modeled; full AES is unnecessary here.
        value = SBOX[int(plaintext) ^ (int(key) & 0xff)]
        trace[self.leak_index:self.leak_index + 5] += 0.8 * value.bit_count()
        return trace
