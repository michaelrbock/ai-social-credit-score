import { getRawDb } from "../../../db";

type ProfileRow = {
  id: string;
  username: string;
  score: number;
  prompt_count: number;
  score_date: string;
  updated_at: string;
};

type SnapshotRow = {
  profile_id: string;
  score: number;
  recorded_at: string;
};

export async function GET() {
  try {
    const db = getRawDb();
    const profiles = (await db.prepare(`
      SELECT id, username, score, prompt_count, score_date, updated_at
      FROM profiles ORDER BY score DESC, updated_at ASC LIMIT 100
    `).all<ProfileRow>()).results;
    const snapshots = (await db.prepare(`
      WITH top_profiles AS (
        SELECT id FROM profiles ORDER BY score DESC, updated_at ASC LIMIT 100
      ), ranked AS (
        SELECT score_snapshots.profile_id, score_snapshots.score, score_snapshots.recorded_at,
          ROW_NUMBER() OVER (PARTITION BY score_snapshots.profile_id ORDER BY score_snapshots.id DESC) AS rank
        FROM score_snapshots JOIN top_profiles ON top_profiles.id = score_snapshots.profile_id
      )
      SELECT profile_id, score, recorded_at FROM ranked WHERE rank <= 7
      ORDER BY profile_id, recorded_at ASC
    `).all<SnapshotRow>()).results;
    const history = new Map<string, { score: number; recordedAt: string }[]>();
    for (const snapshot of snapshots) {
      const entries = history.get(snapshot.profile_id) ?? [];
      entries.push({ score: snapshot.score, recordedAt: snapshot.recorded_at });
      history.set(snapshot.profile_id, entries);
    }
    return Response.json({
      profiles: profiles.map(profile => ({
        username: profile.username,
        score: profile.score,
        promptsScored: profile.prompt_count,
        scoreDate: profile.score_date,
        updatedAt: profile.updated_at,
        history: history.get(profile.id) ?? [],
      })),
    }, { headers: { "Cache-Control": "no-store" } });
  } catch (error) {
    console.error("Leaderboard read failed", error);
    return Response.json({ error: "Leaderboard is unavailable" }, { status: 503 });
  }
}
