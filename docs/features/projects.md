# Projects

Projects are Tank's first-class compartmentalisation unit. Every document, conversation,
threat model, design review, postmortem, report, and tabletop belongs to exactly one
project. This lets you run Tank across multiple teams, products, or short-term engagements
without data bleeding across contexts.

---

## What a project is

| Field | Purpose |
|---|---|
| **Name** | Display name shown in the dashboard and top-nav switcher |
| **Emoji / icon** | Single emoji used as the visual icon in cards and the nav |
| **Color** | Hex accent color used for the card's left bar and header strip |
| **Description** | Optional short description shown on the card |
| **Notes** | Free-form text included in Claude's system prompt for project-scoped chat |

Color and emoji always have defaults (`#6366f1` indigo, `🔐`) — a project is never
rendered without them.

---

## The projects dashboard (`/projects`)

A CSS Grid card layout. Each card shows:

- **Color accent bar** (left edge, 5px, project color)
- **Emoji icon** + **Active badge** (if this project is currently active)
- **Name** + **Description**
- **Actions**: Open → / Switch to / Delete

The card for the project you last opened is sorted to the top of the grid (`tank_last_opened_project`
in `localStorage`). Opening any card updates this key.

---

## Project detail page (`/projects/{id}`)

Accessed via "Open →" from the dashboard. Never navigated to by an in-page switcher — you
always go through the dashboard to change projects.

### Sections

**Header**: 6px color bar across the top, then emoji + name + "Edit" button.

**Notes block**: shown only when the project's notes field is non-empty. Contains the
free-form text you've added. Use this for:
- Scope boundaries ("only the payments cluster, not auth")
- Priorities ("focus on supply-chain risk this quarter")
- Team contacts ("ping @alice for IAM questions")
- Constraints ("all AWS, no GCP")

**Metrics**: document count, conversation count, report count — all scoped to this
project.

**Recent documents** (up to 5): the most recently ingested documents belonging to this
project.

**Recent conversations** (up to 5): the most recently active conversations belonging to
this project. Each is a link to `/chat?conv={id}`.

### Inline editing

Click "Edit" to expand an edit form in-place:
- **Icon**: single emoji input (maxlength 2)
- **Color**: native browser `<input type="color">` — no extra dependencies
- **Name**, **Description**, **Notes**

Saving PATCHes `/api/projects/{id}` and updates the DOM without a full page reload.
The notes block appears or disappears dynamically based on whether the saved notes are
non-empty.

---

## Project-scoped chat

When you start a conversation from within the `/chat` page with an active project,
that conversation is associated with the project's `project_id`. Tank automatically
injects the project's notes into the Claude system prompt as a `## Project Context`
block — so every reply in that conversation is aware of your project-specific priorities
and constraints without you having to repeat them.

The **global side panel** (the persistent panel on every page) creates conversations
with no `project_id`. It intentionally never injects project notes — it's designed as
a lightweight, context-free tool you can use from any page without switching projects.

### Prompt cache behavior

Project notes are appended to the system block, which is the first prompt-cache
breakpoint. Editing project notes invalidates the cache for that project's conversations.
In practice, notes are stable enough that this is rarely a concern.

---

## Active project and data assignment

The **active project** (set via "Switch to" or the top-nav dropdown) determines where
new data lands:

- Ingested documents → assigned to the active project
- New conversations → assigned to the active project
- Generated reports → assigned to the active project

The active project ID is stored in the `app_state` table and persists across restarts.
On startup, Tank validates the stored ID against the DB and resets to `default` if the
project was deleted.

---

## Default project

Every Tank instance has a built-in **Default** project (id = `"default"`) that cannot
be deleted. It acts as a catch-all:

- On first run, all pre-existing data (from before the projects feature) is automatically
  assigned here.
- When you delete a non-default project, its documents and conversations are moved to
  Default (not deleted).
- The Default project gets the standard color and emoji defaults.

---

## API reference

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/projects` | Dashboard page |
| `GET` | `/projects/{id}` | Detail page |
| `GET` | `/api/projects` | JSON list of all projects + active_id |
| `POST` | `/api/projects` | Create project (`name`, `emoji`, `color`, `description`, `notes`) |
| `PATCH` | `/api/projects/{id}` | Update any project field |
| `POST` | `/api/projects/{id}/activate` | Set active project |
| `DELETE` | `/api/projects/{id}` | Delete project (moves data to default) |
