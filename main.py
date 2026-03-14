import csv
import io
import sqlite3
from collections import defaultdict
from datetime import date as today_date
from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

app = FastAPI()
templates = Jinja2Templates(directory="templates")

DB = "workouts.db"


def get_db():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    return con


def init_db():
    con = get_db()
    con.executescript("""
        CREATE TABLE IF NOT EXISTS exercise (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            name         TEXT NOT NULL,
            muscle_group TEXT
        );
        CREATE TABLE IF NOT EXISTS program (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT NOT NULL,
            description TEXT
        );
        CREATE TABLE IF NOT EXISTS workout_template (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            program_id INTEGER NOT NULL REFERENCES program(id),
            name       TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS template_exercise (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            template_id INTEGER NOT NULL REFERENCES workout_template(id),
            exercise_id INTEGER NOT NULL REFERENCES exercise(id),
            sets        INTEGER NOT NULL,
            reps        INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS workout (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            template_id INTEGER REFERENCES workout_template(id),
            date        TEXT NOT NULL,
            notes       TEXT
        );
        CREATE TABLE IF NOT EXISTS workout_set (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            workout_id  INTEGER NOT NULL REFERENCES workout(id),
            exercise_id INTEGER NOT NULL REFERENCES exercise(id),
            sets        INTEGER NOT NULL,
            reps        INTEGER NOT NULL,
            weight      REAL NOT NULL
        );
    """)
    con.commit()
    con.close()


init_db()


# ── Row HTML helpers ───────────────────────────────────────────────────────────

def exercise_row_html(row) -> str:
    return f"""
    <tr id="exercise-{row['id']}">
        <td class="p-2 border">{row['name']}</td>
        <td class="p-2 border text-gray-500">{row['muscle_group'] or '—'}</td>
        <td class="p-2 border text-center">
            <button hx-get="/exercises/{row['id']}/progress"
                    hx-target="#content" hx-swap="innerHTML"
                    class="text-purple-600 hover:underline text-xs">Progress</button>
            <button hx-get="/exercises/{row['id']}/edit"
                    hx-target="#exercise-{row['id']}" hx-swap="outerHTML"
                    class="text-blue-600 hover:underline text-xs ml-2">Edit</button>
            <button hx-delete="/exercises/{row['id']}"
                    hx-target="#exercise-{row['id']}" hx-swap="outerHTML"
                    hx-confirm="Delete this exercise?"
                    class="text-red-500 hover:underline text-xs ml-2">Delete</button>
        </td>
    </tr>
    """


def program_row_html(row) -> str:
    return f"""
    <tr id="program-{row['id']}">
        <td class="p-2 border">{row['name']}</td>
        <td class="p-2 border text-gray-500">{row['description'] or '—'}</td>
        <td class="p-2 border text-center">
            <button hx-get="/programs/{row['id']}"
                    hx-target="#content" hx-swap="innerHTML"
                    class="text-blue-600 hover:underline text-xs">View</button>
            <button hx-get="/programs/{row['id']}/edit"
                    hx-target="#program-{row['id']}" hx-swap="outerHTML"
                    class="text-blue-600 hover:underline text-xs ml-2">Edit</button>
            <button hx-delete="/programs/{row['id']}"
                    hx-target="#program-{row['id']}" hx-swap="outerHTML"
                    hx-confirm="Delete this program and all its templates?"
                    class="text-red-500 hover:underline text-xs ml-2">Delete</button>
        </td>
    </tr>
    """


def template_row_html(row) -> str:
    return f"""
    <tr id="template-{row['id']}">
        <td class="p-2 border">{row['name']}</td>
        <td class="p-2 border text-center">
            <button hx-get="/templates/{row['id']}"
                    hx-target="#content" hx-swap="innerHTML"
                    class="text-blue-600 hover:underline text-xs">View</button>
            <button hx-get="/templates/{row['id']}/edit"
                    hx-target="#template-{row['id']}" hx-swap="outerHTML"
                    class="text-blue-600 hover:underline text-xs ml-2">Edit</button>
            <button hx-delete="/templates/{row['id']}"
                    hx-target="#template-{row['id']}" hx-swap="outerHTML"
                    hx-confirm="Delete this template?"
                    class="text-red-500 hover:underline text-xs ml-2">Delete</button>
        </td>
    </tr>
    """


def template_exercise_row_html(row) -> str:
    return f"""
    <tr id="texercise-{row['id']}">
        <td class="p-2 border">{row['exercise_name']}</td>
        <td class="p-2 border text-center">{row['sets']}</td>
        <td class="p-2 border text-center">{row['reps']}</td>
        <td class="p-2 border text-center">
            <button hx-delete="/template-exercises/{row['id']}"
                    hx-target="#texercise-{row['id']}" hx-swap="outerHTML"
                    hx-confirm="Remove this exercise from the template?"
                    class="text-red-500 hover:underline text-xs">Remove</button>
        </td>
    </tr>
    """


def set_row_html(row) -> str:
    return f"""
    <tr id="set-{row['id']}">
        <td class="p-2 border">{row['exercise_name']}</td>
        <td class="p-2 border text-center">{row['sets']}</td>
        <td class="p-2 border text-center">{row['reps']}</td>
        <td class="p-2 border text-center">{row['weight']}</td>
        <td class="p-2 border text-center">
            <button hx-get="/sets/{row['id']}/edit"
                    hx-target="#set-{row['id']}" hx-swap="outerHTML"
                    class="text-blue-600 hover:underline text-xs">Edit</button>
            <button hx-delete="/sets/{row['id']}"
                    hx-target="#set-{row['id']}" hx-swap="outerHTML"
                    hx-confirm="Delete this set?"
                    class="text-red-500 hover:underline text-xs ml-2">Delete</button>
        </td>
    </tr>
    """


# ── Main page ──────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


# ── Exercises ──────────────────────────────────────────────────────────────────

@app.get("/exercises", response_class=HTMLResponse)
def get_exercises(request: Request):
    con = get_db()
    exercises = con.execute("SELECT * FROM exercise ORDER BY name").fetchall()
    con.close()
    return templates.TemplateResponse(
        "partials/exercises.html", {"request": request, "exercises": exercises}
    )


@app.post("/exercises", response_class=HTMLResponse)
def create_exercise(name: str = Form(...), muscle_group: str = Form("")):
    con = get_db()
    cur = con.execute(
        "INSERT INTO exercise (name, muscle_group) VALUES (?, ?)", (name, muscle_group)
    )
    con.commit()
    row = con.execute("SELECT * FROM exercise WHERE id = ?", (cur.lastrowid,)).fetchone()
    con.close()
    return exercise_row_html(row)


@app.get("/exercises/{exercise_id}/edit", response_class=HTMLResponse)
def edit_exercise_form(exercise_id: int):
    con = get_db()
    row = con.execute("SELECT * FROM exercise WHERE id = ?", (exercise_id,)).fetchone()
    con.close()
    return f"""
    <tr id="exercise-{row['id']}">
        <td colspan="3" class="p-2 border">
            <form hx-put="/exercises/{row['id']}"
                  hx-target="#exercise-{row['id']}" hx-swap="outerHTML"
                  class="flex gap-2 items-center">
                <input name="name" value="{row['name']}" required
                    class="border rounded px-2 py-1 text-sm flex-1" />
                <input name="muscle_group" value="{row['muscle_group'] or ''}" placeholder="Muscle group"
                    class="border rounded px-2 py-1 text-sm w-32" />
                <button type="submit" class="bg-blue-600 text-white px-3 py-1 rounded text-xs hover:bg-blue-700">Save</button>
                <button type="button" hx-get="/exercises/{row['id']}/cancel"
                    hx-target="#exercise-{row['id']}" hx-swap="outerHTML"
                    class="text-gray-500 hover:underline text-xs">Cancel</button>
            </form>
        </td>
    </tr>
    """


@app.get("/exercises/{exercise_id}/cancel", response_class=HTMLResponse)
def cancel_edit_exercise(exercise_id: int):
    con = get_db()
    row = con.execute("SELECT * FROM exercise WHERE id = ?", (exercise_id,)).fetchone()
    con.close()
    return exercise_row_html(row)


@app.put("/exercises/{exercise_id}", response_class=HTMLResponse)
def update_exercise(exercise_id: int, name: str = Form(...), muscle_group: str = Form("")):
    con = get_db()
    con.execute(
        "UPDATE exercise SET name = ?, muscle_group = ? WHERE id = ?",
        (name, muscle_group, exercise_id),
    )
    con.commit()
    row = con.execute("SELECT * FROM exercise WHERE id = ?", (exercise_id,)).fetchone()
    con.close()
    return exercise_row_html(row)


@app.delete("/exercises/{exercise_id}", response_class=HTMLResponse)
def delete_exercise(exercise_id: int):
    con = get_db()
    con.execute("DELETE FROM exercise WHERE id = ?", (exercise_id,))
    con.commit()
    con.close()
    return ""


@app.get("/exercises/{exercise_id}/progress", response_class=HTMLResponse)
def get_exercise_progress(request: Request, exercise_id: int):
    con = get_db()
    exercise = con.execute("SELECT * FROM exercise WHERE id = ?", (exercise_id,)).fetchone()
    rows = con.execute("""
        SELECT w.date, MAX(ws.weight) AS max_weight, SUM(ws.sets * ws.reps * ws.weight) AS volume
        FROM workout_set ws
        JOIN workout w ON ws.workout_id = w.id
        WHERE ws.exercise_id = ?
        GROUP BY w.id, w.date
        ORDER BY w.date ASC
    """, (exercise_id,)).fetchall()
    con.close()
    return templates.TemplateResponse(
        "partials/exercise_progress.html",
        {"request": request, "exercise": exercise, "rows": rows},
    )


# ── Programs ───────────────────────────────────────────────────────────────────

@app.get("/programs", response_class=HTMLResponse)
def get_programs(request: Request):
    con = get_db()
    programs = con.execute("SELECT * FROM program ORDER BY name").fetchall()
    con.close()
    return templates.TemplateResponse(
        "partials/programs.html", {"request": request, "programs": programs}
    )


@app.post("/programs", response_class=HTMLResponse)
def create_program(name: str = Form(...), description: str = Form("")):
    con = get_db()
    cur = con.execute(
        "INSERT INTO program (name, description) VALUES (?, ?)", (name, description)
    )
    con.commit()
    row = con.execute("SELECT * FROM program WHERE id = ?", (cur.lastrowid,)).fetchone()
    con.close()
    return program_row_html(row)


@app.get("/programs/{program_id}/edit", response_class=HTMLResponse)
def edit_program_form(program_id: int):
    con = get_db()
    row = con.execute("SELECT * FROM program WHERE id = ?", (program_id,)).fetchone()
    con.close()
    return f"""
    <tr id="program-{row['id']}">
        <td colspan="3" class="p-2 border">
            <form hx-put="/programs/{row['id']}"
                  hx-target="#program-{row['id']}" hx-swap="outerHTML"
                  class="flex gap-2 items-center">
                <input name="name" value="{row['name']}" required
                    class="border rounded px-2 py-1 text-sm flex-1" />
                <input name="description" value="{row['description'] or ''}" placeholder="Description"
                    class="border rounded px-2 py-1 text-sm flex-1" />
                <button type="submit" class="bg-blue-600 text-white px-3 py-1 rounded text-xs hover:bg-blue-700">Save</button>
                <button type="button" hx-get="/programs/{row['id']}/cancel"
                    hx-target="#program-{row['id']}" hx-swap="outerHTML"
                    class="text-gray-500 hover:underline text-xs">Cancel</button>
            </form>
        </td>
    </tr>
    """


@app.get("/programs/{program_id}/cancel", response_class=HTMLResponse)
def cancel_edit_program(program_id: int):
    con = get_db()
    row = con.execute("SELECT * FROM program WHERE id = ?", (program_id,)).fetchone()
    con.close()
    return program_row_html(row)


@app.put("/programs/{program_id}", response_class=HTMLResponse)
def update_program(program_id: int, name: str = Form(...), description: str = Form("")):
    con = get_db()
    con.execute(
        "UPDATE program SET name = ?, description = ? WHERE id = ?",
        (name, description, program_id),
    )
    con.commit()
    row = con.execute("SELECT * FROM program WHERE id = ?", (program_id,)).fetchone()
    con.close()
    return program_row_html(row)


@app.delete("/programs/{program_id}", response_class=HTMLResponse)
def delete_program(program_id: int):
    con = get_db()
    # Cascade: delete template exercises, then templates, then program
    template_ids = [
        r["id"] for r in con.execute(
            "SELECT id FROM workout_template WHERE program_id = ?", (program_id,)
        ).fetchall()
    ]
    for tid in template_ids:
        con.execute("DELETE FROM template_exercise WHERE template_id = ?", (tid,))
    con.execute("DELETE FROM workout_template WHERE program_id = ?", (program_id,))
    con.execute("DELETE FROM program WHERE id = ?", (program_id,))
    con.commit()
    con.close()
    return ""


@app.get("/programs/{program_id}", response_class=HTMLResponse)
def get_program_detail(request: Request, program_id: int):
    con = get_db()
    program = con.execute("SELECT * FROM program WHERE id = ?", (program_id,)).fetchone()
    tmplts = con.execute(
        "SELECT * FROM workout_template WHERE program_id = ? ORDER BY name", (program_id,)
    ).fetchall()
    con.close()
    return templates.TemplateResponse(
        "partials/program_detail.html",
        {"request": request, "program": program, "templates": tmplts},
    )


# ── Workout Templates ──────────────────────────────────────────────────────────

@app.post("/programs/{program_id}/templates", response_class=HTMLResponse)
def create_template(program_id: int, name: str = Form(...)):
    con = get_db()
    cur = con.execute(
        "INSERT INTO workout_template (program_id, name) VALUES (?, ?)", (program_id, name)
    )
    con.commit()
    row = con.execute("SELECT * FROM workout_template WHERE id = ?", (cur.lastrowid,)).fetchone()
    con.close()
    return template_row_html(row)


@app.get("/templates/{template_id}/edit", response_class=HTMLResponse)
def edit_template_form(template_id: int):
    con = get_db()
    row = con.execute("SELECT * FROM workout_template WHERE id = ?", (template_id,)).fetchone()
    con.close()
    return f"""
    <tr id="template-{row['id']}">
        <td colspan="2" class="p-2 border">
            <form hx-put="/templates/{row['id']}"
                  hx-target="#template-{row['id']}" hx-swap="outerHTML"
                  class="flex gap-2 items-center">
                <input name="name" value="{row['name']}" required
                    class="border rounded px-2 py-1 text-sm flex-1" />
                <button type="submit" class="bg-blue-600 text-white px-3 py-1 rounded text-xs hover:bg-blue-700">Save</button>
                <button type="button" hx-get="/templates/{row['id']}/cancel"
                    hx-target="#template-{row['id']}" hx-swap="outerHTML"
                    class="text-gray-500 hover:underline text-xs">Cancel</button>
            </form>
        </td>
    </tr>
    """


@app.get("/templates/{template_id}/cancel", response_class=HTMLResponse)
def cancel_edit_template(template_id: int):
    con = get_db()
    row = con.execute("SELECT * FROM workout_template WHERE id = ?", (template_id,)).fetchone()
    con.close()
    return template_row_html(row)


@app.put("/templates/{template_id}", response_class=HTMLResponse)
def update_template(template_id: int, name: str = Form(...)):
    con = get_db()
    con.execute("UPDATE workout_template SET name = ? WHERE id = ?", (name, template_id))
    con.commit()
    row = con.execute("SELECT * FROM workout_template WHERE id = ?", (template_id,)).fetchone()
    con.close()
    return template_row_html(row)


@app.delete("/templates/{template_id}", response_class=HTMLResponse)
def delete_template(template_id: int):
    con = get_db()
    con.execute("DELETE FROM template_exercise WHERE template_id = ?", (template_id,))
    con.execute("DELETE FROM workout_template WHERE id = ?", (template_id,))
    con.commit()
    con.close()
    return ""


@app.get("/templates/{template_id}", response_class=HTMLResponse)
def get_template_detail(request: Request, template_id: int):
    con = get_db()
    template = con.execute("""
        SELECT wt.*, p.name AS program_name, p.id AS program_id
        FROM workout_template wt
        JOIN program p ON wt.program_id = p.id
        WHERE wt.id = ?
    """, (template_id,)).fetchone()
    exercises = con.execute("SELECT * FROM exercise ORDER BY name").fetchall()
    texercises = con.execute("""
        SELECT te.*, e.name AS exercise_name
        FROM template_exercise te
        JOIN exercise e ON te.exercise_id = e.id
        WHERE te.template_id = ?
    """, (template_id,)).fetchall()
    con.close()
    return templates.TemplateResponse(
        "partials/template_detail.html",
        {
            "request": request,
            "template": template,
            "exercises": exercises,
            "texercises": texercises,
            "today": today_date.today().isoformat(),
        },
    )


# ── Template Exercises ─────────────────────────────────────────────────────────

@app.post("/templates/{template_id}/exercises", response_class=HTMLResponse)
def add_template_exercise(
    template_id: int,
    exercise_id: int = Form(...),
    sets: int = Form(...),
    reps: int = Form(...),
):
    con = get_db()
    cur = con.execute(
        "INSERT INTO template_exercise (template_id, exercise_id, sets, reps) VALUES (?, ?, ?, ?)",
        (template_id, exercise_id, sets, reps),
    )
    con.commit()
    row = con.execute("""
        SELECT te.*, e.name AS exercise_name
        FROM template_exercise te
        JOIN exercise e ON te.exercise_id = e.id
        WHERE te.id = ?
    """, (cur.lastrowid,)).fetchone()
    con.close()
    return template_exercise_row_html(row)


@app.delete("/template-exercises/{te_id}", response_class=HTMLResponse)
def delete_template_exercise(te_id: int):
    con = get_db()
    con.execute("DELETE FROM template_exercise WHERE id = ?", (te_id,))
    con.commit()
    con.close()
    return ""


# ── CSV Import ────────────────────────────────────────────────────────────────

@app.post("/import/csv", response_class=HTMLResponse)
async def import_csv(request: Request, file: UploadFile = File(...)):
    content = await file.read()
    text = content.decode("utf-8-sig")  # handle BOM from Excel exports
    reader = csv.DictReader(io.StringIO(text))

    con = get_db()
    by_date = defaultdict(list)
    for row in reader:
        by_date[row["date"].strip()].append(row)

    workouts_created = 0
    sets_created = 0
    exercises_created = 0

    for date, rows in sorted(by_date.items()):
        notes = next((r.get("notes", "").strip() for r in rows if r.get("notes", "").strip()), "")
        cur = con.execute("INSERT INTO workout (date, notes) VALUES (?, ?)", (date, notes))
        workout_id = cur.lastrowid
        workouts_created += 1

        for row in rows:
            name = row["exercise"].strip().replace("_", " ").title()
            exercise = con.execute(
                "SELECT id FROM exercise WHERE name = ? COLLATE NOCASE", (name,)
            ).fetchone()
            if not exercise:
                cur2 = con.execute("INSERT INTO exercise (name) VALUES (?)", (name,))
                exercise_id = cur2.lastrowid
                exercises_created += 1
            else:
                exercise_id = exercise["id"]

            con.execute(
                "INSERT INTO workout_set (workout_id, exercise_id, sets, reps, weight) VALUES (?, ?, ?, ?, ?)",
                (workout_id, exercise_id, int(row["sets"]), int(row["reps"]), float(row["weight_lbs"])),
            )
            sets_created += 1

    con.commit()
    con.close()

    return templates.TemplateResponse(
        "partials/import_result.html",
        {
            "request": request,
            "workouts_created": workouts_created,
            "sets_created": sets_created,
            "exercises_created": exercises_created,
        },
    )


# ── Workouts ───────────────────────────────────────────────────────────────────

@app.get("/workouts", response_class=HTMLResponse)
def get_workouts(request: Request):
    con = get_db()
    workouts = con.execute("""
        SELECT w.*, wt.name AS template_name, p.name AS program_name
        FROM workout w
        LEFT JOIN workout_template wt ON w.template_id = wt.id
        LEFT JOIN program p ON wt.program_id = p.id
        ORDER BY w.date DESC
    """).fetchall()
    workout_templates = con.execute("""
        SELECT wt.*, p.name AS program_name
        FROM workout_template wt
        JOIN program p ON wt.program_id = p.id
        ORDER BY p.name, wt.name
    """).fetchall()
    con.close()
    return templates.TemplateResponse(
        "partials/workouts.html",
        {
            "request": request,
            "workouts": workouts,
            "workout_templates": workout_templates,
            "today": today_date.today().isoformat(),
        },
    )


@app.post("/workouts", response_class=HTMLResponse)
def create_workout(
    request: Request,
    date: str = Form(...),
    template_id: str = Form(""),
    notes: str = Form(""),
):
    con = get_db()
    tid = int(template_id) if template_id else None
    cur = con.execute(
        "INSERT INTO workout (template_id, date, notes) VALUES (?, ?, ?)", (tid, date, notes)
    )
    workout_id = cur.lastrowid

    # Auto-populate sets from template
    if tid:
        texercises = con.execute(
            "SELECT * FROM template_exercise WHERE template_id = ?", (tid,)
        ).fetchall()
        for te in texercises:
            con.execute(
                "INSERT INTO workout_set (workout_id, exercise_id, sets, reps, weight) VALUES (?, ?, ?, ?, 0)",
                (workout_id, te["exercise_id"], te["sets"], te["reps"]),
            )

    con.commit()
    workout = con.execute("""
        SELECT w.*, wt.name AS template_name, p.name AS program_name
        FROM workout w
        LEFT JOIN workout_template wt ON w.template_id = wt.id
        LEFT JOIN program p ON wt.program_id = p.id
        WHERE w.id = ?
    """, (workout_id,)).fetchone()
    exercises = con.execute("SELECT * FROM exercise ORDER BY name").fetchall()
    sets = con.execute("""
        SELECT ws.*, e.name AS exercise_name
        FROM workout_set ws
        JOIN exercise e ON ws.exercise_id = e.id
        WHERE ws.workout_id = ?
    """, (workout_id,)).fetchall()
    con.close()
    return templates.TemplateResponse(
        "partials/workout_detail.html",
        {"request": request, "workout": workout, "exercises": exercises, "sets": sets},
    )


@app.get("/workouts/{workout_id}", response_class=HTMLResponse)
def get_workout_detail(request: Request, workout_id: int):
    con = get_db()
    workout = con.execute("""
        SELECT w.*, wt.name AS template_name, p.name AS program_name
        FROM workout w
        LEFT JOIN workout_template wt ON w.template_id = wt.id
        LEFT JOIN program p ON wt.program_id = p.id
        WHERE w.id = ?
    """, (workout_id,)).fetchone()
    exercises = con.execute("SELECT * FROM exercise ORDER BY name").fetchall()
    sets = con.execute("""
        SELECT ws.*, e.name AS exercise_name
        FROM workout_set ws
        JOIN exercise e ON ws.exercise_id = e.id
        WHERE ws.workout_id = ?
    """, (workout_id,)).fetchall()
    con.close()
    return templates.TemplateResponse(
        "partials/workout_detail.html",
        {"request": request, "workout": workout, "exercises": exercises, "sets": sets},
    )


@app.delete("/workouts/{workout_id}", response_class=HTMLResponse)
def delete_workout(workout_id: int):
    con = get_db()
    con.execute("DELETE FROM workout_set WHERE workout_id = ?", (workout_id,))
    con.execute("DELETE FROM workout WHERE id = ?", (workout_id,))
    con.commit()
    con.close()
    return ""


@app.post("/workouts/{workout_id}/duplicate", response_class=HTMLResponse)
def duplicate_workout(request: Request, workout_id: int):
    con = get_db()
    original = con.execute("SELECT * FROM workout WHERE id = ?", (workout_id,)).fetchone()
    cur = con.execute(
        "INSERT INTO workout (template_id, date, notes) VALUES (?, ?, ?)",
        (original["template_id"], today_date.today().isoformat(), original["notes"]),
    )
    new_id = cur.lastrowid
    sets = con.execute("SELECT * FROM workout_set WHERE workout_id = ?", (workout_id,)).fetchall()
    for s in sets:
        con.execute(
            "INSERT INTO workout_set (workout_id, exercise_id, sets, reps, weight) VALUES (?, ?, ?, ?, ?)",
            (new_id, s["exercise_id"], s["sets"], s["reps"], s["weight"]),
        )
    con.commit()
    workout = con.execute("""
        SELECT w.*, wt.name AS template_name, p.name AS program_name
        FROM workout w
        LEFT JOIN workout_template wt ON w.template_id = wt.id
        LEFT JOIN program p ON wt.program_id = p.id
        WHERE w.id = ?
    """, (new_id,)).fetchone()
    exercises = con.execute("SELECT * FROM exercise ORDER BY name").fetchall()
    new_sets = con.execute("""
        SELECT ws.*, e.name AS exercise_name
        FROM workout_set ws
        JOIN exercise e ON ws.exercise_id = e.id
        WHERE ws.workout_id = ?
    """, (new_id,)).fetchall()
    con.close()
    return templates.TemplateResponse(
        "partials/workout_detail.html",
        {"request": request, "workout": workout, "exercises": exercises, "sets": new_sets},
    )


# ── Workout Sets ───────────────────────────────────────────────────────────────

@app.post("/workouts/{workout_id}/sets", response_class=HTMLResponse)
def add_set(
    workout_id: int,
    exercise_id: int = Form(...),
    sets: int = Form(...),
    reps: int = Form(...),
    weight: float = Form(...),
):
    con = get_db()
    con.execute(
        "INSERT INTO workout_set (workout_id, exercise_id, sets, reps, weight) VALUES (?, ?, ?, ?, ?)",
        (workout_id, exercise_id, sets, reps, weight),
    )
    con.commit()
    row = con.execute("""
        SELECT ws.*, e.name AS exercise_name
        FROM workout_set ws
        JOIN exercise e ON ws.exercise_id = e.id
        WHERE ws.workout_id = ? ORDER BY ws.id DESC LIMIT 1
    """, (workout_id,)).fetchone()
    con.close()
    return set_row_html(row)


@app.delete("/sets/{set_id}", response_class=HTMLResponse)
def delete_set(set_id: int):
    con = get_db()
    con.execute("DELETE FROM workout_set WHERE id = ?", (set_id,))
    con.commit()
    con.close()
    return ""


@app.get("/sets/{set_id}/edit", response_class=HTMLResponse)
def edit_set_form(set_id: int):
    con = get_db()
    row = con.execute("""
        SELECT ws.*, e.name AS exercise_name
        FROM workout_set ws
        JOIN exercise e ON ws.exercise_id = e.id
        WHERE ws.id = ?
    """, (set_id,)).fetchone()
    exercises = con.execute("SELECT * FROM exercise ORDER BY name").fetchall()
    options = "".join(
        f'<option value="{e["id"]}" {"selected" if e["id"] == row["exercise_id"] else ""}>{e["name"]}</option>'
        for e in exercises
    )
    con.close()
    return f"""
    <tr id="set-{row['id']}">
        <td colspan="5" class="p-2 border">
            <form hx-put="/sets/{row['id']}"
                  hx-target="#set-{row['id']}" hx-swap="outerHTML"
                  class="flex gap-2 items-center flex-wrap">
                <select name="exercise_id" class="border rounded px-2 py-1 text-sm flex-1">{options}</select>
                <input name="sets" type="number" value="{row['sets']}" min="1" required
                    class="border rounded px-2 py-1 text-sm w-16" placeholder="Sets" />
                <input name="reps" type="number" value="{row['reps']}" min="1" required
                    class="border rounded px-2 py-1 text-sm w-16" placeholder="Reps" />
                <input name="weight" type="number" step="0.5" value="{row['weight']}" min="0" required
                    class="border rounded px-2 py-1 text-sm w-20" placeholder="lbs" />
                <button type="submit" class="bg-blue-600 text-white px-3 py-1 rounded text-xs hover:bg-blue-700">Save</button>
                <button type="button" hx-get="/sets/{row['id']}/cancel"
                    hx-target="#set-{row['id']}" hx-swap="outerHTML"
                    class="text-gray-500 hover:underline text-xs">Cancel</button>
            </form>
        </td>
    </tr>
    """


@app.get("/sets/{set_id}/cancel", response_class=HTMLResponse)
def cancel_edit_set(set_id: int):
    con = get_db()
    row = con.execute("""
        SELECT ws.*, e.name AS exercise_name
        FROM workout_set ws
        JOIN exercise e ON ws.exercise_id = e.id
        WHERE ws.id = ?
    """, (set_id,)).fetchone()
    con.close()
    return set_row_html(row)


@app.put("/sets/{set_id}", response_class=HTMLResponse)
def update_set(
    set_id: int,
    exercise_id: int = Form(...),
    sets: int = Form(...),
    reps: int = Form(...),
    weight: float = Form(...),
):
    con = get_db()
    con.execute(
        "UPDATE workout_set SET exercise_id = ?, sets = ?, reps = ?, weight = ? WHERE id = ?",
        (exercise_id, sets, reps, weight, set_id),
    )
    con.commit()
    row = con.execute("""
        SELECT ws.*, e.name AS exercise_name
        FROM workout_set ws
        JOIN exercise e ON ws.exercise_id = e.id
        WHERE ws.id = ?
    """, (set_id,)).fetchone()
    con.close()
    return set_row_html(row)
