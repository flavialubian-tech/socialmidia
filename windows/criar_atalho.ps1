# Cria o atalho "Social Mídia" na Área de Trabalho (funciona também com a Área de Trabalho no OneDrive).
$raiz = Split-Path -Parent $PSScriptRoot
$desktop = [Environment]::GetFolderPath("Desktop")
$destino = Join-Path $desktop "Social Mídia.lnk"

$shell = New-Object -ComObject WScript.Shell
$atalho = $shell.CreateShortcut($destino)
$atalho.TargetPath = Join-Path $raiz "Iniciar Social Midia.bat"
$atalho.WorkingDirectory = $raiz
$atalho.IconLocation = (Join-Path $raiz "assets\icone.ico") + ",0"
$atalho.WindowStyle = 7  # abre a janela de controle já minimizada
$atalho.Description = "Abrir o Social Mídia Autônoma"
$atalho.Save()

Write-Host ""
Write-Host "  Pronto! O atalho 'Social Mídia' está na sua Área de Trabalho." -ForegroundColor Green
Write-Host "  Dica: clique com o botão direito nele > 'Fixar na barra de tarefas'."
Write-Host ""
