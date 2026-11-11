"""Exercise the real Pygame widget and asynchronous jobs on a headless display."""
import os
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')

import threading
import unittest

from analysis import CaptureCancelled
from session import Game
from terminal import Terminal
import pygame


class TerminalTests(unittest.TestCase):
    def setUp(self):
        self.terminal = Terminal(lambda value: self.game.submit(value))
        self.game = Game(self.terminal)

    def tearDown(self):
        self.terminal.cancel_event.set()
        self.terminal.executor.shutdown(wait=True, cancel_futures=True)
        pygame.quit()

    def send(self, value):
        self.terminal.input = value
        self.terminal.execute()

    def finish(self):
        # Future.result waits without spinning; completion callbacks run on the UI thread.
        try:
            self.terminal.analysis_future.result(timeout=5)
        except CaptureCancelled:
            pass
        self.terminal.draw()

    def test_render_views_editing_and_background_completion(self):
        self.terminal.draw()
        self.send('gui-student')
        self.assertEqual(len(self.terminal.traces), 4)
        self.send('t-threshold 3.25')
        self.send('fixed-trials 100')
        self.send('random-trials 150')
        self.send('run-ttest 1')
        self.finish()
        self.assertIn(1, self.game.tests)
        self.assertIsNotNone(self.terminal.analysis)
        self.terminal.handle_event(pygame.event.Event(pygame.MOUSEMOTION, pos=(384, 90)))
        self.terminal.draw()
        self.terminal.handle_event(pygame.event.Event(pygame.WINDOWLEAVE))
        self.assertIsNone(self.terminal.pointer)
        for size in ((960, 640), (1280, 900), (640, 480), (320, 240)):
            self.terminal.screen = pygame.display.set_mode(size, pygame.RESIZABLE)
            self.terminal.draw()
            for name, values in (('profile', list(range(9))), ('attack', list(range(256)))):
                chart = {'title': name, 'subtitle': 'measurement', 'values': values,
                         'xlabel': 'class', 'ylabel': 'distance', 'highlight': 0}
                self.terminal.show_chart(name, chart)
                self.terminal.draw()
            self.send('view traces')
            self.terminal.draw()
        self.terminal.handle_event(pygame.event.Event(pygame.TEXTINPUT, text='help'))
        self.assertEqual(self.terminal.input, 'help')
        self.terminal.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_HOME, mod=0))
        self.terminal.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_DELETE, mod=0))
        self.assertEqual(self.terminal.input, 'elp')
        self.send('exit')
        self.assertFalse(self.terminal.running)

    def test_stage_aware_tab_completion_and_cycling(self):
        def tab(text=None, cursor=None, reverse=False):
            if text is not None:
                self.terminal.input = text
                self.terminal.cursor = len(text) if cursor is None else cursor
                self.terminal.completion = None
            self.terminal.handle_event(pygame.event.Event(
                pygame.KEYDOWN, key=pygame.K_TAB, mod=pygame.KMOD_SHIFT if reverse else 0))
            return self.terminal.input
        self.assertEqual(tab('cap'), 'cap')  # Username input is not a command.
        self.send('student')
        history = self.terminal.history[:]
        self.assertEqual(tab('cap'), 'capture-power-traces')
        self.assertEqual(tab('run-t 2', cursor=5), 'run-ttest 2')
        self.assertEqual(tab('help ass'), 'help assessment')
        self.assertEqual(tab('view-chart tr'), 'view-chart traces')
        self.assertEqual(tab('build'), 'build')  # Not available in assessment.
        self.assertEqual(self.terminal.history, history)
        self.game.stage = self.terminal.stage_index = 1
        self.assertEqual(tab('set profile-'), 'set profile-')
        self.assertEqual(tab(), 'set profile-key')
        self.assertEqual(tab(), 'set profile-plaintexts')
        self.assertEqual(tab(reverse=True), 'set profile-key')
        self.terminal.handle_event(pygame.event.Event(pygame.TEXTINPUT, text='x'))
        self.assertIsNone(self.terminal.completion)
        self.assertEqual(tab('help pro'), 'help profiling')
        self.assertEqual(tab('run-t'), 'run-t')
        self.game.stage = self.terminal.stage_index = 2
        self.assertEqual(tab('run-'), 'run-attack')
        self.game.stage = self.terminal.stage_index = 3
        self.assertEqual(tab('run-'), 'run-')
        self.assertEqual(tab('export-'), 'export-results')

    def test_only_completed_leaky_chip_test_allows_progression(self):
        from chip import LeakyChip
        self.send('student')
        number = next(i for i, chip in enumerate(self.game.chips, 1) if isinstance(chip, LeakyChip))
        self.send('fixed-trials 50000')
        self.send('random-trials 50000')
        self.send('t-threshold 4.5')
        self.send(f'run-ttest {number}')
        self.send(f'guess-chip {number} {self.game.chips[number - 1].leak_index}')
        self.assertEqual(self.game.stage, 0)
        self.send('cancel-capture')
        self.finish()
        self.assertNotIn(number, self.game.tests)
        self.send(f'guess-chip {number} {self.game.chips[number - 1].leak_index}')
        self.assertEqual(self.game.stage, 0)
        self.send('fixed-trials 20')
        self.send('random-trials 30')
        self.send(f'run-ttest {number}')
        self.finish()
        self.send(f'guess-chip {number} {self.game.chips[number - 1].leak_index}')
        self.assertEqual(self.game.stage, 1)
        self.assertEqual(self.game.assessment_result['chip'], number)
        self.terminal.draw()

    def test_cancel_preserves_results_and_window_close_stops_worker(self):
        started = threading.Event()
        applied = []
        def work(cancel, progress):
            started.set()
            progress(1, 2)
            cancel.wait(timeout=5)
            raise CaptureCancelled('Capture cancelled; previous results kept.')
        self.terminal.show_chart('profile', {'title': 'old', 'subtitle': 'saved',
                                                'values': list(range(9)), 'xlabel': 'HW',
                                                'ylabel': 'power'})
        self.terminal.start_job('test', work, applied.append)
        self.assertTrue(started.wait(timeout=5))
        self.terminal.cancel_job()
        self.finish()
        self.assertFalse(applied)
        self.assertEqual(self.terminal.plot['title'], 'old')
        self.assertIsNone(self.terminal.analysis_future)
        self.assertTrue(any('cancelled' in line for line in self.terminal.lines))
        self.terminal.plot = None
        self.terminal.start_job('test', work, applied.append)
        pygame.event.post(pygame.event.Event(pygame.QUIT))
        self.terminal.run()
        self.assertTrue(self.terminal.cancel_event.is_set())
        self.assertFalse(self.terminal.running)


if __name__ == '__main__':
    unittest.main()
