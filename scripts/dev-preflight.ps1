param(
    [string]$ExampleDir = "examples/langgraph_demo_agent"
)

Write-Host "Running AgentScope Dev Preflight Checks..." -ForegroundColor Cyan

# 1. Check Docker Desktop
Write-Host "1. Checking Docker... " -NoNewline
try {
    $dockerInfo = docker info 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Host "FAILED" -ForegroundColor Red
        Write-Host "Error: Docker Desktop is not running or not reachable."
        Write-Host "Please start Docker Desktop and try again."
        exit 1
    }
    Write-Host "OK" -ForegroundColor Green
} catch {
    Write-Host "FAILED" -ForegroundColor Red
    Write-Host "Error: Docker command not found. Please install Docker."
    exit 1
}

# 2. Check Port 8000
Write-Host "2. Checking port 8000... " -NoNewline
$portListeners = netstat -ano | Select-String "LISTENING" | Select-String ":8000"
if ($portListeners) {
    Write-Host "CONFLICT" -ForegroundColor Yellow
    foreach ($listener in $portListeners) {
        # Extract PID (last column)
        $parts = $listener.Line.Trim() -split '\s+'
        $pidNum = $parts[-1]
        
        try {
            $process = Get-Process -Id $pidNum -ErrorAction SilentlyContinue
            if ($process) {
                Write-Host "Found process $($process.Name) (PID: $pidNum) listening on port 8000." -ForegroundColor Yellow
                $response = Read-Host "Kill this process? (y/n)"
                if ($response -eq 'y') {
                    Stop-Process -Id $pidNum -Force
                    Write-Host "Killed process $pidNum." -ForegroundColor Green
                } else {
                    Write-Host "Port 8000 is still in use. Backend startup may fail." -ForegroundColor Red
                }
            }
        } catch {
            Write-Host "Could not identify process for PID $pidNum."
        }
    }
} else {
    Write-Host "OK (Free)" -ForegroundColor Green
}

# 3. Check Python Dependencies
Write-Host "3. Checking Python dependencies for $ExampleDir... " -NoNewline
$reqFile = "$ExampleDir/requirements.txt"
if (Test-Path $reqFile) {
    # Check if packages can be imported
    $missing = $false
    foreach ($line in Get-Content $reqFile) {
        if ($line.Trim() -eq '' -or $line.StartsWith('#')) { continue }
        $pkg = $line.Split('>')[0].Split('=')[0].Trim()
        
        # Mapping package names to import names
        $importName = $pkg
        if ($pkg -eq "langchain-core") { $importName = "langchain_core" }
        
        try {
            $null = python -c "import $importName" 2>&1
            if ($LASTEXITCODE -ne 0) {
                $missing = $true
                Write-Host "`n  Missing: $pkg" -ForegroundColor Red
            }
        } catch {
            $missing = $true
        }
    }
    
    if ($missing) {
        Write-Host "FAILED" -ForegroundColor Red
        Write-Host "Please run: pip install -r $reqFile"
        exit 1
    } else {
        Write-Host "OK" -ForegroundColor Green
    }
} else {
    Write-Host "SKIPPED (No requirements.txt found)" -ForegroundColor Yellow
}

Write-Host "Preflight complete! You are ready to run the demo." -ForegroundColor Green
