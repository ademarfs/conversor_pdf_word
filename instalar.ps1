#Requires -Version 5.1
<#
.SYNOPSIS
    Instala o Conversor PDF -> Word nesta maquina.

.DESCRIPTION
    1. Localiza o Python 3.10+ (instala o 3.12 via winget, se faltar).
    2. Cria o ambiente virtual .venv e instala as dependencias (requirements.txt).
    3. Verifica o ambiente (Microsoft Word, fontes).
    4. Cria o atalho "Conversor PDF para Word" na area de trabalho.
    5. Inicia o conversor.

    Pode ser executado de novo a qualquer momento (atualiza as dependencias).
    Chamado por instalar.bat; nao precisa de administrador.
#>
param(
    [switch]$NaoIniciar   # so instala, sem abrir o conversor no final
)

$ErrorActionPreference = 'Stop'
$Raiz = $PSScriptRoot
$VersaoMinima = [Version]'3.10'
$Venv = Join-Path $Raiz '.venv'
$PythonVenv = Join-Path $Venv 'Scripts\python.exe'

function Escrever-Etapa([string]$Texto) {
    Write-Host ''
    Write-Host "==> $Texto" -ForegroundColor Cyan
}

function Testar-Python([string]$Exe, [string[]]$Argumentos) {
    # Retorna $true se o executavel for um Python >= versao minima.
    try {
        $versao = & $Exe @Argumentos -c "import sys; print('%d.%d' % sys.version_info[:2])" 2>$null
        return ($LASTEXITCODE -eq 0) -and $versao -and ([Version]$versao -ge $VersaoMinima)
    } catch {
        return $false
    }
}

function Encontrar-Python {
    $candidatos = @(
        @{ Exe = 'py';     Argumentos = @('-3') },
        @{ Exe = 'python'; Argumentos = @() }
    )
    # Instalacoes por usuario (winget/python.org) que ainda nao estao no PATH desta janela
    $locais = Get-ChildItem "$env:LOCALAPPDATA\Programs\Python\Python3*\python.exe" -ErrorAction SilentlyContinue |
              Sort-Object FullName -Descending
    foreach ($local in $locais) { $candidatos += @{ Exe = $local.FullName; Argumentos = @() } }

    foreach ($c in $candidatos) {
        if ((Get-Command $c.Exe -ErrorAction SilentlyContinue) -and (Testar-Python $c.Exe $c.Argumentos)) {
            return $c
        }
    }
    return $null
}

function Instalar-Python {
    if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
        throw "Python $VersaoMinima+ nao encontrado e o winget nao esta disponivel. Instale o Python em https://www.python.org/downloads/ (marque 'Add python.exe to PATH') e execute instalar.bat novamente."
    }
    Escrever-Etapa 'Instalando Python 3.12 (winget)'
    winget install --id Python.Python.3.12 --exact --scope user --silent `
        --accept-package-agreements --accept-source-agreements
    $env:Path = [Environment]::GetEnvironmentVariable('Path', 'Machine') + ';' +
                [Environment]::GetEnvironmentVariable('Path', 'User')
}

function Verificar-Saida([string]$Mensagem) {
    if ($LASTEXITCODE -ne 0) { throw $Mensagem }
}

# ------------------------------------------------------------------------------

Set-Location $Raiz
Write-Host 'Conversor PDF -> Word - instalacao' -ForegroundColor Green

Escrever-Etapa "Procurando Python $VersaoMinima ou superior"
$python = Encontrar-Python
if (-not $python) {
    Instalar-Python
    $python = Encontrar-Python
    if (-not $python) { throw 'Python instalado, mas nao localizado. Feche esta janela e execute instalar.bat de novo.' }
}
Write-Host "Usando: $($python.Exe) $($python.Argumentos -join ' ')"

Escrever-Etapa 'Criando o ambiente virtual (.venv)'
if (-not (Test-Path $PythonVenv)) {
    & $python.Exe @($python.Argumentos) -m venv $Venv
    Verificar-Saida 'Falha ao criar o ambiente virtual.'
} else {
    Write-Host 'Ambiente ja existe; sera atualizado.'
}

Escrever-Etapa 'Instalando dependencias'
& $PythonVenv -m pip install --upgrade pip --disable-pip-version-check --quiet
Verificar-Saida 'Falha ao atualizar o pip (verifique a internet ou o proxy).'
& $PythonVenv -m pip install -r (Join-Path $Raiz 'requirements.txt') --disable-pip-version-check --quiet
Verificar-Saida 'Falha ao instalar as dependencias (verifique a internet ou o proxy).'

Escrever-Etapa 'Verificando o ambiente'
$env:PYTHONIOENCODING = 'utf-8'
& $PythonVenv -m conversor --diagnostico
Verificar-Saida 'O diagnostico falhou.'

Escrever-Etapa 'Criando atalho na area de trabalho'
$areaDeTrabalho = [Environment]::GetFolderPath('Desktop')
$shell = New-Object -ComObject WScript.Shell
$atalho = $shell.CreateShortcut((Join-Path $areaDeTrabalho 'Conversor PDF para Word.lnk'))
$atalho.TargetPath = Join-Path $Raiz 'iniciar.bat'
$atalho.WorkingDirectory = $Raiz
$atalho.Description = 'Converte PDF em Word identico ao original'
$atalho.IconLocation = "$env:SystemRoot\System32\imageres.dll,2"
$atalho.Save()
Write-Host 'Atalho "Conversor PDF para Word" criado.'

Write-Host ''
Write-Host 'Instalacao concluida.' -ForegroundColor Green
if (-not $NaoIniciar) {
    Start-Process -FilePath (Join-Path $Raiz 'iniciar.bat') -WorkingDirectory $Raiz
}
