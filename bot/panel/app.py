"""FastAPI admin panel for creating and managing dynamic bot commands.

Runs in the same process as the Telegram bot. It reads/writes the ``commands``
table in Postgres and, after every change, refreshes the in-process command
registry and the Telegram command menu so updates take effect immediately.
"""

import logging
import re
from pathlib import Path
from urllib.parse import urlparse

from fastapi import Depends, FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from bot import commands, db
from bot.handlers import DB_KEY, set_bot_commands
from bot.panel.auth import (
    AuthRedirect,
    check_credentials,
    get_csrf_token,
    login_required,
    verify_csrf,
)
from bot.panel.rate_limit import LoginRateLimiter


logger = logging.getLogger(__name__)

_BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(_BASE_DIR / "templates"))

NAME_RE = re.compile(r"^[a-z0-9_]{1,32}$")
BUILTIN_COMMANDS = ("start", "help", "about", "ping")
login_limiter = LoginRateLimiter()


def _get_pool(request: Request):
    return request.app.state.application.bot_data.get(DB_KEY)


def _actor(request: Request) -> str:
    return request.session.get("username") or request.app.state.settings.panel_username


def _flash(
    request: Request, message: str, *, kind: str = "success", refresh: bool = False
) -> None:
    request.session["flash"] = {
        "message": message,
        "kind": kind,
        "refresh": refresh,
    }


async def _audit(
    request: Request,
    action: str,
    entity_type: str,
    entity_name: str,
    details: dict | None = None,
) -> None:
    await db.add_audit_log(
        _get_pool(request),
        actor=_actor(request),
        action=action,
        entity_type=entity_type,
        entity_name=entity_name,
        details=details,
    )


async def _refresh(request: Request) -> None:
    """Reload the command registry and republish the Telegram command menu."""
    application = request.app.state.application
    await commands.reload(application.bot_data.get(DB_KEY))
    try:
        await set_bot_commands(application)
    except Exception:  # menu refresh is best-effort; never fail the request on it
        logger.exception("Failed to refresh Telegram command menu.")


def _validate(
    form: dict, *, existing_keyboard: list | None = None
) -> tuple[dict, list[str]]:
    """Validate and normalise submitted command fields. Returns (values, errors)."""
    errors: list[str] = []
    name = (form.get("name") or "").strip().lstrip("/").lower()
    description = (form.get("description") or "").strip()
    reply_type = (form.get("reply_type") or "text").strip()
    reply_text = (form.get("reply_text") or "").strip()
    media_url = (form.get("media_url") or "").strip()
    enabled = form.get("enabled") == "on"
    show_in_menu = form.get("show_in_menu") == "on"

    if not NAME_RE.match(name):
        errors.append("Name must be 1-32 chars: lowercase letters, digits, underscore.")
    if name in commands.RESERVED_NAMES:
        errors.append(f"'{name}' is a built-in command and cannot be overridden.")
    if len(description) > 256:
        errors.append("Description must be 256 characters or fewer (Telegram limit).")
    if reply_type not in commands.REPLY_TYPES:
        errors.append("Invalid reply type.")
    if reply_type == "text" and not reply_text:
        errors.append("Text reply requires a message body.")
    if reply_type in ("photo", "document"):
        if not media_url:
            errors.append("Photo/document reply requires a media URL or Telegram file_id.")
        elif "://" in media_url:
            scheme = urlparse(media_url).scheme
            if scheme not in ("http", "https"):
                errors.append("Media URL must use http or https.")

    values = {
        "name": name,
        "description": description,
        "reply_type": reply_type,
        "reply_text": reply_text,
        "media_url": media_url,
        "keyboard": existing_keyboard,
        "enabled": enabled,
        "show_in_menu": show_in_menu,
    }
    return values, errors


def create_app(application, settings) -> FastAPI:
    app = FastAPI(title="Telegram Bot Studio", docs_url=None, redoc_url=None)
    app.state.application = application
    app.state.settings = settings

    secret = settings.panel_secret_key or secrets_fallback(settings)
    app.add_middleware(
        SessionMiddleware,
        secret_key=secret,
        https_only=settings.panel_secure_cookie,
        same_site="lax",
        max_age=60 * 60 * 12,
    )

    static_dir = _BASE_DIR / "static"
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    @app.exception_handler(AuthRedirect)
    async def _on_auth_redirect(request: Request, exc: AuthRedirect):
        return RedirectResponse("/login", status_code=303)

    @app.get("/healthz")
    async def healthz():
        return {"status": "ok"}

    @app.get("/login", response_class=HTMLResponse)
    async def login_form(request: Request):
        if request.session.get("authenticated"):
            return RedirectResponse("/", status_code=303)
        return templates.TemplateResponse(
            "login.html", {"request": request, "csrf_token": get_csrf_token(request), "error": None}
        )

    @app.post("/login", response_class=HTMLResponse)
    async def login_submit(
        request: Request,
        username: str = Form(""),
        password: str = Form(""),
        csrf_token: str = Form(""),
    ):
        verify_csrf(request, csrf_token)
        client_key = request.client.host if request.client else "unknown"
        if login_limiter.is_blocked(client_key):
            return templates.TemplateResponse(
                "login.html",
                {
                    "request": request,
                    "csrf_token": get_csrf_token(request),
                    "error": "Too many login attempts. Try again in a few minutes.",
                },
                status_code=429,
            )
        if check_credentials(request, username, password):
            login_limiter.reset(client_key)
            request.session["authenticated"] = True
            request.session["username"] = username
            request.session.pop("csrf", None)
            get_csrf_token(request)
            return RedirectResponse("/", status_code=303)
        login_limiter.record_failure(client_key)
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "csrf_token": get_csrf_token(request), "error": "Invalid credentials."},
            status_code=401,
        )

    @app.post("/logout")
    async def logout(request: Request, csrf_token: str = Form("")):
        verify_csrf(request, csrf_token)
        request.session.clear()
        return RedirectResponse("/login", status_code=303)

    @app.get("/", response_class=HTMLResponse, dependencies=[Depends(login_required)])
    async def index(request: Request):
        pool = _get_pool(request)
        items = await db.list_commands(pool) if pool is not None else []
        button_items = await db.list_menu_buttons(pool) if pool is not None else []
        response_button_count = sum(
            len(row)
            for item in items
            for row in (item.get("keyboard") or [])
        )
        audit_items = await db.list_audit_log(pool, limit=8) if pool is not None else []
        return templates.TemplateResponse(
            "list.html",
            {
                "request": request,
                "stats": {
                    "total": len(items),
                    "enabled": sum(bool(item["enabled"]) for item in items),
                    "in_menu": sum(
                        bool(item["enabled"] and item["show_in_menu"]) for item in items
                    ),
                    "buttons": len(button_items) + response_button_count,
                },
                "audit_items": audit_items,
                "csrf_token": get_csrf_token(request),
            },
        )

    @app.post("/activity/clear", dependencies=[Depends(login_required)])
    async def clear_activity(request: Request, csrf_token: str = Form("")):
        verify_csrf(request, csrf_token)
        deleted = await db.clear_audit_log(_get_pool(request))
        _flash(
            request,
            f"Activity history cleared ({deleted} entr{'y' if deleted == 1 else 'ies'} removed).",
        )
        return RedirectResponse("/", status_code=303)

    @app.get(
        "/commands", response_class=HTMLResponse, dependencies=[Depends(login_required)]
    )
    async def commands_index(request: Request):
        pool = _get_pool(request)
        items = await db.list_commands(pool) if pool is not None else []
        return templates.TemplateResponse(
            "commands.html",
            {
                "request": request,
                "commands": items,
                "csrf_token": get_csrf_token(request),
            },
        )

    @app.get("/commands/new", response_class=HTMLResponse, dependencies=[Depends(login_required)])
    async def new_form(request: Request):
        return templates.TemplateResponse(
            "form.html",
            {
                "request": request,
                "csrf_token": get_csrf_token(request),
                "action": "/commands/new",
                "title": "New command",
                "errors": [],
                "values": _empty_command(),
                "reply_types": commands.REPLY_TYPES,
            },
        )

    @app.post("/commands/new", response_class=HTMLResponse, dependencies=[Depends(login_required)])
    async def new_submit(request: Request):
        form = dict(await request.form())
        verify_csrf(request, form.get("csrf_token"))
        values, errors = _validate(form)
        pool = _get_pool(request)
        if pool is None:
            errors.append("Database not connected.")
        if errors:
            return _render_form(request, "/commands/new", "New command", values, errors)
        await db.create_command(pool, **values)
        await _audit(request, "created", "command", values["name"])
        await _refresh(request)
        _flash(request, f"Command /{values['name']} was created.")
        return RedirectResponse("/commands", status_code=303)

    @app.get(
        "/commands/{command_id}/edit",
        response_class=HTMLResponse,
        dependencies=[Depends(login_required)],
    )
    async def edit_form(request: Request, command_id: int):
        pool = _get_pool(request)
        command = await db.get_command(pool, command_id) if pool is not None else None
        if command is None:
            return RedirectResponse("/commands", status_code=303)
        return _render_form(
            request, f"/commands/{command_id}/edit", "Edit command", command, []
        )

    @app.post(
        "/commands/{command_id}/edit",
        response_class=HTMLResponse,
        dependencies=[Depends(login_required)],
    )
    async def edit_submit(request: Request, command_id: int):
        form = dict(await request.form())
        verify_csrf(request, form.get("csrf_token"))
        pool = _get_pool(request)
        existing = await db.get_command(pool, command_id) if pool is not None else None
        values, errors = _validate(
            form, existing_keyboard=existing.get("keyboard") if existing else None
        )
        if pool is None:
            errors.append("Database not connected.")
        if errors:
            return _render_form(
                request, f"/commands/{command_id}/edit", "Edit command", values, errors
            )
        await db.update_command(pool, command_id, **values)
        await _audit(
            request,
            "updated",
            "command",
            values["name"],
            {"previous_name": existing["name"] if existing else values["name"]},
        )
        await _refresh(request)
        _flash(request, f"Command /{values['name']} was updated.")
        return RedirectResponse("/commands", status_code=303)

    @app.get(
        "/response-buttons",
        response_class=HTMLResponse,
        dependencies=[Depends(login_required)],
    )
    async def response_buttons(request: Request, command_id: int | None = None):
        pool = _get_pool(request)
        command_rows = await db.list_commands(pool)
        selected = (
            await db.get_command(pool, command_id) if command_id is not None else None
        )
        return templates.TemplateResponse(
            "response_buttons.html",
            {
                "request": request,
                "commands": command_rows,
                "selected": selected,
                "target_commands": [
                    {"name": name, "description": f"Built-in /{name}"}
                    for name in BUILTIN_COMMANDS
                ]
                + command_rows,
                "selected_targets": {
                    str(label).lstrip("/")
                    for row in (selected.get("keyboard") if selected else []) or []
                    for label in row
                    if str(label).startswith("/")
                },
                "columns": 2,
                "errors": [],
                "csrf_token": get_csrf_token(request),
            },
        )

    @app.post(
        "/response-buttons",
        response_class=HTMLResponse,
        dependencies=[Depends(login_required)],
    )
    async def response_buttons_submit(request: Request):
        form = await request.form()
        verify_csrf(request, form.get("csrf_token"))
        pool = _get_pool(request)
        try:
            command_id = int(form.get("command_id") or "")
        except ValueError:
            command_id = 0
        selected = await db.get_command(pool, command_id)
        errors = [] if selected else ["Select a valid command from the list."]
        clear_buttons = form.get("clear") == "1"
        command_rows = await db.list_commands(pool)
        target_commands = [
            {"name": name, "description": f"Built-in /{name}"}
            for name in BUILTIN_COMMANDS
        ] + command_rows
        valid_targets = {item["name"] for item in target_commands}
        selected_targets = [
            name for name in form.getlist("target_commands") if name in valid_targets
        ]
        try:
            columns = min(3, max(1, int(form.get("columns") or 2)))
        except ValueError:
            columns = 2
        if not selected_targets and not clear_buttons:
            errors.append("Select at least one command for the response buttons.")
        keyboard = [
            [f"/{name}" for name in selected_targets[index : index + columns]]
            for index in range(0, len(selected_targets), columns)
        ]
        if errors:
            return templates.TemplateResponse(
                "response_buttons.html",
                {
                    "request": request,
                    "commands": command_rows,
                    "selected": selected,
                    "target_commands": target_commands,
                    "selected_targets": set(selected_targets),
                    "columns": columns,
                    "errors": errors,
                    "csrf_token": get_csrf_token(request),
                },
                status_code=400,
            )
        await db.update_command_keyboard(
            pool, command_id, None if clear_buttons else keyboard
        )
        await _audit(
            request,
            "cleared" if clear_buttons else "updated",
            "response_buttons",
            selected["name"],
            {"targets": [] if clear_buttons else selected_targets},
        )
        await _refresh(request)
        _flash(
            request,
            (
                f"Response buttons for /{selected['name']} were removed."
                if clear_buttons
                else f"Response buttons for /{selected['name']} were updated."
            ),
            refresh=True,
        )
        return RedirectResponse(
            f"/response-buttons?command_id={command_id}", status_code=303
        )

    @app.post(
        "/commands/{command_id}/delete", dependencies=[Depends(login_required)]
    )
    async def delete(request: Request, command_id: int, csrf_token: str = Form("")):
        verify_csrf(request, csrf_token)
        pool = _get_pool(request)
        if pool is not None:
            command = await db.get_command(pool, command_id)
            if command is None:
                return RedirectResponse("/commands", status_code=303)
            dependencies = await db.command_dependencies(pool, command["name"])
            if dependencies["menu_buttons"] or dependencies["response_buttons"]:
                _flash(
                    request,
                    "Command cannot be deleted while Buttons or Response Buttons "
                    "still target it. Remove those references first.",
                    kind="error",
                )
                return RedirectResponse("/commands", status_code=303)
            await db.delete_command(pool, command_id)
            await _audit(request, "deleted", "command", command["name"])
            await _refresh(request)
            _flash(request, f"Command /{command['name']} was deleted.")
        return RedirectResponse("/commands", status_code=303)

    @app.get("/buttons", response_class=HTMLResponse, dependencies=[Depends(login_required)])
    async def buttons_index(request: Request):
        pool = _get_pool(request)
        items = await db.list_menu_buttons(pool) if pool is not None else []
        return templates.TemplateResponse(
            "buttons.html",
            {
                "request": request,
                "buttons": items,
                "csrf_token": get_csrf_token(request),
            },
        )

    @app.get(
        "/buttons/new",
        response_class=HTMLResponse,
        dependencies=[Depends(login_required)],
    )
    async def button_new_form(request: Request):
        return await _render_button_form(
            request, {}, [], action="/buttons/new", title="Add button"
        )

    @app.post(
        "/buttons/new",
        response_class=HTMLResponse,
        dependencies=[Depends(login_required)],
    )
    async def button_new_submit(request: Request):
        form = dict(await request.form())
        verify_csrf(request, form.get("csrf_token"))
        label = (form.get("label") or "").strip()
        command_name = (form.get("command_name") or "").strip().lstrip("/").lower()
        try:
            row_index = max(0, int(form.get("row_index") or 0))
            sort_order = int(form.get("sort_order") or 0)
        except ValueError:
            row_index, sort_order = 0, 0
        values = {
            "label": label,
            "command_name": command_name,
            "row_index": row_index,
            "sort_order": sort_order,
            "enabled": form.get("enabled") == "on",
        }
        errors = []
        if not label or len(label) > 64:
            errors.append("Button label must be between 1 and 64 characters.")

        pool = _get_pool(request)
        command_rows = await db.list_commands(pool, enabled_only=True)
        valid_commands = set(BUILTIN_COMMANDS) | {item["name"] for item in command_rows}
        if command_name not in valid_commands:
            errors.append("Choose an available command for this button.")
        existing = await db.list_menu_buttons(pool)
        if any(item["label"].casefold() == label.casefold() for item in existing):
            errors.append("A button with this label already exists.")
        if label.casefold() in {"help", "about", "ping"}:
            errors.append("This label is already used by a built-in button.")
        if errors:
            return await _render_button_form(
                request, values, errors, action="/buttons/new", title="Add button"
            )

        await db.create_menu_button(pool, **values)
        await _audit(request, "created", "button", label, {"command": command_name})
        await _refresh(request)
        _flash(
            request,
            f'Button "{label}" was created.',
            refresh=True,
        )
        return RedirectResponse("/buttons", status_code=303)

    @app.get(
        "/buttons/{button_id}/edit",
        response_class=HTMLResponse,
        dependencies=[Depends(login_required)],
    )
    async def button_edit_form(request: Request, button_id: int):
        button = await db.get_menu_button(_get_pool(request), button_id)
        if button is None:
            return RedirectResponse("/buttons", status_code=303)
        return await _render_button_form(
            request,
            button,
            [],
            action=f"/buttons/{button_id}/edit",
            title="Edit button",
        )

    @app.post(
        "/buttons/{button_id}/edit",
        response_class=HTMLResponse,
        dependencies=[Depends(login_required)],
    )
    async def button_edit_submit(request: Request, button_id: int):
        form = dict(await request.form())
        verify_csrf(request, form.get("csrf_token"))
        pool = _get_pool(request)
        current = await db.get_menu_button(pool, button_id)
        if current is None:
            return RedirectResponse("/buttons", status_code=303)
        values, errors = await _validate_button_form(
            pool, form, exclude_button_id=button_id
        )
        if errors:
            return await _render_button_form(
                request,
                values,
                errors,
                action=f"/buttons/{button_id}/edit",
                title="Edit button",
            )
        await db.update_menu_button(pool, button_id, **values)
        await _audit(
            request,
            "updated",
            "button",
            values["label"],
            {"previous_label": current["label"], "command": values["command_name"]},
        )
        await _refresh(request)
        _flash(request, f'Button "{values["label"]}" was updated.', refresh=True)
        return RedirectResponse("/buttons", status_code=303)

    @app.post(
        "/buttons/reorder", dependencies=[Depends(login_required)]
    )
    async def button_reorder(request: Request):
        form = dict(await request.form())
        verify_csrf(request, form.get("csrf_token"))
        try:
            button_ids = [
                int(value) for value in (form.get("order") or "").split(",") if value
            ]
        except ValueError:
            button_ids = []
        existing = await db.list_menu_buttons(_get_pool(request))
        valid_ids = {item["id"] for item in existing}
        if button_ids and set(button_ids) == valid_ids:
            await db.reorder_menu_buttons(_get_pool(request), button_ids)
            await _audit(request, "reordered", "buttons", "reply keyboard")
            await _refresh(request)
            _flash(request, "Button order was updated.", refresh=True)
        else:
            _flash(request, "Button order was invalid; no changes were saved.", kind="error")
        return RedirectResponse("/buttons", status_code=303)

    @app.post(
        "/buttons/{button_id}/delete", dependencies=[Depends(login_required)]
    )
    async def button_delete(
        request: Request, button_id: int, csrf_token: str = Form("")
    ):
        verify_csrf(request, csrf_token)
        pool = _get_pool(request)
        button = await db.get_menu_button(pool, button_id)
        if button is not None:
            await db.delete_menu_button(pool, button_id)
            await _audit(request, "deleted", "button", button["label"])
        await _refresh(request)
        _flash(
            request,
            f'Button "{button["label"]}" was deleted.' if button else "Button not found.",
            kind="success" if button else "error",
            refresh=button is not None,
        )
        return RedirectResponse("/buttons", status_code=303)

    async def _validate_button_form(pool, form, *, exclude_button_id=None):
        label = (form.get("label") or "").strip()
        command_name = (form.get("command_name") or "").strip().lstrip("/").lower()
        try:
            row_index = max(0, int(form.get("row_index") or 0))
            sort_order = int(form.get("sort_order") or 0)
        except ValueError:
            row_index, sort_order = 0, 0
        values = {
            "label": label,
            "command_name": command_name,
            "row_index": row_index,
            "sort_order": sort_order,
            "enabled": form.get("enabled") == "on",
        }
        errors = []
        if not label or len(label) > 64:
            errors.append("Button label must be between 1 and 64 characters.")
        command_rows = await db.list_commands(pool, enabled_only=True)
        valid_commands = set(BUILTIN_COMMANDS) | {item["name"] for item in command_rows}
        if command_name not in valid_commands:
            errors.append("Choose an available command for this button.")
        existing = await db.list_menu_buttons(pool)
        if any(
            item["id"] != exclude_button_id
            and item["label"].casefold() == label.casefold()
            for item in existing
        ):
            errors.append("A button with this label already exists.")
        if label.casefold() in {"help", "about", "ping"}:
            errors.append("This label is already used by a built-in button.")
        return values, errors

    async def _render_button_form(request, values, errors, *, action, title):
        pool = _get_pool(request)
        command_rows = await db.list_commands(pool, enabled_only=True)
        available_commands = [
            {"name": name, "description": f"Built-in /{name}"}
            for name in BUILTIN_COMMANDS
        ] + [
            {
                "name": item["name"],
                "description": item["description"] or f"/{item['name']}",
            }
            for item in command_rows
        ]
        defaults = {
            "label": "",
            "command_name": "help",
            "row_index": 0,
            "sort_order": 0,
            "enabled": True,
        }
        defaults.update(values)
        return templates.TemplateResponse(
            "button_form.html",
            {
                "request": request,
                "csrf_token": get_csrf_token(request),
                "values": defaults,
                "commands": available_commands,
                "errors": errors,
                "action": action,
                "title": title,
            },
            status_code=400 if errors else 200,
        )

    def _render_form(request, action, title, values, errors):
        return templates.TemplateResponse(
            "form.html",
            {
                "request": request,
                "csrf_token": get_csrf_token(request),
                "action": action,
                "title": title,
                "errors": errors,
                "values": values,
                "reply_types": commands.REPLY_TYPES,
            },
            status_code=400 if errors else 200,
        )

    return app


def _empty_command() -> dict:
    return {
        "name": "",
        "description": "",
        "reply_type": "text",
        "reply_text": "",
        "media_url": "",
        "keyboard": None,
        "enabled": True,
        "show_in_menu": True,
    }


def secrets_fallback(settings) -> str:
    """Derive a stable session secret from the password when none is configured.

    Prefer setting PANEL_SECRET_KEY explicitly; this fallback keeps sessions valid
    across restarts without requiring an extra variable.
    """
    import hashlib

    return hashlib.sha256(("panel:" + settings.panel_password).encode()).hexdigest()
