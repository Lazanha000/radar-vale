# Coleta pelo PC e envia ao GitHub: vários sites de câmaras bloqueiam a nuvem (erro 403) mas abrem daqui.
# Roda pela tarefa agendada RadarDoVale; o push dispara a publicação do painel online.
Set-Location $PSScriptRoot
git fetch -q origin
git checkout -q origin/main -- painel/noticias.js   # parte do que a nuvem já coletou
python coletor.py --dias 3
git add painel/noticias.js
git commit -q -m "Coleta pelo PC (fontes que bloqueiam a nuvem)"
git pull -q --rebase --autostash -X theirs origin main   # se a nuvem gravou no meio, vale a versão do PC (a nuvem recupera o resto na próxima coleta)
git push -q origin main
