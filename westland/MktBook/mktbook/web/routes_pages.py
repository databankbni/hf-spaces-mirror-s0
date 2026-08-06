"""HTML page routes."""
from __future__ import annotations

import datetime

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from mktbook.db import queries
from mktbook.ecosystem import detect_ecosystem, inject_ecosystem_tag, read_ecosystem_tag, strip_ecosystem_tag
from mktbook.telemetry import maybe_send_telemetry
from mktbook.config import settings
from mktbook.web.app import TEMPLATES
from mktbook.web.auth import (
    COOKIE_NAME,
    get_password,
    is_authenticated,
    make_session_cookie,
    redirect_to_login,
    set_password,
)
from mktbook.web.workouts import all_workouts, get_workout

router = APIRouter()


# ── Workout Selector (root) ────────────────────────────────────────────

@router.get("/", response_class=HTMLResponse)
async def workout_selector(request: Request) -> HTMLResponse:
    workouts = all_workouts()
    await maybe_send_telemetry(request)
    return TEMPLATES.TemplateResponse("workout_selector.html", {
        "request": request,
        "workouts": workouts,
    })


# ── Workout-scoped pages  /w/{workout_id}/* ────────────────────────────

@router.get("/w/{workout_id}", response_class=HTMLResponse)
async def workout_redirect(workout_id: int) -> RedirectResponse:
    return RedirectResponse(url=f"/w/{workout_id}/", status_code=302)


@router.get("/w/{workout_id}/", response_class=HTMLResponse)
async def w_dashboard(request: Request, workout_id: int) -> HTMLResponse:
    workout = get_workout(workout_id)
    if not workout:
        return HTMLResponse("<h1>Workout not found</h1>", status_code=404)
    bots = await queries.get_all_bots(workout_id=workout_id)
    grades = await queries.get_latest_grades()
    bot_map = {b.id: b for b in bots}
    leaderboard = []
    for g in grades:
        bot = bot_map.get(g.bot_id)
        if bot:  # Only include bots from this workout
            eco = detect_ecosystem(bot)
            ecosystem = "A" if eco == "Ecosystem A" else "B"
            leaderboard.append({
                "bot_name": bot.bot_name,
                "student_name": bot.student_name,
                "overall_score": g.overall_score,
                "objective_score": g.objective_score,
                "quality_score": g.quality_score,
                "human_score": g.human_score,
                "volume_score": g.volume_score,
                "bot_id": g.bot_id,
                "llm_reasoning": g.llm_reasoning,
                "ecosystem": ecosystem,
            })
    # Get bot IDs for this workout to filter messages
    bot_ids = {b.id for b in bots}
    all_msgs = await queries.get_messages(limit=50)
    recent_messages = [m for m in all_msgs if m.bot_id in bot_ids][:20]
    # Workout-specific dashboard stats
    stats = {}
    for bot in bots:
        stats[bot.id] = await queries.get_bot_stats(bot.id)
    return TEMPLATES.TemplateResponse("w_dashboard.html", {
        "request": request,
        "workout": workout,
        "bots": bots,
        "leaderboard": leaderboard,
        "messages": recent_messages,
        "stats": stats,
    })


@router.get("/w/{workout_id}/bots", response_class=HTMLResponse)
async def w_bot_list(request: Request, workout_id: int) -> HTMLResponse:
    workout = get_workout(workout_id)
    if not workout:
        return HTMLResponse("<h1>Workout not found</h1>", status_code=404)
    bots = await queries.get_all_bots(workout_id=workout_id)
    stats = {}
    for b in bots:
        stats[b.id] = await queries.get_bot_stats(b.id)
    return TEMPLATES.TemplateResponse("w_bot_list.html", {
        "request": request,
        "workout": workout,
        "bots": bots,
        "stats": stats,
        "authenticated": is_authenticated(request),
    })


@router.get("/w/{workout_id}/bots/new", response_class=HTMLResponse)
async def w_bot_form_new(request: Request, workout_id: int) -> HTMLResponse:
    workout = get_workout(workout_id)
    if not workout:
        return HTMLResponse("<h1>Workout not found</h1>", status_code=404)
    ecosystem_choice = request.query_params.get("ecosystem", "").upper()
    if ecosystem_choice not in ("A", "B"):
        ecosystem_choice = ""
    return TEMPLATES.TemplateResponse("w_bot_form.html", {
        "request": request,
        "workout": workout,
        "bot": None,
        "ecosystem_choice": ecosystem_choice,
    })


@router.post("/w/{workout_id}/bots/new", response_model=None)
async def w_bot_form_submit(
    request: Request,
    workout_id: int,
    student_name: str = Form(...),
    bot_name: str = Form(...),
    personality: str = Form(""),
    objective: str = Form(""),
    behavior_rules: str = Form(""),
    ecosystem_choice: str = Form(""),
) -> HTMLResponse | RedirectResponse:
    workout = get_workout(workout_id)
    if not workout:
        return HTMLResponse("<h1>Workout not found</h1>", status_code=404)
    # For W5, inject the ecosystem override tag (selector choice takes priority)
    if workout_id == 5 and ecosystem_choice.upper() in ("A", "B"):
        behavior_rules = inject_ecosystem_tag(behavior_rules, ecosystem_choice.upper())
    try:
        bot = await queries.create_bot(
            student_name=student_name,
            bot_name=bot_name,
            personality=personality,
            objective=objective,
            behavior_rules=behavior_rules,
            workout_id=workout_id,
        )
    except Exception as exc:
        error_msg = (
            f"Bot name \"{bot_name}\" is already registered for this workout. Please choose a different name."
            if "unique" in str(exc).lower()
            else f"Could not register bot: {exc}"
        )
        return TEMPLATES.TemplateResponse("w_bot_form.html", {
            "request": request,
            "workout": workout,
            "bot": None,
            "error": error_msg,
            "ecosystem_choice": ecosystem_choice.upper(),
            "form_data": {
                "student_name": student_name,
                "bot_name": bot_name,
                "personality": personality,
                "objective": objective,
                "behavior_rules": strip_ecosystem_tag(behavior_rules),
            },
        }, status_code=422)
    fleet = request.app.state.fleet
    if fleet:
        await fleet.start_bot(bot)
    return RedirectResponse(url=f"/w/{workout_id}/bots/{bot.id}", status_code=303)


@router.get("/w/{workout_id}/bots/{bot_id}", response_class=HTMLResponse)
async def w_bot_detail(request: Request, workout_id: int, bot_id: int) -> HTMLResponse:
    workout = get_workout(workout_id)
    if not workout:
        return HTMLResponse("<h1>Workout not found</h1>", status_code=404)
    bot = await queries.get_bot(bot_id)
    if not bot:
        return HTMLResponse("<h1>Bot not found</h1>", status_code=404)
    stats = await queries.get_bot_stats(bot_id)
    grades = await queries.get_bot_grades(bot_id)
    conversations = await queries.get_bot_conversations(bot_id, limit=20)
    return TEMPLATES.TemplateResponse("w_bot_detail.html", {
        "request": request,
        "workout": workout,
        "bot": bot,
        "stats": stats,
        "grades": grades,
        "conversations": conversations,
    })


@router.get("/w/{workout_id}/bots/{bot_id}/edit", response_class=HTMLResponse)
async def w_bot_form_edit(request: Request, workout_id: int, bot_id: int) -> HTMLResponse:
    workout = get_workout(workout_id)
    if not workout:
        return HTMLResponse("<h1>Workout not found</h1>", status_code=404)
    bot = await queries.get_bot(bot_id)
    if not bot:
        return HTMLResponse("<h1>Bot not found</h1>", status_code=404)
    # For W5, read current ecosystem and strip the tag from the display value
    ecosystem_choice = ""
    behavior_rules_display = bot.behavior_rules
    if workout_id == 5:
        tag = read_ecosystem_tag(bot.behavior_rules or "")
        if tag:
            ecosystem_choice = tag
        else:
            eco = detect_ecosystem(bot)
            ecosystem_choice = "A" if eco == "Ecosystem A" else "B"
        behavior_rules_display = strip_ecosystem_tag(bot.behavior_rules or "")
    return TEMPLATES.TemplateResponse("w_bot_form.html", {
        "request": request,
        "workout": workout,
        "bot": bot,
        "ecosystem_choice": ecosystem_choice,
        "behavior_rules_display": behavior_rules_display,
    })


@router.post("/w/{workout_id}/bots/{bot_id}/edit")
async def w_bot_form_update(
    request: Request,
    workout_id: int,
    bot_id: int,
    student_name: str = Form(...),
    bot_name: str = Form(...),
    personality: str = Form(""),
    objective: str = Form(""),
    behavior_rules: str = Form(""),
    is_active: str = Form("off"),
    ecosystem_choice: str = Form(""),
) -> RedirectResponse:
    # For W5, inject the ecosystem override tag (selector choice takes priority)
    if workout_id == 5 and ecosystem_choice.upper() in ("A", "B"):
        behavior_rules = inject_ecosystem_tag(behavior_rules, ecosystem_choice.upper())
    await queries.update_bot(
        bot_id,
        student_name=student_name,
        bot_name=bot_name,
        personality=personality,
        objective=objective,
        behavior_rules=behavior_rules,
        is_active=1 if is_active == "on" else 0,
    )
    fleet = request.app.state.fleet
    if fleet:
        await fleet.reload_bot(bot_id)
    return RedirectResponse(url=f"/w/{workout_id}/bots/{bot_id}", status_code=303)


@router.get("/w/{workout_id}/grading", response_class=HTMLResponse)
async def w_grading_page(request: Request, workout_id: int) -> HTMLResponse:
    if not is_authenticated(request):
        return redirect_to_login(f"/w/{workout_id}/grading")
    workout = get_workout(workout_id)
    if not workout:
        return HTMLResponse("<h1>Workout not found</h1>", status_code=404)
    bots = await queries.get_all_bots(workout_id=workout_id)
    bot_ids = {b.id for b in bots}
    all_grades = await queries.get_latest_grades()
    bot_map = {b.id: b for b in bots}
    enriched = []
    for g in all_grades:
        if g.bot_id in bot_ids:
            bot = bot_map.get(g.bot_id)
            enriched.append({"grade": g, "bot": bot})
    from mktbook.lti import db as lti_db
    lti_linked_bot_ids = await lti_db.get_linked_bot_ids_for_workout(workout_id)
    return TEMPLATES.TemplateResponse("w_grading.html", {
        "request": request,
        "workout": workout,
        "grades": enriched,
        "lti_linked_bot_ids": lti_linked_bot_ids,
    })


@router.get("/w/{workout_id}/messages", response_class=HTMLResponse)
async def w_messages_redirect(workout_id: int) -> RedirectResponse:
    """Legacy messages URL — redirect to platform."""
    return RedirectResponse(url=f"/w/{workout_id}/platform", status_code=302)


# ── Platform (discussion forum replacement for Discord) ────────────────

@router.get("/w/{workout_id}/platform", response_class=HTMLResponse)
async def w_platform_page(
    request: Request,
    workout_id: int,
    bot_id: int | None = None,
) -> HTMLResponse:
    workout = get_workout(workout_id)
    if not workout:
        return HTMLResponse("<h1>Workout not found</h1>", status_code=404)
    bots = await queries.get_all_bots(workout_id=workout_id)
    if bot_id is not None:
        msgs = await queries.get_messages(limit=500, bot_id=bot_id)
    else:
        msgs = await queries.get_messages_for_workout(workout_id=workout_id, limit=500)
    bot_ecosystems = {
        b.id: ("A" if detect_ecosystem(b) == "Ecosystem A" else "B")
        for b in bots
    }
    return TEMPLATES.TemplateResponse("w_platform.html", {
        "request": request,
        "workout": workout,
        "messages": msgs,
        "bots": bots,
        "bot_ecosystems": bot_ecosystems,
        "selected_bot_id": bot_id,
    })


@router.post("/w/{workout_id}/platform/post")
async def w_platform_post(
    request: Request,
    workout_id: int,
    author_name: str = Form(...),
    message_content: str = Form(...),
) -> RedirectResponse:
    """Accept a human message posted from the platform and dispatch to bots."""
    workout = get_workout(workout_id)
    if not workout:
        return HTMLResponse("<h1>Workout not found</h1>", status_code=404)
    fleet = request.app.state.fleet
    scheduler = getattr(request.app.state, "scheduler", None)
    paused = scheduler.is_paused(workout_id) if scheduler else False
    if fleet and message_content.strip() and not paused:
        await fleet.dispatch_human_message(
            workout_id=workout_id,
            author_name=author_name.strip() or "Visitor",
            content=message_content.strip(),
        )
    return RedirectResponse(url=f"/w/{workout_id}/platform", status_code=303)


# ── Admin / Reset ──────────────────────────────────────────────────────

@router.get("/w/{workout_id}/admin", response_class=HTMLResponse)
async def w_admin_page(
    request: Request,
    workout_id: int,
    done: str = "",
) -> HTMLResponse:
    if not is_authenticated(request):
        return redirect_to_login(f"/w/{workout_id}/admin")
    workout = get_workout(workout_id)
    if not workout:
        return HTMLResponse("<h1>Workout not found</h1>", status_code=404)
    stats = await queries.get_workout_stats(workout_id)

    auto_grader = getattr(request.app.state, "auto_grader", None)
    auto_grade_hours = auto_grader.get_interval(workout_id) if auto_grader else None
    next_run_at = auto_grader.get_next_run_at(workout_id) if auto_grader else None
    if next_run_at:
        mins_until = max(0, int((next_run_at - datetime.datetime.now()).total_seconds() / 60))
    else:
        mins_until = None

    scheduler = getattr(request.app.state, "scheduler", None)
    workout_paused = scheduler.is_paused(workout_id) if scheduler else False

    return TEMPLATES.TemplateResponse("w_admin.html", {
        "request": request,
        "workout": workout,
        "stats": stats,
        "done": done,
        "active_page": "admin",
        "auto_grade_hours": auto_grade_hours,
        "auto_grade_mins_until": mins_until,
        "workout_paused": workout_paused,
    })


@router.post("/w/{workout_id}/admin/auto-grade", response_model=None)
async def w_admin_set_auto_grade(
    request: Request,
    workout_id: int,
    interval_hours: int = Form(0),
) -> RedirectResponse:
    """Enable or disable automatic regrading for a workout."""
    if not is_authenticated(request):
        return redirect_to_login(f"/w/{workout_id}/admin")
    auto_grader = getattr(request.app.state, "auto_grader", None)
    if auto_grader:
        if interval_hours == 0:
            await auto_grader.clear(workout_id)
        else:
            interval_hours = max(1, min(12, interval_hours))
            await auto_grader.set(workout_id, interval_hours)
    return RedirectResponse(url=f"/w/{workout_id}/admin", status_code=303)


@router.post("/w/{workout_id}/admin/pause", response_model=None)
async def w_admin_toggle_pause(
    request: Request,
    workout_id: int,
) -> RedirectResponse:
    """Pause or resume bot-bot conversations for this workout."""
    if not is_authenticated(request):
        return redirect_to_login(f"/w/{workout_id}/admin")
    scheduler = getattr(request.app.state, "scheduler", None)
    if scheduler:
        if scheduler.is_paused(workout_id):
            scheduler.resume_workout(workout_id)
        else:
            scheduler.pause_workout(workout_id)
    return RedirectResponse(url=f"/w/{workout_id}/admin", status_code=303)


@router.post("/w/{workout_id}/admin/reset/conversations")
async def w_admin_reset_conversations(
    request: Request,
    workout_id: int,
) -> RedirectResponse:
    """Wipe all messages, conversations, and grades for this workout."""
    if not is_authenticated(request):
        return redirect_to_login(f"/w/{workout_id}/admin")
    counts = await queries.reset_conversations_for_workout(workout_id)
    fleet = request.app.state.fleet
    # No bots to stop — just data cleared
    return RedirectResponse(
        url=f"/w/{workout_id}/admin?done=conversations&msgs={counts['messages']}&convs={counts['conversations']}&grades={counts['grades']}",
        status_code=303,
    )


@router.post("/w/{workout_id}/admin/reset/bots")
async def w_admin_reset_bots(
    request: Request,
    workout_id: int,
) -> RedirectResponse:
    """Wipe all bots AND their data for this workout."""
    if not is_authenticated(request):
        return redirect_to_login(f"/w/{workout_id}/admin")
    fleet = request.app.state.fleet
    if fleet:
        await fleet.remove_bots_for_workout(workout_id)
    counts = await queries.reset_bots_for_workout(workout_id)
    return RedirectResponse(
        url=f"/w/{workout_id}/admin?done=bots&bots={counts['bots']}&msgs={counts['messages']}&convs={counts['conversations']}",
        status_code=303,
    )


@router.get("/admin", response_class=HTMLResponse)
async def global_admin_page(
    request: Request,
    done: str = "",
) -> HTMLResponse:
    if not is_authenticated(request):
        return redirect_to_login("/admin")
    from mktbook.web.workouts import all_workouts
    workouts = all_workouts()
    global_stats = await queries.get_global_stats()
    per_workout = {}
    for w in workouts:
        per_workout[w["id"]] = await queries.get_workout_stats(w["id"])
    return TEMPLATES.TemplateResponse("admin.html", {
        "request": request,
        "workout": None,
        "workouts": workouts,
        "global_stats": global_stats,
        "per_workout": per_workout,
        "done": done,
    })


@router.post("/admin/reset/conversations")
async def global_admin_reset_conversations(request: Request) -> RedirectResponse:
    """Wipe ALL messages, conversations, and grades across every workout."""
    if not is_authenticated(request):
        return redirect_to_login("/admin")
    counts = await queries.reset_all_conversations()
    return RedirectResponse(
        url=f"/admin?done=conversations&msgs={counts['messages']}&convs={counts['conversations']}&grades={counts['grades']}",
        status_code=303,
    )


@router.post("/admin/reset/all")
async def global_admin_reset_all(request: Request) -> RedirectResponse:
    """Nuclear reset — wipe all bots and all data across every workout."""
    if not is_authenticated(request):
        return redirect_to_login("/admin")
    fleet = request.app.state.fleet
    if fleet:
        await fleet.stop_all()
    counts = await queries.reset_all()
    return RedirectResponse(
        url=f"/admin?done=all&bots={counts['bots']}&msgs={counts['messages']}&convs={counts['conversations']}",
        status_code=303,
    )


# ── Login / Logout / Password ──────────────────────────────────────────

@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, next: str = "/admin") -> HTMLResponse:
    if is_authenticated(request):
        return RedirectResponse(url=next, status_code=302)
    return TEMPLATES.TemplateResponse("login.html", {
        "request": request,
        "next": next,
        "error": False,
    })


@router.post("/login", response_model=None)
async def login_submit(
    request: Request,
    password: str = Form(...),
    next: str = Form("/admin"),
) -> HTMLResponse | RedirectResponse:
    if password.strip() == get_password().strip() or password.strip() == settings.admin_password.strip():
        token = make_session_cookie()
        response = RedirectResponse(url=next if next.startswith("/") else "/admin", status_code=303)
        response.set_cookie(COOKIE_NAME, token, max_age=8 * 3600, httponly=True, samesite="none", secure=True)
        return response
    return TEMPLATES.TemplateResponse("login.html", {
        "request": request,
        "next": next,
        "error": True,
    }, status_code=401)


@router.post("/logout")
async def logout() -> RedirectResponse:
    response = RedirectResponse(url="/", status_code=303)
    response.delete_cookie(COOKIE_NAME)
    return response


@router.get("/admin/password", response_class=HTMLResponse)
async def change_password_page(request: Request, done: str = "") -> HTMLResponse:
    if not is_authenticated(request):
        return redirect_to_login("/admin/password")
    return TEMPLATES.TemplateResponse("admin_password.html", {
        "request": request,
        "workout": None,
        "done": done,
    })


@router.post("/admin/password", response_model=None)
async def change_password_submit(
    request: Request,
    current_password: str = Form(...),
    new_password: str = Form(...),
    confirm_password: str = Form(...),
) -> HTMLResponse | RedirectResponse:
    if not is_authenticated(request):
        return redirect_to_login("/admin/password")
    error = ""
    if current_password.strip() != get_password().strip() and current_password.strip() != settings.admin_password.strip():
        error = "Current password is incorrect."
    elif len(new_password) < 4:
        error = "New password must be at least 4 characters."
    elif new_password != confirm_password:
        error = "New passwords do not match."
    if error:
        return TEMPLATES.TemplateResponse("admin_password.html", {
            "request": request,
            "workout": None,
            "done": "",
            "error": error,
        }, status_code=422)
    set_password(new_password)
    return RedirectResponse(url="/admin/password?done=1", status_code=303)


# ── Legacy routes (kept for backward compatibility) ────────────────────

@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request) -> HTMLResponse:
    bots = await queries.get_all_bots()
    grades = await queries.get_latest_grades()
    bot_map = {b.id: b for b in bots}
    leaderboard = []
    for g in grades:
        bot = bot_map.get(g.bot_id)
        leaderboard.append({
            "bot_name": bot.bot_name if bot else "Unknown",
            "student_name": bot.student_name if bot else "Unknown",
            "overall_score": g.overall_score,
            "bot_id": g.bot_id,
        })
    recent_messages = await queries.get_messages(limit=20)
    return TEMPLATES.TemplateResponse("dashboard.html", {
        "request": request,
        "bots": bots,
        "leaderboard": leaderboard,
        "messages": recent_messages,
    })


@router.get("/bots", response_class=HTMLResponse)
async def bot_list(request: Request) -> HTMLResponse:
    bots = await queries.get_all_bots()
    stats = {}
    for b in bots:
        stats[b.id] = await queries.get_bot_stats(b.id)
    return TEMPLATES.TemplateResponse("bot_list.html", {
        "request": request,
        "bots": bots,
        "stats": stats,
    })


@router.get("/bots/new", response_class=HTMLResponse)
async def bot_form_new(request: Request) -> HTMLResponse:
    return TEMPLATES.TemplateResponse("bot_form.html", {
        "request": request,
        "bot": None,
    })


@router.post("/bots/new")
async def bot_form_submit(
    request: Request,
    student_name: str = Form(...),
    bot_name: str = Form(...),
    personality: str = Form(""),
    objective: str = Form(""),
    behavior_rules: str = Form(""),
) -> RedirectResponse:
    bot = await queries.create_bot(
        student_name=student_name,
        bot_name=bot_name,
        personality=personality,
        objective=objective,
        behavior_rules=behavior_rules,
    )
    fleet = request.app.state.fleet
    if fleet:
        await fleet.start_bot(bot)
    return RedirectResponse(url=f"/bots/{bot.id}", status_code=303)


@router.get("/bots/{bot_id}", response_class=HTMLResponse)
async def bot_detail(request: Request, bot_id: int) -> HTMLResponse:
    bot = await queries.get_bot(bot_id)
    if not bot:
        return HTMLResponse("<h1>Bot not found</h1>", status_code=404)
    stats = await queries.get_bot_stats(bot_id)
    grades = await queries.get_bot_grades(bot_id)
    conversations = await queries.get_bot_conversations(bot_id, limit=20)
    return TEMPLATES.TemplateResponse("bot_detail.html", {
        "request": request,
        "bot": bot,
        "stats": stats,
        "grades": grades,
        "conversations": conversations,
    })


@router.get("/bots/{bot_id}/edit", response_class=HTMLResponse)
async def bot_form_edit(request: Request, bot_id: int) -> HTMLResponse:
    bot = await queries.get_bot(bot_id)
    if not bot:
        return HTMLResponse("<h1>Bot not found</h1>", status_code=404)
    return TEMPLATES.TemplateResponse("bot_form.html", {
        "request": request,
        "bot": bot,
    })


@router.post("/bots/{bot_id}/edit")
async def bot_form_update(
    request: Request,
    bot_id: int,
    student_name: str = Form(...),
    bot_name: str = Form(...),
    personality: str = Form(""),
    objective: str = Form(""),
    behavior_rules: str = Form(""),
    is_active: str = Form("off"),
) -> RedirectResponse:
    await queries.update_bot(
        bot_id,
        student_name=student_name,
        bot_name=bot_name,
        personality=personality,
        objective=objective,
        behavior_rules=behavior_rules,
        is_active=1 if is_active == "on" else 0,
    )
    fleet = request.app.state.fleet
    if fleet:
        await fleet.reload_bot(bot_id)
    return RedirectResponse(url=f"/bots/{bot_id}", status_code=303)


@router.get("/grading", response_class=HTMLResponse)
async def grading_page(request: Request) -> HTMLResponse:
    if not is_authenticated(request):
        return redirect_to_login("/grading")
    grades = await queries.get_latest_grades()
    bots = {b.id: b for b in await queries.get_all_bots()}
    enriched = []
    for g in grades:
        bot = bots.get(g.bot_id)
        enriched.append({"grade": g, "bot": bot})
    return TEMPLATES.TemplateResponse("grading.html", {
        "request": request,
        "grades": enriched,
    })


@router.get("/messages", response_class=HTMLResponse)
async def messages_page(request: Request, bot_id: int | None = None) -> HTMLResponse:
    msgs = await queries.get_messages(limit=200, bot_id=bot_id)
    bots = await queries.get_all_bots()
    return TEMPLATES.TemplateResponse("messages.html", {
        "request": request,
        "messages": msgs,
        "bots": bots,
        "selected_bot_id": bot_id,
    })
