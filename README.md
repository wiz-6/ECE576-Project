# ECE 576 Chip Lab

Run the game in its Pygame terminal window:

```bash
python -m pip install -r requirements.txt
python main.py
```

Enter your WPI username to initialize the game, then type `help` to see commands.
Use Enter to submit, Up/Down to recall commands, and the mouse wheel or
Page Up/Page Down to scroll output. Left/Right, Home/End, Backspace, and Delete
edit the current line. Ctrl+C clears the current input. Type `exit` or close the
window to quit. The window can be resized.

The top half of the window shows the four chip traces on a shared amplitude
scale, with sample counts, mean values, and RMS amplitudes. Chip identities
remain hidden. The bottom half contains the terminal. An initial capture uses
plaintext 0; use `trace` or `trace 42` to acquire a new measurement for all chips.
Traces remain visible until the next capture.

Run `ttest 2 5000 0` to collect 5,000 fixed-plaintext and 5,000 random-plaintext
traces from chip 2 using fixed byte 0 and the same secret key for both groups.
`ttest 2` uses 1,000 traces per group and fixed byte 0. The top panel switches to
a Welch t-statistic curve with thresholds at +4.5 and -4.5; the terminal reports
the peak absolute t-value and number of threshold crossings. Collection runs in
the background. Use `trace` after completion to return to the four-chip view.

The test uses unbiased sample variances at each sample index. A threshold
crossing suggests leakage; a result below the threshold does not establish
that a chip is leakage-free. Results depend on noise, trace count, and the chosen
fixed plaintext (some fixed values produce less mean separation).

Use `guess 2` to guess that chip 2 is leaky. A correct guess prints a win message;
an incorrect guess lets you try again. You can continue using the terminal after winning.
