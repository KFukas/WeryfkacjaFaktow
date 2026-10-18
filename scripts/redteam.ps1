# Eval red-team (domyslnie model "latwowierny" = najgorszy przypadek). Parametr -Llm mock|gullible|anthropic. (ASCII)
param([string]$Llm = "gullible")
Set-Location (Join-Path $PSScriptRoot "..")
.\.venv\Scripts\python.exe -m redteam.eval_agent --llm $Llm
exit $LASTEXITCODE
