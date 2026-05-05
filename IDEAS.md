# Ideas

## Morning post-run sync

- Usual run window: 08:00-08:40.
- Add a scheduler mode that runs Mi Fitness sync around 09:00 every day.
- After sync, refresh the "Ответ на сегодня" card when new or updated activity data is found.
- Keep the current hourly sync only if it is still useful for retries or manual data edits.

## Auto-load details for one new activity

- After sync, if exactly one new activity was added, immediately fetch and store its details.
- This should make the detail page chart ready without pressing "Загрузить" manually.
- If multiple activities were added, keep the current manual/bulk detail loading behavior to avoid long sync runs.

## Telegram integration

- Send a Telegram message after successful sync with the "Ответ на сегодня" recommendation.
- Send auth/sync error notifications, especially when Mi Fitness requires re-login or step-2 verification.
- Optional commands: trigger sync, refresh recommendation, show latest run summary.

## Evening readiness check for morning run

- Since runs usually happen in the morning, add an evening scheduler job that checks whether tomorrow morning is suitable for running.
- Reuse the latest activity data, recovery time, recent load, and "Ответ на сегодня" logic.
- If running is OK, send a Telegram notification like: "Завтра у тебя пробежка утром."
- If running is not OK, send a short rest/recovery explanation instead.

## Weekly running plan

- Generate a weekly running plan on Sunday evening.
- Use recent runs, recovery time, load trend, and current fitness trend to decide how many runs to schedule.
- Include suggested days and run types: easy run, longer run, rest day, or recovery-only day.
- Send the plan to Telegram and show it in the portal.

## Improve overload alerts

- Extend the existing `alerts-section` into a stronger overload prevention system.
- Use calendar-week load instead of simply comparing the last 7 runs with the previous 7 runs.
- Include recovery time, EF trend, and unusually high heart rate at a normal pace.
- Reuse the same overload reasons in "Ответ на сегодня" and Telegram notifications.
- Make alert thresholds configurable in settings.

## Monthly goal companion

- Add a monthly running goal that motivates instead of showing only a dry number.
- Show progress toward the goal, expected progress for today's date, and whether the current pace is ahead or behind.
- Explain what is needed to stay on track: for example, "ещё 3 пробежки по 4 км" or "достаточно двух лёгких пробежек".
- Keep the tone companion-like: supportive, concrete, and realistic, without pushing through overload warnings.
- Integrate with the dashboard, "Ответ на сегодня", weekly plan, and Telegram summaries.

## Weekly plan should account for monthly goal

- When monthly goals exist, use them as one input for the weekly running plan.
- If the runner is behind the monthly goal, suggest realistic catch-up volume without violating recovery or overload alerts.
- If the runner is ahead, allow a lighter week or more recovery-focused plan.
- Keep the weekly plan useful even before monthly goals are implemented.
