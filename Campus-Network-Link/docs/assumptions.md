# Campus Link Design Assumptions

## Availability

- Each link has two transceivers in series: transmitter availability multiplied by cable availability multiplied by receiver availability.
- Cable failure rate is measured in failures per km-hour and needs citation.
- Cable MTTR is read from `data/media.csv` in hours: Cat6 8 h, OM3 12 h, SMF 12 h, and radio 2 h. The selected L5/L6 SMF links therefore imply a 12-hour cable repair time per failure. These values need citation.
- Transceiver MTBF and MTTR are read from `data/params.csv` and currently need citation.
- A spare link doubles the link cost and is assumed to fail independently from the primary link.

## Physical Model

- Noise includes thermal noise, crosstalk noise, and the normal or heavy EMI value selected from the CSV.
- Cat6 uses PAM-5 with `M=5` signal levels over 4 pairs. OM3, SMF, and radio use the CSV-provided `M` and pair counts currently set to 2 levels and 1 pair.

## Shortfall Policy

- Availability shortfall is extra downtime divided by target downtime and is uncapped. Length, rate, power, and SNR hard terms are capped at 1.0. All equal-weight terms and the cap policy are assumptions; downgrade rankings depend on them.
- The tiered selector treats length, power, SNR, and rate shortfalls as HARD because those failures prevent the link from meeting its service requirement. Availability is SOFT because the link can still carry traffic while missing its uptime target.
- Tiered selection minimizes the number and total size of HARD failures before minimizing SOFT availability shortfall; this is a policy choice rather than a physical law.

## Interface Assumptions

- Duplex is recorded as full.
- Simplex behavior is assumed rather than simulated.

## Availability Placeholder Table

| Value | Unit | Source status |
|---|---|---|
| Cable failure rate per km | failures per km-hour | `ASSUMPTION - TODO cite` |
| Cat6 cable MTBF / MTTR | hours | `ASSUMPTION - TODO cite` |
| OM3 cable MTBF / MTTR | hours | `ASSUMPTION - TODO cite` |
| SMF cable MTBF / MTTR | hours | `ASSUMPTION - TODO cite` |
| Radio cable MTBF / MTTR | hours | `ASSUMPTION - TODO cite` |
| Transceiver MTBF / MTTR | hours | `ASSUMPTION - TODO cite` |# Campus Link Design Assumptions

- Each link has two transceivers in series: transmitter availability multiplied by cable availability multiplied by receiver availability.
- A spare link doubles the link cost and is assumed to fail independently from the primary link.
- Noise includes thermal noise, crosstalk noise, and the normal or heavy EMI value selected from the CSV.
- Cat6 uses PAM-5 with `M=5` signal levels over 4 pairs. OM3, SMF, and radio use the CSV-provided `M` and pair counts currently set to 2 levels and 1 pair.
- `cable_failure_rate_per_km` is measured in failures per km-hour. The current value is an unverified assumption and needs citation.
- Cable MTTR is read from `data/media.csv` in hours: Cat6 8 h, OM3 12 h, SMF 12 h, and radio 2 h. For the selected L5/L6 SMF links, the model therefore implies a 12-hour cable repair time per failure; these values remain assumptions until datasheets are confirmed.
- The analytic spare-crossing rate solves single-link downtime equal to the target downtime: `rate = ((A_transceiver^2 / A_target) - 1) / (length_km x cable_MTTR_h)`. The resulting rates are calculated, not grid-point estimates.
- Availability shortfall normalization is capped at 1.0, as are length, rate, power, and SNR shortfall terms. All terms have equal weight. Downgrade rankings depend on this assumption.
- The tiered selector treats length, power, SNR, and rate shortfalls as HARD because those failures prevent the link from meeting its service requirement. Availability is SOFT because the link can still carry traffic while missing its uptime target.
- Tiered selection minimizes the number and total size of HARD failures before minimizing SOFT availability shortfall; this is a policy choice rather than a physical law.
- Duplex is recorded as full, while simplex behavior is assumed rather than simulated.