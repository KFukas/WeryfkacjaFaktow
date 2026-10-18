# Eval red-team offline (model „łatwowierny” = najgorszy przypadek). Argument -Llm mock|gullible|anthropic.
param([string]$Llm = "gullible")
Set-Location (Join-Path $PSScriptRoot "..")
.\.venv\Scripts\python.exe -m redteam.eval_agent --llm $Llm
