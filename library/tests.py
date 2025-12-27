import datetime as dt
import re

from django.test import TestCase

from utils import commit_utils


class CommitUtilsTests(TestCase):
    def test_generate_commit_message_format_and_task(self) -> None:
        """Messages should follow Feature::Task::Task Description."""
        pattern = re.compile(r"^Feature::([A-Za-z]+)::(.+)$")
        seen_tasks: set[str] = set()

        for _ in range(50):
            msg = commit_utils.generate_commit_message()
            match = pattern.match(msg)
            self.assertIsNotNone(match, msg)
            if match:
                task_label, description = match.groups()
                seen_tasks.add(task_label)
                self.assertIn(task_label, {t.value for t in commit_utils.TaskType})
                self.assertGreater(len(description.strip()), 0)
                self.assertLessEqual(len(description), 72)

        # Sanity check that we are not always generating the same TaskType.
        self.assertGreater(len(seen_tasks), 1)

    def test_generate_commit_message_for_specific_task(self) -> None:
        """Explicit TaskType should constrain the prefix."""
        msg = commit_utils.generate_commit_message(commit_utils.TaskType.TEST)
        self.assertTrue(msg.startswith("Feature::Test::"))

    def test_generate_commit_timestamps_within_range_and_ordered(self) -> None:
        """Generated timestamps should be in UTC, ordered, and within range."""
        start = dt.date(2023, 10, 1)
        end = dt.date(2023, 10, 15)
        timestamps = commit_utils.generate_commit_timestamps(
            start, end, commit_count=20, skip_weekends=True, seed=123
        )

        self.assertEqual(len(timestamps), 20)
        self.assertEqual(sorted(timestamps), timestamps)

        for ts in timestamps:
            self.assertIsNotNone(ts.tzinfo)
            self.assertEqual(ts.tzinfo, dt.timezone.utc)
            self.assertGreaterEqual(ts.date(), start)
            self.assertLessEqual(ts.date(), end)
            # Ensure we skipped Saturday (5) and Sunday (6)
            self.assertLess(ts.weekday(), 5)

    def test_build_git_date_env_sets_author_and_committer(self) -> None:
        """Environment mapping must contain matching author and committer dates."""
        ts = dt.datetime(2023, 10, 3, 10, 30, 0, tzinfo=dt.timezone.utc)
        base_env = {"EXISTING_VAR": "keep-me"}

        env = commit_utils.build_git_date_env(ts, base_env)

        expected = "2023-10-03T10:30:00Z"
        self.assertEqual(env["GIT_AUTHOR_DATE"], expected)
        self.assertEqual(env["GIT_COMMITTER_DATE"], expected)
        self.assertEqual(env["EXISTING_VAR"], "keep-me")

