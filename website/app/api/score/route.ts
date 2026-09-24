import { getRawDb } from "../../../db";

const USERNAME = /^[A-Za-z]+[0-9]{3}$/;
const TOKEN = /^[A-Za-z0-9_-]{43}$/;
const RUBRIC = /^niceness-rubric-v[0-9]+$/;
const FIELDS = new Set(["username", "score", "prompt_count", "score_date", "rubric_version"]);

type ScoreUpload = {
  username: string;
  score: number;
  prompt_count: number;
  score_date: string;
  rubric_version: string;
};

function response(body: object, status: number) {
  return Response.json(body, { status, headers: { "Cache-Control": "no-store" } });
}

function bearerToken(request: Request): string | null {
  const authorization = request.headers.get("authorization") ?? "";
  const match = /^Bearer ([A-Za-z0-9_-]{43})$/.exec(authorization);
  return match && TOKEN.test(match[1]) ? match[1] : null;
}

async function tokenHash(token: string): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(token));
  return Array.from(new Uint8Array(digest), byte => byte.toString(16).padStart(2, "0")).join("");
}

function validUpload(value: unknown): value is ScoreUpload {
  if (!value || typeof value !== "object" || Array.isArray(value)) return false;
  const record = value as Record<string, unknown>;
  if (Object.keys(record).some(key => !FIELDS.has(key))) return false;
  return typeof record.username === "string" && record.username.length <= 40 && USERNAME.test(record.username)
    && Number.isInteger(record.score) && Number(record.score) >= 300 && Number(record.score) <= 850
    && Number.isInteger(record.prompt_count) && Number(record.prompt_count) >= 1 && Number(record.prompt_count) <= 1_000_000_000
    && typeof record.score_date === "string" && !Number.isNaN(Date.parse(record.score_date))
    && record.score_date.length <= 40 && record.score_date.endsWith("Z")
    && typeof record.rubric_version === "string" && RUBRIC.test(record.rubric_version);
}

export async function PUT(request: Request) {
  const token = bearerToken(request);
  if (!token) return response({ error: "Missing or invalid upload token" }, 401);

  let payload: unknown;
  try {
    payload = await request.json();
  } catch {
    return response({ error: "Invalid JSON" }, 400);
  }
  if (!validUpload(payload)) return response({ error: "Invalid score summary" }, 400);
  const upload = payload as ScoreUpload;
  const digest = await tokenHash(token);
  const now = new Date().toISOString();

  try {
    const db = getRawDb();
    const profile = await db.prepare(`
      INSERT INTO profiles (id, username, token_hash, score, prompt_count, score_date, rubric_version, updated_at)
      VALUES (?, ?, ?, ?, ?, ?, ?, ?)
      ON CONFLICT(token_hash) DO UPDATE SET
        username = excluded.username,
        score = excluded.score,
        prompt_count = excluded.prompt_count,
        score_date = excluded.score_date,
        rubric_version = excluded.rubric_version,
        updated_at = excluded.updated_at
      WHERE profiles.prompt_count <= excluded.prompt_count
      RETURNING id
    `).bind(crypto.randomUUID(), upload.username, digest, upload.score, upload.prompt_count,
      upload.score_date, upload.rubric_version, now).first<{ id: string }>();
    if (!profile) return response({ error: "Stale prompt count" }, 409);

    await db.prepare(`
      INSERT INTO score_snapshots (profile_id, score, prompt_count, recorded_at)
      VALUES (?, ?, ?, ?)
      ON CONFLICT(profile_id, prompt_count) DO UPDATE SET
        score = excluded.score,
        recorded_at = excluded.recorded_at
    `).bind(profile.id, upload.score, upload.prompt_count, now).run();
    return response({ username: upload.username, score: upload.score }, 200);
  } catch (error) {
    const message = error instanceof Error ? messageWithCause(error) : "";
    if (message.includes("UNIQUE constraint failed: profiles.username")) {
      return response({ error: "username_taken" }, 409);
    }
    console.error("Score upload failed", error);
    return response({ error: "Score storage is unavailable" }, 503);
  }
}

function messageWithCause(error: Error): string {
  return `${error.message} ${error.cause instanceof Error ? error.cause.message : ""}`;
}

export async function DELETE(request: Request) {
  const token = bearerToken(request);
  if (!token) return response({ error: "Missing or invalid upload token" }, 401);

  try {
    const db = getRawDb();
    const digest = await tokenHash(token);
    await db.batch([
      db.prepare("DELETE FROM score_snapshots WHERE profile_id IN (SELECT id FROM profiles WHERE token_hash = ?)").bind(digest),
      db.prepare("DELETE FROM profiles WHERE token_hash = ?").bind(digest),
    ]);
    return new Response(null, { status: 204, headers: { "Cache-Control": "no-store" } });
  } catch (error) {
    console.error("Unpublish failed", error);
    return response({ error: "Score storage is unavailable" }, 503);
  }
}
