"""Pygame terminal widget for the game's text command interface."""
from concurrent.futures import ThreadPoolExecutor

import contextlib
import io
import math
import os
import textwrap

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
import pygame


class Terminal:
    def __init__(self, submit):
        pygame.init()
        self.screen = pygame.display.set_mode((960, 640), pygame.RESIZABLE)
        pygame.display.set_caption("ECE 576 | Chip Lab Terminal")
        self.font = pygame.font.SysFont("monospace", 20)
        self.small_font = pygame.font.SysFont("monospace", 14)
        self.analysis = None
        self.analysis_future = None
        self.analysis_job = None
        self.executor = ThreadPoolExecutor(max_workers=1)
        self.traces = []
        self.plaintext = 0
        self.capture_count = 0
        self.submit = submit
        self.lines = []
        self.input = ""
        self.cursor = 0
        self.prompt = "username> "
        self.history = []
        self.history_index = 0
        self.draft = ""
        self.scroll = 0
        self.running = True

    def write(self, text):
        self.lines.extend(str(text).splitlines())
        self.lines = self.lines[-5000:]
        self.scroll = 0

    def execute(self):
        value = self.input
        self.write(self.prompt + value)
        self.input = ""
        self.cursor = 0
        if value.strip():
            self.history.append(value)
        self.history_index = len(self.history)
        self.draft = ""
        output = io.StringIO()
        try:
            with contextlib.redirect_stdout(output):
                keep_running = self.submit(value)
            if keep_running is False:
                self.running = False
        except Exception as error:
            output.write(f"An error occurred: {error}\n")
        self.write(output.getvalue())

    def recall(self, direction):
        if self.history_index == len(self.history):
            self.draft = self.input
        self.history_index = max(0, min(len(self.history), self.history_index + direction))
        self.input = (self.history[self.history_index]
                      if self.history_index < len(self.history) else self.draft)
        self.cursor = len(self.input)

    def handle_event(self, event):
        if event.type == pygame.QUIT:
            self.running = False
        elif event.type == pygame.MOUSEWHEEL:
            self.scroll = max(0, self.scroll + event.y * 3)
        elif event.type == pygame.TEXTINPUT:
            self.input = self.input[:self.cursor] + event.text + self.input[self.cursor:]
            self.cursor += len(event.text)
            self.scroll = 0
        elif event.type == pygame.KEYDOWN:
            if event.key == pygame.K_RETURN or event.key == pygame.K_KP_ENTER:
                self.execute()
            elif event.key == pygame.K_BACKSPACE and self.cursor:
                self.input = self.input[:self.cursor - 1] + self.input[self.cursor:]
                self.cursor -= 1
            elif event.key == pygame.K_DELETE:
                self.input = self.input[:self.cursor] + self.input[self.cursor + 1:]
            elif event.key == pygame.K_LEFT:
                self.cursor = max(0, self.cursor - 1)
            elif event.key == pygame.K_RIGHT:
                self.cursor = min(len(self.input), self.cursor + 1)
            elif event.key == pygame.K_HOME:
                self.cursor = 0
            elif event.key == pygame.K_END:
                self.cursor = len(self.input)
            elif event.key == pygame.K_UP:
                self.recall(-1)
            elif event.key == pygame.K_DOWN:
                self.recall(1)
            elif event.key == pygame.K_PAGEUP:
                self.scroll += 10
            elif event.key == pygame.K_PAGEDOWN:
                self.scroll = max(0, self.scroll - 10)
            elif event.key == pygame.K_c and event.mod & pygame.KMOD_CTRL:
                self.write(self.prompt + self.input + "^C")
                self.input = ""
                self.cursor = 0

    def start_ttest(self, work, chip_number, count, plaintext):
        if self.analysis_future is not None:
            print("A t-test is already running. Please wait for it to finish.")
            return
        self.analysis_job = (chip_number, count, plaintext)
        self.analysis_future = self.executor.submit(work)
        print(f"Collecting {count} fixed + {count} random traces from chip {chip_number}...")

    def poll_analysis(self):
        if self.analysis_future is None or not self.analysis_future.done():
            return
        try:
            values = self.analysis_future.result()
            self.analysis = (*self.analysis_job, values)
            peak_index = max(range(len(values)), key=lambda i: abs(values[i]))
            crossings = sum(abs(value) > 4.5 for value in values)
            self.write(f"Chip {self.analysis_job[0]}: peak |t|={abs(values[peak_index]):.2f} "
                       f"at sample {peak_index}; {crossings} samples exceed |t| > 4.5.")
            self.write("Threshold crossings suggest leakage; no crossing does not prove absence of leakage.")
        except Exception as error:
            self.write(f"T-test failed: {error}")
        finally:
            self.analysis_future = None

    def draw_ttest(self, width, height):
        chip_number, count, plaintext, values = self.analysis
        font = self.small_font
        def label(text, pos, color=(173, 193, 211)):
            self.screen.blit(font.render(text, True, color), pos)
        label(f"CHIP {chip_number} / WELCH T-TEST | {count} traces/group | fixed={plaintext}", (20, 12),
              (111, 231, 181))
        label("Fixed vs random plaintext | dashed thresholds: +/-4.5 | trace to return", (20, 34))
        plot = pygame.Rect(65, 65, max(1, width - 90), max(1, height - 108))
        finite = [abs(value) for value in values if math.isfinite(value)]
        limit = max(6, max(finite, default=0) * 1.15)
        def y(value):
            value = max(-limit, min(limit, float(value)))
            return plot.centery - value / limit * (plot.height / 2)
        pygame.draw.rect(self.screen, (13, 20, 29), plot)
        for value in (-limit, 0, limit):
            gy = y(value)
            pygame.draw.line(self.screen, (40, 53, 66), (plot.left, gy), (plot.right, gy))
            label(f"{value:.1f}", (4, gy - 7))
        for value in (-4.5, 4.5):
            gy = y(value)
            for x in range(plot.left, plot.right, 12):
                pygame.draw.line(self.screen, (238, 161, 104), (x, gy), (min(x + 6, plot.right), gy))
            label(f"{value:+.1f}", (4, gy - 7), (238, 161, 104))
        points = [(plot.left + i * (plot.width - 1) / (len(values) - 1), y(value))
                  for i, value in enumerate(values)]
        pygame.draw.aalines(self.screen, (111, 231, 181), False, points)
        label("0", (plot.left, plot.bottom + 5))
        label("Sample index", (plot.centerx - 50, plot.bottom + 5))
        label(str(len(values) - 1), (plot.right - 25, plot.bottom + 5))

    def set_traces(self, traces, plaintext):
        """Keep a snapshot; redraws must not acquire new measurements."""
        self.analysis = None
        self.traces = [list(trace) for trace in traces]
        self.plaintext = plaintext
        self.capture_count += 1

    def draw_dashboard(self, width, height):
        self.screen.set_clip(pygame.Rect(0, 0, width, height))
        self.screen.fill((19, 28, 39), (0, 0, width, height))

        def label(text, position, color=(173, 193, 211)):
            self.screen.blit(self.small_font.render(text, True, color), position)

        if self.analysis is not None:
            self.draw_ttest(width, height)
            self.screen.set_clip(None)
            pygame.draw.line(self.screen, (65, 88, 107), (0, height), (width, height), 2)
            return
        label("CHIP LAB / TRACE MONITOR", (20, 12), (111, 231, 181))
        if not self.traces:
            label("Enter your username below to initialize the chips.", (20, 44))
            label("Power traces and measurement statistics will appear here.", (20, 66))
        else:
            label(f"Capture {self.capture_count} | Plaintext 0x{self.plaintext:02X} | "
                  "trace [0-255] to capture again", (20, 34))
            low = min(min(trace) for trace in self.traces)
            high = max(max(trace) for trace in self.traces)
            span = max(high - low, 1.0)
            low -= span * 0.08
            high += span * 0.08
            colors = [(111, 231, 181), (102, 183, 255), (230, 183, 105), (194, 152, 247)]
            card_width = max(1, (width - 48) // 2)
            card_height = max(1, (height - 70) // 2)
            for index, trace in enumerate(self.traces[:4]):
                x = 20 + (index % 2) * (card_width + 8)
                y = 60 + (index // 2) * (card_height + 4)
                mean = sum(trace) / len(trace)
                rms = math.sqrt(sum(value * value for value in trace) / len(trace))
                label(f"CHIP {index + 1} | {len(trace)} samples | RMS {rms:.2f}",
                      (x, y), colors[index])
                plot = pygame.Rect(x + 32, y + 21, max(1, card_width - 40),
                                   max(1, card_height - 58))
                if card_height < 70:
                    continue
                pygame.draw.rect(self.screen, (13, 20, 29), plot)
                for fraction in (0, 0.5, 1):
                    gy = plot.top + round(fraction * (plot.height - 1))
                    pygame.draw.line(self.screen, (40, 53, 66), (plot.left, gy), (plot.right - 1, gy))
                    label(f"{high - fraction * (high - low):.0f}", (x, gy - 6))
                points = [(plot.left + i * (plot.width - 1) / max(1, len(trace) - 1),
                           plot.bottom - 1 - (value - low) / (high - low) * (plot.height - 1))
                          for i, value in enumerate(trace)]
                if len(points) > 1:
                    pygame.draw.aalines(self.screen, colors[index], False, points)
                label(f"0   sample index   {len(trace) - 1} | mean {mean:.2f}",
                      (x, plot.bottom + 3))
        self.screen.set_clip(None)
        pygame.draw.line(self.screen, (65, 88, 107), (0, height), (width, height), 2)

    def draw(self):
        self.poll_analysis()
        width, height = self.screen.get_size()
        self.screen.fill((15, 20, 27))
        split = height // 2
        self.draw_dashboard(width, split)
        self.screen.set_clip(pygame.Rect(0, split + 2, width, height - split - 2))
        line_height = self.font.get_linesize()
        cell_width = self.font.size("M")[0]
        columns = max(1, (width - 40) // cell_width)
        rows = max(1, (height - split - 112) // line_height)
        wrapped = []
        for line in self.lines:
            wrapped.extend(textwrap.wrap(line, columns, replace_whitespace=False,
                                         drop_whitespace=False) or [""])
        self.scroll = min(self.scroll, max(0, len(wrapped) - rows))
        end = len(wrapped) - self.scroll
        for index, line in enumerate(wrapped[max(0, end - rows):end]):
            self.screen.blit(self.font.render(line, True, (197, 213, 224)),
                             (20, split + 20 + index * line_height))
        pygame.draw.line(self.screen, (48, 64, 78), (20, height - 83), (width - 20, height - 83))
        # Horizontally scroll long input to keep the insertion point visible.
        full_input = self.prompt + self.input
        cursor_column = len(self.prompt) + self.cursor
        start = max(0, cursor_column - columns + 1)
        self.screen.blit(self.font.render(full_input[start:start + columns], True, (111, 231, 181)),
                         (20, height - 68))
        if pygame.time.get_ticks() % 1000 < 500:
            x = 20 + (cursor_column - start) * cell_width
            pygame.draw.line(self.screen, (111, 231, 181), (x, height - 68),
                             (x, height - 68 + line_height - 2), 2)
        hint = "UP/DOWN history | Wheel/PgUp/PgDn scroll"
        self.screen.blit(self.font.render(hint, True, (110, 130, 148)), (20, height - 30))
        self.screen.set_clip(None)
        pygame.display.flip()

    def run(self):
        clock = pygame.time.Clock()
        pygame.key.set_repeat(400, 35)
        pygame.key.start_text_input()
        try:
            while self.running:
                for event in pygame.event.get():
                    self.handle_event(event)
                self.draw()
                clock.tick(60)
        finally:
            self.executor.shutdown(wait=False, cancel_futures=True)
            pygame.quit()
