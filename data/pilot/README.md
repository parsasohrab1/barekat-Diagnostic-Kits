# qPCR Pilot Data

> **Provenance warning:** the origin of `pilot_qpcr.csv` is undocumented, and its labels are perfectly
> separable by the Ct = 30 cutoff, so it behaves like synthetic data. Do not cite it as independent
> lab ground truth. See `docs/TRL_ASSESSMENT.md`.

The file `pilot_qpcr.csv` is a small set (~60 samples). Out-of-fold evaluation:

```bash
python scripts/evaluate_pilot.py
```
