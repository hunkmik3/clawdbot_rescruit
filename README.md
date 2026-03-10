# Clawbot Apify MVP

Phien ban MVP cho he thong tim kiem va thu thap ung vien su dung Apify.

## 1) Cai dat

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Dien cac bien trong `.env`:

- `APIFY_API_TOKEN`: token Apify
- Actor ID cho tung platform ban muon su dung:
  - `APIFY_ACTOR_LINKEDIN_ID`
  - `APIFY_ACTOR_ARTSTATION_ID`
  - `APIFY_ACTOR_X_ID`
  - `APIFY_ACTOR_INSTAGRAM_ID`

## 2) Chay API

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## 3) Tao job thu thap

```bash
curl -X POST http://127.0.0.1:8000/jobs \
  -H "Content-Type: application/json" \
  -d '{
    "keywords": ["2D animator", "background artist"],
    "platforms": ["artstation", "linkedin"],
    "location": "Vietnam",
    "max_items_per_platform": 20,
    "actor_overrides": {
      "linkedin": "your-actor-id-if-different",
      "instagram": "apify/instagram-scraper"
    },
    "actor_inputs": {
      "instagram": {
        "search": [
          { "searchType": "hashtag", "query": "2danimation", "searchLimit": 1 }
        ],
        "resultsType": "details",
        "resultsLimit": 20,
        "maxRequestRetries": 3
      }
    }
  }'
```

## 4) Theo doi ket qua

```bash
curl http://127.0.0.1:8000/jobs
curl http://127.0.0.1:8000/jobs/<job_id>
curl http://127.0.0.1:8000/jobs/<job_id>/results
```

## Luu y kien truc

- Job duoc chay qua `BackgroundTasks` cua FastAPI (de MVP don gian).
- Du lieu job luu trong `data/jobs/*.json`.
- Muc tieu tiep theo:
  - thay `BackgroundTasks` bang queue (Celery/RQ)
  - them DB that su (PostgreSQL)
  - them Google Sheets sync
  - them outreach templates/senders
