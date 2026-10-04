# CEP I.1: Campus Network Link Design

> Python link-budget and media-selection toolkit with a Packet Tracer model that connects six campus buildings with the cheapest cabling that actually works.

![Python](https://img.shields.io/badge/python-3.9%2B-blue)
![pandas](https://img.shields.io/badge/pandas-data%20tables-150458)
![Cisco Packet Tracer](https://img.shields.io/badge/Cisco-Packet%20Tracer-1BA0D7)
![Status](https://img.shields.io/badge/status-course%20project-lightgrey)

---

## Table of Contents

1. [Overview](#overview)
2. [The Problem](#the-problem)
3. [How It Works](#how-it-works)
4. [The Five Tests](#the-five-tests)
5. [Example Output](#example-output)
6. [Repository Structure](#repository-structure)
7. [Input Data](#input-data)
8. [Installation and Usage](#installation-and-usage)
9. [Methodology and Formulas](#methodology-and-formulas)
10. [Packet Tracer Model](#packet-tracer-model)
11. [Sensitivity Analysis](#sensitivity-analysis)
12. [Verification](#verification)
13. [Assumptions and Limitations](#assumptions-and-limitations)
14. [Key Terms](#key-terms)
15. [Team and Responsibilities](#team-and-responsibilities)
16. [Project Roadmap](#project-roadmap)

---

## Overview

A university needs to connect **six buildings** located between **40 m and 1.8 km** apart. Each link must carry a required data rate and meet an uptime target. The budget is fixed and too small to run fibre everywhere.

This project builds a small engineering toolkit that:

1. Reads the campus description from CSV tables.
2. Tests **every cable option on every link**.
3. Rejects options that fail, and records exactly why.
4. Picks the **cheapest option that passes** all tests.
5. Stress-tests the plan by cutting the budget by 15%.
6. Proves the final network works in **Cisco Packet Tracer**.

Nothing is hard-coded. Changing a distance, price or target means editing a CSV and re-running the program.

---

## The Problem

Two links are deliberately difficult:

- **An EMI-heavy corridor:** a service corridor full of electromagnetic interference, where copper suffers.
- **An open-ground run:** no conduit, so the cable is unprotected and needs armoured cable or trenching.

Four factors pull against each other:

| Factor | What happens | Why it matters |
|---|---|---|
| Distance | Signal weakens with cable length | Copper stops working beyond about 100 m |
| Bandwidth | A cable only carries signals up to a certain speed | Limits data rate; fibre bandwidth shrinks with distance |
| Reliability | Higher uptime needs better parts or a spare link | Costs more money |
| Cost | Fibre and spare links are expensive | Budget is fixed, so the best option cannot be bought everywhere |

The deliverable is a **justified media plan**: which cable for each link, which line code, whether a spare is needed, and a calculation proving each link works.

---

## How It Works

```
 Scenario files        Python               Media plan          Packet Tracer        Final
    (CSV)         link-budget model     (media_plan.csv)         network           report
      |                   |                     |                    |                 |
      +-----------------> +-------------------> +------------------> +---------------> +
                          |
                          +--> also runs the sensitivity test
```

**Python decides what to build. Packet Tracer proves it works as a network.** The two halves share exactly one file: `results/media_plan.csv`.

| Part | What it is |
|---|---|
| 1. Scenario files | Three CSV tables: links, cable options, and parameters (budget, safety factor, etc.) |
| 2. Link-budget engine | Checks one link with one cable type: loss, noise, speed limits, uptime, cost |
| 3. Selection engine | Discards failing options (recording why) and picks the cheapest that passes |
| 4. Sensitivity engine | Cuts the budget by 15% and finds which link breaks first |
| 5. Network model | Packet Tracer file with six buildings, devices, IP addressing and matching cables |
| 6. Report | Joins calculations, plan and simulation into one argument |

---

## The Five Tests

Every (link, cable) option must answer **yes** to all five questions to survive:

1. **Does enough signal reach the other end?** Attenuation and power margin.
2. **Is the signal clear above the noise?** Signal-to-noise ratio (thermal, crosstalk and EMI).
3. **Can the cable carry the required speed?** Must fit under both the Shannon and Nyquist limits.
4. **Is the uptime target met?** Availability, adding a spare link if needed.
5. **Can we afford it?** Total cost within budget.

---

## Example Output

The shape of the final plan looks like this. *These are illustrative values; real results come from your own data.*

| Link | Distance | Chosen medium | Spare link | Reason |
|---|---|---|---|---|
| L1 | 40 m | Cat6 copper | No | Short and cheap, passes every test |
| L2 | 90 m | Cat6 copper | No | Within the 100 m copper limit |
| L3 | 250 m | Armoured multimode fibre | No | Too far for copper; no conduit, so armoured cable |
| L4 | 600 m | Single-mode fibre | No | EMI rules out copper; multimode too short |
| L5 | 1.2 km | Single-mode fibre | Yes | 99.99% uptime target needs a spare path |
| L6 | 1.8 km | Single-mode fibre | Yes | Longest link, 99.99% target |

The engine also produces:

- a **rejected-options table** (e.g. *L4 copper rejected: noise too high in the EMI corridor*),
- a **cost table** showing the plan fits the budget,
- a **sensitivity result** naming the link that fails first at a 15% budget cut.

---

## Repository Structure

```
.
├── data/
│   ├── links.csv            # The six links and their requirements
│   ├── media.csv            # Cable catalogue with datasheet sources
│   └── params.csv           # Budget, safety factor, noise figure, margins
├── code/
│   ├── load.py              # Reads the three CSV files
│   ├── physics.py           # Signal loss, noise, SNR, Shannon, Nyquist
│   ├── linecode.py          # Line-code rules and spectrum plots
│   ├── reliability.py       # Availability (uptime) calculations
│   ├── select.py            # Filtering, cost, cheapest choice, rejected list
│   ├── sensitivity.py       # Budget cut, downgrade rule, sweep
│   └── main.py              # Runs everything, saves results and plots
├── results/
│   ├── options.csv          # Every link x media combination with all test columns
│   ├── media_plan.csv       # FINAL PLAN: the only file handed to Packet Tracer
│   ├── rejected.csv         # Every rejected option and the test it failed
│   ├── sensitivity.csv      # Budget-cut sweep results
│   └── *.png                # Spectrum and sensitivity plots
├── packet_tracer/
│   ├── skeleton.pkt         # Working network with placeholder cables
│   ├── final.pkt            # Network with media plan applied
│   └── address_table.md     # VLSM addressing plan and topology sketch
└── report/
    └── report.pdf           # Final report
```

> Note: `select.py` shadows Python's standard-library `select` module when run from the `code/` folder. If you hit import problems, rename it (e.g. `selection.py`).

---

## Input Data

### `data/links.csv`

Columns: `link_id, bldg_a, bldg_b, length_m, target_mbps, avail_target, emi_heavy, has_conduit`

Starting scenario:

| Link | Distance | Rate | Uptime | Special |
|---|---|---|---|---|
| L1 | 40 m | 1 Gbps | 99.9% | |
| L2 | 90 m | 1 Gbps | 99.9% | |
| L3 | 250 m | 1 Gbps | 99.95% | Open ground, no conduit |
| L4 | 600 m | 1 Gbps | 99.95% | EMI-heavy corridor |
| L5 | 1.2 km | 1 Gbps | 99.99% | |
| L6 | 1.8 km | 1 Gbps | 99.99% | Farthest building |

### `data/media.csv`

Four options: **Cat6 copper**, **multimode fibre (OM3)**, **single-mode fibre**, and optionally a **radio link**. For each: signal loss per km, bandwidth, maximum distance, cost per metre, install cost per metre, fixed cost (connectors and transceivers), MTBF and MTTR. Every number has a `source` column pointing to its datasheet.

### `data/params.csv`

Budget, the 15% cut, safety factor (1.5), noise figure, connector loss and minimum power margin. The budget is set **between** the "all single-mode" cost and the "cheapest possible" cost, so the trade-off is real.

---

## Installation and Usage

### Requirements

- Python 3.9+
- `pandas`, `numpy`, `matplotlib`
- Cisco Packet Tracer (for the network model)

### Setup

```bash
git clone https://github.com/<your-username>/<repo-name>.git
cd <repo-name>
pip install pandas numpy matplotlib
```

### Run

```bash
cd code
python main.py
```

This reads `data/`, runs every calculation, and writes the tables and plots to `results/`.

### Using the results in Packet Tracer

1. Open `packet_tracer/skeleton.pkt`.
2. Read `results/media_plan.csv`.
3. Swap each link's cable to match the plan (copper straight-through, or fibre with fibre modules at both ends).
4. Set speed and duplex to **full** on each interface.

### For the sensitivity teammate

Use `select_plan_tiered(options_df, budget)` from `code/selection.py` for budget-cut analysis. It returns `(plan_df, budget_met)`. The plan includes `link_id`, `media`, `spare`, `cost`, `length_shortfall`, `rate_shortfall`, `avail_shortfall`, `power_shortfall`, `snr_shortfall`, `total_shortfall`, and `valid`. `budget_met` is `True` when the selected plan cost is within the supplied budget and `False` when the lowest-cost fallback still cannot fit.

---

## Methodology and Formulas

### Step-by-step pipeline

| Step | Computation | Output columns |
|---|---|---|
| 5 | Build option table: 6 links x 4 media = 24 rows | `options.csv` |
| 6 | Signal loss and power margin | `loss_db`, `margin_db`, `pass_power` |
| 7 | Noise and SNR | `noise_dbm`, `snr_db` |
| 8 | Shannon and Nyquist limits | `shannon_mbps`, `nyquist_mbps`, `pass_rate` |
| 9 | Line-code choice | `line_code` |
| 10 | Availability | `avail`, `redundancy_needed` |
| 11 | Cost and selection | `media_plan.csv`, `rejected.csv` |
| 12 | Sensitivity analysis | `sensitivity.csv` |

### Attenuation and power margin

- **Copper:** `loss = dB_per_100m x length / 100`. Example: 90 m of Cat6 at 100 MHz loses 22 x 0.9 = **19.8 dB**. Copper is not allowed beyond 100 m.
- **Fibre:** `received power = transmit power - fibre loss - connector loss`. Example, L6 over 1.8 km single-mode: -9 - 0.63 - 1.0 = **-10.6 dBm**. With a -20 dBm receiver sensitivity the margin is **9.4 dB**. Gigabit multimode reaches only about 550 m, so it fails on L6.
- **Radio:** `free-space loss = 20 log10(km) + 20 log10(MHz) + 32.44`.
- An option is kept only if its margin meets the minimum in `params.csv`.

### Noise and SNR

```
Thermal noise (dBm) = -174 + 10 log10(bandwidth) + noise figure
SNR = received power - total noise
```

Crosstalk and EMI noise are added to thermal noise. **Convert each to milliwatts, sum, then convert back to dBm. Never add dB values directly.** The EMI link receives a much larger EMI term. Fibre is skipped here because it is immune to EMI; its test is the power margin.

### Shannon and Nyquist limits

```
Shannon:  C = B x log2(1 + SNR)          (SNR as a ratio, set by noise)
Nyquist:  max rate = 2 x B x log2(M)     (set by bandwidth; M = signal levels)
```

Worked example: B = 100 MHz and SNR = 30 dB (ratio 1000) gives about 997 Mbps. With a 1 Gbps target and safety factor 1.5 (1.5 Gbps required), that option **fails**. Fibre bandwidth shrinks with distance: `B = (MHz*km) / length_km`. The target must fit under **both** limits.

### Line coding

| Code | Bandwidth needed | Keeps clock in sync? |
|---|---|---|
| NRZ | About R/2 | Poorly: long runs of the same bit lose sync |
| RZ | About R | Better, but uses more bandwidth |
| Manchester | About R | Yes: every bit has a transition (50% efficient) |
| Block codes (4B/5B, 8b/10b, 64b/66b) | Low per bit | Yes: run length is limited |

**Rule:** choose the code that uses the least bandwidth and still keeps sync. Use Manchester only if the channel bandwidth is at least equal to the data rate; otherwise use a block code. Power spectra are plotted for a random bit stream with a fixed seed (NRZ narrowest, Manchester widest).

### Availability

```
A = MTBF / (MTBF + MTTR)
Link uptime = transceiver x cable x transceiver
Two parallel links: A = 1 - (1 - A_link)^2
```

Reference downtime: 99.9% is about **8.8 hours/year**; 99.99% is about **53 minutes/year**.

### Cost and selection

```
cost = fixed + (cost_per_m + install_per_m) x length
```

- A spare link **doubles** the cost.
- The no-conduit link adds trenching or armoured-cable cost.
- Options failing the power, rate or availability test are removed; the cheapest survivor is chosen per link.
- If the total exceeds the budget, the **downgrade rule** reduces the links that save the most money for the least harm.
- Every rejection is logged with the test it failed.

---

## Packet Tracer Model

Packet Tracer **cannot simulate signal loss or noise**. It verifies addressing, routing, reachability, speed and duplex. The link budget is proven in Python; the network is proven in Packet Tracer.

**Design**

- Each building has one router (or layer-3 switch), one LAN switch and a few PCs.
- Addressing uses **VLSM**: one `/30` per building-to-building link and one LAN subnet per building, sized for its hosts.
- Routing is static or OSPF.

**Validation (Step 17)**

- `ping` and `traceroute` between every pair of buildings
- `show ip route` and `show interfaces` (speed, duplex, errors)
- Shutting a link to show traffic rerouting where a spare exists
- Full duplex on all switched links (half duplex only applies to hubs; Packet Tracer has no true simplex mode, so simplex is stated as an assumption and explained)

---

## Sensitivity Analysis

The budget is cut to **0.85 x budget** and the downgrade rule is run again. Each link's shortfall in **length, rate and availability** is scored; the first link with a shortfall is the answer. The cut is then swept across **0, 5, 10 ... 30%** and plotted.

**Outputs:** `results/sensitivity.csv` and a plot of shortfalls against budget cut.

---

## Verification

To make sure the numbers can be trusted:

- Two links are checked **by hand or in a spreadsheet** and compared to code output.
- A **brute-force search** over every media combination confirms the plan is truly the cheapest that works.
- The **dB to milliwatt conversion** is unit-tested.

---

## Assumptions and Limitations

**Assumptions**

- Two transceivers per link.
- A spare link costs double and fails independently of the primary.
- Noise sources counted: thermal, crosstalk, EMI (copper only).
- Simplex is assumed, not simulated.

**This project is not**

- A real installation plan (no cable-route drawings or labour schedule).
- A physics simulator (the physics lives in the Python models).
- An advanced optimiser: it uses a simple, explainable and checkable selection rule.

---

## Key Terms

| Term | Plain meaning |
|---|---|
| Attenuation | Signal lost along the cable, measured in dB |
| Noise | Unwanted signal that mixes with the real signal |
| SNR | Signal-to-noise ratio: how much stronger the signal is than the noise |
| Shannon capacity | Fastest data rate the noise level allows |
| Nyquist limit | Fastest data rate the cable bandwidth allows |
| Line coding | How 1s and 0s become electrical or light signals |
| Availability | Share of time a link is working |
| Duplex | Full: both directions at once. Half: one direction at a time. Simplex: one direction only |
| EMI | Electromagnetic interference from nearby electrical equipment |

---

## Team and Responsibilities

| Role | Owns |
|---|---|
| Python pair | Steps 5 to 13: calculations, selection, sensitivity, checking |
| Packet Tracer pair | Steps 14 to 17: design, build and test the network |
| Documentation member | Step 19, and writing alongside every other step |
| Everyone | Steps 1 to 4, 18 and 20 |

---

## Project Roadmap

| Stage | Steps | Share of time |
|---|---|---|
| Set up | 1 to 4 | 5% |
| Calculations and network model | 5 to 17 | 55% |
| Integration | 18 | 10% |
| Report and review | 19 to 20 | 30% |

**Final checklist**

- [ ] `links.csv`, `media.csv` and `params.csv` complete, with sources
- [ ] Per-link table: loss, noise, SNR, Shannon, Nyquist, line code, uptime, cost
- [ ] Media plan and table of rejected options
- [ ] Packet Tracer file with ping and duplex evidence
- [ ] Answer to the 15% budget cut, with the sweep plot
- [ ] Report, code and Packet Tracer file all agree

---

## License

Add a license of your choice (e.g. MIT) before publishing.
