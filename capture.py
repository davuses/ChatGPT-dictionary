import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from auth import require_api_auth
from database import (
    CaptureItemRecord,
    PageNoteRecord,
    db_add_capture_item,
    db_clear_promoted_items,
    db_delete_capture_item,
    db_delete_page_note,
    db_get_entries_by_ids,
    db_get_page_note_by_url,
    db_promote_capture_items,
    db_update_capture_item,
    db_upsert_page_note,
)
from utils import (
    get_all_words,
    get_IPA,
    get_thesaurus_senses_plain,
    invalidate_quiz_pool_cache,
    invalidate_words_cache,
    normalize_page_url,
    parse_entry_text,
    validate_entry_fields,
)

logger = logging.getLogger(__name__)

api_router = APIRouter(
    prefix="/api/v1",
    dependencies=[Depends(require_api_auth)],
)


class UpsertPageNoteRequest(BaseModel):
    url: str
    title: str = ""
    notes_md: str = ""


class AddCaptureItemRequest(BaseModel):
    url: str
    title: str = ""
    word: str
    context: str = ""
    definition_text: str = ""
    timestamp_seconds: Optional[int] = Field(default=None, ge=0)


class UpdateCaptureItemRequest(BaseModel):
    word: Optional[str] = None
    context: Optional[str] = None
    definition_text: Optional[str] = None


class PromoteItemsRequest(BaseModel):
    item_ids: list[int] = Field(default_factory=list)


class ClearPromotedRequest(BaseModel):
    note_id: Optional[int] = None


def _canonical_url_or_400(raw_url: str) -> str:
    try:
        return normalize_page_url(raw_url)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


def _serialize_item(
    item: CaptureItemRecord, all_words: dict[str, list[int]]
) -> dict[str, object]:
    return {
        "id": item.id,
        "page_note_id": item.page_note_id,
        "word": item.word,
        "context": item.context,
        "definition_text": item.definition_text,
        "timestamp_seconds": item.timestamp_seconds,
        "promoted_entry_id": item.promoted_entry_id,
        "existing_entry_ids": list(all_words.get(item.word.strip().lower(), [])),
        "created_at": item.created_at,
    }


def _serialize_page_note(
    url: str,
    note: PageNoteRecord | None,
    all_words: dict[str, list[int]],
    fallback_title: str = "",
) -> dict[str, object]:
    if note is None:
        return {
            "id": None,
            "url": url,
            "title": fallback_title.strip(),
            "notes_md": "",
            "created_at": None,
            "updated_at": None,
            "items": [],
        }
    return {
        "id": note.id,
        "url": note.url,
        "title": note.title,
        "notes_md": note.notes_md,
        "created_at": note.created_at,
        "updated_at": note.updated_at,
        "items": [_serialize_item(item, all_words) for item in note.items],
    }


@api_router.get("/page-note", response_class=JSONResponse)
def get_page_note(url: str = Query(...), title: str = Query("")):
    canonical_url = _canonical_url_or_400(url)
    note = db_get_page_note_by_url(canonical_url)
    all_words = get_all_words()
    return JSONResponse(
        _serialize_page_note(canonical_url, note, all_words, fallback_title=title),
        headers={"Cache-Control": "no-store"},
    )


@api_router.put("/page-note", response_class=JSONResponse)
def put_page_note(payload: UpsertPageNoteRequest):
    canonical_url = _canonical_url_or_400(payload.url)
    note = db_upsert_page_note(canonical_url, payload.title, payload.notes_md)
    all_words = get_all_words()
    return JSONResponse(
        _serialize_page_note(
            canonical_url, note, all_words, fallback_title=payload.title
        ),
        headers={"Cache-Control": "no-store"},
    )


@api_router.delete("/page-note/{note_id}", response_class=JSONResponse)
def delete_page_note(note_id: int):
    if not db_delete_page_note(note_id):
        raise HTTPException(status_code=404, detail="Page note not found")
    return JSONResponse({"message": "deleted"}, headers={"Cache-Control": "no-store"})


@api_router.post("/page-note/clear-promoted", response_class=JSONResponse)
def clear_promoted_items(payload: Optional[ClearPromotedRequest] = None):
    note_id = payload.note_id if payload is not None else None
    deleted = db_clear_promoted_items(note_id)
    return JSONResponse({"deleted": deleted}, headers={"Cache-Control": "no-store"})


@api_router.post("/page-note/items", response_class=JSONResponse, status_code=201)
def add_capture_item(payload: AddCaptureItemRequest):
    canonical_url = _canonical_url_or_400(payload.url)
    clean_word = " ".join(payload.word.split())
    if not clean_word:
        raise HTTPException(status_code=400, detail="Word cannot be empty.")
    note, item = db_add_capture_item(
        normalized_url=canonical_url,
        title=payload.title,
        word=clean_word,
        context=" ".join(payload.context.split()),
        definition_text=payload.definition_text,
        timestamp_seconds=payload.timestamp_seconds,
    )
    all_words = get_all_words()
    return JSONResponse(
        {
            "url": note.url,
            "item": _serialize_item(item, all_words),
        },
        status_code=201,
        headers={"Cache-Control": "no-store"},
    )


@api_router.patch("/page-note/items/{item_id}", response_class=JSONResponse)
def patch_capture_item(item_id: int, payload: UpdateCaptureItemRequest):
    word = None
    if payload.word is not None:
        word = " ".join(payload.word.split())
        if not word:
            raise HTTPException(status_code=400, detail="Word cannot be empty.")
    context = (
        " ".join(payload.context.split()) if payload.context is not None else None
    )
    updated = db_update_capture_item(
        item_id,
        word=word,
        context=context,
        definition_text=payload.definition_text,
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Capture item not found")
    all_words = get_all_words()
    return JSONResponse(
        {"item": _serialize_item(updated, all_words)},
        headers={"Cache-Control": "no-store"},
    )


@api_router.delete("/page-note/items/{item_id}", response_class=JSONResponse)
def delete_capture_item(item_id: int):
    if not db_delete_capture_item(item_id):
        raise HTTPException(status_code=404, detail="Capture item not found")
    return JSONResponse({"message": "deleted"}, headers={"Cache-Control": "no-store"})


@api_router.post("/page-note/promote", response_class=JSONResponse)
def promote_capture_items(payload: PromoteItemsRequest):
    if not payload.item_ids:
        raise HTTPException(status_code=400, detail="No item_ids provided")
    results = db_promote_capture_items(payload.item_ids, validate_entry_fields)
    if any(r.get("status") == "created" for r in results):
        invalidate_words_cache()
        invalidate_quiz_pool_cache()
    return JSONResponse({"results": results}, headers={"Cache-Control": "no-store"})


@api_router.get("/lookup", response_class=JSONResponse)
def lookup_word(word: str = Query(...)):
    clean_word = " ".join(word.split())
    if not clean_word:
        raise HTTPException(status_code=400, detail="Word cannot be empty.")

    all_words = get_all_words()
    existing_ids = list(all_words.get(clean_word.lower(), []))
    existing_entries = []
    for summary in db_get_entries_by_ids(existing_ids):
        ctx, parsed_word = parse_entry_text(summary.text)
        existing_entries.append(
            {
                "id": summary.id,
                "word": parsed_word,
                "context": ctx,
                "visit_count": summary.visit_count,
            }
        )

    ipa = ""
    try:
        ipa = get_IPA(clean_word)
    except Exception as error:
        logger.warning("IPA lookup failed for %r: %s", clean_word, type(error).__name__)

    senses: list[dict[str, object]] = []
    thesaurus_error: str | None = None
    try:
        senses = [dict(sense) for sense in get_thesaurus_senses_plain(clean_word)]
    except Exception as error:
        logger.warning(
            "Thesaurus lookup failed for %r: %s", clean_word, type(error).__name__
        )
        thesaurus_error = "Thesaurus lookup temporarily unavailable"

    return JSONResponse(
        {
            "word": clean_word,
            "ipa": ipa,
            "existing_entries": existing_entries,
            "senses": senses,
            "thesaurus_error": thesaurus_error,
        },
        headers={"Cache-Control": "no-store"},
    )
