# VLX-Flow Release Checklist

## First Public Release

- [x] English README
- [x] Chinese README
- [x] Logo asset
- [x] Overview figure
- [x] TTFT comparison figure
- [x] Demo video asset
- [x] Apache-2.0 license
- [x] Contribution guide
- [x] Release status document
- [ ] Final project page URL
- [ ] Final VLX website URL
- [ ] Inference code release
- [ ] Checkpoint release
- [ ] Install instructions
- [ ] Inference quick start

## Release Boundary

The first release may publish documentation, figures, and demo materials before inference code or checkpoints are available. README and website copy must use explicit "Coming soon" wording for unavailable artifacts. Training code is not part of the planned public release scope and should not be described as coming soon.

## Copy Checks

- [x] README avoids runnable install commands before inference code release.
- [x] README_zh avoids runnable install commands before inference code release.
- [x] README and README_zh both distinguish available artifacts from coming-soon artifacts.
- [x] Contribution guide limits current contribution scope to documentation and release clarity.
- [ ] Project page URL is added after the final VLX website URL is known.
- [ ] GitHub repository URL is added to the website after publication.

## Asset Checks

- [x] `assets/figures/logo.png`
- [x] `assets/figures/vlx-flow-overview.png`
- [x] `assets/figures/ttft-comparison.png`
- [x] `assets/demo/VLX-Flow.mp4`
- [x] Demo video file is retained, but README video embed stays commented out until GitHub rendering is confirmed.
