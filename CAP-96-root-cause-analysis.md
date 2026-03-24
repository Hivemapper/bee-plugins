# [CAP-96] Root Cause Analysis: Dashcam Failure to Generate AI Events

**Device:** Bee dashcam (ID: e9Yz-0lj4Y, Firmware: 7.0.1)
**Drive Session:** 2026-03-23 ~16:18-17:15 UTC (session `ee6eb5d5`), San Francisco Bay Area
**System Clock:** Stuck at 2025-01-13 (never synced due to no internet)

## Executive Summary

The drive session produced **zero AI events** (both vision and IMU-based) reaching the beekeeper upload pipeline. The root cause is a **cascade of failures originating from missing classifier model files on disk and complete LTE connectivity failure**, which together prevented the AI inference pipeline from producing vision events and prevented IMU events from being delivered upstream.

## Root Cause Chain

### 1. PRIMARY: Classifier Model Files Missing on Disk

**All classifier models have missing blob files on the filesystem**, despite being registered in the `model_zoo` database table. During every map-ai startup (6+ restarts observed), the following warning is logged:

```
One or both files missing for model classifySpeedLimit.
One or both files missing for model classifySpeedTypeUS.
One or both files missing for model classifyTurnRule.
One or both files missing for model classifyOnRed.
One or both files missing for model classifyHighwaySignType.
One or both files missing for model hereClassifier.
One or both files missing for model embeddings.
One or both files missing for model ObjectDetectionUS.
```

**Impact:** The `ClassificationRouterNode` in map-ai sends frames to classifier outputs (`output_to_classifier_N`), but with no model files loaded, the classifiers never produce results. This causes the persistent warning:

```
No input received from any classifier after 10000 attempts
```

This warning appeared **348 times** across all map-ai log files (213 in most recent, 21 during active drive, 114 in earliest log), confirming the classifiers were non-functional for the **entire session**.

Without classifier output, no vision AI events can be written to the `ai_events_vision` table in odc-api.db, which remained at **0 rows**.

**Evidence from model_zoo DB:**
| Model | zoo_version | on_device_version | Status |
|-------|-------------|-------------------|--------|
| ObjectDetectionUS | 4 | 0 | Version mismatch - files missing |
| SpeedClassificationUS | 0 | 0 | Never downloaded |
| classifySpeedLimit | 0 | 0 | Never downloaded |
| classifySpeedTypeUS | 2 | 0 | Version mismatch - files missing |
| classifyTurnRule | 1 | 0 | Version mismatch - files missing |
| classifyOnRed | 0 | 0 | Never downloaded |
| classifyHighwaySignType | 0 | 0 | Never downloaded |
| hereClassifier | 1 | 0 | Version mismatch - files missing |
| embeddings | 1 | 0 | Version mismatch - files missing |
| highlandUs | 5 | 5 | OK |
| laneDetection | 2 | 2 | OK |

The `on_device_version` is 0 for all classifier models, meaning the model files were **never successfully downloaded to the device** or were deleted. Only `highlandUs` (landmark detection) and `laneDetection` have matching versions and were functional.

### 2. CONTRIBUTING: Complete LTE/Internet Connectivity Failure

LTE was **never online** during the entire session:
- `FKM Uploads - No IP address for LTE interface` logged every 5 seconds in odc-api
- `LTE STATUS false` logged **3,981 times** in beekeeper-plugin (never `true`)
- All DNS lookups failed with `Temporary failure in name resolution` / `getaddrinfo EAI_AGAIN`
- model-zoo could not download missing models (`LTE not available, skipping LTE update`)

**Impact:** Even if models had been present, model-zoo could not update them. More critically, the device could not register with the backend (`deviceSessionToken` was always empty), so no data could be uploaded.

### 3. CONTRIBUTING: map-ai Pipeline Overload and Crash

During the active drive portion, the `LocateLandmarkNode` (which DID have its model files — `highlandUs`) became progressively slower:
- Started at 0.5-3 seconds per frame
- Degraded to 22-145 seconds per frame
- Triplet queue filled to max capacity (251 items), causing frame drops
- Eventually triggered an **X_LINK_ERROR** hardware communication failure on the DepthAI device at 20:27:17
- Process was killed; first restart failed due to Redis being unavailable

### 4. CONTRIBUTING: IMU Events Generated but Not Delivered

The fusion database DID contain 6 IMU-based AI events (Swerving, Harsh Braking, Aggressive Acceleration, High Speed), but beekeeper-plugin's `fetchRecentAIEvents` returned empty arrays (`imuAIEvents, []`) every 10-second poll cycle. This suggests either:
- The odc-api `/aiEvents/getEvents` endpoint queries a different table/session than where fusion stores events
- The session ID mismatch (fusion used session `872635d3`/`a3e6744a`/etc. while beekeeper polled session `0267b1d2`) prevented matching

### 5. CONTRIBUTING: Missing `/data/recording/aievents` Directory

The beekeeper-plugin logged warnings that the `aievents` output directory did not exist on disk, meaning even if events were detected, the video clip segmentation pipeline had no output path.

## Data Pipeline Status Summary

| Component | Status | Notes |
|-----------|--------|-------|
| GNSS/GPS | Working | 3D fix, 20+ satellites, 4 Hz data, ~57 min drive |
| IMU | Working | 200 Hz data, 6 events detected in fusion DB |
| Camera/DepthAI | Degraded then crashed | X_LINK_ERROR after overload |
| Object Detection (highlandUs) | Working | 1,677 landmarks, 532 map features detected |
| Lane Detection | Working | 52 lane counts recorded |
| Classifier Models | NOT WORKING | All model files missing from disk |
| Vision AI Events | NOT WORKING | 0 events in ai_events_vision table |
| IMU AI Events delivery | NOT WORKING | 6 events in fusion DB but 0 reached beekeeper |
| LTE Connectivity | NOT WORKING | Interface had no IP address entire session |
| Model Zoo Updates | NOT WORKING | Cannot download without internet |
| Plugin API | NOT WORKING | plugin-api-access.log is empty (0 bytes) |
| FrameKM Upload | NOT WORKING | `isFrameKmProcessingAndUploadEnabled: false` |

## Recommendations

### Immediate Fixes
1. **Investigate why classifier model files are missing from the device filesystem.** The model_zoo DB has entries with `on_device_version = 0` for all classifiers. Either the files were never downloaded, were deleted during a firmware update, or the storage path is misconfigured. Check `/opt/model-zoo/` or equivalent model storage directory.

2. **Investigate the LTE modem failure.** The `wwan0` interface had no IP address for 57+ minutes of driving. This is either a hardware issue, SIM provisioning issue, or modem firmware bug.

3. **Fix the session ID mismatch for IMU events.** The fusion DB stored events under sessions `872635d3`, `a3e6744a`, etc., but beekeeper polled with session `0267b1d2`. These need to be aligned for IMU events to flow through.

### Preventive Measures
4. **Add model file integrity check at boot.** map-ai should refuse to start (or clearly fail) if required classifier models are missing, rather than silently running without classifiers.

5. **Create the `/data/recording/aievents` directory at boot** if it doesn't exist.

6. **Address LocateLandmarkNode performance degradation.** Processing time grew from <3s to >145s during a single drive, suggesting unbounded state accumulation. Consider capping tracked landmarks or adding periodic cleanup.

7. **Ensure `isFrameKmProcessingAndUploadEnabled` and `isVideoApiProcessingEnabled` are set to `true`** for devices expected to generate and upload AI events.
