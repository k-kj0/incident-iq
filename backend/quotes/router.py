import structlog
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core import get_session
from ..gtm.router import auth
from .compare import compare_quotes
from .models import QuoteDocument
from .service import analyze_pages, pages_from_pdf
from .ui import PAGE

log = structlog.get_logger()
MAX_PDF_BYTES = 10 * 1024 * 1024


class QuoteIn(BaseModel):
    filename: str = Field(min_length=1, max_length=256)
    pages: list[str] = Field(min_length=1, max_length=200)
    extractor: str = Field("rules", pattern="^(rules|llm)$")


class CompareIn(BaseModel):
    quote_ids: list[int] = Field(min_length=2, max_length=5)


def _store(db: Session, tenant: str, filename: str, pages: list[str], extractor: str) -> QuoteDocument:
    try:
        result = analyze_pages(pages, extractor)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    carrier = (result["extraction"].get("carrier") or {}).get("value")
    doc = QuoteDocument(tenant_id=tenant, filename=filename, carrier=carrier, extractor=extractor,
                        pages=pages, extraction=result["extraction"], verification=result["verification"],
                        rejected=result["rejected"], failed_count=result["failed_count"])
    db.add(doc)
    db.commit()
    log.info("quote_ingested", tenant=tenant, quote_id=doc.id, extractor=extractor,
             coverages=len(result["extraction"]["coverages"]), failed=doc.failed_count)
    return doc


def _summary(d: QuoteDocument) -> dict:
    return {"id": d.id, "filename": d.filename, "carrier": d.carrier, "extractor": d.extractor,
            "coverages": len(d.extraction.get("coverages", [])), "unverified_claims": d.failed_count,
            "rejected_claims": len(d.rejected or []), "created_at": d.created_at}


def _get(db: Session, tenant: str, quote_id: int) -> QuoteDocument:
    d = db.get(QuoteDocument, quote_id)
    if d is None or d.tenant_id != tenant:
        raise HTTPException(status_code=404, detail="quote not found")
    return d


def build_quotes_router() -> APIRouter:
    r = APIRouter(prefix="/api/v3/quotes", tags=["quotes"])

    @r.get("/ui", response_class=HTMLResponse)
    def ui():
        return PAGE

    @r.post("")
    def create(req: QuoteIn, tenant: str = Depends(auth), db: Session = Depends(get_session)):
        return _summary(_store(db, tenant, req.filename, req.pages, req.extractor))

    @r.post("/upload")
    async def upload(file: UploadFile = File(...), tenant: str = Depends(auth),
                     db: Session = Depends(get_session)):
        data = await file.read()
        if len(data) > MAX_PDF_BYTES:
            raise HTTPException(status_code=413, detail="PDF larger than 10 MB")
        try:
            pages = pages_from_pdf(data)
        except ImportError:
            raise HTTPException(status_code=501, detail="pdfplumber is not installed")
        except Exception:
            raise HTTPException(status_code=422, detail="could not read this file as a PDF")
        if not any(p.strip() for p in pages):
            raise HTTPException(status_code=422, detail="no extractable text (scanned PDF?)")
        return _summary(_store(db, tenant, file.filename or "quote.pdf", pages, "rules"))

    @r.get("")
    def list_quotes(tenant: str = Depends(auth), db: Session = Depends(get_session)):
        rows = db.scalars(select(QuoteDocument).where(QuoteDocument.tenant_id == tenant)
                          .order_by(QuoteDocument.id.desc()).limit(100)).all()
        return {"items": [_summary(d) for d in rows]}

    @r.get("/{quote_id}")
    def detail(quote_id: int, tenant: str = Depends(auth), db: Session = Depends(get_session)):
        d = _get(db, tenant, quote_id)
        return {**_summary(d), "pages": d.pages, "extraction": d.extraction,
                "verification": d.verification, "rejected": d.rejected}

    @r.post("/compare")
    def compare(req: CompareIn, tenant: str = Depends(auth), db: Session = Depends(get_session)):
        if len(set(req.quote_ids)) != len(req.quote_ids):
            raise HTTPException(status_code=422, detail="quote_ids must be distinct")
        docs = [_get(db, tenant, i) for i in req.quote_ids]
        return compare_quotes([
            {"id": d.id, "name": d.carrier or d.filename, "extraction": d.extraction,
             "failed_fields": [v["field"] for v in d.verification if not v["ok"]]} for d in docs])

    return r
