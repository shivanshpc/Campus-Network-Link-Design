# Hand-check material: L2 Cat6 and L6 SMF

How to use this sheet: copy the inputs into a spreadsheet, build each formula yourself without looking at the code, and compare your result with the project's computed value. Leave the two rightmost columns for your own work.

### L2 Cat6 inputs

| Source file and column | Value | Unit |
|---|---:|---|
| `data/links.csv:link_id` | `L2` | id |
| `data/links.csv:length_m` | `90` | m |
| `data/links.csv:target_mbps` | `1000` | Mbps |
| `data/links.csv:avail_target` | `np.float64(0.999)` | fraction |
| `data/links.csv:emi_heavy` | `False` | boolean |
| `data/media.csv:loss_db_per_100m` | `22` | dB/100 m |
| `data/media.csv:bandwidth_mhz` | `100` | MHz |
| `data/media.csv:signal_levels` | `5` | levels |
| `data/media.csv:pairs` | `4` | pairs |
| `data/media.csv:max_distance_m` | `100` | m |
| `data/media.csv:tx_power_dbm` | `0` | dBm |
| `data/params.csv:noise_figure_db` | `6` | dB |
| `data/params.csv:connector_loss_db` | `1` | dB |
| `data/params.csv:crosstalk_noise_dbm` | `-80` | dBm |
| `data/params.csv:emi_noise_dbm_normal` | `-90` | dBm |
| `data/params.csv:safety_factor` | `np.float64(1.5)` | factor |
| `data/params.csv:transceiver_mtbf_h` | `500000` | hours |
| `data/params.csv:transceiver_mttr_h` | `4` | hours |

### L2 Cat6 calculations

| step | formula | unit | project computed value | rounded display value | my spreadsheet value | match? |
|---|---|---|---|---|---|---|
| attenuation | 22 dB/100 m x 90 m / 100 m | dB | 19.8 | 19.8 |  |  |
| rx power | tx power - attenuation - connector loss | dBm | -20.8 | -20.8 |  |  |
| thermal noise | -174 dBm + 10 log10(B_hz) + noise figure | dBm | -88.0 | -88 |  |  |
| thermal noise power | 10^(thermal dBm / 10) | mW | 1.584893192461111e-09 | 1.58489e-09 |  |  |
| crosstalk noise power | 10^(crosstalk dBm / 10) | mW | 1e-08 | 1e-08 |  |  |
| EMI noise power | 10^(normal EMI dBm / 10) | mW | 1e-09 | 1e-09 |  |  |
| total noise | 10 log10(thermal_mW + crosstalk_mW + EMI_mW) | dBm | -79.0015046594173 | -79.0015 |  |  |
| SNR | rx power - total noise | dB | 58.201504659417296 | 58.2015 |  |  |
| per-pair Shannon | B x log2(1 + 10^(SNR/10)) | Mbps | 1933.4123532132858 | 1933.41 |  |  |
| per-pair Nyquist | 2 x B x log2(M) | Mbps | 464.38561897747246 | 464.386 |  |  |
| total Shannon | pairs x per-pair Shannon | Mbps | 7733.649412853143 | 7733.65 |  |  |
| total Nyquist | pairs x per-pair Nyquist | Mbps | 1857.5424759098898 | 1857.54 |  |  |
| required rate | target Mbps x safety factor | Mbps | 1500.0 | 1500 |  |  |
| pass power | distance <= maximum distance | boolean | True | True |  |  |
| pass SNR | SNR >= Shannon-derived required SNR | boolean | True | True |  |  |
| pass rate | required rate <= Shannon and Nyquist | boolean | True | True |  |  |
| pass availability | link availability >= target or spare availability >= target | boolean | True | True |  |  |
| transceiver availability | MTBF / (MTBF + MTTR) | fraction | 0.9999920000639995 | 0.999992 |  |  |
| cable availability | cable MTBF / (cable MTBF + cable MTTR) | fraction | 0.9999928000518397 | 0.999993 |  |  |
| link availability | A_tx x A_cable x A_rx | fraction | 0.9999768003590354 | 0.999977 |  |  |
| downtime per year | (1 - link availability) x 8760 x 60 | minutes/year | 12.193731291016885 | 12.1937 |  |  |
| cost | fixed + (cost/m + install/m) x length | currency units | 280.0 | 280 |  |  |

### L6 SMF with spare inputs

| Source file and column | Value | Unit |
|---|---:|---|
| `data/links.csv:link_id` | `L6` | id |
| `data/links.csv:length_m` | `1800` | m |
| `data/links.csv:target_mbps` | `1000` | Mbps |
| `data/links.csv:avail_target` | `np.float64(0.9999)` | fraction |
| `data/media.csv:loss_db_per_km` | `np.float64(0.35)` | dB/km |
| `data/media.csv:bandwidth_mhz_km` | `100000` | MHz-km |
| `data/media.csv:max_distance_m` | `10000` | m |
| `data/media.csv:tx_power_dbm` | `-9` | dBm |
| `data/media.csv:rx_sensitivity_dbm` | `-20` | dBm |
| `data/media.csv:mttr_h` | `12` | hours |
| `data/media.csv:cable_failure_rate_per_km` | `np.float64(1e-05)` | failures/km-hour |
| `data/params.csv:connector_loss_db` | `1` | dB |
| `data/params.csv:transceiver_mtbf_h` | `500000` | hours |
| `data/params.csv:transceiver_mttr_h` | `4` | hours |

### L6 SMF with spare calculations

| step | formula | unit | project computed value | rounded display value | my spreadsheet value | match? |
|---|---|---|---|---|---|---|
| fibre loss | 0.35 dB/km x 1.8 km | dB | 0.63 | 0.63 |  |  |
| connector loss | CSV connector loss | dB | 1.0 | 1 |  |  |
| rx power | tx power - fibre loss - connector loss | dBm | -10.63 | -10.63 |  |  |
| margin | rx power - receiver sensitivity | dB | 9.37 | 9.37 |  |  |
| bandwidth at distance | bandwidth MHz-km / length km | MHz | 55555.555555555555 | 55555.6 |  |  |
| availability of one link | A_tx x A_cable x A_rx | fraction | 0.9997680502931346 | 0.999768 |  |  |
| availability with spare | 1 - (1 - A_link)^2 | fraction | 0.9999999461993335 | 1 |  |  |
| downtime per year | (1 - A_with_spare) x 8760 x 60 | minutes/year | 0.028277630300532763 | 0.0282776 |  |  |
| cost with spare doubling | 2 x [fixed + (cost/m + install/m) x length] | currency units | 49200.0 | 49200 |  |  |
