CREATE TABLE `profiles` (
	`id` text PRIMARY KEY NOT NULL,
	`username` text NOT NULL,
	`token_hash` text NOT NULL,
	`score` integer NOT NULL,
	`prompt_count` integer NOT NULL,
	`score_date` text NOT NULL,
	`rubric_version` text NOT NULL,
	`updated_at` text NOT NULL
);
--> statement-breakpoint
CREATE UNIQUE INDEX `idx_profiles_username` ON `profiles` (`username`);--> statement-breakpoint
CREATE UNIQUE INDEX `idx_profiles_token_hash` ON `profiles` (`token_hash`);--> statement-breakpoint
CREATE INDEX `idx_profiles_score` ON `profiles` (`score`);--> statement-breakpoint
CREATE TABLE `score_snapshots` (
	`id` integer PRIMARY KEY AUTOINCREMENT NOT NULL,
	`profile_id` text NOT NULL,
	`score` integer NOT NULL,
	`prompt_count` integer NOT NULL,
	`recorded_at` text NOT NULL,
	FOREIGN KEY (`profile_id`) REFERENCES `profiles`(`id`) ON UPDATE no action ON DELETE cascade
);
--> statement-breakpoint
CREATE UNIQUE INDEX `idx_snapshots_profile_prompt_count` ON `score_snapshots` (`profile_id`,`prompt_count`);--> statement-breakpoint
CREATE INDEX `idx_snapshots_profile_id` ON `score_snapshots` (`profile_id`,`id`);