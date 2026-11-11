"""Pygame terminal widget for the game's text command interface."""
from concurrent.futures import ThreadPoolExecutor

import contextlib
import io
import math
import os
import re
import textwrap
import threading

from analysis import CaptureCancelled

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
import pygame


class Terminal:
    INPUT_COLOR = (111, 231, 181)
    OUTPUT_COLOR = (197, 213, 224)

    def __init__(self, submit):
        pygame.init()
        self.screen = pygame.display.set_mode((960, 640), pygame.RESIZABLE)
        pygame.display.set_caption("ECE 576 | Chip Lab Terminal")
        self.font = pygame.font.SysFont("monospace", 20)
        self.bold_font = pygame.font.SysFont("monospace", 20, bold=True)
        self.small_font = pygame.font.SysFont("monospace", 14)
        self.axis_font = pygame.font.SysFont("monospace", 16)
        self.pointer = None
        self.trace_buttons = []
        self.stage_text = "WELCOME"
        self.stage_index = None
        self.plot = None
        self.charts = {}
        self.job_progress = (0, 1)
        self.cancel_event = threading.Event()
        self.analysis = None
        self.analysis_future = None
        self.analysis_job = None
        self.executor = ThreadPoolExecutor(max_workers=1)
        self.traces = []
        self.plaintext = 0
        self.capture_count = 0
        self.submit = submit
        self.completion_provider = lambda text: []
        self.completion = None
        self.lines = []
        self.line_colors = []
        self.input = ""
        self.cursor = 0
        self.prompt = "username> "
        self.history = []
        self.history_index = 0
        self.draft = ""
        self.scroll = 0
        self.running = True

    def write(self, text, color=None):
        lines = str(text).splitlines()
        self.lines.extend(lines)
        self.line_colors.extend([color or self.OUTPUT_COLOR] * len(lines))
        self.lines = self.lines[-5000:]
        self.line_colors = self.line_colors[-5000:]
        self.scroll = 0

    def execute(self):
        value = self.input
        self.write(self.prompt + value, self.INPUT_COLOR)
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

    def complete_input(self, reverse=False):
        state = (self.input, self.cursor, self.stage_index, self.analysis_future is not None)
        if self.completion is not None and self.completion["state"] == state:
            session = self.completion
            session["index"] = (session["index"] + (-1 if reverse else 1)) % len(session["choices"])
            replacement = session["choices"][session["index"]]
        else:
            choices = self.completion_provider(self.input[:self.cursor])
            if not choices:
                self.completion = None
                return
            start = self.cursor
            while start > 0 and not self.input[start - 1].isspace():
                start -= 1
            end = self.cursor
            while end < len(self.input) and not self.input[end].isspace():
                end += 1
            prefix = self.input[start:self.cursor]
            replacement = os.path.commonprefix(choices)
            session = {"prefix": self.input[:start], "suffix": self.input[end:],
                       "choices": choices, "index": -1}
            if len(choices) == 1:
                replacement = choices[0]
            elif reverse:
                session["index"] = len(choices) - 1
                replacement = choices[-1]
            elif replacement == prefix:
                self.write("Matches: " + "  ".join(choices))
        self.input = session["prefix"] + replacement + session["suffix"]
        self.cursor = len(session["prefix"]) + len(replacement)
        session["state"] = (self.input, self.cursor, self.stage_index, self.analysis_future is not None)
        self.completion = session
        self.scroll = 0

    def handle_event(self, event):
        if event.type == pygame.QUIT:
            self.running = False
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.plot is not None and self.plot.get("kind") == "recovery" and self.plot.get("result"):
                for rect, direction in self.trace_buttons:
                    if rect.collidepoint(event.pos):
                        total = len(self.plot["result"]["display_traces"])
                        self.plot["index"] = (self.plot["index"] + direction) % total
                        break
        elif event.type == pygame.MOUSEMOTION:
            self.pointer = event.pos
        elif event.type == pygame.WINDOWLEAVE:
            self.pointer = None
        elif event.type == pygame.MOUSEWHEEL:
            self.scroll = max(0, self.scroll + event.y * 3)
        elif event.type == pygame.TEXTINPUT:
            self.completion = None
            self.input = self.input[:self.cursor] + event.text + self.input[self.cursor:]
            self.cursor += len(event.text)
            self.scroll = 0
        elif event.type == pygame.KEYDOWN:
            if event.key == pygame.K_TAB:
                self.complete_input(reverse=bool(event.mod & pygame.KMOD_SHIFT))
                return
            self.completion = None
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
                self.write(self.prompt + self.input + "^C", self.INPUT_COLOR)
                self.input = ""
                self.cursor = 0

    def reset_views(self):
        self.analysis = None
        self.plot = None
        self.charts.clear()
        self.traces = []
        self.capture_count = 0

    def start_job(self, title, work, complete):
        if self.analysis_future is not None:
            print("An experiment is already running.")
            return
        self.analysis_job = (title, complete)
        self.cancel_event = threading.Event()
        self.job_progress = (0, 1)
        def progress(done, total):
            self.job_progress = (done, total)
        self.analysis_future = self.executor.submit(work, self.cancel_event, progress)
        print(title + "... Use cancel-capture to stop.")

    def cancel_job(self):
        if self.analysis_future is not None:
            self.cancel_event.set()
            print("Stopping the experiment...")
        else:
            print("No experiment is running.")

    def poll_analysis(self):
        if self.analysis_future is None or not self.analysis_future.done():
            return
        output = io.StringIO()
        try:
            result = self.analysis_future.result()
            if self.cancel_event.is_set():
                raise CaptureCancelled("Capture cancelled; previous results kept.")
            with contextlib.redirect_stdout(output):
                self.analysis_job[1](result)
        except CaptureCancelled as error:
            output.write(str(error))
        except Exception as error:
            output.write(f"Experiment failed: {error}")
        finally:
            self.analysis_future = None
            self.write(output.getvalue())

    def show_chart(self, name, chart):
        self.charts[name] = chart
        self.plot = chart
        self.analysis = None

    def draw_recovery(self, width, height):
        from chip import SBOX
        chart = self.plot
        result, profile = chart["result"], chart["profile"]
        green, amber = (111, 231, 181), (255, 197, 112)
        def label(text, pos, color=(173, 193, 211)):
            self.screen.blit(self.small_font.render(text, True, color), pos)
        label("KEY RECOVERY / target measurements vs learned profile", (20, 12), green)
        self.trace_buttons = []
        if result is None:
            label(f"Accepted sample: {chart['sample']} | Target key: fixed and unknown", (20, 36))
            inputs = chart["inputs"]
            label(f"Selected plaintext bytes: {len(inputs) if inputs else 'not set'} | Target captures: 0", (20, 58))
            if width < 600 or height < 200:
                label("Submitted profile ready | No target measurements", (20, 82))
                return
            panel_width = max(1, (width - 110) // 2)
            left = pygame.Rect(46, 94, panel_width, max(1, height - 154))
            right = pygame.Rect(left.right + 62, 94, panel_width, left.height)
            label("Target power trace (a.u.)", (left.left, 76))
            pygame.draw.rect(self.screen, (13, 20, 29), left)
            label("No target traces captured", (left.left + 12, left.centery - 8))
            for index in (0, 100, 199):
                x = left.left + index * (left.width - 1) / 199
                label(str(index), (x - 5, left.bottom + 2))
            x = left.left + chart["sample"] * (left.width - 1) / 199
            pygame.draw.line(self.screen, amber, (x, left.top), (x, left.bottom - 1))
            label("Time (sample index)", (left.left, left.bottom + 18))
            label("Submitted profile (a.u.)", (right.left, 76))
            pygame.draw.rect(self.screen, (13, 20, 29), right)
            means = profile["means"]
            padding = max(.5, (max(means) - min(means)) * .12)
            low, high = min(means) - padding, max(means) + padding
            def point(index, value):
                return (right.left + index * (right.width - 1) / 8,
                        right.bottom - 1 - (value - low) / (high - low) * (right.height - 1))
            for value in (low, (low + high) / 2, high):
                gy = point(0, value)[1]
                pygame.draw.line(self.screen, (40, 53, 66), (right.left, gy), (right.right - 1, gy))
                label(f"{value:.1f}", (right.left - 35, gy - 7))
            points = [point(index, value) for index, value in enumerate(means)]
            pygame.draw.aalines(self.screen, green, False, points)
            for index, pos in enumerate(points):
                pygame.draw.circle(self.screen, green, pos, 3)
                label(str(index), (pos[0] - 3, right.bottom + 2))
            label("Hamming weight of S-box output", (right.left, right.bottom + 18))
            label("Green: submitted profile | Amber: accepted sample", (20, height - 23))
            return
        traces = result["display_traces"]
        item = traces[chart["index"]]
        candidate = chart["candidate"]
        hw = SBOX[item["plaintext"] ^ candidate].bit_count()
        predicted = profile["means"][hw]
        observed = item["observation"]
        label(f"Input 0x{item['plaintext']:02X} | Trace {chart['index'] + 1}/{len(traces)} "
              f"(one per input) | {result['count']} total captures", (20, 34))
        label(f"Secret-key candidate 0x{candidate:02X} | HW {hw} | Sample {chart['sample']}: "
              f"obs {observed:.3f}, pred {predicted:.3f}, error {observed - predicted:+.3f}", (20, 54), amber)
        if width < 600 or height < 200:
            label("Observed and predicted values are in relative power units (a.u.).", (20, 82))
            return
        gap = 62
        panel_width = max(1, (width - 110) // 2)
        left = pygame.Rect(46, 94, panel_width, max(1, height - 154))
        right = pygame.Rect(left.right + gap, 94, panel_width, left.height)
        def plot_values(rect, values, xlabel, color=green, include=()):
            low, high = min([*values, *include]), max([*values, *include])
            padding = max(.5, (high - low) * .12)
            low, high = low - padding, high + padding
            def point(index, value):
                return (rect.left + index * (rect.width - 1) / max(1, len(values) - 1),
                        rect.bottom - 1 - (value - low) / (high - low) * (rect.height - 1))
            pygame.draw.rect(self.screen, (13, 20, 29), rect)
            for value in (low, (low + high) / 2, high):
                gy = point(0, value)[1]
                pygame.draw.line(self.screen, (40, 53, 66), (rect.left, gy), (rect.right - 1, gy))
                label(f"{value:.1f}", (rect.left - 35, gy - 7))
            pygame.draw.aalines(self.screen, color, False, [point(i, v) for i, v in enumerate(values)])
            label(xlabel, (rect.left, rect.bottom + 18))
            return point
        label("Target power trace (a.u.)", (left.left, 76))
        point = plot_values(left, item["values"], "Time (sample index)", (102, 183, 255))
        for index in (0, 100, 199):
            label(str(index), (point(index, 0)[0] - 5, left.bottom + 2))
        gx, gy = point(chart["sample"], observed)
        pygame.draw.line(self.screen, amber, (gx, left.top), (gx, left.bottom - 1))
        pygame.draw.circle(self.screen, amber, (gx, gy), 4)
        fit = chart["fit"]
        fit_values = [value for value in fit["means"] if value is not None]
        label(f"Profile + secret-key fit 0x{candidate:02X} (a.u.)", (right.left, 76))
        point = plot_values(right, profile["means"], "Hamming weight of S-box output",
                            include=(observed, *fit_values))
        blue = (102, 183, 255)
        for index, value in enumerate(fit["means"]):
            if value is None:
                continue
            if index and fit["means"][index - 1] is not None:
                pygame.draw.line(self.screen, blue, point(index - 1, fit["means"][index - 1]),
                                 point(index, value), 2)
            pygame.draw.circle(self.screen, blue, point(index, value), 4)
        for index, mean in enumerate(profile["means"]):
            pygame.draw.circle(self.screen, green, point(index, mean), 3)
            label(str(index), (point(index, mean)[0] - 3, right.bottom + 2))
        gy = point(0, observed)[1]
        for gx in range(right.left, right.right, 10):
            pygame.draw.line(self.screen, amber, (gx, gy), (min(gx + 5, right.right - 1), gy))
        measured = point(hw, observed)
        pygame.draw.line(self.screen, amber, point(hw, predicted), measured, 2)
        pygame.draw.circle(self.screen, amber, measured, 4)
        for x, title, direction in ((20, "< Previous", -1), (130, "Next >", 1)):
            rect = pygame.Rect(x, height - 26, 100, 22)
            pygame.draw.rect(self.screen, (35, 59, 73), rect, border_radius=3)
            label(title, (x + 8, height - 23))
            self.trace_buttons.append((rect.move(0, 40), direction))
        label("Green: profile | Blue: secret-key candidate fit | Amber: sample", (250, height - 23))

    def draw_profile(self, width, height):
        profile = self.plot
        counts, means = profile["counts"], profile["values"]
        filled = sum(n > 0 for n in counts)
        def label(text, pos, color=(173, 193, 211), font=None):
            self.screen.blit((font or self.small_font).render(text, True, color), pos)
        label("PROFILE NOTEBOOK / measured class statistics", (20, 12), (111, 231, 181))
        key = f"0x{profile['key']:02X}" if profile["key"] is not None else "--"
        sample = str(profile["sample"]) if profile["sample"] is not None else "--"
        state = "submitted" if profile["accepted"] else ("ready / not submitted" if profile.get("ready") else ("incomplete" if filled < 9 else "not ready"))
        label(f"Sample: {sample} | FIXED key: {key} | {filled}/9 classes | {state}", (20, 34))
        inputs = profile.get("inputs")
        if inputs:
            preview = ",".join(map(str, inputs))
            if len(preview) > 48:
                preview = preview[:45] + "..."
            label(f"Varying plaintexts: {preview} | {profile.get('trials', 20)} trials/input", (20, 52))
        else:
            label("Plaintexts: not selected (byte values 0-255)", (20, 52))
        table_width = min(390, width - 40)
        columns = [20 + int(table_width * fraction) for fraction in (0, .15, .39, .7)]
        row_height = max(8, min(22, (height - 92) // 11))
        font = (self.axis_font if row_height >= 19 else
                pygame.font.SysFont("monospace", max(8, row_height - 2)))
        for text, x in zip(("HW", "Traces", "Mean (a.u.)", "Std dev"), columns):
            label(text, (x, 82), font=font)
        for hw in range(9):
            y = 82 + (hw + 1) * row_height
            color = (111, 231, 181) if counts[hw] else (104, 123, 142)
            mean = f"{means[hw]:.3f}" if counts[hw] else "--"
            std = f"{profile['stddev'][hw]:.3f}" if counts[hw] else "--"
            if hw % 2 == 0:
                pygame.draw.rect(self.screen, (23, 34, 46),
                                 (16, y - 1, table_width + 8, row_height))
            for text, x in zip((str(hw), str(counts[hw]), mean, std), columns):
                label(text, (x, y), color, font)
        if width < 740 or height < 230:
            return
        plot = pygame.Rect(455, 84, max(1, width - 485), max(1, height - 125))
        label("Mean relative power (a.u.)", (plot.left, plot.top - 18))
        pygame.draw.rect(self.screen, (13, 20, 29), plot)
        observed = [value for value in means if value is not None]
        low, high = (min(observed), max(observed)) if observed else (-1, 1)
        padding = max((high - low) * .15, .5)
        low, high = low - padding, high + padding
        def point(hw, value):
            return (plot.left + hw * (plot.width - 1) / 8,
                    plot.bottom - 1 - (value - low) / (high - low) * (plot.height - 1))
        for fraction in (0, .5, 1):
            value = low + fraction * (high - low)
            gy = point(0, value)[1]
            pygame.draw.line(self.screen, (40, 53, 66), (plot.left, gy), (plot.right - 1, gy))
            label(f"{value:.1f}", (plot.left - 40, gy - 7))
        for hw, mean in enumerate(means):
            x = point(hw, low)[0]
            label(str(hw), (x - 4, plot.bottom + 4))
            if mean is None:
                continue
            pos = point(hw, mean)
            if hw and means[hw - 1] is not None:
                pygame.draw.aaline(self.screen, (111, 231, 181), point(hw - 1, means[hw - 1]), pos)
            pygame.draw.circle(self.screen, (111, 231, 181), pos, 4)
        label("Hamming weight of S-box output", (plot.left, plot.bottom + 23))

    def draw_chart(self, width, height):
        chart = self.plot
        font = self.small_font
        def label(text, pos, color=(173, 193, 211)):
            self.screen.blit(font.render(text, True, color), pos)
        label(chart["title"], (20, 12), (111, 231, 181))
        label(chart["subtitle"], (20, 34))
        plot = pygame.Rect(70, 68, max(1, width - 100), max(1, height - 115))
        values = chart["values"]
        low, high = min(values), max(values)
        padding = max((high - low) * 0.15, 0.1)
        low, high = low - padding, high + padding
        def point(index, value):
            return (plot.left + index * (plot.width - 1) / max(1, len(values) - 1),
                    plot.bottom - 1 - (value - low) * (plot.height - 1) / (high - low))
        pygame.draw.rect(self.screen, (13, 20, 29), plot)
        for fraction in (0, .5, 1):
            value = low + fraction * (high - low)
            gy = point(0, value)[1]
            pygame.draw.line(self.screen, (40, 53, 66), (plot.left, gy), (plot.right, gy))
            label(f"{value:.2f}", (4, gy - 7))
        points = [point(i, value) for i, value in enumerate(values)]
        pygame.draw.aalines(self.screen, (111, 231, 181), False, points)
        if chart.get("markers"):
            for index, pos in enumerate(points):
                pygame.draw.circle(self.screen, (111, 231, 181), pos, 4)
                label(str(index), (pos[0] - 4, plot.bottom + 4))
        else:
            label("0", (plot.left, plot.bottom + 4))
            label(str(len(values) - 1), (plot.right - 24, plot.bottom + 4))
        if "highlight" in chart:
            best = chart["highlight"]
            pygame.draw.circle(self.screen, (255, 190, 100), points[best], 5)
        label(chart["xlabel"], (max(70, plot.centerx - 135), plot.bottom + 22))
        label(chart["ylabel"], (70, 51))

    def draw_ttest(self, width, height):
        chip_number, fixed_count, random_count, plaintext, values, threshold = self.analysis
        font = self.small_font
        def label(text, pos, color=(173, 193, 211)):
            self.screen.blit(font.render(text, True, color), pos)
        label(f"CHIP {chip_number} / WELCH T-TEST | {fixed_count} fixed / {random_count} random | byte={plaintext}", (20, 12),
              (111, 231, 181))
        label(f"Y: Welch t (unitless) | X: time (sample index) | thresholds: +/-{threshold:g}", (20, 34))
        plot = pygame.Rect(65, 65, max(1, width - 90), max(1, height - 124))
        finite = [abs(value) for value in values if math.isfinite(value)]
        limit = max(6, max(finite, default=0) * 1.15, threshold)
        def y(value):
            value = max(-limit, min(limit, float(value)))
            return plot.centery - value / limit * (plot.height / 2)
        pygame.draw.rect(self.screen, (13, 20, 29), plot)
        last = len(values) - 1
        def x(index):
            return plot.left + round(index * (plot.width - 1) / max(1, last))
        # Keep labels separated as the window shrinks, while retaining both endpoints.
        minimum_gap = 64
        step = next((step for step in (10, 20, 25, 50, 100, 200)
                     if step * (plot.width - 1) / max(1, last) >= minimum_gap), 200)
        ticks = [0] + [i for i in range(step, last, step)
                       if x(last) - x(i) >= minimum_gap] + [last]
        for index in range(0, last + 1, max(1, step // 4)):
            gx = x(index)
            pygame.draw.line(self.screen, (29, 41, 54),
                             (gx, plot.top), (gx, plot.bottom - 1))
            pygame.draw.line(self.screen, (83, 103, 122),
                             (gx, plot.bottom), (gx, plot.bottom + 3))
        for index in ticks:
            gx = x(index)
            pygame.draw.line(self.screen, (47, 64, 81),
                             (gx, plot.top), (gx, plot.bottom - 1))
            pygame.draw.line(self.screen, (173, 193, 211),
                             (gx, plot.bottom), (gx, plot.bottom + 6))
            tick = self.axis_font.render(str(index), True, (211, 224, 235))
            self.screen.blit(tick, (gx - tick.get_width() // 2, plot.bottom + 8))
        for value in (-limit, 0, limit):
            gy = y(value)
            pygame.draw.line(self.screen, (40, 53, 66), (plot.left, gy), (plot.right, gy))
            label(f"{value:.1f}", (4, gy - 7))
        for value in (-threshold, threshold):
            gy = y(value)
            for dash_x in range(plot.left, plot.right, 12):
                pygame.draw.line(self.screen, (238, 161, 104),
                                 (dash_x, gy), (min(dash_x + 6, plot.right), gy))
            label(f"{value:+g}", (4, gy - 7), (238, 161, 104))
        points = [(plot.left + i * (plot.width - 1) / (len(values) - 1), y(value))
                  for i, value in enumerate(values)]
        pygame.draw.aalines(self.screen, (111, 231, 181), False, points)
        if self.pointer is not None and plot.collidepoint(self.pointer):
            index = round((self.pointer[0] - plot.left) * last / max(1, plot.width - 1))
            gx, gy = x(index), y(values[index])
            pygame.draw.line(self.screen, (204, 218, 231),
                             (gx, plot.top), (gx, plot.bottom - 1))
            pygame.draw.circle(self.screen, (255, 197, 112), (gx, gy), 4)
            text = f"Sample {index} | t = {values[index]:+.3f}"
        else:
            text = "Hover for sample / t-value"
        readout = self.axis_font.render(text, True, (255, 197, 112))
        readout_x = max(plot.left, plot.right - readout.get_width())
        if readout_x - plot.left >= 120:
            label("Sample index", (plot.left, height - 23))
        self.screen.blit(readout, (readout_x, height - 23))

    def set_traces(self, traces, plaintext):
        """Keep a snapshot; redraws must not acquire new measurements."""
        self.analysis = None
        self.plot = None
        self.traces = [list(trace) for trace in traces]
        self.plaintext = plaintext
        self.capture_count += 1

    def draw_dashboard(self, width, height):
        self.screen.set_clip(pygame.Rect(0, 0, width, height))
        self.screen.fill((19, 28, 39), (0, 0, width, height))

        def label(text, position, color=(173, 193, 211)):
            self.screen.blit(self.small_font.render(text, True, color), position)

        if self.plot is not None or self.analysis is not None:
            if self.plot is not None:
                if self.plot.get("kind") == "recovery":
                    self.draw_recovery(width, height)
                elif self.plot.get("kind") == "profile":
                    self.draw_profile(width, height)
                else:
                    self.draw_chart(width, height)
            else:
                self.draw_ttest(width, height)
            self.screen.set_clip(None)
            pygame.draw.line(self.screen, (65, 88, 107), (0, height), (width, height), 2)
            return
        label("SIMULATED POWER TRACES / one capture per chip", (20, 12), (111, 231, 181))
        if not self.traces:
            label("Enter your username below to initialize the chips.", (20, 44))
            label("Power traces and measurement statistics will appear here.", (20, 66))
        else:
            label("Power during one modeled AES S-box operation, including measurement noise.", (20, 34))
            label(f"Y: relative power (a.u.) | X: time (sample index) | "
                  f"Capture {self.capture_count} | Plaintext 0x{self.plaintext:02X}", (20, 52))
            low = min(min(trace) for trace in self.traces)
            high = max(max(trace) for trace in self.traces)
            span = max(high - low, 1.0)
            low -= span * 0.08
            high += span * 0.08
            colors = [(111, 231, 181), (102, 183, 255), (230, 183, 105), (194, 152, 247)]
            card_width = max(1, (width - 48) // 2)
            card_height = max(1, (height - 90) // 2)
            for index, trace in enumerate(self.traces[:4]):
                x = 20 + (index % 2) * (card_width + 8)
                y = 80 + (index // 2) * (card_height + 4)
                mean = sum(trace) / len(trace)
                rms = math.sqrt(sum(value * value for value in trace) / len(trace))
                label(f"CHIP {index + 1} | {len(trace)} samples | mean {mean:.2f} | RMS {rms:.2f}",
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
                label("0", (plot.left, plot.bottom + 3))
                label("Time (sample index)", (max(plot.left + 20, plot.centerx - 72), plot.bottom + 3))
                label(str(len(trace) - 1), (plot.right - 24, plot.bottom + 3))
        self.screen.set_clip(None)
        pygame.draw.line(self.screen, (65, 88, 107), (0, height), (width, height), 2)

    def draw_stage_header(self, width):
        labels = ("1  Leak assessment", "2  Profiling", "3  Key recovery")
        if width < 740:
            labels = ("1  Assess", "2  Profile", "3  Recover")
        for index, title in enumerate(labels):
            left = index * width // 3
            right = (index + 1) * width // 3
            current = self.stage_index == index
            done = self.stage_index is not None and self.stage_index > index
            background = (35, 59, 73) if current else (17, 25, 34)
            color = (229, 242, 249) if current else ((111, 231, 181) if done else (107, 126, 144))
            pygame.draw.rect(self.screen, background, (left, 0, right - left, 38))
            if current or done:
                pygame.draw.line(self.screen, color, (left + 8, 37), (right - 8, 37), 2)
            text = self.small_font.render(title, True, color)
            self.screen.blit(text, (left + 12, 12))

    def draw(self):
        self.poll_analysis()
        width, height = self.screen.get_size()
        self.screen.fill((15, 20, 27))
        split = height // 2
        # Charts use local coordinates beneath the persistent stage strip.
        screen, pointer = self.screen, self.pointer
        header = min(40, max(0, split - 1))
        try:
            self.screen = screen.subsurface((0, header, width, max(1, split - header)))
            if pointer is not None:
                self.pointer = (pointer[0], pointer[1] - header)
            self.draw_dashboard(width, max(1, split - header))
        finally:
            self.screen, self.pointer = screen, pointer
        self.draw_stage_header(width)
        self.screen.set_clip(pygame.Rect(0, split + 2, width, height - split - 2))
        line_height = self.font.get_linesize()
        cell_width = self.font.size("M")[0]
        columns = max(1, (width - 40) // cell_width)
        rows = max(1, (height - split - 112) // line_height)
        wrapped = []
        for line, color in zip(self.lines, self.line_colors):
            heading = re.match(r"^[A-Za-z][A-Za-z0-9 /()_-]{0,62}:", line)
            bold_end = heading.end() if heading and color == self.OUTPUT_COLOR else 0
            segments = textwrap.wrap(line, columns, replace_whitespace=False,
                                     drop_whitespace=False, expand_tabs=False) or [""]
            offset = 0
            for segment in segments:
                bold_count = max(0, min(len(segment), bold_end - offset))
                wrapped.append((segment, color, bold_count))
                offset += len(segment)
        self.scroll = min(self.scroll, max(0, len(wrapped) - rows))
        end = len(wrapped) - self.scroll
        for index, (line, color, bold_count) in enumerate(wrapped[max(0, end - rows):end]):
            y = split + 20 + index * line_height
            x = 20
            if bold_count:
                heading = self.bold_font.render(line[:bold_count], True, color)
                self.screen.blit(heading, (x, y))
                x += heading.get_width()
            self.screen.blit(self.font.render(line[bold_count:], True, color), (x, y))
        pygame.draw.line(self.screen, (48, 64, 78), (20, height - 83), (width - 20, height - 83))
        # Horizontally scroll long input to keep the insertion point visible.
        full_input = self.prompt + self.input
        cursor_column = len(self.prompt) + self.cursor
        start = max(0, cursor_column - columns + 1)
        self.screen.blit(self.font.render(full_input[start:start + columns], True, self.INPUT_COLOR),
                         (20, height - 68))
        if pygame.time.get_ticks() % 1000 < 500:
            x = 20 + (cursor_column - start) * cell_width
            pygame.draw.line(self.screen, (111, 231, 181), (x, height - 68),
                             (x, height - 68 + line_height - 2), 2)
        if self.analysis_future is not None:
            done, total = self.job_progress
            hint = f"RUNNING {done}/{total} ({100 * done // max(1, total)}%) | cancel-capture to stop"
        else:
            hint = f"{self.stage_text} | help / show-stage-goal"
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
            self.cancel_event.set()
            self.executor.shutdown(wait=False, cancel_futures=True)
            pygame.quit()
