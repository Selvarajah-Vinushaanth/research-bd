# Frontend API Changes – V3 (Chat Quality + Reading List Fix)

> **Date**: 2025-03-12  
> **Backend version**: 1.0.0  
> **Summary**: Upgraded chat QA model from extractive to generative LLM; fixed reading list returning empty.

---

## 1. Chat Responses – Generative LLM Upgrade

### What changed
The backend QA model has been upgraded from **extractive QA** (`deepset/roberta-base-squad2`, which only returned short text spans) to a **generative LLM** (`mistralai/Mistral-7B-Instruct-v0.3`).

### Impact on frontend
- **`POST /api/v1/chat/ask`** and **`POST /api/v1/chat/multi-paper`** now return **long, Markdown-formatted** answers instead of short text fragments.
- The `answer` field may contain:
  - Headings (`##`, `###`)
  - Bullet points / numbered lists
  - **Bold** and *italic* text
  - Multi-paragraph responses (typically 200–600 words)
- The `confidence` field is now a heuristic (0.5 – 0.95) based on answer quality rather than the old extractive span score.

### Frontend requirements
| Area | Action needed |
|------|--------------|
| **Chat message rendering** | Ensure you render the `answer` field with a **Markdown renderer** (e.g. `react-markdown`). If you're already using ReactMarkdown in ChatPage.tsx — **no change needed**. |
| **Message container styling** | Longer answers may need scrollable containers or auto-expanding message bubbles. |
| **Loading indicator** | Generative responses take 3-8 seconds (vs <1s for extractive). Consider adding a typing/thinking indicator. |

### Response format (unchanged schema)
```json
{
  "session_id": "...",
  "message_id": "...",
  "question": "What is the main finding?",
  "answer": "## Main Finding\n\nThe paper presents...\n\n### Key Contributions\n\n- **Finding 1**: ...\n- **Finding 2**: ...",
  "confidence": 0.82,
  "sources": [...],
  "tokens_used": 512,
  "response_time": 4.2
}
```

---

## 2. Reading List – Route Fix

### What changed
The `GET /api/v1/collections/reading-list` endpoint was being intercepted by the `GET /api/v1/collections/{collection_id}` route (FastAPI was treating `"reading-list"` as a `collection_id` path parameter). This caused the reading list to return a 404 or empty result.

**Fix**: All `/reading-list` and `/annotations` routes are now defined **before** any `/{collection_id}` routes in the router.

### Query parameter fix
The `GET /api/v1/collections/reading-list` endpoint now accepts **`status`** as the query parameter name (previously was `status_filter`).

| Before (broken) | After (fixed) |
|-----------------|---------------|
| `GET /collections/reading-list?status_filter=UNREAD` | `GET /collections/reading-list?status=UNREAD` |

### Frontend requirements
| Area | Action needed |
|------|--------------|
| **Reading list fetch** | If you're already sending `?status=UNREAD` — **no change needed**. |
| **Error handling** | The endpoint now correctly returns `200` with the item list instead of 404. |

---

## 3. Collection "Add Paper" – Existing Endpoint

The endpoint to add a paper to a collection already exists:

```
POST /api/v1/collections/{collection_id}/papers/{paper_id}
```

To populate a **dropdown of existing papers**, use:

```
GET /api/v1/papers?page=1&page_size=100
```

This returns all the user's papers with `id`, `title`, `authors`, `status`.

### Suggested frontend flow
1. User clicks "Add Paper" on a collection
2. Frontend fetches `GET /api/v1/papers` to list all user papers
3. Show a dropdown/select with paper titles
4. On selection, call `POST /api/v1/collections/{collection_id}/papers/{paper_id}`

---

## 4. Files Modified (Backend)

| File | Change |
|------|--------|
| `app/ai_models/qa_model.py` | Replaced extractive-only QA with generative (Mistral-7B-Instruct) + extractive fallback |
| `app/api/collection_routes.py` | Reordered routes: reading-list & annotations before `/{collection_id}` to fix routing conflict; fixed `status` query param |
| `app/config.py` | Added `GENERATIVE_MODEL` setting |

---

## 5. No Breaking Changes

All existing API schemas, endpoints, and response shapes are unchanged. The only differences are:
- Chat `answer` field now contains richer Markdown content (backward compatible)
- Reading list endpoint now works correctly (was broken before)
- `status` query param accepted (was `status_filter` before, which the frontend wasn't using)
