"""Local, in-memory educational side-channel lab. Run this file to open Pygame."""
import math
import random
import time
import pygame
from lab_model import (WINDOWS, SAMPLES, experiments, byte, capture, average, welch, ranking)

BG = (19, 24, 32)
FG = (232, 237, 243)
MUTED = (172, 185, 201)
BLUE = (93, 200, 250)
ORANGE = (255, 184, 97)


class Lab:
    def __init__(self):
        pygame.init()
        self.screen = pygame.display.set_mode((1280, 900))
        pygame.display.set_caption('Toy cipher side-channel lab')
        self.font = pygame.font.Font(None, 24)
        self.small = pygame.font.Font(None, 21)
        self.rng = random.Random()
        self.chips = experiments(self.rng)
        self.selected = 0
        self.tab = 'Observe'
        self.focus = None
        self.widgets = []
        self.job = None
        self.progress = (0, 0)
        self.cache = {}
        self.running = True

    @property
    def state(self):
        return self.chips[self.selected]

    def text(self, value, x, y, color=FG, small=False):
        self.screen.blit((self.small if small else self.font).render(str(value), True, color), (x, y))

    def button(self, label, rect, action, active=False):
        rect = pygame.Rect(rect)
        pygame.draw.rect(self.screen, (48, 72, 96) if active else (42, 49, 61), rect)
        self.text(label, rect.x + 10, rect.y + 9)
        self.widgets.append((rect, 'button', action))

    def field(self, label, name, x, y, width=100):
        self.text(label, x, y, MUTED, True)
        rect = pygame.Rect(x, y + 24, width, 34)
        pygame.draw.rect(self.screen, (40, 48, 60), rect)
        pygame.draw.rect(self.screen, BLUE if self.focus == name else MUTED, rect, 1)
        self.text(self.state.settings[name], x + 8, y + 32)
        self.widgets.append((rect, 'field', name))

    def slider(self, label, name, low, high, x, y, width):
        value = self.state.settings[name]
        self.text(f'{label}: {value}', x, y, MUTED)
        rect = pygame.Rect(x, y + 26, width, 22)
        pygame.draw.line(self.screen, MUTED, (x, rect.centery), (rect.right, rect.centery), 3)
        px = x + (value - low) / (high - low) * width
        pygame.draw.circle(self.screen, BLUE, (int(px), rect.centery), 7)
        self.widgets.append((rect, 'slider', (name, low, high)))

    def plot(self, rect, title, series, threshold=None):
        r = pygame.Rect(rect)
        pygame.draw.rect(self.screen, (27, 34, 44), r)
        self.text(title, r.x + 12, r.y + 8)
        finite = [v for _, vals, _ in series for v in vals if v is not None and math.isfinite(v)]
        bound = max([abs(v) for v in finite] + ([threshold * 1.2] if threshold else [1]))
        left, right, top, bottom = r.x + 62, r.right - 15, r.y + 48, r.bottom - 28
        def ypos(v):
            return bottom - (v + bound) / (2 * bound) * (bottom - top)
        for v in [-bound, 0, bound]:
            yy = ypos(v)
            pygame.draw.line(self.screen, (57, 67, 81), (left, yy), (right, yy))
            self.text(f'{v:.1f}', r.x + 5, yy - 7, MUTED, True)
        if threshold:
            for v in [-threshold, threshold]:
                pygame.draw.line(self.screen, ORANGE, (left, ypos(v)), (right, ypos(v)))
        for n, (label, vals, color) in enumerate(series):
            self.text(label, left + n * 150, r.y + 29, color, True)
            previous = None
            for i, v in enumerate(vals):
                if v is None:
                    previous = None
                    continue
                point = (left + i / (SAMPLES - 1) * (right - left),
                         ypos(max(-bound, min(bound, v))))
                if previous:
                    pygame.draw.line(self.screen, color, previous, point, 2)
                if math.isinf(v):
                    pygame.draw.circle(self.screen, ORANGE, (int(point[0]), int(point[1])), 4)
                previous = point
        self.text('0', left, bottom + 7, MUTED, True)
        self.text('sample index (0-63)', (left + right) // 2 - 65, bottom + 7, MUTED, True)
        self.text('63', right - 17, bottom + 7, MUTED, True)

    def threshold(self):
        try:
            value = float(self.state.settings['threshold'])
            if not math.isfinite(value) or value <= 0:
                raise ValueError
            return value
        except ValueError:
            raise ValueError('Threshold must be a finite positive number.') from None

    def start(self, kind):
        if self.job:
            return
        st, cfg = self.state, self.state.settings
        try:
            p = byte(cfg['copy_plaintext']) if kind == 'label' else (byte(cfg['plaintext']) if kind in ('observe', 'test') else 0)
            key = byte(cfg['copy_key']) if kind in ('label', 'profile') else None
            n = cfg['trials']
            if kind == 'test':
                self.threshold()
                if n < 2:
                    raise ValueError('Test requires at least two trials per group.')
            fingerprints = st.profile.fingerprints() if kind == 'recover' else None
        except ValueError as exc:
            st.message = str(exc)
            return
        if kind in ('profile', 'label'):
            st.clear_recovery()
        if kind == 'observe':
            st.observed = []
            cfg['index'] = 0
        elif kind == 'test':
            st.fixed, st.random_group = [], []
        total = 256 * cfg['repetitions'] if kind == 'profile' else (2 * n if kind == 'test' else n)
        self.progress = (0, total)
        self.cache.clear()
        def work():
            for i in range(total):
                if kind in ('profile', 'label'):
                    plain = i // cfg['repetitions'] if kind == 'profile' else p
                    st.profile.add(capture(st.chip, key, plain, self.rng), key)
                elif kind == 'test':
                    dest = st.fixed if i < n else st.random_group
                    dest.append(st.measure(p if i < n else self.rng.randrange(256), self.rng))
                elif kind == 'observe':
                    st.observed.append(st.measure(self.rng.randrange(256) if cfg['random'] else p, self.rng))
                else:
                    st.add_target(st.measure(self.rng.randrange(256), self.rng), fingerprints)
                self.progress = (i + 1, total)
                yield
            st.message = f'Completed {total:,} measurements.'
            if kind in ('profile', 'label'):
                st.message += ' Recovery reset because the profile changed.'
        self.job = work()

    def tick(self):
        if self.job:
            deadline = time.perf_counter() + .008
            while time.perf_counter() < deadline:
                try:
                    next(self.job)
                except StopIteration:
                    self.job = None
                    self.cache.clear()
                    break

    def cached(self, key, compute):
        if key not in self.cache:
            self.cache[key] = compute()
        return self.cache[key]

    def set_value(self, key, value):
        self.state.settings[key] = value

    def submit(self):
        try:
            correct = self.state.check_guess(byte(self.state.settings['guess']))
            self.state.message = 'Correct key!' if correct else 'Incorrect guess. Collect more evidence and try again.'
        except ValueError as exc:
            self.state.message = str(exc)

    def draw(self):
        self.screen.fill(BG)
        self.widgets = []
        st, cfg = self.state, self.state.settings
        self.text('SIDE-CHANNEL LAB | Toy byte cipher: substitution(plaintext XOR key)', 24, 18)
        self.text('Synthetic signals, arbitrary units. 256 possible keys. Each target keeps one secret key for this session.', 24, 47, MUTED)
        for i, chip in enumerate(self.chips):
            self.button(chip.chip.name, (24 + i * 155, 78, 140, 36), ('chip', i), i == self.selected)
        for i, tab in enumerate(['Observe', 'Test', 'Profile / Recover']):
            self.button(tab, (670 + i * 195, 78, 185, 36), ('tab', tab), self.tab == tab)
        self.field('Plaintext (hex)', 'plaintext', 24, 134)
        self.slider('Trials (per group in Test)', 'trials', 1, 2000, 180, 134, 400)
        if self.tab == 'Observe':
            self.button('Random plaintext' if cfg['random'] else 'Fixed plaintext', (630, 149, 200, 38), ('toggle', 'random'))
            self.button('Capture batch', (870, 149, 180, 38), ('start', 'observe'))
            self.button('Individual trial' if cfg['individual'] else 'Batch average', (24, 209, 190, 36), ('toggle', 'individual'))
            if st.observed:
                self.button('< Previous', (235, 209, 125, 36), ('step', -1))
                self.button('Next >', (370, 209, 110, 36), ('step', 1))
                t = st.observed[cfg['index']]
                self.text(f'Trial {cfg["index"] + 1}/{len(st.observed)}: plaintext {t.plaintext:02X}, ciphertext {t.ciphertext:02X}', 510, 219)
            for j, signal in enumerate(WINDOWS):
                vals = ()
                if st.observed and not self.job:
                    vals = getattr(st.observed[cfg['index']], signal) if cfg['individual'] else self.cached((self.selected, signal, 'observe'), lambda: average(st.observed, signal))
                self.plot((24, 270 + j * 250, 1232, 235), f'{signal.upper()} | amplitude (arbitrary units)', [('measured', vals, BLUE)])
        elif self.tab == 'Test':
            self.field('Threshold |t|', 'threshold', 630, 134)
            self.button('Collect fixed / random', (820, 149, 250, 38), ('start', 'test'))
            try:
                threshold = self.threshold()
            except ValueError:
                threshold = None
            results = []
            for j, signal in enumerate(WINDOWS):
                a, b, ts = (), (), ()
                if st.fixed and st.random_group and not self.job:
                    a, b, ts = self.cached((self.selected, signal, 'test'), lambda: (average(st.fixed, signal), average(st.random_group, signal), welch(st.fixed, st.random_group, signal)))
                self.plot((24, 245 + j * 255, 610, 240), f'{signal.upper()} | group means (arbitrary units)', [('fixed', a, BLUE), ('random', b, ORANGE)])
                self.plot((650, 245 + j * 255, 606, 240), f'{signal.upper()} | Welch t', [('t statistic', ts, BLUE)], threshold)
                if ts and threshold:
                    crossings = sum(t is not None and abs(t) > threshold for t in ts)
                    undefined = sum(t is None for t in ts)
                    infinite = sum(t is not None and math.isinf(t) for t in ts)
                    results.append(f'{signal}: {crossings} crossings; {undefined} undefined; {infinite} infinite')
            self.text(' | '.join(results) or 'Collect independent groups to compare their sample means.', 24, 205, MUTED)
            if results:
                detected = any(t is not None and abs(t) > threshold for signal in WINDOWS for t in self.cache[(self.selected, signal, 'test')][2])
                self.text('Threshold crossings: evidence of leakage.' if detected else 'No leakage detected at this trial count.', 24, 770, BLUE)
            self.text('No detection does not establish security. Equal constants: undefined (gaps); unequal constants: infinite (edge dots).', 24, 800, MUTED, True)
        else:
            self.field('Copy key (hex)', 'copy_key', 24, 215)
            self.field('Copy plaintext (hex)', 'copy_plaintext', 190, 215, 140)
            self.button('Collect labeled batch', (370, 239, 225, 36), ('start', 'label'))
            self.slider('Repetitions / plaintext', 'repetitions', 2, 100, 24, 307, 420)
            self.button('Build profile (256 values)', (490, 322, 280, 38), ('start', 'profile'))
            self.text('Profile features: mean power samples 18-25; mean EM samples 40-47. Labels: HW(substitution(p XOR copy key)).', 24, 385, MUTED, True)
            self.text('Class (HW):', 24, 420)
            self.text('Measurements:', 24, 452)
            for i, count in enumerate(st.profile.counts):
                self.text(i, 200 + i * 95, 420)
                self.text(count, 200 + i * 95, 452)
            self.text(f'Coverage: {sum(n >= 2 for n in st.profile.counts)}/9 classes with >=2 samples. Variance floor: 0.000001.', 24, 487, MUTED)
            for i, mode in enumerate(['power', 'em', 'combined']):
                self.button(mode.upper(), (24 + i * 150, 534, 140, 36), ('mode', mode), cfg['mode'] == mode)
            self.button('Add target batch', (510, 534, 200, 36), ('start', 'recover'))
            self.text(f'Accumulated target traces: {len(st.target)}', 24, 600)
            if st.target:
                for i, (key, score) in enumerate(ranking(st.scores, cfg['mode'])[:5]):
                    self.text(f'{i + 1}.  {key:02X}    log likelihood {score:.2f}', 24, 636 + i * 29, BLUE)
            self.field('Submit key guess (hex)', 'guess', 810, 600, 190)
            self.button('Check guess', (1030, 624, 180, 36), ('guess', None))
            self.text('Useful recovery requires detectable leakage and enough profile measurements.', 510, 708, MUTED, True)
            self.text('Profile changes reset target scores. Copy keys never change the target key.', 510, 738, MUTED, True)
            self.text('Scores use learned Gaussian fingerprints; power + EM assumes independent features.', 510, 768, MUTED, True)
        if self.job:
            done, total = self.progress
            self.text(f'Collecting: {done:,} / {total:,} ({done / total:.0%}) - controls locked until complete', 24, 844, BLUE)
        else:
            self.text(st.message, 24, 844, BLUE)
        self.text('All data stays in memory. Close window or Esc to exit.', 24, 875, MUTED, True)

    def event(self, event):
        if event.type == pygame.QUIT or (event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE):
            self.running = False
            return
        if self.job:
            return
        if event.type == pygame.KEYDOWN and self.focus:
            value = self.state.settings[self.focus]
            if event.key == pygame.K_BACKSPACE:
                self.set_value(self.focus, value[:-1])
            elif event.key in (pygame.K_RETURN, pygame.K_TAB):
                self.focus = None
            elif event.key == pygame.K_a and event.mod & pygame.KMOD_CTRL:
                self.set_value(self.focus, '')
            elif event.unicode.isprintable() and len(value) < 12:
                self.set_value(self.focus, value + event.unicode)
        click = event.type == pygame.MOUSEBUTTONDOWN and event.button == 1
        drag = event.type == pygame.MOUSEMOTION and event.buttons[0]
        if not (click or drag):
            return
        if click:
            self.focus = None
        for rect, kind, payload in self.widgets:
            if not rect.collidepoint(event.pos):
                continue
            if kind == 'slider':
                name, low, high = payload
                self.set_value(name, round(low + (high - low) * (event.pos[0] - rect.x) / (rect.width - 1)))
            elif click and kind == 'field':
                self.focus = payload
            elif click:
                action, value = payload
                if action == 'chip':
                    self.selected = value
                elif action == 'tab':
                    self.tab = value
                elif action == 'toggle':
                    self.set_value(value, not self.state.settings[value])
                elif action == 'mode':
                    self.set_value('mode', value)
                elif action == 'step':
                    self.set_value('index', (self.state.settings['index'] + value) % len(self.state.observed))
                elif action == 'start':
                    self.start(value)
                elif action == 'guess':
                    self.submit()
            break

    def run(self):
        clock = pygame.time.Clock()
        while self.running:
            for event in pygame.event.get():
                self.event(event)
            self.tick()
            self.draw()
            pygame.display.flip()
            clock.tick(60)
        pygame.quit()


if __name__ == '__main__':
    Lab().run()
