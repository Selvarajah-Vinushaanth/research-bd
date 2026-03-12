# Backend API Changes v2 – Frontend Integration Guide

> **Date**: 2026-03-12  
> **Version**: 1.2.0  
> **Audience**: Frontend developers  

---

## Summary of Changes

| # | Change | Impact on Frontend |
|---|--------|--------------------|
| 1 | **New endpoint** `GET /api/v1/collections/{id}` — Collection detail with papers | Frontend can now show papers inside a collection |
| 2 | **New endpoint** `DELETE /api/v1/collections/reading-list/{item_id}` — Remove from reading list | Frontend can now delete reading list items |
| 3 | Reading list responses now include **paper_title, paper_authors, paper_status** | Update reading list UI to show paper info |
| 4 | Notes responses now include **paper_title** | Update notes UI to show linked paper title |
| 5 | Chat session history now returns **flat message list** (separate USER & ASSISTANT messages) | Update chat UI to render flat message array |
| 6 | Dashboard recent activity **limited to 15** items and now includes **resource_id** & **details** | No breaking change; activity feed is now bounded |

---

## 1. Collection Detail — View & Add Papers

### New Endpoint: Get Collection with Papers

```
GET /api/v1/collections/{collection_id}
```

**Auth required.** Returns the collection metadata plus all papers in it.

**Response 200:**
```json
{
  "id": "uuid",
  "name": "Transformer Papers",
  "description": "Key papers on transformers",
  "is_public": false,
  "paper_count": 3,
  "papers": [
    {
      "id": "paper-uuid-1",
      "title": "Attention Is All You Need",
      "authors": ["Vaswani, A.", "Shazeer, N."],
      "abstract": "We propose a new...",
      "status": "PROCESSED",
      "keywords": ["transformer", "attention"],
      "created_at": "2026-01-01T00:00:00Z",
      "added_at": "2026-01-15T10:30:00Z"
    }
  ],
  "created_at": "2026-01-01T00:00:00Z"
}
```

### Existing Endpoint: Add Paper to Collection

```
POST /api/v1/collections/{collection_id}/papers/{paper_id}
```

**Auth required.** Response: `201 { "message": "Paper added to collection" }`

**Error Responses:**
| Status | Detail | When |
|--------|--------|------|
| 404 | `"Collection not found"` | Invalid collection_id or wrong user |
| 404 | `"Paper not found"` | Invalid paper_id |
| 409 | `"Paper already in collection"` | Duplicate |

### Existing Endpoint: Remove Paper from Collection

```
DELETE /api/v1/collections/{collection_id}/papers/{paper_id}
```

**Auth required.** Response: `204 No Content`

### Frontend Implementation Guide

On the **Collection Detail page** (`/collections/:id`):

1. Fetch collection with papers: `GET /api/v1/collections/{id}`
2. Display papers list with title, authors, status badge, added date
3. Add an **"Add Paper"** button that opens a modal:
   - Fetch user's papers via `GET /api/v1/papers` 
   - Show a searchable list of papers
   - On select, call `POST /api/v1/collections/{id}/papers/{paper_id}`
   - On success, refetch collection detail (`invalidateQueries(["collection", id])`)
4. Each paper card should have a **"Remove"** button:
   - On click (with confirmation), call `DELETE /api/v1/collections/{id}/papers/{paper_id}`
   - Refetch collection detail

```tsx
// Example: Add paper to collection
const addPaperToCollection = async (collectionId: string, paperId: string) => {
  await api.post(`/collections/${collectionId}/papers/${paperId}`);
  // Invalidate query to refresh the collection detail
  queryClient.invalidateQueries(["collection", collectionId]);
  toast.success("Paper added to collection");
};

// Example: Remove paper from collection
const removePaperFromCollection = async (collectionId: string, paperId: string) => {
  await api.delete(`/collections/${collectionId}/papers/${paperId}`);
  queryClient.invalidateQueries(["collection", collectionId]);
  toast.success("Paper removed from collection");
};
```

---

## 2. Reading List — Now Complete with Paper Details & Delete

### Updated Response Shape

All reading list endpoints (`POST`, `GET`, `PUT`) now return **paper details**:

```json
{
  "id": "uuid",
  "paper_id": "paper-uuid",
  "paper_title": "Attention Is All You Need",
  "paper_authors": ["Vaswani, A.", "Shazeer, N."],
  "paper_status": "PROCESSED",
  "priority": "HIGH",
  "status": "UNREAD",
  "notes": "Must read this week",
  "due_date": "2026-06-01T00:00:00Z",
  "added_at": "2026-01-01T00:00:00Z"
}
```

**New fields added to response:**
| Field | Type | Description |
|-------|------|-------------|
| `paper_title` | `string \| null` | Title of the linked paper |
| `paper_authors` | `string[] \| null` | Authors of the linked paper |
| `paper_status` | `string \| null` | Processing status of the paper (`PROCESSED`, etc.) |

### New Endpoint: Delete Reading List Item

```
DELETE /api/v1/collections/reading-list/{item_id}
```

**Auth required.** Response: `204 No Content`

**Error Responses:**
| Status | Detail | When |
|--------|--------|------|
| 404 | `"Item not found"` | Invalid item_id or wrong user |

### Frontend Implementation Guide

On the **Reading List page** (`/reading-list`):

1. Display `paper_title` and `paper_authors` instead of just `paper_id`
2. Show `paper_status` as a badge (e.g., "Processed" in green)
3. Add a **"Remove"** button on each item:
   - Call `DELETE /api/v1/collections/reading-list/{item_id}`
   - Refetch reading list
4. The priority badge should be color-coded: Urgent=red, High=orange, Medium=blue, Low=gray
5. The status dropdown should allow inline changes via `PUT /api/v1/collections/reading-list/{item_id}`

```tsx
// Delete reading list item
const removeFromReadingList = async (itemId: string) => {
  await api.delete(`/collections/reading-list/${itemId}`);
  queryClient.invalidateQueries(["reading-list"]);
  toast.success("Removed from reading list");
};
```

---

## 3. Notes — Now Include Paper Title

### Updated Response Shape

All note endpoints (`POST /create`, `GET`, `GET /{id}`, `PUT /{id}`, `POST /generate`) now return `paper_title`:

```json
{
  "id": "uuid",
  "user_id": "user-uuid",
  "paper_id": "paper-uuid",
  "paper_title": "Attention Is All You Need",
  "title": "Key Findings",
  "content": "The paper shows that...",
  "note_type": "MANUAL",
  "tags": ["important"],
  "is_pinned": false,
  "created_at": "2026-01-01T00:00:00Z",
  "updated_at": "2026-01-01T00:00:00Z"
}
```

**New field:**
| Field | Type | Description |
|-------|------|-------------|
| `paper_title` | `string \| null` | Title of the linked paper (null if note is not linked to a paper) |

### Frontend Implementation Guide

- Display `paper_title` on note cards (e.g., "Linked to: Attention Is All You Need")
- Use it as a clickable link to navigate to `/papers/{paper_id}`
- In the notes filter, you can now display paper titles instead of raw IDs

---

## 4. Chat History — Flat Message List

### What Changed

Previously, each message record contained both the user question (`message` field) and the AI answer (`response` field) in **one object**. This made it confusing for the frontend to render a chat timeline.

**Now**, `GET /api/v1/chat/sessions/{session_id}` returns a **flat list** of separate USER and ASSISTANT messages.

### Updated Response Shape

```json
{
  "session": {
    "id": "uuid",
    "title": "Discussion about Transformers",
    "session_type": "SINGLE_PAPER",
    "paper_id": "paper-uuid",
    "is_active": true,
    "message_count": 4,
    "created_at": "2026-01-01T00:00:00Z",
    "updated_at": "2026-01-01T00:05:00Z"
  },
  "messages": [
    {
      "id": "msg1_user",
      "role": "USER",
      "content": "What is the main contribution of this paper?",
      "confidence": null,
      "tokens_used": null,
      "response_time": null,
      "created_at": "2026-01-01T00:00:00Z"
    },
    {
      "id": "msg1_assistant",
      "role": "ASSISTANT",
      "content": "The main contribution of this paper is the Transformer architecture, which relies entirely on self-attention mechanisms to draw global dependencies between input and output...",
      "confidence": 0.92,
      "tokens_used": 256,
      "response_time": 2.1,
      "created_at": "2026-01-01T00:00:01Z"
    },
    {
      "id": "msg2_user",
      "role": "USER",
      "content": "How does self-attention work?",
      "confidence": null,
      "tokens_used": null,
      "response_time": null,
      "created_at": "2026-01-01T00:01:00Z"
    },
    {
      "id": "msg2_assistant",
      "role": "ASSISTANT",
      "content": "Self-attention, also known as intra-attention, is a mechanism that computes attention scores between all positions in a sequence...",
      "confidence": 0.88,
      "tokens_used": 312,
      "response_time": 1.8,
      "created_at": "2026-01-01T00:01:01Z"
    }
  ]
}
```

### Key Changes

| Before | After |
|--------|-------|
| Each message had both `message` and `response` fields | Each message has a single `content` field |
| `role` was always `USER` on the record | `role` is either `USER` or `ASSISTANT` |
| Frontend had to split one record into two bubbles | Frontend renders each item as one bubble |
| Message ID was the same for question+answer | IDs are `{original_id}_user` and `{original_id}_assistant` |

### Frontend Implementation Guide

```tsx
// Render chat messages
{messages.map((msg) => (
  <div
    key={msg.id}
    className={msg.role === "USER" ? "chat-bubble-right" : "chat-bubble-left"}
  >
    {msg.role === "ASSISTANT" ? (
      <ReactMarkdown>{msg.content}</ReactMarkdown>
    ) : (
      <p>{msg.content}</p>
    )}
    {msg.confidence && (
      <span className="confidence-badge">
        Confidence: {(msg.confidence * 100).toFixed(0)}%
      </span>
    )}
  </div>
))}
```

---

## 5. Dashboard — Recent Activity Changes

### What Changed

- Recent activity is now **limited to 15** items (was 20)
- Each activity now includes `resource_id` and `details` for linking

### Updated Response Shape (within dashboard response)

```json
{
  "recent_activity": [
    {
      "action": "PAPER_UPLOADED",
      "resource": "paper",
      "resource_id": "paper-uuid-123",
      "details": null,
      "timestamp": "2026-03-12T10:30:00Z"
    },
    {
      "action": "CHAT_QUESTION",
      "resource": "chat",
      "resource_id": "session-uuid-456",
      "details": {"question_length": 45},
      "timestamp": "2026-03-12T09:15:00Z"
    },
    {
      "action": "PAPER_SUMMARIZED",
      "resource": "paper",
      "resource_id": "paper-uuid-789",
      "details": {"summary_type": "STRUCTURED"},
      "timestamp": "2026-03-12T08:00:00Z"
    }
  ]
}
```

**New fields in each activity item:**
| Field | Type | Description |
|-------|------|-------------|
| `resource_id` | `string \| null` | ID of the resource (paper ID, session ID, etc.) — use for linking |
| `details` | `object \| null` | Extra context about the action |

### Frontend Implementation Guide

- Use `resource_id` to create clickable links in the activity feed:
  - `resource === "paper"` → link to `/papers/{resource_id}`
  - `resource === "chat"` → link to `/chat/{resource_id}`
  - `resource === "user"` / `resource === "auth"` → no link needed
- Show only these 15 items; no pagination needed
- Display human-readable action labels:

```tsx
const actionLabels: Record<string, string> = {
  PAPER_UPLOADED: "Uploaded a paper",
  PAPER_SUMMARIZED: "Generated summary",
  CHAT_QUESTION: "Asked a question",
  USER_REGISTERED: "Account created",
  USER_LOGIN: "Logged in",
};
```

---

## 6. Migration Checklist for Frontend

### Must Do

- [ ] **Collection detail page** (`/collections/:id`): Fetch `GET /api/v1/collections/{id}` to get papers list
- [ ] **Add Paper to Collection**: Add button + modal on collection detail page that calls `POST /api/v1/collections/{id}/papers/{paper_id}`
- [ ] **Remove Paper from Collection**: Add remove button on each paper card that calls `DELETE /api/v1/collections/{id}/papers/{paper_id}`
- [ ] **Reading list**: Update UI to show `paper_title`, `paper_authors`, `paper_status` from response
- [ ] **Reading list delete**: Add remove button that calls `DELETE /api/v1/collections/reading-list/{item_id}`
- [ ] **Notes**: Display `paper_title` field on note cards
- [ ] **Chat history**: Update to render flat `messages` array with `role` and `content` (not `message`/`response`)
- [ ] **Dashboard activity**: Use `resource_id` for linking, show max 15 items

### TypeScript Interface Updates

```typescript
// Updated ReadingListItem
interface ReadingListItem {
  id: string;
  paper_id: string;
  paper_title: string | null;    // NEW
  paper_authors: string[] | null; // NEW
  paper_status: string | null;    // NEW
  priority: "LOW" | "MEDIUM" | "HIGH" | "URGENT";
  status: "UNREAD" | "READING" | "COMPLETED" | "SKIPPED";
  notes: string | null;
  due_date: string | null;
  added_at: string;
}

// Updated NoteResponse
interface NoteResponse {
  id: string;
  user_id: string;
  paper_id: string | null;
  paper_title: string | null;  // NEW
  title: string;
  content: string;
  note_type: string;
  tags: string[];
  is_pinned: boolean;
  created_at: string;
  updated_at: string;
}

// NEW: Flat chat message (replaces old ChatMessageResponse for history)
interface ChatMessageFlat {
  id: string;
  role: "USER" | "ASSISTANT";
  content: string;              // was split across `message` and `response`
  confidence: number | null;
  tokens_used: number | null;
  response_time: number | null;
  created_at: string;
}

// Updated ChatHistoryResponse
interface ChatHistoryResponse {
  session: ChatSessionResponse;
  messages: ChatMessageFlat[];  // flat list, not the old format
}

// NEW: Collection detail
interface CollectionDetailResponse {
  id: string;
  name: string;
  description: string | null;
  is_public: boolean;
  paper_count: number;
  papers: CollectionPaper[];    // NEW: full paper list
  created_at: string;
}

interface CollectionPaper {
  id: string;
  title: string;
  authors: string[];
  abstract: string | null;
  status: string;
  keywords: string[];
  created_at: string;
  added_at: string;            // when it was added to this collection
}

// Updated DashboardActivity
interface DashboardActivity {
  action: string;
  resource: string | null;
  resource_id: string | null;  // NEW
  details: Record<string, any> | null; // NEW
  timestamp: string;
}
```

### React Query Keys

```typescript
// New/updated query keys
["collection", collectionId]       // GET /collections/{id} — detail with papers
["reading-list", filters]          // GET /collections/reading-list
["chat-history", sessionId]        // GET /chat/sessions/{id} — now flat messages
```

---

## API Endpoint Quick Reference

| Method | Endpoint | What's New |
|--------|----------|------------|
| `GET` | `/api/v1/collections/{id}` | **NEW** — Collection detail with papers |
| `POST` | `/api/v1/collections/{id}/papers/{paper_id}` | Existing — Add paper to collection |
| `DELETE` | `/api/v1/collections/{id}/papers/{paper_id}` | Existing — Remove paper from collection |
| `DELETE` | `/api/v1/collections/reading-list/{item_id}` | **NEW** — Delete reading list item |
| `GET` | `/api/v1/collections/reading-list` | **UPDATED** — Now includes paper details |
| `POST` | `/api/v1/collections/reading-list` | **UPDATED** — Response includes paper details |
| `PUT` | `/api/v1/collections/reading-list/{item_id}` | **UPDATED** — Response includes paper details |
| `GET` | `/api/v1/chat/sessions/{id}` | **UPDATED** — Flat message list (USER/ASSISTANT) |
| `GET` | `/api/v1/notes` | **UPDATED** — Includes `paper_title` |
| `POST` | `/api/v1/notes/create` | **UPDATED** — Includes `paper_title` |
| `GET` | `/api/v1/notes/{id}` | **UPDATED** — Includes `paper_title` |
| `PUT` | `/api/v1/notes/{id}` | **UPDATED** — Includes `paper_title` |
| `GET` | `/api/v1/advanced/dashboard` | **UPDATED** — 15 items, includes `resource_id` & `details` |
