# Contributing to VLX-Flow

VLX-Flow is currently preparing its first public release. The first release focuses on project positioning, demo assets, technical documentation, and release tracking. Inference code and checkpoint contribution guidelines will be expanded once public artifacts are available.

## Release Boundary

Before inference code and checkpoints are public, contributions should focus on documentation and release clarity. Please do not open pull requests that assume a runnable inference tree exists.

## Current Contribution Scope

- Documentation issues and corrections
- Broken links or asset problems
- Clarifications for VLX-Flow technical descriptions
- Suggestions for examples, tutorials, or release notes
- Bilingual wording improvements for English and Chinese materials

## Not Yet Open

- Training code changes
- Inference code changes
- Checkpoint packaging
- Benchmark reproduction scripts

Inference, checkpoint packaging, and benchmark reproduction areas will be opened after the corresponding public artifacts are released. Training code is not part of the planned public release scope.

## Issue Guidelines

Please keep issues concrete. Include:

- the page or file involved
- what is incorrect or unclear
- the expected wording or behavior when possible

Good issue examples:

- "The README says an artifact is available, but release checklist marks it as coming soon."
- "The Chinese README does not match the English release boundary."
- "The demo video path is broken on GitHub."

## Pull Request Guidelines

For documentation pull requests:

- Keep English and Chinese pages aligned when changing release status or core claims.
- Do not add install, quick-start, or inference commands until code is public.
- Keep asset paths relative to the repository root.
- Prefer small focused changes with a clear reason.
