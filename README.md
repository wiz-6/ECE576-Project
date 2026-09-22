# Minimal Pygame side-channel lab

A local educational simulation of a **one-byte toy cipher**, not AES/DES or a
secure encryption scheme. Everything stays in memory; restarting assigns new
random secret target keys and clears all measurements.

## Install and run

Requires Python 3.10+ and a desktop display. Pygame is the only external dependency.

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python side_channel_lab.py
```

The window is 1280 x 900. Click a chip or screen tab. Click fields to edit;
Ctrl+A clears a field, Backspace deletes, and Enter finishes editing. Byte fields
accept hexadecimal `00` through `FF` (an optional `0x` prefix is accepted).
Click or drag sliders. Esc or closing the window exits, including during capture.
Captures run in short event-loop batches with progress; experiment controls lock
until completion. Each chip retains separate settings, measurements, and profiles.

## Experiments

- **Observe:** Choose a plaintext, fixed/random mode, and 1–2,000 trials. Capture
  a batch, then switch between its average and individual trials with Previous /
  Next. Random mode draws a fresh independent byte for each trial (repeats are
  possible). Traces stay unchanged until the next capture.
- **Test:** Collect independent fixed and random groups with the same target key.
  Trials specifies the size of **each** group and must be at least two. The plots
  show both group averages and sample-wise Welch t statistics. Edit the positive
  threshold (default 4.5) to change the crossing criterion. Orange horizontal
  lines mark both signs of the threshold. Crossings are evidence of leakage,
  not a security proof or a calibrated family-wise significance test. No detection
  does not establish security. Fixed plaintexts whose intermediate Hamming weight
  is near the random-group mean can produce little first-order mean difference;
  try other plaintexts and more traces.
- **Profile / Recover:** The profiling copy accepts your own key and plaintext.
  Collect labeled batches manually, or Build profile to sweep all 256 plaintexts
  with 2–100 repetitions per value. Measurements accumulate in nine Hamming-weight
  classes. Every class needs at least two samples before recovery. Add target
  batch collects random public plaintexts and accumulates scores for all 256 keys.
  Select power, EM, or combined scoring and inspect the top five guesses. Submit
  a guess for correctness feedback; the target key is never displayed. Changing
  profile measurements clears previous target measurements/scores; editing the
  copy key does not change the target key.

Profiling is available on every chip. More measurements and detectable leakage
are needed for useful recovery; the largest score is not a guarantee of success.

## Model and statistics

`lab_model.py` contains the simulation and statistics independently of Pygame.
Encryption is a fixed nonlinear byte permutation of `plaintext XOR key`; the
permutation is generated once with a fixed seed. Signals have 64 samples, a fixed
background waveform, and independent unit Gaussian noise in each signal/sample.
The intermediate's Hamming weight modulates power samples 18–25 and EM samples
40–47. The neutrally named chips have no displayed preset leakage ratings.
For instructors, their model behaviors are A: no leakage, B: weak leakage,
C: strong power leakage, and D: strong EM leakage.

Profiles learn empirical means and unbiased variances of the **window-average
feature**, grouped by intermediate Hamming weight. A variance floor of `1e-6`
prevents singular Gaussian densities. Recovery uses only public plaintexts,
measured features, and learned fingerprints; it does not use target ciphertexts
or the secret key. Combined scores add the two signal log likelihoods under an
independence assumption. Sparse extreme-Hamming-weight classes can yield poor
variance estimates; collect more profiling repetitions when needed.

Welch statistics use unbiased sample variances and independent group sizes.
Two equal zero-variance groups yield an undefined statistic (plot gap); unequal
constant groups yield signed infinity (edge marker and a crossing). Counts of
both cases are shown explicitly.

## Verification

```sh
python -m unittest -v
```

Seeded checks cover encryption, input validation, averaging, Welch calculations
including zero variance, profile labels/counts, strong-signal detection and key
recovery, and experiment isolation. A calibrated fixture compares weak leakage
at 20 versus 2,000 trials per group, choosing a fixed plaintext with HW=0; this
is a reproducible demonstration, not a guarantee for arbitrary fixed plaintexts.
Headless Pygame checks exercise controls, capture flows, missing-profile messages,
and rendering all three screens. Screenshots are written to `/tmp/lab-*.png`.
