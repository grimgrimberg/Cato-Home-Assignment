# Deployment Notes

## Local Run
```
py -3 -m daily_movers run --mode movers --region us --top 20 --out runs/<date>
```

## Scheduled Run (Windows Task Scheduler)
1. Create a new task.
2. Action: start a program.
3. Program: `py`
4. Arguments: `-3 -m daily_movers run --mode movers --region us --top 20 --out runs/%DATE% --no-open`
5. Set environment variables in the task or via a `.env` file in the repo.

## Email Delivery
- For demo use, Ethereal SMTP is recommended.
- `digest.eml` is always written even if SMTP is not configured.

## Artifacts and Persistence
Outputs are written to `runs/<date>` (or the `--out` directory).
Ensure the output directory is persisted if running in CI or scheduled jobs.
