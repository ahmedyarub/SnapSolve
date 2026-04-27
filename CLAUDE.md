# Verification Loop
Before declaring a task complete, you MUST verify the code against the static analyzers.

- If you are operating in a WSL/Linux terminal, run: `./scripts/verify.sh`
- If you are operating in a Windows terminal, run: `pwsh .\scripts\verify.ps1`

If the script returns a non-zero exit code, you must read the terminal error output, fix the unused variables/imports or formatting issues, and run the script again until it passes. Do not commit or declare completion until the script outputs success.