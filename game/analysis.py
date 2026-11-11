"""Fixed-versus-random first-order TVLA for a single simulated chip."""
import numpy as np


def welch_t(fixed_mean, fixed_variance, random_mean, random_variance, fixed_count, random_count):
    """Welch statistic using unbiased sample variances and independent group sizes."""
    difference = fixed_mean - random_mean
    standard_error = np.sqrt(fixed_variance / fixed_count + random_variance / random_count)
    result = np.zeros_like(difference, dtype=float)
    np.divide(difference, standard_error, out=result, where=standard_error > 0)
    result[(standard_error == 0) & (difference != 0)] = np.sign(
        difference[(standard_error == 0) & (difference != 0)]) * np.inf
    return result


def collect_ttest(chip, key, fixed_count, random_count, plaintext=0, cancel=None, progress=None):
    """Interleave acquisitions while both groups have remaining trials."""
    if not (2 <= fixed_count <= 50000 and 2 <= random_count <= 50000 and 0 <= plaintext <= 255):
        raise ValueError("Use 2-50000 trials in each group and a plaintext byte from 0 to 255")
    rng = np.random.default_rng()
    means = np.zeros((2, 200))
    m2 = np.zeros_like(means)
    counts = (fixed_count, random_count)
    total = sum(counts)
    done = 0
    for trial in range(1, max(counts) + 1):
        for group, count in enumerate(counts):
            if trial > count:
                continue
            checkpoint(cancel, progress, done, total)
            value = plaintext if group == 0 else int(rng.integers(0, 256))
            trace = chip.get_trace(value, key)
            delta = trace - means[group]
            means[group] += delta / trial
            m2[group] += delta * (trace - means[group])
            done += 1
    checkpoint(cancel, progress, done, total)
    variances = m2 / (np.asarray(counts)[:, None] - 1)
    return welch_t(means[0], variances[0], means[1], variances[1], *counts)


class CaptureCancelled(Exception):
    """A capture was stopped without changing the session's results."""


def checkpoint(cancel, progress, done, total):
    if cancel is not None and cancel.is_set():
        raise CaptureCancelled("Capture cancelled; previous results kept.")
    if progress is not None and (done % 25 == 0 or done == total):
        progress(done, total)


def build_profile(chip, key, sample, plaintexts, count=20, cancel=None, progress=None):
    """Keep the chosen key fixed and measure only the student's selected plaintexts."""
    from chip import SBOX
    if not (0 <= key <= 255 and 0 <= sample < 200 and 2 <= count <= 5000):
        raise ValueError("Profile needs a byte key, sample 0-199, and 2-5000 trials/input")
    if not plaintexts or any(not isinstance(p, int) or not 0 <= p <= 255 for p in plaintexts):
        raise ValueError("Select plaintext bytes from 0 through 255")
    means, m2 = np.zeros(9), np.zeros(9)
    counts = np.zeros(9, dtype=int)
    total = len(plaintexts) * count
    done = 0
    for trial in range(count):
        for plaintext in plaintexts:
            checkpoint(cancel, progress, done, total)
            hw = SBOX[plaintext ^ key].bit_count()
            value = float(chip.get_trace(plaintext, key)[sample])
            counts[hw] += 1
            delta = value - means[hw]
            means[hw] += delta / counts[hw]
            m2[hw] += delta * (value - means[hw])
            done += 1
    checkpoint(cancel, progress, done, total)
    return {"key": key, "sample": sample, "plaintexts": list(plaintexts), "trials_per_input": count,
            "batches": [{"plaintexts": list(plaintexts), "trials_per_input": count}],
            "counts": counts.tolist(),
            "means": [float(means[hw]) if counts[hw] else None for hw in range(9)],
            "stddev": [float(np.sqrt(m2[hw] / (counts[hw] - 1))) if counts[hw] > 1 else None for hw in range(9)],
            "monotonic": bool(np.all(counts >= 20)) and bool(np.all(np.diff(means) > 0))}


def merge_profiles(previous, incoming):
    """Pool measured class statistics without retaining all profiling traces."""
    if previous is None:
        return incoming
    if (previous["key"], previous["sample"]) != (incoming["key"], incoming["sample"]):
        raise ValueError("Profiles must use the same known key and sample")
    import copy
    result = copy.deepcopy(previous)
    if "plaintexts" in incoming:
        result["plaintexts"] = sorted(set(previous.get("plaintexts", [])) | set(incoming["plaintexts"]))
        result.setdefault("batches", []).append({"plaintexts": incoming["plaintexts"],
                                                "trials_per_input": incoming["trials_per_input"]})
    for hw, n2 in enumerate(incoming["counts"]):
        if not n2:
            continue
        n1 = previous["counts"][hw]
        mean2 = incoming["means"][hw]
        variance2 = incoming["stddev"][hw] ** 2
        if not n1:
            result["means"][hw] = mean2
            result["stddev"][hw] = incoming["stddev"][hw]
        else:
            delta = mean2 - previous["means"][hw]
            result["means"][hw] += delta * n2 / (n1 + n2)
            m2 = ((n1 - 1) * previous["stddev"][hw] ** 2 + (n2 - 1) * variance2
                  + delta ** 2 * n1 * n2 / (n1 + n2))
            result["stddev"][hw] = float(np.sqrt(m2 / (n1 + n2 - 1)))
        result["counts"][hw] += n2
    result["monotonic"] = (all(n >= 20 for n in result["counts"])
                           and bool(np.all(np.diff(result["means"]) > 0)))
    return result


def rank_keys(plaintexts, observations, means):
    """Mean squared template distance for every possible key byte; lower is better."""
    from chip import SBOX
    plaintexts = np.asarray(plaintexts, dtype=np.uint8)
    observations = np.asarray(observations, dtype=float)
    means = np.asarray(means, dtype=float)
    if plaintexts.ndim != 1 or observations.shape != plaintexts.shape or not len(plaintexts):
        raise ValueError("Provide one observed value for each plaintext")
    if means.shape != (9,):
        raise ValueError("Provide nine Hamming-weight class means")
    weights = np.array([value.bit_count() for value in SBOX])
    scores = np.empty(256)
    for key in range(256):
        prediction = means[weights[plaintexts ^ key]]
        scores[key] = np.mean((observations - prediction) ** 2)
    return scores


def candidate_profile(plaintexts, observations, candidate):
    """Observed class means under a candidate's HW assignments; no secret-key access."""
    from chip import SBOX
    groups = [[] for _ in range(9)]
    for plaintext, value in zip(plaintexts, observations):
        groups[SBOX[int(plaintext) ^ candidate].bit_count()].append(float(value))
    return {"candidate": candidate, "counts": [len(group) for group in groups],
            "means": [float(np.mean(group)) if group else None for group in groups]}


def recover_key(chip, key, profile, count=200, cancel=None, progress=None, plaintexts=None):
    """Acquire new unknown-key traces, then match observations against the profile."""
    if not 1 <= count <= 50000:
        raise ValueError("Use 1-50000 attack traces")
    if not plaintexts or any(not isinstance(p, int) or not 0 <= p <= 255 for p in plaintexts):
        raise ValueError("Select target plaintext bytes from 0 through 255")
    if count < len(plaintexts):
        raise ValueError("Trace count must cover every selected plaintext at least once")
    selected_inputs = list(plaintexts)
    plaintexts = [selected_inputs[i % len(selected_inputs)] for i in range(count)]
    observations = []
    display_traces = []
    seen = set()
    for index, plaintext in enumerate(plaintexts):
        checkpoint(cancel, progress, index, count)
        trace = chip.get_trace(plaintext, key)
        observation = float(trace[profile["sample"]])
        observations.append(observation)
        if plaintext not in seen:
            display_traces.append({"index": index, "plaintext": plaintext,
                                   "observation": observation, "values": trace.tolist()})
            seen.add(plaintext)
    checkpoint(cancel, progress, count, count)
    scores = rank_keys(plaintexts, observations, profile["means"])
    ranking = np.argsort(scores, kind="stable").tolist()
    return {"count": count, "sample": profile["sample"], "plaintexts": plaintexts,
            "observations": observations, "scores": scores.tolist(), "ranking": ranking,
            "selected_inputs": selected_inputs, "display_traces": display_traces,
            "candidate_fit": candidate_profile(plaintexts, observations, ranking[0])}
