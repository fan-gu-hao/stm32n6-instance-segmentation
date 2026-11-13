# STM32N6 Real-Time Instance Segmentation and Region Events

[繁體中文](README.md) | **English**

This project uses the STM32N6570-DK and YOLOv8n-seg to cover model export, ST INT8 quantization, NPU compilation and deployment, postprocessing interface adaptation, camera and display integration, UART communication, person-region events, performance and memory experiments, and board acceptance testing.

This English overview corresponds to the Chinese homepage. Detailed reports and historical logs retain their original languages.

## Model and System Pipeline

Model pipeline: original `.pt` → ONNX → SavedModel → ST per-channel INT8 TFLite → ST Edge AI / Neural-ART → N6 model code, weights, and command data.

The ST compilation stage also generates an internal ONNX representation and quantization metadata. The ST-quantized deployment model is distinguished from the INT8 model produced by the export tool.

The production firmware uses a single main loop with camera interrupt callbacks: capture → synchronous inference → segmentation postprocessing → region state update → UART output and display update.

The model, drivers, and core postprocessing retain their upstream origins. The project workflows, adaptation patches, and added application logic are listed below.

## Completed Implementation and Experiments

| Area | Work completed |
| --- | --- |
| Models and environments | Record environment and tool versions; validate the original model on images; test PC webcam inference; export model formats; perform ST per-channel INT8 quantization; verify quantized interfaces; compare three models on the PC |
| Compilation and deployment | Correct postprocessing output mapping; automate pre-deployment header checks; fix local code-generation parameters; analyze NPU compilation and memory allocation; integrate runtime and build settings; fix boot-image alignment and deploy to the board |
| Firmware and communication | Integrate camera and inference flow; add structured UART output, person-region state and display, validity checks and failure handling, and performance instrumentation; archive interrupt-driven UART experiments |
| A2: Correctness validation | Prepare fixed inputs and collect board tensors; diagnose numerical and backend differences; apply common postprocessing and inspect worst cases; run a 50-image regression and investigate individual differences |
| A3: Performance measurement | Measure the full pipeline and logging overhead; repeat inference and profile execution blocks |
| A4: Memory experiments | Check baseline allocation and firmware layout; compare code generation under controlled settings; measure both configurations on the board and verify output regression |
| A1: Sources and rebuild | Freeze sources and verify restoration in an isolated directory; perform a clean rebuild and flash readback verification |
| A5: Board acceptance | Test cold boots and controlled region events; analyze a long-run anomaly and repeat the test; inject a fault and restore production firmware |
| Records and delivery | Preserve versioned evidence and commits for each stage |

The [complete work index](docs/WORK_IMPLEMENTATION_INDEX.md) maps 34 work items to their code, modifications, and results.
The [supplement archive](docs/publication_supplement_20261113/README.md) contains additional historical programs and raw evidence.
The documentation distinguishes completed tests from operational scripts that have not yet been preserved as a complete set. A demonstration video is planned.

See the [engineering workflow and implementation evidence](docs/engineering-workflow.md) for the process overview, model conversion, and interface details.

## Validation Results

| Stage | Main results | Full record |
| --- | --- | --- |
| A1: Sources and rebuild | Source freeze, clean rebuild, flash readback, and restoration verification in an isolated directory completed | [A1 report](docs/a1_reproducible_20260918/README.md) |
| A2: Fixed-input validation | Four-image workflow validation and a 50-image regression completed; N6 person precision 0.870 and recall 0.678 | [A2 report](docs/a2_validation_20260918/README.md) |
| A3: Performance | Mean fixed-input inference time: 48.6066 ms; camera pipeline including logging: approximately 8.066–10.046 frames/s | [A3 report](docs/a3_performance_20260918/README.md) |
| A4: Memory allocation | Compiler-reported physical RAM pool usage reduced by 162.5625 KiB; board outputs for 50 images are byte-for-byte identical to the original N6 baseline | [A4 report](docs/a4_memory_20260918/README.md) |
| A5: Board acceptance | Three cold boots, three entry/exit trials, a 30-minute stability retest, simulated capture timeout, and production firmware restoration passed | [A5 report](docs/a5_acceptance_20260919/README.md) |

The A2 dataset contains 25 images with people and 25 without, with 59 annotated person instances.
PC INT8 person precision / recall is 0.872 / 0.695; N6 achieves 0.870 / 0.678.
These are results from a small, fixed regression set, not standard COCO mAP.

A3 fixed-input inference timing and the full camera cycle cover different scopes.
The full cycle includes capture, inference, postprocessing, display, and logging.

A4 changes the allocatable capacity of `npuRAM6` from 448 KiB to 320 KiB.
Mean inference times for A / B are 48.6079 / 48.5992 ms, a difference of approximately 0.02%.
This difference is not treated as evidence of a meaningful speedup. The production camera firmware retains the original configuration; B remains a validated allocation experiment.

## Main Source Files

| File | Purpose |
| --- | --- |
| [main.c](firmware/Application/STM32N6570-DK/Src/main.c) | Application flow, output, and failure handling |
| [app_camerapipeline.c](firmware/Application/STM32N6570-DK/Src/app_camerapipeline.c) | Camera capture pipeline |
| [project_region_event.h](firmware/Application/STM32N6570-DK/Inc/project_region_event.h) | Region-event logic |
| [app_config.h](firmware/Application/STM32N6570-DK/Inc/app_config.h) | Application configuration |
| [Quantization configuration](configs/yolov8n_seg_int8_int8.yaml) | SavedModel source, calibration data, per-channel quantization, and INT8 interface settings |
| [Three-model comparison script](scripts/check_seg_models_pc.sh) | Compare the original model, floating-point TFLite, and ST INT8 using common images |
| [Model Zoo modifications](tools/model_zoo_overrides/) | Local code-generation and detection/mask output-mapping patches |
| [Deployment script](scripts/deploy_n6_seg.sh) | Tool and model checks, ST-LINK identification, code generation, build, image packaging, and flashing |
| [Source map](docs/PUBLIC_SOURCE_MAP.md) | Mapping between the publication copy and the original project files |

The `firmware/` directory contains copies of the core source files. Building requires the pinned upstream project, SDK, and dependencies documented in A1.

## Rebuild and Delivery Materials

- [Source freeze and rebuild evidence](docs/a1_reproducible_20260918/README.md)
- [Pinned patches and dependency records](patches/a1_source_20260918/)
- [Firmware and delivery index](docs/a5_acceptance_20260919/DELIVERY.md)
- [Existing operational scripts](scripts/)

Validation covers a clean rebuild in the existing development environment and verification of restored sources and dependencies in an isolated directory.
Automated environment setup and a full rebuild on a fresh computer have not been validated.

## Validation Scope and Limitations

- Fixed inputs use a central square crop, bilinear resizing to 256×256, and RGB. Pixel equivalence with the camera DCMIPP pipeline has not been separately validated.
- PC INT8 and N6 raw outputs have numerical differences; see A2. The byte-for-byte equality in A4 is relative to the original N6 baseline.
- A4 RAM figures come from compiler allocation reports, not whole-board peak runtime memory measurements.
- The first long-run test retains one sequence discontinuity in the A5 record; its cause remains undetermined. A subsequent 30-minute retest synchronized to a fresh boot passed.
- Capture-timeout validation uses software fault injection to test invalid-state indication, removal of stale boxes, and cessation of result publication.

## Follow-up Dual-Model Project

[STM32N6 Voice-Guided Object Finder](https://github.com/fan-gu-hao/stm32n6-voice-object-finder) builds on this project's model deployment and vision integration work. It adds on-board audio capture, custom keyword spotting (KWS) training, INT8 deployment, Python/C comparisons, cache coherency, and FreeRTOS coordination of two models. The projects share a development lineage while retaining their own model versions and validation results.

## Third-Party Sources and Licenses

- [ST Model Zoo](https://github.com/STMicroelectronics/stm32ai-modelzoo-services)
- [ST STM32N6 Instance Segmentation example](https://github.com/STMicroelectronics/STM32N6-GettingStarted-InstanceSegmentation)
- [Archived upstream license files](licenses/)
- [Source and modification map](docs/PUBLIC_SOURCE_MAP.md)

Third-party files retain their original copyright notices and license information.
Prepare models, SDKs, runtime libraries, and other dependencies according to the A1 records.
