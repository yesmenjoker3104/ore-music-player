# ore-music-player

## Project Status

- This repository is being rebuilt as a clean-room personal music player.
- The tracked wxPython prototype was intentionally removed from the working tree. Do not restore legacy files or treat the old architecture as the target unless the user explicitly asks for it.
- A source and test scaffold now exists, but the placeholder files contain no application code yet. Do not treat the scaffold as a runnable application.
- There is currently no runnable entrypoint or approved build/test command. Document exact commands here when implementation makes them valid.

## Product Direction

- Required first-release capabilities: playlists, A-B loop playback, and slower playback speed.
- Planned capabilities: per-part volume control after source separation, and chord-progression analysis.
- Keep playback, playlist state, audio processing, and analysis independent enough that future DSP or ML features do not require rewriting the UI.

## Development Policy

- Use Python 3.13 as the project baseline and create environments in `.venv`.
- Treat `pyproject.toml` as the source of truth for runtime and development dependencies, tooling, and the supported Python range.
- Keep application code under `src/ore_music_player/` and focused tests under `tests/` once implementation begins.
- Use SQLite for playlist and analysis metadata; keep generated audio assets in a file cache rather than storing binary audio in the database.
- Do not hard-code personal music directories, device-specific paths, or credentials.
- Do not add an unverified playback backend as a runtime dependency. Confirm seeking, A-B looping, speed range, supported formats, and pitch-preserving time stretch in a disposable probe first.
- Keep long-running source-separation and chord-analysis work off the UI and playback threads.
- Update `DESIGN.md` when a product or architecture decision changes, and update `README.md` when setup or usage changes.

## Design Before Implementation

- Do not modify project files during product or architecture discussion unless the user explicitly requests implementation.
- If the user has previously asked not to implement, require an explicit implementation request such as "実装を開始して" or "コードを書いて" before editing. Do not treat ambiguous confirmations such as "お願いします", "了解", or "進めましょう" as permission to edit; ask for confirmation when the intent is unclear.
- Before implementation, confirm the GUI toolkit, playback backend, supported audio formats, playlist persistence format, and the time-stretching approach for slow playback.
- Prefer a layered design with domain state and use cases separate from platform/audio adapters and UI code.
- Treat A-B loop points and playback speed as application state, not as widget-only state, so they can be tested without opening the UI.
- Keep audio analysis behind an explicit service boundary; analysis must not block the playback or UI thread.

## Before Editing

- In a multi-root workspace, verify the checkout before reading or editing project files. Run `git rev-parse --show-toplevel`, `git remote get-url origin`, and `git status --short --branch` from the intended repository.
- Confirm that the repository root is the intended `ore-music-player` checkout and that its remote points to `yesmenjoker3104/ore-music-player`. Do not rely on the terminal's parent directory or the active editor file alone.
- If the repository identity cannot be confirmed, stop and ask the user rather than editing another workspace folder.
- Before implementation, classify decisions as `Confirmed`, `Proposed`, or `Open`. Do not promote a proposal into a requirement without user confirmation.
- At the implementation boundary, summarize the confirmed requirements, unresolved decisions, affected files, and the first focused validation command. Record the confirmed product and architecture decisions in `DESIGN.md` before adding substantial code.

## Dependency Spike

- Before committing to a GUI or playback backend, validate it in the selected Python 3.13 virtual environment with a small, disposable probe.
- The probe must verify package imports, opening a generated or fixture audio file, seeking, A-B boundary handling, and the requested speed range.
- Verify that slow playback preserves pitch. Do not describe a backend as compatible with the product requirements based only on a generic playback-rate property.
- Record the tested package versions, supported formats, and any platform limitations before building the main application around the dependency.

## Legacy Context

- The removed prototype used wxPython/wxGlade for its GUI and pygame.mixer plus mutagen for MP3 playback and metadata.
- Those technologies are historical context only. Reuse them only after evaluating whether they support accurate seeking, time stretching, future source separation, and the target platforms.
- Do not reintroduce hard-coded personal music paths, generated GUI files, or image assets from the prototype.

## Validation Expectations

- Add focused tests for playlist ordering, A-B loop boundaries, speed state, and persistence before relying on UI-level tests.
- Keep audio-device and file-format checks separate from pure domain tests.
- After implementation begins, document the smallest repeatable validation command and use it after each focused change.