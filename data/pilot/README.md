# دادهٔ پایلوت qPCR

فایل `pilot_qpcr.csv` یک مجموعهٔ کوچک (~۶۰ نمونه) با برچسب واقعی برای اعتبارسنجی Se/Sp است.

```bash
python scripts/evaluate_pilot.py
# یا
curl -X POST http://localhost:8000/api/v1/ml/evaluate-pilot
```
