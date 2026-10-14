# Controller follow-up

Handheld validation — October 13, 2026.

- [x] D-pad F-key mappings: confirmed working by the user, 10/10.
- [ ] Left-stick mapping: current priority. With Moonlight mouse emulation off,
  capture raw X/Y values at center, cardinal positions, diagonals, and through
  full clockwise/counterclockwise rotations. Confirm axis directions, ranges,
  center drift, and deadzones before mapping the full stick.
  - [x] Raw capture received: active device was `/dev/input/event28`; L-stick
    uses `ABS_X` and `ABS_Y`. Observed X range: -32766 to 32766; observed Y
    range: -32767 to 32765. Both started and ended at 0. Right-stick axes,
    triggers, and D-pad hats remained at 0 during the L-stick capture.
  - [x] Vertical action chosen: zoom. L-stick up/down now sends rate-limited
    wheel up/down; bumpers retain camera tilt. No mouse emulation is required.
  - [x] Implement directional filtering to avoid unwanted zoom during horizontal
    rotation. A held-right sample had Y=-10679 (~33% of full travel), enough
    to cross the existing 25% threshold if applied independently to Y.
    Timed prompts overlapped some movements; the capture was sampled at 5 Hz,
    so it does not establish smoothness or exact clockwise/counterclockwise paths.
    Default minor-axis cutoff is 50% of the dominant axis; deliberate diagonals
    retain both rotation and zoom. Zoom defaults to at most six wheel ticks/second.
  - [ ] Validate the new mapping on the handheld: cardinal rotation/zoom,
    diagonals, center release, focus changes, and reconnects. Keep the pointer
    over the game viewport when testing wheel zoom; tune rate/direction if needed.
- [ ] Right-stick behavior: not yet confirmed working as intended. Capture raw
  controller events through full rotations in both directions, including
  cardinal positions, diagonals, and return to center. Identify the actual axes,
  ranges, and deadzones, then improve the mapping and verify virtual mouse behavior.
- [x] D-pad up/down scrolling overlap occurs in mouse emulation mode; the user
  reports it does not occur with mouse emulation off. Use normal controller mode
  for the stick mapping work.
