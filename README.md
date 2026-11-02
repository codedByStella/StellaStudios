# StellaStudios

> **Project status: Retired · Historical implementation**
>
> StellaStudios is a retired audiovisual production pipeline. Its original video-generation integration depended on OpenAI Sora, which has since closed. As a result, the original system is no longer functional as a complete end-to-end application.
>
> The architecture separates video generation behind a dedicated provider integration. Rebooting the pipeline was designed to be straightforward: replace the Sora model call while retaining the existing orchestration, metadata handling, media-processing stages, and FFmpeg assembly.
>
> This repository is a portfolio publication for technical inspection, not an actively maintained or supported application. It documents the original implementation and is not presented as a currently operational service.

**AI-assisted, human-directed development.** StellaStudios is a Python-based audiovisual production pipeline built to coordinate creative metadata, video generation, synthetic narration, soundtrack selection, subtitle creation, and automated video assembly.

> **Historical source showcase.** This repository preserves the engineering structure and implementation of the original project. It is published to demonstrate the architecture, integrations, orchestration, media-processing workflow, and engineering decisions. It is not intended to represent a currently deployable production service.

## Project overview

StellaStudios was developed to turn a structured creative brief into an assembled short-form video through a sequence of specialized processing stages.

Rather than treating video creation as one generative request, the application coordinates separate services and local processing components. Each stage produces an artifact that is handed to subsequent stages for processing and assembly.

The original workflow includes:

- Structured creative metadata generated through GPT.
- Video generation through the Sora integration.
- Synthetic narration through ElevenLabs.
- Selection and processing of existing soundtrack assets.
- Phrase-level subtitle generation in Advanced SubStation Alpha (ASS) format.
- Audio processing and video assembly through FFmpeg.
- Watermark compositing.
- Artifact archiving and downstream publishing integrations.

The original system also included scheduled orchestration and uploader components. Those capabilities are documented as part of the historical implementation, not represented as currently operating services.

## Pipeline workflow

The original pipeline separates creative generation, media processing, and final assembly.

### 1. Creative metadata

A GPT integration converts the creative brief and selected preset into structured JSON metadata.

The metadata provides downstream stages with a shared description of the intended content, narration, and production parameters.

The implementation includes validation for required fields, unexpected keys, string types, forbidden characters, configured word ranges, and hashtag counts.

### 2. Soundtrack selection

The music stage selects an existing soundtrack from a local asset collection.

It inspects available audio duration, selects an appropriate segment, and uses FFmpeg to extract and process the resulting clip.

This stage is asset selection and processing, not live music generation from the creative metadata.

### 3. Narration synthesis

The ElevenLabs integration generates synthetic narration from the prepared script.

The resulting audio is saved as a separate artifact for use during subtitle generation and final assembly.

### 4. Subtitle generation

The subtitle stage processes the narration text, removes supported voice markers, divides the text into phrases, and distributes subtitle cues across the measured audio duration.

It generates styled ASS subtitle files with configured typography, outlines, and visual effects.

Subtitle timing is phrase-level and duration-based. It is not word-level timestamp alignment.

### 5. Video generation

The original video-generation integration used OpenAI Sora.

The dedicated video node submits the scene prompt, handles the provider's generation workflow, retrieves the resulting video, and saves it for downstream processing.

**This integration is retired.** Sora has closed, so the original provider call can no longer complete its intended workflow.

The video-generation boundary is isolated from the rest of the pipeline. The intended reactivation path is to replace the Sora model call while retaining the surrounding orchestration and media-processing architecture.

### 6. Media assembly

The stitcher combines the separate media artifacts using FFmpeg.

The assembly process handles:

- Video input.
- Synthetic narration.
- Selected soundtrack.
- Subtitle rendering.
- Audio mixing and processing.
- Optional watermark compositing.

The result is a single assembled video artifact.

### 7. Archiving and publishing

The archiver organizes completed production artifacts and handles their movement into the archive.

The wider project also contains separate uploader integrations and scheduled orchestration components. These are part of the historical source, not an assertion that automated publishing is currently active.

## Architecture

The application is organized into specialized modules rather than one monolithic production script.

| **Component** | **Responsibility** |
|---|---|
| `engine/parts/gpt/` | Creative metadata generation, presets, and output validation |
| `engine/parts/music/` | Local soundtrack selection, extraction, and audio processing |
| `engine/parts/elevenlab/` | Synthetic narration generation |
| `engine/parts/sora/` | Historical Sora video-generation integration |
| `engine/parts/subtitler/` | Phrase segmentation and ASS subtitle generation |
| `engine/parts/stitcher/` | FFmpeg-based media assembly and watermark processing |
| `engine/parts/wiring/` | Pipeline coordination and artifact archiving |
| `engine/parts/core/` | Shared configuration and secret resolution |
| `engine/parts/autonomous/` | Scheduled orchestration |
| `engine/daemons/uploader/` | Downstream publishing integrations |
| `engine/parts/youtube/` | YouTube upload integration |

### Engineering considerations

Several implementation decisions are central to StellaStudios.

- **Specialized processing nodes:** Creative generation, narration, soundtrack processing, subtitles, video generation, and assembly are separate responsibilities.
- **Structured metadata:** A shared metadata contract provides consistent information to downstream processing stages.
- **Slug-aware handoffs:** Production identifiers are propagated through media stages to help associate artifacts with the intended job.
- **Shared secret resolution:** External service credentials are handled through a common configuration layer.
- **Bounded processing:** External media processes and selected requests use timeouts rather than being allowed to wait indefinitely.
- **Artifact protection:** Metadata creation and archival use collision-aware handling to reduce accidental overwrites.
- **Failure containment:** Publishing integrations record submission intent and distinguish confirmed rejection from ambiguous outcomes, avoiding blind automatic retries when an upload's result is uncertain.
- **Modular video integration:** The Sora dependency is isolated behind its own processing node, keeping the surrounding pipeline independent of the specific video-generation model.

These mechanisms demonstrate deliberate failure handling and modular design. They do not establish complete concurrency isolation or automatic recovery from every possible failure.

## Technology

- Python
- OpenAI GPT API
- OpenAI Sora API (retired integration)
- ElevenLabs API
- FFmpeg
- FFprobe
- Advanced SubStation Alpha (ASS)
- Dropbox integration
- YouTube Data API
- Scheduled Python orchestration
- JSON-based metadata and configuration

## AI-assisted development methodology

StellaStudios was developed through an iterative, AI-assisted process. AI is disclosed as part of the development methodology, not hidden or presented as unaided authorship.

Models were used to accelerate implementation, explore alternatives, and investigate unfamiliar problems. Their output was not treated as authoritative. The engineering value comes from how the tools are directed, challenged, and held accountable to the wider application context.

### 1. Challenge the reasoning

Proposed implementations are interrogated rather than accepted at face value. Their assumptions are questioned, and design decisions are expected to have a defensible rationale. Models are allowed to explore beyond the immediate task when a detour may expose a useful conflict, application, or overlooked use case, provided the reasoning holds up. Agreement is not the objective; finding the strongest defensible solution is.

### 2. Account for failure modes

Context-window limits, conversational drift, hallucinations, and stateless API calls all affect reliability. Weak information sources and search systems that reward visibility rather than accuracy introduce further risks. A confident answer can still be wrong, incomplete, or detached from the actual implementation. Those limitations must be accounted for rather than mistaking fluency for evidence.

### 3. Verify, don't defer

Models can reframe a question, narrowly rebut a claim while missing its substance, distort emphasis, construct strawmen, or dismiss inconvenient evidence. Discussions are brought back to their original context, and disagreements are investigated rather than resolved by automatically accepting either the model's conclusion or the developer's own. Model reasoning is adopted only when it withstands scrutiny.

**The principle:** AI can generate possibilities, challenge assumptions, and accelerate execution. It cannot be trusted to police its own reasoning. That responsibility stays with the operator, who must preserve context, demand intellectual honesty, and verify that an answer has merit before building on it.

AI assistance is therefore treated as a development tool, not a substitute for engineering judgment. Responsibility for requirements, architecture, integration, review, verification, and final implementation decisions remains with the developer.

## Retirement and reactivation

StellaStudios is retired because its original video-generation provider, Sora, has closed.

The project was structured so that video generation is handled by a dedicated node rather than being embedded throughout the application. This separation means the intended reactivation path does not require rebuilding the entire pipeline.

Replacing the Sora model call allows the surrounding system to retain its existing responsibilities:

- Creative metadata generation.
- Production coordination and artifact handoffs.
- Narration synthesis.
- Soundtrack selection and processing.
- Subtitle generation.
- FFmpeg assembly and watermarking.
- Artifact archiving.

The replacement provider would need to satisfy the video node's expected integration contract. The architectural intent, however, is a localized model replacement rather than a wholesale redesign.

No replacement provider has been integrated or tested in this retired publication.

## Limitations

This repository documents a historical implementation, not an active service.

- The original Sora integration no longer functions.
- The original end-to-end workflow cannot currently complete.
- The scheduled publishing cycle is not active.
- Shared staging storage does not provide complete per-job concurrency isolation.
- Subtitle timing is phrase-level and duration-based, not word-accurate alignment.
- External model output and provider availability remain outside the application's control.
- Source inspection does not establish current end-to-end operation or a verified reboot with another provider.

These limitations are stated to distinguish implemented functionality from intended behavior and historical operation.

## Publication scope

This repository is published as a technical showcase of StellaStudios.

The source demonstrates the original architecture, module boundaries, service integrations, processing workflow, artifact handling, and engineering decisions. It should not be interpreted as a supported installation, active hosted service, or currently functional video-generation product.

The historical Sora integration is retained as part of the project's implementation history. Its presence does not imply that the provider remains available.

## Copyright and usage

Copyright © 2026 codedByStella. All rights reserved.

This repository is published for portfolio and technical-demonstration purposes only. No permission is granted to copy, modify, distribute, sublicense, or commercially use this code without prior written authorization.
