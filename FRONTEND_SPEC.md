# 🧠 AI Research Assistant — Frontend Specification for Lovable

> **Copy-paste this entire document into Lovable to generate the complete frontend.**

---

## Project Overview

Build a **modern, production-ready frontend** for an AI Research Assistant platform. This is an academic research tool that helps researchers upload PDF papers, search them semantically, chat with papers using AI (RAG), generate summaries, manage notes, organize collections, and discover insights.

**Tech Stack:**
- **React 18+** with **TypeScript**
- **Vite** for bundling
- **Tailwind CSS** + **shadcn/ui** component library
- **React Router v6** for routing
- **TanStack Query (React Query)** for API state management
- **Zustand** for global auth/UI state
- **Axios** for HTTP requests
- **Lucide React** for icons
- **Recharts** for dashboard charts
- **React Markdown** for rendering AI responses
- **React Dropzone** for file uploads
- **Sonner** (or React Hot Toast) for toast notifications
- **Framer Motion** for subtle animations

**Design Style:**
- Clean, minimal, professional academic aesthetic
- Dark mode and light mode toggle
- Responsive: desktop-first but fully mobile-friendly
- Color palette: Deep indigo/violet primary, slate grays, white backgrounds, subtle gradients
- Card-based layouts with generous whitespace
- Smooth hover states and transitions

---

## Backend API Reference

**Base URL:** `http://localhost:8000`
**API Prefix:** `/api/v1`
**Auth:** JWT Bearer token in `Authorization: Bearer <token>` header
**Content-Type:** `application/json` (except file upload which is `multipart/form-data`)

---

### Authentication Endpoints

#### `POST /api/v1/auth/register` — Register
No auth required.
```json
// Request
{
  "email": "user@example.com",        // required, valid email
  "password": "StrongP@ss1",          // required, min 8 chars, 1 uppercase, 1 digit, 1 special char
  "full_name": "John Doe",            // required, 2-100 chars
  "institution": "MIT",               // optional
  "research_interests": ["NLP", "CV"] // optional, array of strings
}
// Response 201
{
  "id": "uuid",
  "email": "user@example.com",
  "full_name": "John Doe",
  "role": "RESEARCHER",
  "institution": "MIT",
  "research_interests": ["NLP", "CV"],
  "is_active": true,
  "created_at": "2026-01-01T00:00:00Z",
  "updated_at": "2026-01-01T00:00:00Z"
}
```

#### `POST /api/v1/auth/login` — Login
No auth required.
```json
// Request
{
  "email": "user@example.com",
  "password": "StrongP@ss1"
}
// Response 200
{
  "access_token": "eyJ...",
  "refresh_token": "eyJ...",
  "token_type": "bearer",
  "expires_in": 1800
}
```

#### `POST /api/v1/auth/refresh` — Refresh Token
No auth required.
```json
// Request
{ "refresh_token": "eyJ..." }
// Response 200 — same shape as login response
```

#### `GET /api/v1/auth/profile` — Get Current User Profile
Auth required.
```json
// Response 200 — same shape as register response (UserResponse)
```

#### `PUT /api/v1/auth/profile` — Update Profile
Auth required. All fields optional.
```json
// Request
{
  "full_name": "Updated Name",
  "institution": "Stanford",
  "research_interests": ["ML"],
  "bio": "Researcher in ML"
}
// Response 200 — UserResponse
```

#### `POST /api/v1/auth/change-password` — Change Password
Auth required.
```json
// Request
{
  "current_password": "OldP@ss1",
  "new_password": "NewP@ss2"
}
// Response 200
{ "message": "Password updated successfully" }
```

---

### Paper Endpoints

#### `POST /api/v1/papers/upload` — Upload PDF
Auth required. Content-Type: `multipart/form-data`.
- Field `file`: PDF file (max 50MB)
```json
// Response 202
{
  "id": "uuid",
  "title": "Paper Title",
  "status": "PROCESSING",
  "message": "Paper uploaded and processing started"
}
```

#### `GET /api/v1/papers` — List Papers (Paginated)
Auth required. Query params:
- `page` (int, default 1)
- `page_size` (int, default 20, max 100)
- `status` (optional: "UPLOADED", "PROCESSING", "COMPLETED", "FAILED")
- `search` (optional: text search on title/abstract)
```json
// Response 200
{
  "papers": [
    {
      "id": "uuid",
      "title": "Attention Is All You Need",
      "authors": ["Vaswani, A."],
      "abstract": "We propose...",
      "status": "COMPLETED",
      "file_name": "attention.pdf",
      "file_hash": "abc123",
      "page_count": 15,
      "published_year": 2017,
      "journal": "NeurIPS",
      "doi": "10.1234/...",
      "tags": ["transformer", "attention"],
      "language": "en",
      "created_at": "2026-01-01T00:00:00Z",
      "updated_at": "2026-01-01T00:00:00Z"
    }
  ],
  "total": 42,
  "page": 1,
  "page_size": 20,
  "total_pages": 3
}
```

#### `GET /api/v1/papers/{paper_id}` — Get Paper Detail
Auth required.
```json
// Response 200 — PaperDetailResponse (PaperResponse + extras)
{
  // ...all PaperResponse fields...
  "chunk_count": 45,
  "summaries": [...],
  "insights": [...]
}
```

#### `PUT /api/v1/papers/{paper_id}` — Update Paper
Auth required. All fields optional.
```json
// Request
{
  "title": "Updated Title",
  "authors": ["Author A"],
  "abstract": "Updated abstract",
  "tags": ["tag1"],
  "published_year": 2024,
  "journal": "Nature"
}
// Response 200 — PaperResponse
```

#### `DELETE /api/v1/papers/{paper_id}` — Delete Paper
Auth required. Response: 204 No Content.

#### `POST /api/v1/papers/search` — Semantic Search
Auth required.
```json
// Request
{
  "query": "transformer attention mechanism",  // required, 3-500 chars
  "top_k": 10,                                 // optional, 1-50, default 10
  "paper_id": "uuid",                          // optional, search within specific paper
  "threshold": 0.5                             // optional, 0.0-1.0, default 0.5
}
// Response 200
{
  "results": [
    {
      "chunk_id": "uuid",
      "paper_id": "uuid",
      "paper_title": "Attention Is All You Need",
      "content": "The dominant sequence transduction models...",
      "similarity": 0.89,
      "chunk_index": 3
    }
  ],
  "query": "transformer attention mechanism",
  "total_results": 10
}
```

#### `GET /api/v1/papers/{paper_id}/related?top_k=5` — Related Papers
Auth required. Query: `top_k` (int, 1-50, default 10).
```json
// Response 200
{
  "paper_id": "uuid",
  "related": [
    { "paper_id": "uuid", "title": "BERT...", "similarity": 0.82, "authors": [...] }
  ]
}
```

#### `GET /api/v1/papers/{paper_id}/citations?format=APA` — Generate Citations
Auth required. Query: `format` (APA|MLA|IEEE|CHICAGO|HARVARD|BIBTEX, default APA).
```json
// Response 200
{
  "paper_id": "uuid",
  "citations": {
    "APA": "Vaswani, A. (2017). Attention Is All You Need...",
    "MLA": "...",
    "IEEE": "...",
    "CHICAGO": "...",
    "HARVARD": "...",
    "BIBTEX": "@article{...}"
  }
}
```

---

### Chat (RAG) Endpoints

#### `POST /api/v1/chat/ask` — Ask Question About a Paper
Auth required.
```json
// Request
{
  "question": "What is the main contribution of this paper?",  // required, 3-2000 chars
  "paper_id": "uuid",             // optional (if not set, searches all papers)
  "session_id": "uuid",           // optional (continue existing session)
  "top_k": 5,                     // optional, 1-20, default 5
  "include_sources": true          // optional, default true
}
// Response 200
{
  "answer": "The main contribution is...",
  "confidence": 0.92,
  "sources": [
    {
      "chunk_id": "uuid",
      "content": "We propose a new...",
      "similarity": 0.89,
      "chunk_index": 3,
      "paper_title": "Attention Is All You Need"
    }
  ],
  "session_id": "uuid",
  "question": "What is the main contribution?",
  "model_used": "deepset/roberta-base-squad2",
  "processing_time": 1.23,
  "paper_id": "uuid"
}
```

#### `POST /api/v1/chat/multi-paper` — Ask Across Multiple Papers
Auth required.
```json
// Request
{
  "question": "Compare attention mechanisms across these papers",
  "paper_ids": ["uuid1", "uuid2", "uuid3"],  // required, 2-20 paper IDs
  "session_id": "uuid",                       // optional
  "top_k": 5                                  // optional, 1-20
}
// Response 200 — same shape as single paper ChatResponse
```

#### `GET /api/v1/chat/sessions?page=1&page_size=20` — List Chat Sessions
Auth required.
```json
// Response 200
{
  "sessions": [
    {
      "id": "uuid",
      "title": "Discussion about Transformers",
      "session_type": "SINGLE_PAPER",
      "paper_id": "uuid",
      "message_count": 12,
      "created_at": "2026-01-01T00:00:00Z",
      "updated_at": "2026-01-01T00:00:00Z",
      "last_message_at": "2026-01-01T00:05:00Z",
      "is_active": true
    }
  ],
  "total": 5,
  "page": 1
}
```

#### `GET /api/v1/chat/sessions/{session_id}/history` — Get Chat History
Auth required.
```json
// Response 200
{
  "session_id": "uuid",
  "messages": [
    {
      "id": "uuid",
      "role": "USER",
      "content": "What is attention?",
      "sources": null,
      "confidence": null,
      "created_at": "2026-01-01T00:00:00Z"
    },
    {
      "id": "uuid",
      "role": "ASSISTANT",
      "content": "Attention is a mechanism...",
      "sources": [...],
      "confidence": 0.92,
      "created_at": "2026-01-01T00:00:01Z"
    }
  ]
}
```

#### `DELETE /api/v1/chat/sessions/{session_id}` — Delete Session
Auth required. Response: 204 No Content.

---

### Research Endpoints

#### `POST /api/v1/research/summarize/{paper_id}?summary_type=STRUCTURED&force=false` — Summarize Paper
Auth required. Query params:
- `summary_type`: "STRUCTURED" | "BRIEF" | "DETAILED" | "ABSTRACT" (default "STRUCTURED")
- `force`: boolean (default false, force regeneration)
```json
// Response 200
{
  "paper_id": "uuid",
  "summary_type": "STRUCTURED",
  "summary": "This paper proposes...",
  "sections": { "introduction": "...", "methods": "...", "results": "..." },
  "key_points": ["Point 1", "Point 2"],
  "word_count": 350,
  "generated_at": "2026-01-01T00:00:00Z",
  "model_used": "facebook/bart-large-cnn",
  "cached": false,
  "processing_time": 5.2
}
```

#### `POST /api/v1/research/insights/{paper_id}` — Extract Insights
Auth required.
```json
// Response 200 — dict with insights
{
  "paper_id": "uuid",
  "insights": {
    "key_findings": [...],
    "methodology": "...",
    "limitations": [...],
    "future_work": [...]
  }
}
```

#### `POST /api/v1/research/cluster` — Run Topic Clustering
Auth required.
```json
// Request
{
  "algorithm": "kmeans",     // optional: "kmeans" or "hdbscan", default "kmeans"
  "n_clusters": 5,           // optional, 2-50, default 5
  "min_cluster_size": 3      // optional, min 2, default 3
}
// Response 200
{
  "cluster_id": "uuid",
  "algorithm": "kmeans",
  "clusters": [
    {
      "id": 0,
      "label": "Transformer Architectures",
      "paper_count": 8,
      "keywords": ["attention", "transformer", "self-attention"],
      "paper_ids": ["uuid1", "uuid2"]
    }
  ],
  "total_papers": 25,
  "created_at": "2026-01-01T00:00:00Z"
}
```

#### `GET /api/v1/research/clusters` — List All Clusters
Auth required.
```json
// Response 200
[
  {
    "id": "uuid",
    "name": "Topic Cluster #1",
    "algorithm": "kmeans",
    "cluster_count": 5,
    "total_papers": 25,
    "created_at": "2026-01-01T00:00:00Z"
  }
]
```

---

### Notes Endpoints

#### `POST /api/v1/notes` — Create Note
Auth required.
```json
// Request
{
  "paper_id": "uuid",                     // optional
  "title": "Key Findings",                // optional, max 200, default "Untitled Note"
  "content": "The paper shows that...",    // required, min 1 char
  "note_type": "MANUAL",                  // optional: MANUAL|AI_GENERATED|HIGHLIGHT|ANNOTATION
  "tags": ["important", "methodology"]     // optional
}
// Response 201
{
  "id": "uuid",
  "paper_id": "uuid",
  "title": "Key Findings",
  "content": "The paper shows that...",
  "note_type": "MANUAL",
  "tags": ["important", "methodology"],
  "is_pinned": false,
  "paper_title": "Attention Is All You Need",
  "created_at": "2026-01-01T00:00:00Z",
  "updated_at": "2026-01-01T00:00:00Z"
}
```

#### `GET /api/v1/notes` — List Notes
Auth required. Query params:
- `paper_id` (optional): filter by paper
- `tag` (optional): filter by tag
- `pinned` (optional, bool): only pinned
- `page` (int, default 1)
- `page_size` (int, default 20, max 100)
```json
// Response 200
{ "notes": [NoteResponse], "total": 42, "page": 1 }
```

#### `GET /api/v1/notes/{note_id}` — Get Note
Auth required. Response: NoteResponse.

#### `PUT /api/v1/notes/{note_id}` — Update Note
Auth required. All fields optional.
```json
// Request
{
  "title": "Updated Title",
  "content": "Updated content",
  "tags": ["updated"],
  "is_pinned": true
}
```

#### `DELETE /api/v1/notes/{note_id}` — Delete Note
Auth required. Response: 204.

#### `POST /api/v1/notes/generate/{paper_id}` — AI-Generate Note
Auth required.
```json
// Request
{
  "paper_id": "uuid",                       // required
  "note_type": "AI_GENERATED"               // optional
}
// Response 200 — NoteResponse (AI-generated content)
```

---

### Collection Endpoints

#### `POST /api/v1/collections` — Create Collection
Auth required.
```json
// Request
{
  "name": "Transformer Papers",          // required, 1-100 chars
  "description": "Key papers on...",     // optional
  "is_public": false                     // optional, default false
}
// Response 201
{
  "id": "uuid",
  "name": "Transformer Papers",
  "description": "Key papers on...",
  "is_public": false,
  "paper_count": 0,
  "created_at": "2026-01-01T00:00:00Z"
}
```

#### `GET /api/v1/collections` — List Collections
Auth required. Response: list of CollectionResponse.

#### `PUT /api/v1/collections/{collection_id}` — Update Collection
Auth required. Fields optional: `name`, `description`, `is_public`.

#### `DELETE /api/v1/collections/{collection_id}` — Delete Collection
Auth required. Response: 204.

#### `POST /api/v1/collections/{collection_id}/papers/{paper_id}` — Add Paper to Collection
Auth required. Response: 201.

#### `DELETE /api/v1/collections/{collection_id}/papers/{paper_id}` — Remove Paper
Auth required. Response: 204.

#### `POST /api/v1/reading-list` — Add to Reading List
Auth required.
```json
// Request
{
  "paper_id": "uuid",                // required
  "priority": "MEDIUM",             // optional: LOW|MEDIUM|HIGH|URGENT, default MEDIUM
  "notes": "Need to read this",     // optional
  "due_date": "2026-06-01"          // optional
}
// Response 201
{
  "id": "uuid",
  "paper_id": "uuid",
  "paper_title": "Attention Is All You Need",
  "priority": "MEDIUM",
  "status": "UNREAD",
  "notes": "Need to read this",
  "due_date": "2026-06-01",
  "added_at": "2026-01-01T00:00:00Z"
}
```

#### `GET /api/v1/reading-list?status=UNREAD&priority=HIGH` — Get Reading List
Auth required. Query params: `status` (UNREAD|READING|COMPLETED|SKIPPED), `priority` (LOW|MEDIUM|HIGH|URGENT).

#### `PUT /api/v1/reading-list/{item_id}` — Update Reading List Item
Auth required. Optional: `status`, `priority`, `notes`.

#### `POST /api/v1/annotations` — Create Annotation
Auth required.
```json
// Request
{
  "paper_id": "uuid",               // required
  "page_number": 5,                 // optional
  "content": "Important finding",   // required
  "highlight_text": "We found...",  // optional
  "color": "#FFFF00",              // optional, default yellow
  "tags": ["key-finding"]          // optional
}
// Response 201
{
  "id": "uuid",
  "paper_id": "uuid",
  "page_number": 5,
  "content": "Important finding",
  "highlight_text": "We found...",
  "color": "#FFFF00",
  "created_at": "2026-01-01T00:00:00Z",
  "updated_at": "2026-01-01T00:00:00Z"
}
```

#### `GET /api/v1/annotations/{paper_id}` — Get Paper Annotations
Auth required.

#### `DELETE /api/v1/annotations/{annotation_id}` — Delete Annotation
Auth required. Response: 204.

---

### Advanced Endpoints

#### `POST /api/v1/advanced/compare` — Compare Papers
Auth required.
```json
// Request
{
  "paper_ids": ["uuid1", "uuid2"]   // required, 2-10 paper IDs
}
// Response 200
{
  "papers": [{ "id": "uuid", "title": "..." }],
  "similarities": [{ "paper_a": "uuid", "paper_b": "uuid", "similarity": 0.75 }],
  "common_themes": ["attention", "transformers"],
  "unique_contributions": { "uuid1": ["contribution1"], "uuid2": ["contribution2"] },
  "comparison_summary": "Both papers address...",
  "generated_at": "2026-01-01T00:00:00Z"
}
```

#### `POST /api/v1/advanced/literature-review` — Auto Literature Review
Auth required.
```json
// Request
{
  "paper_ids": ["uuid1", "uuid2", "uuid3"],  // required, 2-20 paper IDs
  "topic": "Transformer architectures"        // optional
}
// Response 200
{
  "topic": "Transformer architectures",
  "introduction": "This review covers...",
  "themes": [
    {
      "name": "Self-Attention Mechanisms",
      "description": "...",
      "papers": ["uuid1", "uuid2"]
    }
  ],
  "paper_summaries": [{ "paper_id": "uuid", "title": "...", "summary": "..." }],
  "conclusion": "In summary...",
  "generated_at": "2026-01-01T00:00:00Z"
}
```

#### `POST /api/v1/advanced/timeline` — Research Timeline
Auth required. Body: `{ "paper_ids": ["uuid1", ...] }`
```json
// Response 200
{
  "timeline": [
    { "year": 2017, "papers": [{ "id": "uuid", "title": "...", "authors": [...] }] },
    { "year": 2018, "papers": [...] }
  ],
  "total_span": "2017-2024"
}
```

#### `GET /api/v1/advanced/graph?limit=50` — Citation/Research Graph
Auth required. Query: `limit` (5-200, default 50).
```json
// Response 200
{
  "nodes": [{ "id": "uuid", "title": "...", "type": "paper" }],
  "edges": [{ "source": "uuid1", "target": "uuid2", "weight": 0.8 }],
  "metadata": { "total_nodes": 25, "total_edges": 40 }
}
```

#### `GET /api/v1/advanced/recommendations?limit=10` — Personalized Recommendations
Auth required. Query: `limit` (1-50, default 10).
```json
// Response 200
{
  "recommendations": [
    {
      "paper_id": "uuid",
      "title": "Recommended Paper",
      "score": 0.85,
      "reason": "Based on your interest in attention mechanisms",
      "authors": [...]
    }
  ]
}
```

#### `GET /api/v1/advanced/dashboard` — Research Dashboard
Auth required.
```json
// Response 200
{
  "papers": { "total": 42, "processed": 40, "processing": 1, "failed": 1 },
  "chat": { "total_sessions": 15, "total_messages": 120 },
  "notes": { "total": 35, "ai_generated": 10, "manual": 25 },
  "reading_list": { "total": 20, "completed": 8, "completion_rate": 0.4 },
  "recent_activity": [
    { "action": "uploaded_paper", "resource": "Attention Is All You Need", "timestamp": "..." }
  ]
}
```

---

## Pages & Routes

### Public Routes (no auth)
| Route | Page |
|-------|------|
| `/login` | Login page |
| `/register` | Registration page |

### Protected Routes (require auth)
| Route | Page |
|-------|------|
| `/` or `/dashboard` | Dashboard — overview stats, recent activity, quick actions |
| `/papers` | Papers Library — grid/list of all papers with search, filter, sort |
| `/papers/:id` | Paper Detail — full paper info, summaries, insights, actions |
| `/chat` | Chat — RAG Q&A interface, session list sidebar |
| `/chat/:sessionId` | Chat Session — continue existing conversation |
| `/search` | Semantic Search — search across all papers |
| `/notes` | Notes — list/grid of all notes, filter by paper/tag |
| `/collections` | Collections — manage paper collections |
| `/collections/:id` | Collection Detail — papers in this collection |
| `/reading-list` | Reading List — prioritized reading queue |
| `/research` | Research Tools — summarization, clustering, compare |
| `/advanced/compare` | Paper Comparison — side-by-side analysis |
| `/advanced/literature-review` | Auto Literature Review generator |
| `/advanced/graph` | Research Graph — interactive visualization |
| `/settings` | User Settings — profile, password, preferences |

---

## Page Designs

### 1. Login Page (`/login`)
- Centered card with app logo and name "AI Research Assistant"
- Email and password fields
- "Sign In" button (primary)
- Link to register page: "Don't have an account? Sign up"
- Show validation errors inline
- Redirect to `/dashboard` on success
- Store tokens in localStorage

### 2. Register Page (`/register`)
- Centered card, same style as login
- Fields: Full Name, Email, Password (with strength indicator), Institution (optional), Research Interests (tag input, optional)
- Password requirements shown below field
- "Create Account" button
- Link to login: "Already have an account? Sign in"
- On success, redirect to login with success message

### 3. Dashboard (`/dashboard`)
- **Top bar:** Greeting "Welcome back, {name}", date
- **Stats cards row:** Total Papers (with icon), Chat Sessions, Notes Created, Reading Progress (circular progress)
- **Quick Actions:** Upload Paper button, New Chat button, Create Note button, Search Papers button
- **Recent Activity feed:** Timeline of recent actions
- **Papers by Status:** Small donut/pie chart (Completed, Processing, Failed)
- **Reading List Progress:** Progress bar showing completion rate

### 4. Papers Library (`/papers`)
- **Top bar:** "My Papers" title, Upload button (primary), toggle grid/list view
- **Filters bar:** Search input, Status dropdown (All/Processing/Completed/Failed), sort by (Date/Title/Year)
- **Paper cards (grid view):** Title, authors (truncated), abstract preview (2 lines), status badge (color-coded), tags, upload date, page count. Click → go to paper detail
- **Paper cards (list view):** Compact table-like rows
- **Empty state:** Illustration + "Upload your first paper" CTA
- **Pagination:** Page controls at bottom
- **Upload modal:** Drag-and-drop zone (react-dropzone), accept only .pdf, show file name after selection, upload progress bar

### 5. Paper Detail (`/papers/:id`)
- **Header section:** Title (large), Authors, Journal + Year, DOI link, Status badge, Tags (editable), Action buttons (Chat with Paper, Summarize, Get Citations, Find Related, Delete)
- **Tab navigation:**
  - **Overview:** Abstract, metadata table (page count, language, uploaded date, file hash)
  - **Summary:** Generated summary with type selector (Structured/Brief/Detailed/Abstract). Show sections if structured. "Generate" button, loading state with skeleton
  - **Insights:** Key findings, methodology, limitations, future work — displayed as cards
  - **Citations:** All 6 formats in tabs, copy-to-clipboard button for each
  - **Related Papers:** Cards showing related papers with similarity scores, click to navigate
  - **Notes:** Notes for this paper, create new note inline
  - **Annotations:** List of annotations with page numbers, colors, content

### 6. Chat Page (`/chat`)
- **Left sidebar (collapsible):**
  - "New Chat" button at top
  - List of past sessions: title, date, message count, paper name
  - Click session → load it
  - Delete session (trash icon with confirmation)
- **Main chat area:**
  - If no session selected: landing page with suggested questions and paper selector
  - If session active:
    - Messages displayed in chat bubble style
    - User messages: right-aligned, blue/indigo
    - AI messages: left-aligned, gray, rendered as Markdown
    - Sources section below AI messages: collapsible list of source chunks with paper title, similarity score, content preview
    - Confidence badge on AI messages (high/medium/low with colors)
  - **Input area at bottom:**
    - Text input (auto-resize textarea)
    - Paper selector dropdown (optional — to scope questions)
    - Send button
    - Loading indicator while waiting for response
- **Multi-paper chat:** Option to select multiple papers for cross-paper questions

### 7. Semantic Search (`/search`)
- **Large search bar** at top (centered, prominent)
- **Filters:** Paper selector (optional), Result count slider (1-50), Similarity threshold slider
- **Results:** Cards showing:
  - Paper title + link
  - Matching chunk content (highlighted)
  - Similarity score (progress bar or badge)
  - Chunk index
- **Empty state:** Search illustration + "Search across your research papers"

### 8. Notes Page (`/notes`)
- **Top bar:** "My Notes" title, "Create Note" button
- **Filters:** Paper dropdown, Tag filter, Pinned toggle, search
- **Notes grid:** Cards with:
  - Title (bold)
  - Content preview (3 lines)
  - Note type badge (Manual/AI Generated/Highlight/Annotation)
  - Tags
  - Pin icon (toggle)
  - Paper link
  - Date
  - Edit/Delete actions
- **Create/Edit Note modal:**
  - Title input
  - Rich text content area
  - Paper selector dropdown
  - Note type selector
  - Tags input (chip/tag style)
- **AI Note Generation:** Button on paper cards, generates note automatically

### 9. Collections (`/collections`)
- **Top bar:** "Collections" title, "New Collection" button
- **Collection cards:** Name, description, paper count, public/private badge, date
- **Collection detail (`/collections/:id`):**
  - Collection name, description (editable)
  - Grid of papers in this collection
  - "Add Paper" button → modal with paper search/select
  - Remove paper button on each card

### 10. Reading List (`/reading-list`)
- **Top bar:** "Reading List" title, progress summary ("8 of 20 completed")
- **Filters:** Status tabs (All/Unread/Reading/Completed/Skipped), Priority filter
- **List items:** Card for each item:
  - Paper title + link
  - Priority badge (color-coded: Urgent=red, High=orange, Medium=blue, Low=gray)
  - Status dropdown (inline change)
  - Due date
  - Notes (expandable)
  - Remove button
- **Add to reading list:** Available from paper detail page

### 11. Research Tools (`/research`)
- **Tab/card layout with 3 sections:**
  - **Summarization:** Select paper → choose summary type → generate → display result
  - **Topic Clustering:** Choose algorithm (K-Means/HDBSCAN) → set params → run → show cluster results with paper groupings
  - **Paper Comparison:** Multi-select papers (2-10) → compare → show side-by-side similarities, unique contributions, common themes

### 12. Advanced: Literature Review (`/advanced/literature-review`)
- **Step 1:** Select papers (multi-select with search)
- **Step 2:** Optional topic input
- **Step 3:** Generate button
- **Result:** Rendered as a formatted document with:
  - Introduction
  - Themed sections with paper references
  - Individual paper summaries
  - Conclusion

### 13. Advanced: Research Graph (`/advanced/graph`)
- **Interactive network visualization** (use a library like react-force-graph or vis-network)
- Nodes = papers, Edges = similarity connections
- Node size based on connections
- Click node → show paper info popup
- Zoom, pan, drag nodes
- Limit slider (5-200 nodes)

### 14. Settings (`/settings`)
- **Profile section:** Edit name, institution, bio, research interests
- **Security section:** Change password form
- **Preferences section:** Theme toggle (dark/light)

---

## Global Components

### Layout
- **App Shell:** Sidebar navigation (left) + top bar + main content area
- **Sidebar:** App logo, navigation links with icons:
  - Dashboard (LayoutDashboard icon)
  - Papers (FileText)
  - Chat (MessageSquare)
  - Search (Search)
  - Notes (StickyNote)
  - Collections (FolderOpen)
  - Reading List (BookOpen)
  - Research (FlaskConical)
  - Advanced → submenu: Compare, Literature Review, Graph (Sparkles)
  - Settings (Settings) — at bottom
  - Logout (LogOut) — at bottom
- **Sidebar:** Collapsible on mobile (hamburger menu)
- **Top bar:** Page title, user avatar dropdown (Profile, Settings, Logout)

### Auth State Management
- Store `access_token` and `refresh_token` in localStorage
- Create an Axios interceptor that:
  - Adds `Authorization: Bearer <token>` to every request
  - On 401 response, tries to refresh the token using the refresh endpoint
  - If refresh fails, redirects to `/login`
- Protected route wrapper component that checks for token existence
- On app load, validate token by calling `GET /api/v1/auth/profile`

### Error Handling
- Global error boundary
- API error toast notifications (show error message from response)
- Form validation errors shown inline
- 404 page for unknown routes
- Loading skeletons for all data-fetching states
- Empty states with illustrations for empty lists
- Retry buttons on failed requests

### Toast Notifications
Use Sonner for:
- Success: "Paper uploaded successfully", "Note created", etc.
- Error: API error messages
- Info: "Processing paper...", "Generating summary..."

---

## API Client Setup

Create an API client module with:
```typescript
// Base Axios instance
const api = axios.create({
  baseURL: "http://localhost:8000/api/v1",
  headers: { "Content-Type": "application/json" }
});

// Request interceptor — attach JWT
api.interceptors.request.use(config => {
  const token = localStorage.getItem("access_token");
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

// Response interceptor — handle 401, refresh token
api.interceptors.response.use(
  response => response,
  async error => {
    if (error.response?.status === 401) {
      // Try refresh, if fails redirect to /login
    }
    return Promise.reject(error);
  }
);
```

Use **TanStack Query** for all data fetching with proper cache keys:
- `["papers", page, filters]`
- `["paper", paperId]`
- `["chat-sessions"]`
- `["chat-history", sessionId]`
- `["notes", filters]`
- `["collections"]`
- `["reading-list", filters]`
- `["dashboard"]`

Use mutations with `onSuccess` invalidation for all create/update/delete operations.

---

## Key UX Requirements

1. **Instant feedback:** Loading spinners on buttons while API calls are in progress, disable buttons to prevent double-clicks
2. **Optimistic updates:** For toggling pin on notes, changing reading list status
3. **Confirmation dialogs:** For all delete actions (papers, notes, sessions, collections)
4. **Keyboard shortcuts:** Enter to send chat messages, Ctrl+K for global search
5. **Responsive:** Works on tablet and mobile — sidebar collapses to hamburger
6. **Accessibility:** Proper ARIA labels, focus management, semantic HTML
7. **Copy to clipboard:** For citations, with "Copied!" feedback
8. **File upload:** Drag-and-drop zone with visual feedback, file type validation, size limit warning
9. **Markdown rendering:** AI chat responses and summaries rendered as Markdown with code blocks, lists, headings
10. **Debounced search:** Search inputs debounce by 300ms before firing API calls

---

## Environment Variables

```env
VITE_API_BASE_URL=http://localhost:8000/api/v1
```

This should be the only env variable needed. All API calls go through this base URL.

---

## Summary

This is a complete AI-powered research assistant with:
- 51 API endpoints across 8 route groups
- Full CRUD for papers, notes, collections, reading lists, annotations
- AI features: RAG chat, summarization, insight extraction, clustering, paper comparison, literature reviews
- Real-time search with semantic similarity
- Interactive research graph visualization
- Comprehensive dashboard with stats and activity

Build every page, every component, every API integration. The backend is fully functional at `http://localhost:8000`. Make sure CORS is handled (backend allows `http://localhost:3000`).
