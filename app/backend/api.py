"""
GIÁO TRÌNH AI - Backend API
Kết nối với hệ thống RAG hiện có (ChromaDB + Query Expansion + GPT)
KHÔNG xây lại embedding / chunking / ChromaDB.
"""

import os
import re
import json
import tempfile
from pathlib import Path
from typing import Optional, List, Dict, Any
from collections import defaultdict

from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field
from openai import OpenAI
import chromadb
from pypdf import PdfReader

# ==================== CẤU HÌNH ====================
# Đường dẫn tới project RAG hiện có.
# Có thể override bằng biến môi trường RAG_PROJECT_ROOT
RAG_PROJECT_ROOT = Path(
    os.getenv(
        "RAG_PROJECT_ROOT",
        str(Path.home() / "Documents" / "For RAG" / "RAG_GiaoTrinh"),
    )
)
CHROMA_PATH = Path(os.getenv("CHROMA_PATH", str(RAG_PROJECT_ROOT / "chroma_db")))
COLLECTION_NAME = os.getenv("CHROMA_COLLECTION", "giaotrinh_physics")
EMBEDDING_MODEL = "text-embedding-3-small"
CHAT_MODEL = os.getenv("CHAT_MODEL", "gpt-4o-mini")  # hoặc gpt-4o

# Thử import query expansion từ project hiện có
QUERY_EXPANSION_AVAILABLE = False
expand_query_fn = None

try:
    import sys
    scripts_path = str(RAG_PROJECT_ROOT / "scripts")
    if scripts_path not in sys.path:
        sys.path.insert(0, scripts_path)
    # Thử các tên module phổ biến
    for mod_name in ["query_expansion", "rag_query"]:
        try:
            mod = __import__(mod_name)
            if hasattr(mod, "expand_query"):
                expand_query_fn = mod.expand_query
                QUERY_EXPANSION_AVAILABLE = True
                print(f"[INFO] Loaded expand_query from {mod_name}")
                break
            if hasattr(mod, "query_expansion"):
                expand_query_fn = mod.query_expansion
                QUERY_EXPANSION_AVAILABLE = True
                print(f"[INFO] Loaded query_expansion from {mod_name}")
                break
        except Exception:
            continue
except Exception as e:
    print(f"[WARN] Could not load existing query expansion: {e}")

# ==================== OPENAI CLIENT ====================
def get_openai_client() -> OpenAI:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise HTTPException(
            status_code=500,
            detail="OPENAI_API_KEY không được cấu hình trong môi trường.",
        )
    return OpenAI(api_key=api_key)


# ==================== CHROMADB ====================
_chroma_client = None
_collection = None


def get_collection():
    global _chroma_client, _collection
    if _collection is not None:
        return _collection
    if not CHROMA_PATH.exists():
        raise HTTPException(
            status_code=500,
            detail=f"Không tìm thấy ChromaDB tại: {CHROMA_PATH}. "
            "Hãy kiểm tra biến môi trường CHROMA_PATH hoặc RAG_PROJECT_ROOT.",
        )
    try:
        _chroma_client = chromadb.PersistentClient(path=str(CHROMA_PATH))
        _collection = _chroma_client.get_collection(name=COLLECTION_NAME)
        print(f"[INFO] Connected to collection '{COLLECTION_NAME}' "
              f"({_collection.count()} vectors)")
        return _collection
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Lỗi kết nối ChromaDB: {str(e)}",
        )


# ==================== QUERY EXPANSION (fallback nếu không import được) ====================
# Mapping thuật ngữ vật lý phổ biến Việt → Anh (dựa trên mô tả hệ thống)
PHYSICS_TERM_MAP = {
    "chuyển động ném xiên": "projectile motion",
    "ném xiên": "projectile motion",
    "chuyển động ném ngang": "horizontal projectile motion",
    "ném ngang": "horizontal throw",
    "định luật newton": "newton's laws of motion",
    "định luật 2 newton": "newton's second law",
    "định luật ii newton": "newton's second law",
    "định luật 1 newton": "newton's first law",
    "định luật 3 newton": "newton's third law",
    "động lượng": "momentum",
    "xung lượng": "impulse",
    "năng lượng": "energy",
    "động năng": "kinetic energy",
    "thế năng": "potential energy",
    "cơ năng": "mechanical energy",
    "lực ma sát": "friction force",
    "ma sát": "friction",
    "gia tốc": "acceleration",
    "vận tốc": "velocity",
    "quãng đường": "displacement path",
    "chuyển động thẳng đều": "uniform linear motion",
    "chuyển động thẳng biến đổi đều": "uniformly accelerated linear motion",
    "chuyển động tròn": "circular motion",
    "lực hướng tâm": "centripetal force",
    "dao động điều hòa": "simple harmonic motion",
    "sóng": "wave",
    "ánh sáng": "light",
    "điện trường": "electric field",
    "từ trường": "magnetic field",
    "điện từ": "electromagnetic",
    "nhiệt động lực học": "thermodynamics",
    "entropy": "entropy",
    "công": "work",
    "công suất": "power",
}


def fallback_expand_query(query: str) -> str:
    """
    Query Expansion đơn giản: nhận diện thuật ngữ tiếng Việt → thêm thuật ngữ tiếng Anh.
    Không thay thế hoàn toàn, chỉ mở rộng.
    """
    q_lower = query.lower().strip()
    expanded_terms = []
    for vi, en in PHYSICS_TERM_MAP.items():
        if vi in q_lower:
            expanded_terms.append(en)
    if expanded_terms:
        # Giữ nguyên query gốc + thêm thuật ngữ Anh
        return f"{query} {' '.join(expanded_terms)}"
    return query


def expand_user_query(query: str) -> str:
    """Ưu tiên dùng hàm từ project hiện có, fallback nếu không có."""
    if expand_query_fn is not None:
        try:
            result = expand_query_fn(query)
            if isinstance(result, str) and result.strip():
                return result
            if isinstance(result, dict) and "expanded" in result:
                return result["expanded"]
        except Exception as e:
            print(f"[WARN] expand_query_fn failed: {e}, using fallback")
    return fallback_expand_query(query)


# ==================== RETRIEVAL ====================
def embed_query(text: str, client: OpenAI) -> List[float]:
    resp = client.embeddings.create(model=EMBEDDING_MODEL, input=text)
    return resp.data[0].embedding


def retrieve_chunks(
    query: str,
    client: OpenAI,
    n_results: int = 8,
) -> List[Dict[str, Any]]:
    """
    Query Expansion → Embedding → ChromaDB retrieval.
    Trả về list dict: {text, metadata, distance}
    """
    expanded = expand_user_query(query)
    print(f"[RETRIEVE] Original: {query}")
    print(f"[RETRIEVE] Expanded: {expanded}")

    collection = get_collection()
    query_embedding = embed_query(expanded, client)

    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=n_results,
        include=["documents", "metadatas", "distances"],
    )

    chunks = []
    docs = results.get("documents", [[]])[0]
    metas = results.get("metadatas", [[]])[0]
    dists = results.get("distances", [[]])[0]

    for doc, meta, dist in zip(docs, metas, dists):
        chunks.append(
            {
                "text": doc or "",
                "metadata": meta or {},
                "distance": dist,
            }
        )
    return chunks


def aggregate_sources(chunks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Gom các chunk cùng chapter/section/source thành một nguồn dễ đọc.
    Không hiển thị chunk_id cho người dùng.
    """
    # Key: (chapter, section, source)
    groups: Dict[tuple, Dict] = {}

    for ch in chunks:
        m = ch.get("metadata") or {}
        chapter = m.get("chapter") or m.get("chapter_title") or "Unknown"
        section = m.get("section") or ""
        section_title = m.get("section_title") or ""
        source = m.get("source") or "Unknown"
        page = m.get("page")
        local_page = m.get("local_page")

        key = (str(chapter), str(section), str(source))
        if key not in groups:
            groups[key] = {
                "chapter": chapter,
                "chapter_title": m.get("chapter_title") or chapter,
                "section": section,
                "section_title": section_title,
                "source": source,
                "pages": set(),
                "local_pages": set(),
            }
        if page is not None:
            try:
                groups[key]["pages"].add(int(page))
            except (ValueError, TypeError):
                pass
        if local_page is not None:
            try:
                groups[key]["local_pages"].add(int(local_page))
            except (ValueError, TypeError):
                pass

    sources = []
    for g in groups.values():
        pages = sorted(g["pages"])
        page_str = ""
        if pages:
            if len(pages) == 1:
                page_str = str(pages[0])
            else:
                # Gom khoảng liên tục
                ranges = []
                start = pages[0]
                prev = pages[0]
                for p in pages[1:]:
                    if p == prev + 1:
                        prev = p
                    else:
                        if start == prev:
                            ranges.append(str(start))
                        else:
                            ranges.append(f"{start}–{prev}")
                        start = prev = p
                if start == prev:
                    ranges.append(str(start))
                else:
                    ranges.append(f"{start}–{prev}")
                page_str = ", ".join(ranges)

        sources.append(
            {
                "chapter": g["chapter"],
                "chapter_title": g["chapter_title"],
                "section": g["section"],
                "section_title": g["section_title"],
                "source": g["source"],
                "pages": page_str,
                "page_list": pages,
            }
        )

    # Sắp xếp theo chapter rồi section
    sources.sort(key=lambda x: (x["chapter"], x["section"]))
    return sources


# ==================== PDF / TXT EXTRACTION ====================
def extract_text_from_pdf(file_path: str) -> str:
    try:
        reader = PdfReader(file_path)
        texts = []
        for page in reader.pages:
            t = page.extract_text()
            if t:
                texts.append(t)
        return "\n\n".join(texts).strip()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Không đọc được PDF: {str(e)}")


def extract_text_from_txt(file_path: str) -> str:
    try:
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            return f.read().strip()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Không đọc được TXT: {str(e)}")


async def process_upload(file: Optional[UploadFile]) -> Optional[str]:
    if file is None or not file.filename:
        return None
    suffix = Path(file.filename).suffix.lower()
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = tmp.name

    try:
        if suffix == ".pdf":
            text = extract_text_from_pdf(tmp_path)
        elif suffix in (".txt", ".md", ".text"):
            text = extract_text_from_txt(tmp_path)
        else:
            raise HTTPException(
                status_code=400,
                detail=f"Định dạng không hỗ trợ: {suffix}. Chỉ hỗ trợ PDF và TXT.",
            )
        if not text or len(text.strip()) < 5:
            raise HTTPException(status_code=400, detail="File rỗng hoặc không có nội dung text.")
        # Giới hạn độ dài để tránh prompt quá dài
        max_chars = 12000
        if len(text) > max_chars:
            text = text[:max_chars] + "\n\n[... nội dung đã được cắt ngắn ...]"
        return text
    finally:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass


# ==================== PROMPT BUILDING ====================
def build_system_prompt(response_grammar: Optional[str]) -> str:
    base = """Bạn là trợ lý AI chuyên sâu về giáo trình Vật lý đại học.
Bạn CHỈ được trả lời dựa trên các đoạn context được cung cấp từ giáo trình.
Không được bịa nguồn, không được thêm thông tin ngoài giáo trình trừ khi người dùng yêu cầu rõ ràng.

Luôn ưu tiên:
- Chính xác với nội dung giáo trình
- Trích dẫn rõ Chapter, Section, PDF page, Source khi có
- Công thức toán học viết bằng LaTeX (dùng $...$ hoặc $$...$$)
"""
    if response_grammar and response_grammar.strip():
        base += f"""

=== NGỮ PHÁP CỦA CÂU TRẢ LỜI (Response Grammar) ===
Người dùng đã quy định cách tổ chức, diễn đạt và trình bày câu trả lời như sau.
Bạn PHẢI tuân thủ nghiêm ngặt các quy định này:

{response_grammar.strip()}
=== HẾT RESPONSE GRAMMAR ===
"""
    return base


def build_user_prompt(
    user_request: str,
    context_chunks: List[Dict[str, Any]],
    template: Optional[str] = None,
) -> str:
    # Xây context có metadata
    context_parts = []
    for i, ch in enumerate(context_chunks, 1):
        m = ch.get("metadata") or {}
        header = (
            f"[Đoạn {i}] "
            f"Chapter: {m.get('chapter', '?')} | "
            f"Section: {m.get('section', '?')} {m.get('section_title', '')} | "
            f"Page: {m.get('page', '?')} | "
            f"Source: {m.get('source', '?')}"
        )
        context_parts.append(f"{header}\n{ch.get('text', '')}")

    context_block = "\n\n---\n\n".join(context_parts) if context_parts else "(Không tìm thấy đoạn liên quan trong giáo trình)"

    prompt = f"""=== CONTEXT TỪ GIÁO TRÌNH ===
{context_block}
=== HẾT CONTEXT ===

"""
    if template and template.strip():
        prompt += f"""=== MẪU / TÀI LIỆU THAM KHẢO CHO YÊU CẦU ===
{template.strip()}
=== HẾT MẪU ===

"""
    prompt += f"""=== YÊU CẦU CỦA NGƯỜI DÙNG ===
{user_request.strip()}
=== HẾT YÊU CẦU ===

Hãy trả lời yêu cầu dựa trên context giáo trình ở trên, tuân thủ Response Grammar (nếu có).
"""
    return prompt


# ==================== FASTAPI APP ====================
app = FastAPI(
    title="GIÁO TRÌNH AI",
    description="API cho hệ thống hỏi đáp / viết / phân tích dựa trên giáo trình Vật lý",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve frontend
FRONTEND_DIR = Path(__file__).parent.parent / "frontend"
if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")


@app.get("/")
async def root():
    index = FRONTEND_DIR / "index.html"
    if index.exists():
        return FileResponse(str(index))
    return {"message": "GIÁO TRÌNH AI API", "docs": "/docs"}


@app.get("/health")
async def health():
    try:
        col = get_collection()
        count = col.count()
        return {
            "status": "ok",
            "collection": COLLECTION_NAME,
            "vectors": count,
            "chroma_path": str(CHROMA_PATH),
            "query_expansion": "loaded" if QUERY_EXPANSION_AVAILABLE else "fallback",
        }
    except Exception as e:
        return JSONResponse(
            status_code=503,
            content={"status": "error", "detail": str(e)},
        )


class QueryRequest(BaseModel):
    """Dùng khi gọi JSON thuần (không upload file)."""
    request: str = Field(..., description="Câu hỏi hoặc yêu cầu của người dùng")
    template: Optional[str] = Field(None, description="Mẫu / tài liệu tham khảo (text)")
    response_grammar: Optional[str] = Field(None, description="Ngữ pháp của câu trả lời")
    n_results: int = Field(8, ge=3, le=20)


@app.post("/api/query")
async def api_query_json(body: QueryRequest):
    """Endpoint JSON thuần (không upload)."""
    return await _process_query(
        user_request=body.request,
        template_text=body.template,
        grammar_text=body.response_grammar,
        n_results=body.n_results,
    )


@app.post("/api/query-with-files")
async def api_query_with_files(
    request: str = Form(..., description="Câu hỏi hoặc yêu cầu"),
    template_text: Optional[str] = Form(None),
    response_grammar_text: Optional[str] = Form(None),
    template_file: Optional[UploadFile] = File(None),
    grammar_file: Optional[UploadFile] = File(None),
    n_results: int = Form(8),
):
    """
    Endpoint chính: nhận request + optional template (text hoặc file) + optional Response Grammar (text hoặc file).
    """
    # Ưu tiên file nếu có, nếu không dùng text
    template = await process_upload(template_file) if template_file and template_file.filename else None
    if not template and template_text:
        template = template_text.strip() or None

    grammar = await process_upload(grammar_file) if grammar_file and grammar_file.filename else None
    if not grammar and response_grammar_text:
        grammar = response_grammar_text.strip() or None

    return await _process_query(
        user_request=request,
        template_text=template,
        grammar_text=grammar,
        n_results=n_results,
    )


async def _process_query(
    user_request: str,
    template_text: Optional[str],
    grammar_text: Optional[str],
    n_results: int = 8,
) -> Dict[str, Any]:
    if not user_request or not user_request.strip():
        raise HTTPException(status_code=400, detail="Yêu cầu không được để trống.")

    try:
        client = get_openai_client()

        # 1. Retrieval (chỉ dùng phần query, không đưa instruction/grammar vào embedding)
        # Tách query content đơn giản: lấy 1-2 câu đầu hoặc toàn bộ nếu ngắn
        query_for_retrieval = user_request.strip()
        # Nếu request quá dài và có vẻ là instruction, vẫn dùng toàn bộ nhưng expansion sẽ xử lý
        chunks = retrieve_chunks(query_for_retrieval, client, n_results=n_results)

        # 2. Aggregate sources
        sources = aggregate_sources(chunks)

        # 3. Build prompts
        system_prompt = build_system_prompt(grammar_text)
        user_prompt = build_user_prompt(user_request, chunks, template_text)

        # 4. Call GPT
        completion = client.chat.completions.create(
            model=CHAT_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.4,
            max_tokens=4096,
        )
        answer = completion.choices[0].message.content or ""

        return {
            "success": True,
            "answer": answer,
            "sources": sources,
            "meta": {
                "expanded_query": expand_user_query(query_for_retrieval),
                "n_chunks": len(chunks),
                "model": CHAT_MODEL,
            },
        }
    except HTTPException:
        raise
    except Exception as e:
        print(f"[ERROR] {type(e).__name__}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Lỗi xử lý yêu cầu: {str(e)}. Vui lòng thử lại hoặc kiểm tra cấu hình.",
        )


# Cho phép chạy trực tiếp
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "api:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", 8000)),
        reload=True,
    )
