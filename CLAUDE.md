# Verification Loop

Before declaring a task complete, you MUST verify the code against the static analyzers.

- If you are operating in a WSL/Linux terminal, run: `./scripts/verify.sh`
- If you are operating in a Windows terminal, run: `pwsh -File scripts/verify.ps1`

If the script returns a non-zero exit code, you must read the terminal error output, fix the unused variables/imports or
formatting issues, and run the script again until it passes. Do not commit or declare completion until the script
outputs success.

When done with any task, run the following PowerShell commannd to notify me that the task is done:
`New-BurntToastNotification -Text 'Claude Code', 'I am done with the loop!'`
Don't run it in bash.
Always use front-slashes when running commands.
For example: instead of `ruff format core\output.py`, use `ruff format core/output.py`.