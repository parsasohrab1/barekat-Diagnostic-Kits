# qPCR Pilot Data

The file `pilot_qpcr.csv` is a small set (~60 samples) with true labels for validating Se/Sp.

```bash
python scripts/evaluate_pilot.py
# or
curl -X POST http://localhost:8000/api/v1/ml/evaluate-pilot
```
