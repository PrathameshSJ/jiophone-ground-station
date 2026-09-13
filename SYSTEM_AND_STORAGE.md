# JioPhone F90M System Architecture & Debloating Guide

## Memory Map & Utilization
* **Total RAM**: 512 MB physical (405.6 MB mapped to Linux)
* **ZRAM Swap**: 256 MB compressed swap partition
* **Low Memory Killer (LMK)**:
  * Minimum free memory thresholds range from 4 MB to 65 MB.
  * When free memory approaches 65 MB, background tasks are aggressively killed to prioritize foreground apps.

## Partitions & Storage Layout
* **eMMC Capacity**: 4.0 GB
* **User Data (`/sdcard` / `/data/media/0`)**: ~1.0 GB free
* **System Partition (`/system`)**: Read-only EXT4 (`/dev/block/bootdevice/by-name/system`)
* **Data Partition (`/data`)**: Read-write EXT4 (`/dev/block/bootdevice/by-name/userdata`)

---

---

## Safe Debloating & Optimization (Ultra-Lean Mode Without Root)

### Does It Need Root to Kill Background Apps & Daemons?
* **For System & Hardware Daemons (Qualcomm / Android services)**: **NO, root is NOT needed!**
  * In Android's Gonk Linux architecture, `/system/bin/stop <service>` writes to the `ctl.stop.<service>` property handled by `init` (`PID 1`, running as `root`).
  * The production SELinux policy grants UID 2000 (`shell`) permission to invoke `ctl.stop` on system services.
  * Direct POSIX `kill -9 <PID>` across different UIDs is blocked by kernel security, but Android's `stop` tool cleanly halts the services and their sub-processes.
* **For KaiOS WebApps**:
  * WebApps run as sandboxed child processes under B2G (`/system/b2g/b2g`).
  * They can be cleanly closed without root via Gecko's Remote Debugger Protocol (RDP) on TCP 6000 (`/data/local/debugger-socket`) using `{"to": webappsActor, "type": "close", "manifestURL": "..."}`.
  * When **Physical Screen Blackout** is active (`navigator.mozPower.screenEnabled = false`), the compositor and homescreen enter dormant state, meaning zero CPU or GPU time is spent rendering anything other than the camera stream loop.

### The 14 Bloat Daemons Safe to Terminate for Dedicated Camera/IoT Usage
When using the JioPhone as a dedicated wireless camera streamer, sensor node, or server, the following 14 background services can be terminated:

```bash
# 1. Location & GPS Subsystem (~50 MB RAM)
stop loc_launcher   # Kills lowi-server, xtwifi-inet-agent, xtwifi-client

# 2. Cellular Modem & VoLTE IMS Subsystem (~40 MB RAM)
stop imsqmidaemon   # VoLTE QMI daemon
stop imsdatadaemon  # VoLTE data daemon
stop ims_rtp_daemon # VoLTE audio stream daemon
stop cnd            # Carrier network daemon
stop qti            # Qualcomm tethering interface
stop ril-daemon     # Radio Interface Layer (SIM card)
stop netmgrd        # Cellular data manager
stop qmuxd          # Modem multiplexer

# 3. OEM Diagnostics & Telemetry
stop fidodaemon     # FIDO biometric/auth
stop tct_diag       # Alcatel/TCT hardware diagnostics
stop tctd           # OEM daemon

# 4. Audio & Security
stop audiod         # Audio server (camera app streams video only)
stop gatekeeperd    # Keyguard gatekeeper
stop keystore       # Android crypto store
```

### Memory Impact
* **Stock KaiOS Idle**: ~20 MB free RAM (95% utilized), 60+ MB ZRAM swap thrashing.
* **After Stripping 14 Daemons**: **85 MB free physical RAM** (~79% utilized), ZRAM swap reduced to ~7 MB.
* **CPU & Thermals**: Eliminates background wakeups, dropping CPU core temperature by 4–8 °C and extending battery life significantly.

### Restoring System Services
If the phone is ever needed again as a standard phone:
```bash
start ril-daemon
start netmgrd
start qmuxd
start audiod
start loc_launcher
start fidodaemon
start tctd
```

---

## Thermal Sensor Zones

The device reports 11 thermal zones under `/sys/class/thermal/thermal_zone*/`:

| Thermal Sensor | Component | Typical Normal Range |
| :--- | :--- | :--- |
| `tsens_tz_sensor0` – `sensor4` | Qualcomm Cortex-A7 Cores | 45 °C – 65 °C |
| `pm8909_tz` | Qualcomm PMIC (Power IC) | 48 °C – 62 °C |
| `battery` / `bms` | Li-ion Battery Cell | 28 °C – 40 °C |
| `pa_therm0` | 4G LTE Power Amplifier | 30 °C – 45 °C |
| `xo_therm` | Crystal Oscillator | 35 °C – 45 °C |
