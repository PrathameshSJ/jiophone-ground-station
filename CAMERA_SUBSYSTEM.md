# JioPhone F90M Camera Subsystem & Streaming

## Sensor Hardware Specifications
* **Rear Main Camera**:
  * Resolution: 2.0 Megapixels ($1600 \times 1200$)
  * Sensor Interface: Qualcomm CSI-2 (Camera Serial Interface)
  * V4L2 Nodes: `/dev/video0` (ISP node), `/dev/video1` (Sensor control)
* **Front Selfie Camera**:
  * Resolution: 0.3 Megapixels VGA ($640 \times 480$)
  * V4L2 Nodes: `/dev/video2`
* **ISP Subsystem**:
  * Qualcomm MSM8909 VFE (Video Front End)
  * Hardware JPEG Encoder: `/system/lib/libmmjpeg_interface.so`
  * Daemon: `/system/bin/mm-qcamera-daemon`

---

## Hardware Sensor Diagnostic Verification

The phone contains Qualcomm's native hardware verification tool: `/system/bin/mm-qcamera-app`.

Running automated regression testing via ADB verifies hardware sensor communication directly:
```bash
adb -s 192.168.1.8:5555 shell "echo 1 | mm-qcamera-app"
```
**Test Output**:
```text
Starting Regression testing!!
 Verifying open/close cameras... Passed
 Verifying start/stop preview... Passed
 TOTAL_TEST_CASE = 2, NUM_TEST_RAN = 2, rc=0
 Regression test passed!!
```
This confirms both sensors and the VFE ISP pipeline are fully operational.

---

## Live Video Streaming Architecture

### Method 1: WebRTC / Browser Streamer (High-FPS, Low-Latency)
1. The telemetry server hosts an HTML5 camera sender endpoint at:
   `http://192.168.1.15:8000/cam_sender`
2. When the phone's browser visits this URL, it requests camera access via standard WebRTC:
   ```javascript
   navigator.mediaDevices.getUserMedia({
     video: { facingMode: 'environment', width: 640, height: 480 },
     audio: false
   })
   ```
3. Video frames are rendered to a canvas, encoded to JPEG, and pushed over WebSocket or HTTP multipart to the live dashboard.

### Method 2: On-Demand Hardware Sensor Check
* The telemetry dashboard provides a "Run Hardware Diagnostic" button that invokes `mm-qcamera-app` directly over ADB to verify ISP state and sensor health without needing any browser interaction.
