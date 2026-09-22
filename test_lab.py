import math
import os
os.environ['SDL_VIDEODRIVER'] = 'dummy'
os.environ['SDL_AUDIODRIVER'] = 'dummy'
import random
import unittest
from lab_model import *


class ModelTests(unittest.TestCase):
    def test_cipher_and_validation(self):
        self.assertEqual(len(set(SBOX)), 256)
        self.assertEqual(encrypt(0x12, 0x34), SBOX[0x26])
        self.assertEqual(byte('0xff'), 255)
        for text in ['100', '-1', 'xyz', '']:
            with self.assertRaises(ValueError):
                byte(text)

    def test_average_welch(self):
        def trace(v):
            return Trace(0, 0, (v,) * SAMPLES, (v,) * SAMPLES)
        a, b = [trace(1), trace(3)], [trace(2), trace(4)]
        self.assertEqual(average(a, 'power'), (2.,) * SAMPLES)
        self.assertAlmostEqual(welch(a, b, 'power')[0], -1 / math.sqrt(2))
        self.assertIsNone(welch([trace(1)] * 2, [trace(1)] * 2, 'em')[0])
        self.assertEqual(welch([trace(2)] * 2, [trace(1)] * 2, 'em')[0], math.inf)
        with self.assertRaises(ValueError):
            welch(a[:1], b, 'power')

    def groups(self, chip, n):
        rng = random.Random(812)
        key = 93
        # Explicit calibrated fixed plaintext whose intermediate has HW=0.
        plain = SBOX.index(0) ^ key
        return ([capture(chip, key, plain, rng) for _ in range(n)],
                [capture(chip, key, rng.randrange(256), rng) for _ in range(n)])

    def test_leakage_fixtures(self):
        for chip, signal in [(CHIPS[2], 'power'), (CHIPS[3], 'em')]:
            self.assertGreater(max(abs(t) for t in welch(*self.groups(chip, 100), signal)), 4.5)
        low = max(abs(t) for t in welch(*self.groups(CHIPS[1], 20), 'power'))
        high = max(abs(t) for t in welch(*self.groups(CHIPS[1], 2000), 'power'))
        self.assertLess(low, 4.5)
        self.assertGreater(high, 4.5)
        self.assertLess(max(abs(t) for t in welch(*self.groups(CHIPS[0], 2000), 'power')), 4.5)

    def test_profile_recovery_and_isolation(self):
        rng = random.Random(99)
        states = experiments(rng)
        for chip_index, signal in [(2, 'power'), (3, 'em')]:
            st = states[chip_index]
            key_before = st._key
            for p in range(256):
                for _ in range(12):
                    st.profile.add(capture(st.chip, 17, p, rng), 17)
            self.assertEqual(st.profile.counts, [12 * math.comb(8, h) for h in range(9)])
            fp = st.profile.fingerprints()
            for _ in range(100):
                trace = st.measure(rng.randrange(256), rng)
                # The ciphertext is deliberately replaced: scoring cannot use it.
                st.add_target(Trace(trace.plaintext, -1, trace.power, trace.em), fp)
            for mode in (signal, 'combined'):
                self.assertEqual(ranking(st.scores, mode)[0][0], key_before)
            self.assertTrue(st.check_guess(key_before))
            self.assertEqual(st._key, key_before)
        self.assertEqual(states[0].profile.counts, [0] * 9)
        self.assertEqual(states[0].target, [])
        with self.assertRaises(ValueError):
            states[0].profile.fingerprints()


class UITests(unittest.TestCase):
    def test_controls_and_screens(self):
        import pygame
        from side_channel_lab import Lab
        app = Lab()
        app.rng.seed(5)
        def finish():
            while app.job:
                app.tick()
        def click(x, y):
            app.event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=(x, y)))
        app.draw()
        click(50, 175)
        app.event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_a, mod=pygame.KMOD_CTRL, unicode='a'))
        app.event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_f, mod=0, unicode='F'))
        self.assertEqual(app.state.settings['plaintext'], 'F')
        click(180, 171)
        self.assertEqual(app.state.settings['trials'], 1)
        click(579, 171)
        self.assertEqual(app.state.settings['trials'], 2000)
        app.state.settings['trials'] = 1
        app.tab = 'Test'
        app.start('test')
        self.assertIsNone(app.job)
        app.state.settings['trials'] = 100
        app.start('test'); finish(); app.draw()
        app.state.settings['threshold'] = 'nan'
        app.draw()
        app.state.settings['threshold'] = '4.5'
        app.selected = 2
        app.state.settings['random'] = True
        app.start('observe'); finish()
        self.assertGreater(len({t.plaintext for t in app.state.observed}), 1)
        saved = tuple(app.state.observed)
        app.tab = 'Observe'; app.draw()
        self.assertEqual(tuple(app.state.observed), saved)
        pygame.image.save(app.screen, '/tmp/lab-observe.png')
        app.tab = 'Test'; app.start('test'); finish(); app.draw()
        pygame.image.save(app.screen, '/tmp/lab-test.png')
        app.tab = 'Profile / Recover'; app.start('recover')
        self.assertIsNone(app.job)
        app.start('profile'); finish()
        app.start('recover'); finish(); app.draw()
        pygame.image.save(app.screen, '/tmp/lab-profile.png')
        self.assertEqual(len(app.state.target), 100)
        app.start('label'); finish()
        self.assertEqual(len(app.state.target), 0)
        app.selected = 0
        self.assertEqual(app.state.observed, [])
        app.event(pygame.event.Event(pygame.QUIT))
        self.assertFalse(app.running)
        pygame.quit()


if __name__ == '__main__':
    unittest.main()
