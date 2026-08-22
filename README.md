# GIÁO TRÌNH AI — Web Application

Ứng dụng web hiện đại kết nối với hệ thống RAG giáo trình Vật lý đã hoàn thành.

**Không xây lại** embedding, chunking, ChromaDB hay Query Expansion core.

---

## Kiến trúc

```
USER REQUEST
     │
     ├── Query content  ──► Query Expansion ──► ChromaDB (giaotrinh_physics)
     │
     ├── Template (optional)
     │
     └── Response Grammar  ──► GPT Prompt
              │
              ▼
         Câu trả lời đẹp + Nguồn trích dẫn
```

---

## Cấu trúc thư mục đề xuất

Đặt thư mục `app/` vào trong project RAG hiện có:

```
RAG_GiaoTrinh/
├── scripts/                  # (giữ nguyên)
│   ├── query_expansion.py
│   ├── rag_query.py
│   └── ...
├── chroma_db/                # (giữ nguyên)
├── data/
└── app/                      # ← thư mục mới
    ├── frontend/
    │   ├── index.html
    │   ├── style.css
    │   └── app.js
    └── backend/
        └── api.py
```

Hoặc giữ nguyên cấu trúc trong `giaotrinh_ai_app/` và chỉ cần set biến môi trường.

---

## Yêu cầu

- Python 3.10+
- `OPENAI_API_KEY` đã có trong environment
- ChromaDB đã build sẵn (collection `giaotrinh_physics`)
- Các package trong `requirements.txt`

```bash
pip install -r requirements.txt
```

---

## Cách chạy

### 1. Di chuyển vào thư mục app (hoặc set path)

```bash
# Cách A: nếu bạn copy app/ vào RAG_GiaoTrinh/
cd "$HOME/Documents/For RAG/RAG_GiaoTrinh"

# Cách B: chạy từ thư mục giaotrinh_ai_app và chỉ định root
export RAG_PROJECT_ROOT="$HOME/Documents/For RAG/RAG_GiaoTrinh"
export CHROMA_PATH="$HOME/Documents/For RAG/RAG_GiaoTrinh/chroma_db"
```

### 2. Đảm bảo API key

```bash
export OPENAI_API_KEY="sk-..."   # nếu chưa có trong shell
```

### 3. Chạy backend

```bash
cd app/backend
uvicorn api:app --host 0.0.0.0 --port 8000 --reload
```

Hoặc từ thư mục gốc project:

```bash
uvicorn app.backend.api:app --host 0.0.0.0 --port 8000 --reload
```

(Tùy thuộc cách bạn đặt PYTHONPATH / cấu trúc.)

### 4. Mở trình duyệt

```
http://localhost:8000
```

---

## Biến môi trường quan trọng

| Biến | Mặc định | Mô tả |
|------|----------|--------|
| `OPENAI_API_KEY` | (bắt buộc) | OpenAI API key |
| `RAG_PROJECT_ROOT` | `~/Documents/For RAG/RAG_GiaoTrinh` | Root project RAG |
| `CHROMA_PATH` | `$RAG_PROJECT_ROOT/chroma_db` | Đường dẫn ChromaDB |
| `CHROMA_COLLECTION` | `giaotrinh_physics` | Tên collection |
| `CHAT_MODEL` | `gpt-4o-mini` | Model chat (có thể đổi `gpt-4o`) |
| `PORT` | `8000` | Port server |

---

## API Endpoints

| Method | Path | Mô tả |
|--------|------|--------|
| GET | `/` | Giao diện web |
| GET | `/health` | Kiểm tra ChromaDB + số vectors |
| POST | `/api/query` | JSON body (không upload file) |
| POST | `/api/query-with-files` | multipart/form-data (hỗ trợ upload PDF/TXT) |

### Ví dụ gọi `/api/query` (JSON)

```bash
curl -X POST http://localhost:8000/api/query \
  -H "Content-Type: application/json" \
  -d '{
    "request": "Chuyển động ném xiên được mô tả như thế nào?",
    "response_grammar": "Trả lời bằng tiếng Việt.\nGiải thích cho sinh viên năm nhất.\nSử dụng phong cách hỏi đáp Socratic.\nDùng LaTeX cho công thức.\nCuối cùng phải chỉ rõ Chapter, Section và PDF page."
  }'
```

---

## Query Expansion

Backend **ưu tiên** load hàm `expand_query` (hoặc `query_expansion`) từ:

- `scripts/query_expansion.py`
- `scripts/rag_query.py`

Nếu không tìm thấy, dùng **fallback mapping** thuật ngữ Vật lý Việt → Anh (đã có sẵn trong `api.py`).

**Không thay đổi logic RAG core.** Chỉ wrap lại để gọi từ API.

---

## Phân biệt Query vs Instruction

- **Query content** (phần tìm kiếm) → đi qua Query Expansion → Embedding → ChromaDB.
- **Template** + **Response Grammar** → chỉ đưa vào system/user prompt của GPT, **không** đưa vào embedding query.

---

## Test bắt buộc

### Test 1
- **Request:** `Chuyển động ném xiên được mô tả như thế nào?`
- **Response Grammar:**
  ```
  Trả lời bằng tiếng Việt.
  Giải thích cho sinh viên năm nhất.
  Sử dụng phong cách hỏi đáp Socratic.
  Dùng LaTeX cho công thức.
  Cuối cùng phải chỉ rõ Chapter, Section và PDF page.
  ```
- Kỳ vọng nguồn: Chapter 04, Section 4.3 — Projectile Motion, pages ~112–115

### Test 2
- **Request:** `Viết lại phần Chuyển động ném xiên theo phong cách hỏi đáp Socratic.`
- **Response Grammar:** chuỗi câu hỏi–trả lời, LaTeX, ghi nguồn.

### Test 3
- **Request:** `Viết lại Chương 1 bằng LaTeX theo mẫu tôi upload.`
- Upload file mẫu + Response Grammar tương ứng.

---

## Ghi chú kỹ thuật

- PDF upload được extract text bằng `pypdf` (chỉ dùng tạm thời cho request hiện tại, **không** ingest vào ChromaDB).
- Nguồn được **gom** theo (chapter, section, source) và hiển thị dạng dễ đọc, không lộ `chunk_id`.
- Markdown + MathJax được render phía client.
- API key **chỉ** nằm ở backend (env), không bao giờ đưa ra frontend.

---

## Troubleshooting

1. **`Không tìm thấy ChromaDB`**  
   → Kiểm tra `CHROMA_PATH` và `chroma_db` tồn tại.

2. **`OPENAI_API_KEY không được cấu hình`**  
   → `export OPENAI_API_KEY=...`

3. **Query Expansion không load**  
   → Backend vẫn chạy với fallback. Xem log `[INFO] Loaded expand_query from ...` hoặc `[WARN]`.

4. **CORS / Static files**  
   → Chạy đúng bằng `uvicorn` từ thư mục chứa `api.py` hoặc set PYTHONPATH.

Chúc bạn dạy và học vui vẻ với GIÁO TRÌNH AI!
