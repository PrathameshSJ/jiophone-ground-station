# JioPhone F90M Keypad Responsiveness Analysis

## The Problem
> **Symptom**: Keys must be clicked 4 to 5 times before an action is registered, even though the phone has never been dropped or mechanically damaged.

---

## Root Causes Identified

Our hardware and kernel analysis reveals that this behavior is caused by a compound issue: **passive hardware oxidation** coupled with **firmware/driver mismatch** and **Gecko main-thread starvation**.

### 1. Contact Oxidation Under Snap Domes (Passive Hardware Degradation)
* **Design**: The JioPhone F90M does not use individual mechanical micro-switches. It uses a flexible polyester dome sheet stuck over copper traces on the main PCB with nickel-plated metal snap domes.
* **Why it happens without drops**: Even if a phone has never been dropped, atmospheric oxygen, humidity, and trace sulfur slowly penetrate the adhesive edges of the dome sheet. Over months or years in storage, a thin layer of copper oxide ($Cu_2O$) and nickel oxide forms between the bottom of the dome and the center pad.
* **Why clicking 5 times works**: When you press firmly 4 or 5 times in succession, the mechanical flexing of the metal dome physically scrapes and micro-punctures the oxide layer. This temporarily reduces the contact resistance below the logic-low threshold ($\approx 10\,\text{k}\Omega$) of the Qualcomm PM8909 GPIO pull-up resistor, allowing the contact to finally register.

### 2. Firmware / Kernel Debounce Timing Mismatch
* **Driver**: The Linux kernel driver is `matrix-keypad` (`matrix_keypad_4105` on IRQs 324, 325, 424, 425 under `/devices/soc.0/matrix_keypad.68`).
* **The Conflict**: The flashed firmware is compiled for the **Nokia 8110 4G (FIH lb4105)**. The Nokia 8110 uses a sliding mechanism and a different keypad PCB with distinct switch contact bounce characteristics.
* **Debounce Filter**: The kernel driver enforces a debounce delay (`debounce_ms`) and column scan delay (`col_scan_delay_us`). If a bouncing contact switch on the JioPhone does not hold a continuous steady electrical signal across the debounce polling window defined in the Nokia kernel device tree, the kernel completely discards the key event as electrical noise.

### 3. Gecko UI Event Loop Starvation & Swap Thrashing
* **RAM & Swap State**:
  * Usable RAM: `405.6 MB`
  * Free RAM: only `~19.8 MB`
  * Active Swap: `256.0 MB` (over 90% utilized)
* **The Lag Effect**: KaiOS is built on Mozilla Gecko. Input events from `/dev/input/event0` are sent to the B2G main thread event loop. Because memory is near exhaustion, the kernel constantly swaps memory pages in and out of the slow eMMC flash (`iowait`). When the Gecko main thread is blocked by I/O wait or garbage collection, key events sit in the queue or get dropped, making the phone appear completely unresponsive until the UI thread catches up.

### 4. CPU Power Gating & Deep Sleep Latency
* The Qualcomm Snapdragon 205 drops both Cortex-A7 cores to 200 MHz or deep sleep states (`C3`/`C4`) when the screen or system is idle.
* The first 1 or 2 key presses wake the `msm_tlmm_irq` interrupt and spin up the CPU clock PLLs. The system often treats the initial press purely as a wake event before the UI is ready to accept character input.

---

## How to Test: Hardware vs Software

You can verify whether a key press is reaching the kernel or dying in the UI:

```bash
# Connect to phone via wireless ADB
adb -s 192.168.1.8:5555 shell

# Monitor the raw hardware events in real time:
getevent -l /dev/input/event0
```

* **If every physical press immediately prints a line** (e.g. `EV_KEY KEY_1 DOWN`):
  * The hardware switches and kernel driver are working fine. The problem is 100% **Gecko UI lag and swap thrashing**.
* **If pressing a key produces NO output on the terminal until the 4th or 5th click**:
  * The metal snap dome has physical **contact oxidation** or the kernel debounce timing is dropping the bouncy contact.

---

## Recommended Fixes & Workarounds

1. **Software Debloating (Reduces Swap Thrashing)**:
   * Disable unused KaiOS background services (telemetry, KaiOS store push daemons, FOTA updater).
   * Freeing ~40 MB of RAM stops eMMC swap thrashing and dramatically restores UI responsiveness.
2. **Contact Cleaning (Hardware Solution)**:
   * Carefully remove the rear shell and keypad sticker.
   * Clean the copper pads and underside of the nickel domes using 99% Isopropyl Alcohol (IPA) on a cotton swab to dissolve oxidation.
3. **Use Remote Control (Zero Hardware Lag)**:
   * You can send key events directly over Wi-Fi/ADB, bypassing the physical keypad entirely:
     ```bash
     # Simulate pressing Key 5:
     adb -s 192.168.1.8:5555 shell "sendevent /dev/input/event0 1 6 1; sendevent /dev/input/event0 0 0 0; sendevent /dev/input/event0 1 6 0; sendevent /dev/input/event0 0 0 0"
     ```
