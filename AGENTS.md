# ore-music-player

## Non-Negotiable Editing Rules

- Do not create, edit, delete, or revert project files unless the user explicitly asks for that exact file operation.
- Requests such as "続けましょう", "お願いします", or "進めましょう" do not authorize file changes. In those cases, inspect and explain only.
- Before any file-editing tool call, state the exact files to change, why each file must change, and the focused validation command.
- If the user has not explicitly authorized the change, stop before editing.
- Review requests are read-only. Sample-code requests produce chat responses only. Implementation requires explicit user authorization.
- Test execution must not modify project files unless the user explicitly requests generated-file changes.
- Never revert user changes or previously requested documentation changes. Before reverting, identify the exact unauthorized changes and report them.

## Project Status

- This repository is being rebuilt as a clean-room personal music player.
- The tracked wxPython prototype was intentionally removed from the working tree. Do not restore legacy files or treat the old architecture as the target unless the user explicitly asks for it.
- The domain playback model, application services, SQLite persistence, libmpv backend, bootstrap, PySide6 UI, and package entrypoint are implemented.
- The application is runnable with `python -m ore_music_player` when the Windows mpv shared DLL is present under the local, ignored `vendor/mpv/` directory.
- Source separation, per-part volume control, and chord analysis remain intentionally unimplemented.
- The current repeatable validation commands are `python -m pytest -q` and `python -m ruff check src tests` from the project root.

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

## Current Implementation Boundary

- Implemented domain types: `Track`, `LoopRegion`, `PlaybackSettings`, `PlaybackState`, and `PlaybackStatus`.
- Implemented playback rules: speed validation from `0.50` to `1.50` in `0.05` steps, play/pause/stop, seeking, A/B points, and loop state.
- Implemented application service: `PlaybackService` coordinates the domain state with the `PlaybackBackend` protocol.
- Implemented tests: domain, playback-service, playlist, SQLite repository, and PlaylistView tests currently pass 43 tests.
- Implemented UI scope: multi-file and recursive folder loading, playback queue navigation, seeking, A/B points, A/B looping, speed control, and playlist CRUD with multi-track add/remove.
- Not implemented or limited: playlist folder import, playlist reorder UI, queue listing/shuffle/repeat details, missing-file warnings and skip behavior, source separation, per-part volume control, and chord analysis.

## Design Before Implementation

- Do not modify project files during product or architecture discussion unless the user explicitly requests implementation.
- If the user has previously asked not to implement, require an explicit implementation request such as "実装を開始して" or "コードを書いて" before editing. Do not treat ambiguous confirmations such as "お願いします", "了解", or "進めましょう" as permission to edit; ask for confirmation when the intent is unclear.
- Confirmed implementation choices: PySide6 for the GUI, `python-mpv`/libmpv for playback, SQLite for playlist persistence, and `audio_pitch_correction=True` for mpv playback speed changes.
- Supported file filters currently exposed by the UI are `.mp3`, `.wav`, `.flac`, `.m4a`, and `.ogg`.
- Before extending the application, confirm any new GUI behavior, playback backend behavior, supported audio formats, persistence changes, and time-stretching assumptions.
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
- The current implementation uses libmpv and requires a local Windows shared DLL (`libmpv-2.dll`, `mpv-2.dll`, or `mpv-1.dll`) under `vendor/mpv/`.
- Keep real audio-device and format checks separate from the regular domain/UI test suite.
- Record package versions, supported formats, and platform limitations when changing the playback backend.

## Legacy Context

- The removed prototype used wxPython/wxGlade for its GUI and pygame.mixer plus mutagen for MP3 playback and metadata.
- Those technologies are historical context only. Reuse them only after evaluating whether they support accurate seeking, time stretching, future source separation, and the target platforms.
- Do not reintroduce hard-coded personal music paths, generated GUI files, or image assets from the prototype.

## Validation Expectations

- Add focused tests for playlist ordering, A-B loop boundaries, speed state, and persistence before relying on UI-level tests.
- Keep audio-device and file-format checks separate from pure domain tests.
- The smallest repeatable validation command is `python -m pytest -q` followed by `python -m ruff check src tests` from the project root.
- Set `QT_QPA_PLATFORM=offscreen` on headless environments before running the Qt tests.
- After each focused change, run the smallest relevant test first and then the full validation commands before reporting completion.