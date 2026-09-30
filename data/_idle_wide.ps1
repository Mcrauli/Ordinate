param([string]$tag, [string]$only)
$p = Start-Process -FilePath .venv/Scripts/python.exe -ArgumentList 'data/_rohbau_wide.py',$tag,"only=$only" -NoNewWindow -PassThru -RedirectStandardOutput "data/output/_wide_$tag.log" -RedirectStandardError "data/output/_wide_$tag.err"
$p.PriorityClass = 'Idle'; $p.WaitForExit()
