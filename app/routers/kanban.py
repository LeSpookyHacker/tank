"""Kanban board generator — page + API routes."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from app.config import TEMPLATES_DIR
from app.rate_limiter import limiter
from app.storage import kanban_store

router = APIRouter(prefix="/api/kanban")
page = APIRouter()
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


# ── Page routes ───────────────────────────────────────────────────────────────

@page.get("/kanban", response_class=HTMLResponse)
async def kanban_landing(request: Request):
    return templates.TemplateResponse(
        request=request, name="followups.html",
        context={"boards": kanban_store.list_boards()},
    )


@page.get("/kanban/boards/{board_id}", response_class=HTMLResponse)
async def kanban_board_page(request: Request, board_id: str):
    board = kanban_store.get_board(board_id)
    if not board:
        return RedirectResponse("/kanban")
    cards = kanban_store.list_cards_for_board(board_id)
    return templates.TemplateResponse(
        request=request, name="kanban_board.html",
        context={"board": board, "cards": cards},
    )


# ── Board API ─────────────────────────────────────────────────────────────────

class CreateBoard(BaseModel):
    title: str = Field(max_length=200)
    description: str | None = Field(None, max_length=1000)


class UpdateBoard(BaseModel):
    title: str = Field(max_length=200)
    description: str | None = Field(None, max_length=1000)


@router.get("/boards")
async def list_boards() -> dict:
    return {"boards": kanban_store.list_boards()}


@router.post("/boards")
@limiter.limit("60/minute")
async def create_board(request: Request, body: CreateBoard) -> dict:
    bid = kanban_store.create_board(title=body.title, description=body.description)
    return {"id": bid}


@router.put("/boards/{board_id}")
async def update_board(board_id: str, body: UpdateBoard) -> dict:
    if not kanban_store.get_board(board_id):
        raise HTTPException(status_code=404, detail="Board not found")
    kanban_store.update_board(board_id, title=body.title, description=body.description)
    return {"ok": True}


@router.delete("/boards/{board_id}")
async def delete_board(board_id: str) -> dict:
    if not kanban_store.get_board(board_id):
        raise HTTPException(status_code=404, detail="Board not found")
    kanban_store.delete_board(board_id)
    return {"ok": True}


@router.get("/boards/{board_id}/cards")
async def get_board_cards(board_id: str) -> dict:
    if not kanban_store.get_board(board_id):
        raise HTTPException(status_code=404, detail="Board not found")
    return {"cards": kanban_store.list_cards_for_board(board_id)}


# ── Reorder ───────────────────────────────────────────────────────────────────

class ReorderBody(BaseModel):
    columns: dict[str, list[str]]


@router.post("/boards/{board_id}/reorder")
async def reorder_board(board_id: str, body: ReorderBody) -> dict:
    if not kanban_store.get_board(board_id):
        raise HTTPException(status_code=404, detail="Board not found")
    kanban_store.reorder_board(board_id, body.columns)
    return {"ok": True}


# ── Card API ──────────────────────────────────────────────────────────────────

class CreateCard(BaseModel):
    title: str = Field(max_length=200)
    body: str | None = Field(None, max_length=2000)
    column: str = "todo"


class UpdateCard(BaseModel):
    title: str = Field(max_length=200)
    body: str | None = Field(None, max_length=2000)


@router.post("/boards/{board_id}/cards")
@limiter.limit("120/minute")
async def create_card(request: Request, board_id: str, body: CreateCard) -> dict:
    if not kanban_store.get_board(board_id):
        raise HTTPException(status_code=404, detail="Board not found")
    cid = kanban_store.create_card(
        board_id=board_id, title=body.title,
        body=body.body, column=body.column,
    )
    return {"id": cid}


@router.put("/cards/{card_id}")
async def update_card(card_id: str, body: UpdateCard) -> dict:
    if not kanban_store.get_card(card_id):
        raise HTTPException(status_code=404, detail="Card not found")
    kanban_store.update_card(card_id, title=body.title, body=body.body)
    return {"ok": True}


@router.delete("/cards/{card_id}")
async def delete_card(card_id: str) -> dict:
    if not kanban_store.get_card(card_id):
        raise HTTPException(status_code=404, detail="Card not found")
    kanban_store.delete_card(card_id)
    return {"ok": True}
