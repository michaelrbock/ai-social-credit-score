import { integer, sqliteTable, text, uniqueIndex, index } from "drizzle-orm/sqlite-core";

export const profiles = sqliteTable("profiles", {
  id: text("id").primaryKey(),
  username: text("username").notNull(),
  tokenHash: text("token_hash").notNull(),
  score: integer("score").notNull(),
  promptCount: integer("prompt_count").notNull(),
  scoreDate: text("score_date").notNull(),
  rubricVersion: text("rubric_version").notNull(),
  updatedAt: text("updated_at").notNull(),
}, (table) => [
  uniqueIndex("idx_profiles_username").on(table.username),
  uniqueIndex("idx_profiles_token_hash").on(table.tokenHash),
  index("idx_profiles_score").on(table.score),
]);

export const scoreSnapshots = sqliteTable("score_snapshots", {
  id: integer("id").primaryKey({ autoIncrement: true }),
  profileId: text("profile_id").notNull().references(() => profiles.id, { onDelete: "cascade" }),
  score: integer("score").notNull(),
  promptCount: integer("prompt_count").notNull(),
  recordedAt: text("recorded_at").notNull(),
}, (table) => [
  uniqueIndex("idx_snapshots_profile_prompt_count").on(table.profileId, table.promptCount),
  index("idx_snapshots_profile_id").on(table.profileId, table.id),
]);
