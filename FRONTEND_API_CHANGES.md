# Backend API Changes – Frontend Integration Guide

> **Date**: 2026-03-12  
> **Version**: 1.1.0  
> **Audience**: Frontend developers  

---

## Table of Contents

1. [Summary of Changes](#1-summary-of-changes)  
2. [New Environment Variables (Backend Team)](#2-new-environment-variables-backend-team)  
3. [API Changes – PDF Upload](#3-api-changes--pdf-upload)  
4. [New Endpoint – PDF Download](#4-new-endpoint--pdf-download)  
5. [New Endpoint – PDF Preview URL](#5-new-endpoint--pdf-preview-url)  
6. [AI Processing (Embeddings / Summarization / Q&A)](#6-ai-processing-embeddings--summarization--qa)  
7. [Celery Worker Changes](#7-celery-worker-changes)  
8. [Migration Checklist for Frontend](#8-migration-checklist-for-frontend)  
9. [Full Request / Response Examples](#9-full-request--response-examples)  
10. [Error Codes Reference](#10-error-codes-reference)  

---

## 1. Summary of Changes

| # | Change | Impact on Frontend |
|---|--------|--------------------|
| 1 | Uploaded PDFs are now stored in **Google Cloud Storage** (GCS) | No API contract change – `file_url` field still returned. |
| 2 | **New endpoint** `GET /api/v1/papers/{paper_id}/download` | Frontend should call this to download the PDF. |
| 3 | **New endpoint** `GET /api/v1/papers/{paper_id}/preview-url` | Returns a signed URL for PDF preview in browser. |
| 4 | AI models (embedding, summarization, QA) now run via **Hugging Face Inference API** | No API contract change – same request/response shapes. Latency may slightly increase on cold starts (~10-30 s first call), then is fast. |
| 5 | **Celery worker** task routing fixed | No API contract change – processing is now reliable. Papers should move from `PROCESSING` → `PROCESSED` correctly. |

---

## 2. New Environment Variables (Backend Team)

These are set on the **backend** only. Frontend does not need these, but is listed for awareness:

```env
# Hugging Face Inference API – free tier
HUGGINGFACE_API_TOKEN=hf_xxxxxxxxx

# Google Cloud Storage
GCP_PROJECT_ID=your-project
GCP_BUCKET_NAME=research-assistant-papers
GCP_CREDENTIALS_PATH=/path/to/credentials.json
```

---

## 3. API Changes – PDF Upload

### Endpoint

```
POST /api/v1/papers/upload
```

### What Changed

- **Before**: PDF bytes were received but **not persisted** to any storage.
- **After**: PDF bytes are uploaded to GCS at path `papers/{user_id}/{sha256_hash}.pdf`.

### Frontend Impact

**None.** The request and response contract is identical:

**Request** (multipart form):
```
Content-Type: multipart/form-data
Authorization: Bearer <token>

file: <binary PDF>
```

**Response** (202 Accepted):
```json
{
  "id": "clxyz...",
  "title": "Attention Is All You Need",
  "status": "PROCESSING",
  "message": "Paper uploaded and processing started"
}
```

> **Note**: The `status` field may now be `"PROCESSED"` immediately if the synchronous fallback was used (Celery not running). Poll `GET /api/v1/papers/{id}` for status updates.

---

## 4. New Endpoint – PDF Download

### Endpoint

```
GET /api/v1/papers/{paper_id}/download
```

### Authentication

Requires `Authorization: Bearer <token>` header.

### Description

Downloads the original uploaded PDF. The backend fetches the file from GCS and **streams** it to the client. The frontend never needs GCS credentials.

### Response

- **200 OK** — Binary PDF stream  
  - `Content-Type: application/pdf`  
  - `Content-Disposition: attachment; filename="paper_title.pdf"`  
  - `Content-Length: <bytes>`

### Error Responses

| Status | Body | When |
|--------|------|------|
| 401 | `{"detail": "Not authenticated"}` | Missing / invalid token |
| 403 | `{"detail": "Access denied"}` | Paper belongs to another user |
| 404 | `{"detail": "Paper not found"}` | Invalid `paper_id` |
| 404 | `{"detail": "No PDF file associated with this paper"}` | Paper has no `file_url` |
| 404 | `{"detail": "PDF file not found in cloud storage"}` | File missing in GCS |
| 503 | `{"detail": "Cloud storage is not configured"}` | GCS not set up on backend |

### Frontend Usage Example (React)

```tsx
const downloadPdf = async (paperId: string) => {
  const response = await fetch(`/api/v1/papers/${paperId}/download`, {
    headers: { Authorization: `Bearer ${token}` },
  });

  if (!response.ok) {
    const err = await response.json();
    throw new Error(err.detail);
  }

  const blob = await response.blob();
  const url = URL.createObjectURL(blob);

  // Trigger browser download
  const a = document.createElement("a");
  a.href = url;
  a.download = response.headers.get("Content-Disposition")
    ?.split("filename=")[1]
    ?.replace(/"/g, "") || "paper.pdf";
  a.click();
  URL.revokeObjectURL(url);
};
```

---

## 5. New Endpoint – PDF Preview URL

### Endpoint

```
GET /api/v1/papers/{paper_id}/preview-url
```

### Authentication

Requires `Authorization: Bearer <token>` header.

### Description

Returns a **time-limited signed URL** (valid for 60 minutes) that points directly to the PDF in GCS. The frontend can use this URL in an `<iframe>`, a PDF viewer component (e.g., `react-pdf`, `PDF.js`), or the browser's built-in PDF viewer.

### Response (200 OK)

```json
{
  "preview_url": "https://storage.googleapis.com/research-assistant-papers/papers/userId/hash.pdf?X-Goog-Signature=...",
  "expires_in_minutes": 60
}
```

### Error Responses

Same error table as the download endpoint above.

### Frontend Usage Example (React)

```tsx
// Option A: Open in new tab
const previewPdf = async (paperId: string) => {
  const res = await fetch(`/api/v1/papers/${paperId}/preview-url`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  const { preview_url } = await res.json();
  window.open(preview_url, "_blank");
};

// Option B: Embed in iframe
const PdfPreview = ({ paperId }: { paperId: string }) => {
  const [url, setUrl] = useState<string | null>(null);

  useEffect(() => {
    fetch(`/api/v1/papers/${paperId}/preview-url`, {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then((r) => r.json())
      .then(({ preview_url }) => setUrl(preview_url));
  }, [paperId]);

  if (!url) return <Spinner />;
  return <iframe src={url} width="100%" height="800px" />;
};
```

### Which Endpoint to Use?

| Use Case | Endpoint |
|----------|----------|
| **"Download" button** — user saves PDF to disk | `GET /papers/{id}/download` |
| **"Preview" button** — view PDF inline in browser | `GET /papers/{id}/preview-url` |

---

## 6. AI Processing (Embeddings / Summarization / Q&A)

### What Changed

All three AI models now call the **Hugging Face Inference API** instead of loading model weights locally:

| Model | HF Model ID | Purpose |
|-------|-------------|---------|
| Embedding | `sentence-transformers/all-MiniLM-L6-v2` | Vector embeddings for semantic search |
| Summarizer | `facebook/bart-large-cnn` | Paper summarization |
| QA | `deepset/roberta-base-squad2` | Question answering on paper chunks |

### Frontend Impact

**None.** All existing API endpoints remain identical:

- `POST /api/v1/papers/search` — semantic search (unchanged)
- `POST /api/v1/chat/sessions/{id}/messages` — Q&A chat (unchanged)
- `GET /api/v1/research/papers/{id}/summary` — summarization (unchanged)

### Performance Notes

| Aspect | Before (Local) | After (HF API) |
|--------|----------------|-----------------|
| First request | 2-5 min (model download) | 10-30 s (cold start) |
| Subsequent requests | Fast | Fast (~1-3 s) |
| Memory usage | 2-4 GB RAM | ~100 MB RAM |
| Model weight download | Required | Not required |

> **Cold start**: The first call to each model after it has been idle may take 10-30 seconds as Hugging Face loads the model. The backend automatically retries. The frontend should show a loading spinner and **not** set an aggressive timeout (recommend ≥ 120 s).

---

## 7. Celery Worker Changes

### Root Cause of the Bug

The Celery worker configuration used **custom queue routing**:

```python
# BEFORE (broken for dev)
task_routes = {
    "process_paper_task": {"queue": "paper_processing"},
    ...
}
```

When you ran `make dev-worker`, the worker only listened on the **default `celery` queue**, but tasks were routed to `paper_processing`, `embedding`, `ai_tasks` queues → tasks were never picked up.

### Fix

1. Custom queue routing is **disabled by default** (commented out).
2. The `make dev-worker` command now explicitly listens on all queues: `-Q celery,paper_processing,embedding,ai_tasks`.
3. The upload endpoint now dispatches to `queue="celery"` (the default) so any worker picks it up.

### Frontend Impact

**None.** But papers should now reliably progress through processing:

```
PENDING → PROCESSING → PROCESSED
```

If you were showing a "stuck in processing" state, it should now resolve. You can poll `GET /api/v1/papers/{paper_id}` and check:

```json
{
  "status": "PROCESSED",
  "processing_progress": 1.0
}
```

---

## 8. Migration Checklist for Frontend

### Must Do

- [ ] **Add "Preview" button** for each paper that calls `GET /api/v1/papers/{paper_id}/preview-url` and opens the returned URL (iframe or new tab).
- [ ] **Add "Download" button** for each paper that calls `GET /api/v1/papers/{paper_id}/download` and triggers a file save.
- [ ] **Handle new HTTP 503** error from download/preview endpoints (show "Cloud storage not configured" message).
- [ ] **Increase API timeout** for summarization / Q&A / search endpoints to **120 seconds** (HF API cold start can take 10-30 s).

### Nice to Have

- [ ] Show a "Model warming up, please wait..." message if requests take > 10 s.
- [ ] Add progress polling for paper processing status (`processing_progress` field, 0.0 → 1.0).
- [ ] Cache the `preview_url` for up to 50 minutes (it's valid for 60) to avoid unnecessary API calls.

### No Changes Needed

- [ ] Paper upload form — no changes.
- [ ] Chat / Q&A interface — no changes.
- [ ] Semantic search — no changes.
- [ ] Paper list / detail views — no changes (existing `file_url` field is still present).
- [ ] Authentication — no changes.

---

## 9. Full Request / Response Examples

### 9.1 Upload a Paper

```bash
curl -X POST http://localhost:8000/api/v1/papers/upload \
  -H "Authorization: Bearer <token>" \
  -F "file=@paper.pdf"
```

```json
{
  "id": "abc123",
  "title": "Attention Is All You Need",
  "status": "PROCESSING",
  "message": "Paper uploaded and processing started"
}
```

### 9.2 Download a Paper PDF

```bash
curl -X GET http://localhost:8000/api/v1/papers/abc123/download \
  -H "Authorization: Bearer <token>" \
  -o downloaded.pdf
```

Response: Binary PDF stream with appropriate headers.

### 9.3 Get Preview URL

```bash
curl -X GET http://localhost:8000/api/v1/papers/abc123/preview-url \
  -H "Authorization: Bearer <token>"
```

```json
{
  "preview_url": "https://storage.googleapis.com/bucket/papers/uid/hash.pdf?X-Goog-Signature=abc...",
  "expires_in_minutes": 60
}
```

### 9.4 Check Paper Processing Status

```bash
curl -X GET http://localhost:8000/api/v1/papers/abc123 \
  -H "Authorization: Bearer <token>"
```

```json
{
  "id": "abc123",
  "title": "Attention Is All You Need",
  "status": "PROCESSED",
  "processing_progress": 1.0,
  "file_url": "papers/user-id/sha256hash.pdf",
  ...
}
```

### 9.5 Paper Status Values

| Status | Meaning | Frontend Action |
|--------|---------|----------------|
| `PENDING` | Just created, not yet processed | Show spinner |
| `PROCESSING` | Embeddings / metadata being generated | Show progress bar using `processing_progress` (0.0-1.0) |
| `PROCESSED` | Ready for search, Q&A, summarization | Enable all features |
| `FAILED` | Processing failed | Show error + "Reprocess" button |
| `ARCHIVED` | Soft-deleted | Hide or show greyed out |

---

## 10. Error Codes Reference

### New Error Codes

| Endpoint | Status | Detail | When |
|----------|--------|--------|------|
| `GET /papers/{id}/download` | 503 | `"Cloud storage is not configured"` | GCS credentials missing on backend |
| `GET /papers/{id}/download` | 404 | `"PDF file not found in cloud storage"` | File deleted from GCS |
| `GET /papers/{id}/preview-url` | 503 | `"Cloud storage is not configured"` | GCS credentials missing on backend |
| `GET /papers/{id}/preview-url` | 500 | `"Failed to generate preview URL"` | GCS signed URL generation failed |

### Existing Error Codes (Unchanged)

| Status | Detail | When |
|--------|--------|------|
| 400 | `"Only PDF files are accepted"` | Non-PDF upload |
| 400 | `"File exceeds 50MB limit"` | File too large |
| 409 | `"This paper has already been uploaded"` | Duplicate PDF hash |
| 401 | `"Not authenticated"` | Missing / expired token |
| 403 | `"Access denied"` | User doesn't own the paper |
| 404 | `"Paper not found"` | Invalid paper ID |

---

## Appendix: Backend Running Instructions

For local development, the backend team should run:

```bash
# Terminal 1 — Start services (PostgreSQL + Redis)
docker compose up -d postgres redis

# Terminal 2 — Run the backend API
make dev

# Terminal 3 — Run the Celery worker (IMPORTANT — must be a separate terminal)
make dev-worker
```

> **Note for backend team**: Make sure your `.env` file has `HUGGINGFACE_API_TOKEN` set. Get a free token at https://huggingface.co/settings/tokens.
