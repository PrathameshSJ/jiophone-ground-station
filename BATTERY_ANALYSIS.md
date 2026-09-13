# JioPhone F90M Battery & Power Telemetry Analysis

## Battery Specifications
* **Battery Model**: `FIH2000-lb4105` (Foxconn FIH Lithium-Ion cell)
* **Nominal Design Capacity**: `2000 mAh` (7.40 Wh)
* **Design Voltage (Max Charging)**: `4.20 V` (`4,200,000 µV`)
* **Cutoff Voltage**: `3.40 V`
* **Fuel Gauge Controller**: Qualcomm QPNP VM-BMS (`qpnp-vm-bms-10`)
* **Charger IC**: Qualcomm QPNP Linear Charger (`qpnp-linear-charger-8`)

---

## Live Sysfs Telemetry Nodes

All battery and BMS parameters can be queried directly from the Linux kernel:

| Parameter | Kernel Sysfs Node | Unit / Scale |
| :--- | :--- | :--- |
| **Instantaneous Voltage** | `/sys/class/power_supply/battery/voltage_now` | µV (divide by 1,000,000 for Volts) |
| **Open-Circuit Voltage (OCV)** | `/sys/class/power_supply/bms/voltage_ocv` | µV |
| **Current Draw** | `/sys/class/power_supply/battery/current_now` | µA (Negative = Charging, Positive = Discharging) |
| **Reported State of Charge** | `/sys/class/power_supply/battery/capacity` | % (0 to 100) |
| **Battery Temperature** | `/sys/class/power_supply/battery/temp` | 0.1 °C (divide by 10 for °C) |
| **Internal Resistance** | `/sys/class/power_supply/bms/resistance_now` | mΩ (milliohms) |
| **Cycle Count** | `/sys/class/power_supply/bms/cycle_count` | Cycles |

---

## Battery Health & Capacity Estimation Methodology

Because older Li-ion batteries degrade over time, the nominal 2000 mAh rating may no longer reflect the true usable capacity. We determine the actual capacity using two complementary techniques:

### 1. Coulometric Discharge Integration ($\Delta Q$)
While the phone is running on battery (discharging):
$$\Delta Q = \int_{t_1}^{t_2} I_{\text{discharge}}(t) \, dt \approx \sum_{k} I_k \cdot \Delta t$$
Where $I_k$ is measured in mA and $\Delta t$ in hours.

The effective usable capacity $C_{\text{actual}}$ (in mAh) is:
$$C_{\text{actual}} = \frac{\Delta Q}{\text{SoC}(t_1) - \text{SoC}(t_2)}$$

### 2. Open-Circuit Voltage (OCV) Mapping
When idle, the battery cell voltage follows the standard Lithium Cobalt Oxide / NMC chemical curve:
* **$4.20\,\text{V}$**: $100\%$ SoC
* **$4.05\,\text{V}$**: $\approx 85\%$ SoC
* **$3.90\,\text{V}$**: $\approx 70\%$ SoC
* **$3.80\,\text{V}$**: $\approx 50\%$ SoC
* **$3.70\,\text{V}$**: $\approx 30\%$ SoC
* **$3.64\,\text{V}$**: $\approx 16-18\%$ SoC (Current reading: $3.639\,\text{V} \rightarrow 16\%$)
* **$3.50\,\text{V}$**: $\approx 7\%$ SoC
* **$3.40\,\text{V}$**: $0\%$ (Emergency Cutoff)

### 3. Internal Resistance Analysis
* **Current Reading**: `152 mΩ` (`resistance_now`).
* **Evaluation**:
  * Brand new Li-ion cell: $80 - 150\,\text{m}\Omega$
  * Slightly aged / functional cell: $150 - 250\,\text{m}\Omega$
  * Degraded / End-of-life cell: $> 350\,\text{m}\Omega$
* **Conclusion**: At **$152\,\text{m}\Omega$**, the battery cell internal chemistry is in **very good condition** with low internal impedance and minimal degradation!

---

## Power Consumption Profile: Active Polling vs Deep Standby

When running on battery, you may observe discharge rates between **~200 mA and 270 mA** under active monitoring:

### Why Active Telemetry Consumes ~200–270 mA:
1. **Wi-Fi Radio Sleep Invalidation**: Rapid polling (e.g. querying ADB every 1.5 seconds) forces the Qualcomm WCN3610 Wi-Fi radio to maintain high-power active RX/TX state ($\approx 90–120\,\text{mA}$).
2. **CPU Wake Locks & Core Scaling**: Each shell query spins up both Cortex-A7 CPU cores, preventing the Snapdragon 205 from dropping into C2/C3 power-collapse sleep ($\approx 70–100\,\text{mA}$).
3. **Base System & PMIC**: Base system power rail draws $\approx 30\,\text{mA}$.

### When Idle / Low-Power Polling (~25–40 mA):
* When polling is slowed or stopped, the Wi-Fi radio enters standard 802.11 power-save sleep (listening only on beacon DTIM intervals).
* The CPU drops to 200 MHz and enters deep sleep states.
* **True Deep Standby Discharge Rate**: **$25 - 40\,\text{mA}$**, delivering **$50 - 80\,\text{hours}$ (2 to 3.3 days)** of runtime on a full charge!

---

## Projected Battery Life at 100% Charge

Given the device's baseline power consumption profiles:

| Mode | Average Discharge Rate ($I_{\text{avg}}$) | Projected Runtime on Full Charge ($2000\,\text{mAh}$) |
| :--- | :--- | :--- |
| **Deep Standby (Screen off, Wi-Fi sleep)** | $25 - 40\,\text{mA}$ | **$50 - 80\,\text{hours}$ (2 to 3.3 days)** |
| **Active Telemetry / Server Mode (Fast polling)** | $180 - 240\,\text{mA}$ | **$8 - 11\,\text{hours}$** |
| **Headless Linux Server (`stop b2g`)** | $30 - 50\,\text{mA}$ | **$40 - 65\,\text{hours}$ (up to 2.7 days)** |
| **Continuous Camera Streaming** | $280 - 380\,\text{mA}$ | **$5 - 7\,\text{hours}$** |

*Formula for runtime at any given discharge rate*:
$$T_{\text{hours}} = \frac{C_{\text{actual}} \times (\text{Current \%} / 100)}{I_{\text{discharge}}}$$
