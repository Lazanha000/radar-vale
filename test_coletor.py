"""Checagem rápida da lógica que decide o que entra no painel: python test_coletor.py"""
import coletor as c

P = c.padroes(["Datas", "Jacinto", "Santo Antônio do Jacinto", "Jequitinhonha", "Diamantina", "Araçuaí", "Medina"])

# nome comum só vale com contexto de MG
assert c.marcar("Veja as datas do concurso", P) == []
assert c.marcar("Prefeitura de Datas abre vagas", P) == ["Datas"]
# nome longo não vira também o curto
assert c.marcar("Obra em Santo Antônio do Jacinto, MG", P) == ["Santo Antônio do Jacinto"]
# região e rio não são a cidade; a cidade é
assert c.marcar("Seca no Vale do Jequitinhonha", P) == []
assert c.marcar("Seca no Vale do Jequitinhonha", P, regiao=True) == [c.REGIAO]
assert c.marcar("Câmara de Jequitinhonha aprova projeto", P) == ["Jequitinhonha"]
assert c.marcar("Turismo na Chapada Diamantina", P) == []
# acento e caixa não importam; fonte própria é confiável mesmo sem contexto
assert c.marcar("ARAÇUAÍ recebe feira", P) == ["Araçuaí"]
assert c.marcar("Edital de concurso", P, "Medina", confiavel=True) == ["Medina"]
assert c.marcar("Edital de concurso", P, "Medina") == []
assert c.marcar("Concurso EMATER MG: 120 vagas", P, "Datas") == []
assert c.marcar("Lula ganha em Jacinto (MG)", P, "Jacinto") == ["Jacinto"]

RSS = """<rss><channel><item><title>Câmara aprova lei - Fonte X</title><link>https://a.b/1</link>
<pubDate>Mon, 02 Nov 2026 01:30:01 GMT</pubDate><source>Fonte X</source></item></channel></rss>"""
b = c.parse_feed(RSS)[0]
assert b["d"] == "2026-11-02T01:30:01Z" and b["f"] == "Fonte X"
i = c.monta(b, "x", "imprensa", P, "Araçuaí")
assert i["t"] == "Câmara aprova lei" and i["a"] and i["m"] == ["Araçuaí"]
try:
    c.parse_feed("<html><body>oi</body></html>")
    raise SystemExit("página HTML não podia virar feed")
except ValueError:
    pass

# imprensa: mesmo título vira um item só, com cidades somadas e o link direto no lugar do Google
a = {"t": "Chuva forte", "u": "https://news.google.com/x", "d": "2026-01-02T00:00:00Z", "m": ["Medina"], "k": "imprensa", "r": "", "a": False, "f": "G"}
b2 = dict(a, u="https://site/1", m=["Datas"], d="2026-01-03T00:00:00Z", f="Site")
j = list(c.juntar([a, b2]).values())
assert len(j) == 1 and j[0]["m"] == ["Datas", "Medina"] and j[0]["u"] == "https://site/1" and j[0]["d"].startswith("2026-01-02")
# site próprio: mesmo título na mesma cidade junta; em cidades diferentes fica separado
p1 = dict(a, k="prefeitura", o="Medina")
assert len(c.juntar([p1, dict(p1, u="u2")])) == 1
assert len(c.juntar([p1, dict(p1, o="Datas")])) == 2
# página institucional (mesmo título em 3+ sites) sai; em 2 fica
fixa = [dict(p1, t="Portal da Transparência", o=o) for o in ("A", "B", "C")]
assert c.sem_paginas_fixas(fixa) == [] and len(c.sem_paginas_fixas(fixa[:2])) == 2
# eleição: resultado por cidade sim; notícia política e da câmara não
E = lambda s: bool(c.ELEICAO.search(c.norm(s)))
assert E("336ª zona eleitoral de Turmalina (MG): votos por local de votação no 2º turno")
assert E("Em Leme do Prado (MG), Lula vence com 69,49% dos votos")
assert E("Lula vence a eleição presidencial em Comercinho (MG)")
assert not E("Lula deve voltar a Minas na próxima semana e mira Vale do Jequitinhonha")
assert not E("Cidades do Vale lideram ranking de abstenção")
assert c.NORMA_APROVADA.match(c.norm("Lei Ordinária-PMI nº 3.128")) and not c.NORMA_APROVADA.match(c.norm("Portaria-CMA nº 39"))
assert c.NORMA_APROVADA.match(c.norm("Decreto Legislativo nº 2")) and not c.NORMA_APROVADA.match(c.norm("Decreto nº 5"))
# sitemap: só página de notícia, não a listagem nem páginas institucionais
assert c.NOTICIA_URL.search("https://x.mg.gov.br/noticia/detalhe/1713")
assert c.NOTICIA_URL.search("https://x.mg.gov.br/noticias/campeonato-2026")
assert not c.NOTICIA_URL.search("https://x.mg.gov.br/noticia") and not c.NOTICIA_URL.search("https://x.mg.gov.br/noticias")
assert not c.NOTICIA_URL.search("https://x.mg.gov.br/licitacoes")
assert c.meta('<meta property="og:title" content="A &amp; B - Prefeitura de X">', "og:title") == "A & B - Prefeitura de X"
# aba Câmaras
L = lambda t, k="camara", a=False, e=False: c.legislativo({"t": t, "k": k, "a": a, "e": e})
assert L("Câmara aprova LDO 2027", a=True) == "aprovado"
assert L("Projeto de Lei nº 047-2026") == "projeto" and L("REUNIÃO ORDINÁRIA, DIA 31 DE OUTUBRO") == "sessao"
assert L("3º REUNIÃO EXTRA- ORDINÁRIA") == "sessao" and L("DIA DOS PAIS - 2026") == "outro"
assert L("Portaria-CMA nº 39: posse de servidor", "lei") == "norma"
assert L("Vereador defende democracia em Capelinha", "imprensa") == "outro" and L("Chuva em Almenara", "imprensa") is None
assert L("CÂMARA Municipal, 213ª zona eleitoral", "imprensa", e=True) is None
assert L("Prefeito sanciona lei do piso", "prefeitura", a=True) == "aprovado" and L("Vacinação", "prefeitura") is None
# leis do modelo /legislacoes/get/todas: data do arquivo, aprovação pelo tipo
J = {"data": [{"id": 445, "ano": "2026", "titulo": "Lei", "identificacao": "1876/2026", "ementa": "Revisão geral",
               "arquivo": {"created_at": "2026-08-14T00:23:13.000000Z"}},
              {"id": 9, "ano": "2025", "titulo": "Portaria", "identificacao": "3/2025", "ementa": "Nomeia", "arquivo": None}]}
(l1, a1), (l2, a2) = c.ler_leis(J, "h")
assert l1["t"] == "Lei nº 1876/2026: Revisão geral" and l1["u"] == "https://h/legislacoes/445" and l1["d"] == "2026-08-14T00:23:13Z" and a1
assert l2["d"] == "2025-01-01T00:00:00Z" and not a2
assert c.NORMA_APROVADA.match(c.norm("Proposição de Lei")) and not c.NORMA_APROVADA.match(c.norm("Projeto de Lei"))
# proposições do modelo pr-item: situação vira aprovação
HTML = """<article class="pr-item"><span class="pr-item-tipo">Projeto de Lei</span>
<a class="pr-item-num" href="https://h/legislativo/proposicao/abc">Nº 024-2026</a>
<h3 class="pr-item-ementa"><a href="x">FIXA A DESPESA</a></h3><span class="pr-item-autor"><i></i> Poder Executivo </span>
<span>Protocolo em 02/10/2026 &middot; nº 552</span><span class="lg-badge lg-badge-neu">Aprovada</span></article>"""
(p, ap), = c.ler_proposicoes(HTML)
assert p["t"] == "Projeto de Lei Nº 024-2026: FIXA A DESPESA" and p["d"] == "2026-10-02T12:00:00Z" and ap
assert p["r"] == "Situação: Aprovada · Autor: Poder Executivo" and p["u"] == "https://h/legislativo/proposicao/abc"
assert L("Projeto de Lei Nº 1: X", "proposicao") == "projeto" and L("Projeto de Lei Nº 1: X", "proposicao", a=True) == "aprovado"
assert L("Projeto de Lei nº 3/2026: Y", "lei") == "projeto" and L("Portaria nº 3: Z", "lei") == "norma"
# saúde das fontes: guarda o último sucesso mesmo quando a coleta seguinte falha (ex.: nuvem bloqueada)
it1 = {"d": "2026-10-01T00:00:00Z"}
s1 = c.atualizar_saude({}, [("A", [it1], None), ("B", [], "HTTPError"), ("C", [], "sem feed")], {"C": [it1]}, "T1", "PC")
assert s1["A"] == {"ok": "T1", "onde": "PC", "itens": 1, "erro": None, "recente": "2026-10-01T00:00:00Z"}
assert s1["B"]["erro"] == "HTTPError" and "ok" not in s1["B"] and s1["C"]["ok"] == "T1"
s2 = c.atualizar_saude(s1, [("A", [], "HTTPError")], {}, "T2", "nuvem")
assert s2["A"]["ok"] == "T1" and s2["A"]["onde"] == "PC" and s2["A"]["falha"] == "T2" and s2["A"]["recente"] == "2026-10-01T00:00:00Z"
assert "B" not in s2  # fonte que saiu da lista sai da saúde
# assuntos: palavra inteira, sem acento, vários por notícia; nome de cidade não vira assunto
A = c.assuntos
assert A("Hospital de Araçuaí abre vagas para médicos") == ["saude", "economia"]
assert A("Seca no Vale: Copasa amplia caminhões-pipa") == ["agua"]
assert A("Sigma Lithium amplia mineração de lítio") == ["mineracao"]
assert A("Rio do Prado recebe festival") == ["cultura"] and A("Turmalina e Diamantina") == []
assert A("Homem morre afogado em represa") == ["seguranca", "agua"]
assert A("Carreata em Água Boa") == [] and A("Sismo perto de Araçuaí") == ["agua"]
assert A("Prefeitura abre processo seletivo para professores") == ["educacao", "concursos"]
# selo de confiança: cidade no título/resumo; prefeitura/câmara sempre confiável
CF = lambda t, m, k="imprensa": c.confirmada({"t": t, "r": "", "m": m, "k": k}, P)
assert CF("Chuva forte em Medina (MG)", ["Medina"]) and not CF("Chuva forte em 230 cidades de MG", ["Medina"])
assert CF("Seca castiga o Vale do Jequitinhonha", [c.REGIAO]) and CF("Edital", ["Medina"], "prefeitura")
assert not CF("Obra em Araçuaí", ["Medina"])  # cita outra cidade, não a do item
# Assembleia: link público, situação e texto para achar a cidade
AL = {"resultado": {"listaItem": [{"siglaTipoProjeto": "PL", "numero": "6209", "ano": "2026", "tipoProjeto": "PROJETO DE LEI",
      "ementa": "Declara de utilidade pública associação de Medina.", "situacao": "Aguardando sanção", "autor": "Deputado X      PSD\n",
      "dataPublicacao": "2026-10-23", "indexacao": "Utilidade pública, Município de Medina"}]}}
(b, texto, a), = c.ler_assembleia(AL)
assert b["u"] == "https://www.almg.gov.br/projetos-de-lei/PL/6209/2026" and a and b["t"].startswith("Projeto de lei 6209/2026: Declara")
assert b["r"] == "Situação: Aguardando sanção · Autor: Deputado X PSD" and c.marcar(texto, P) == ["Medina"]
RQ = {"resultado": {"listaItem": [{"siglaTipoProjeto": "RQC", "numero": "1", "ano": "2026", "tipoProjeto": "REQUERIMENTO DE COMISSÃO",
      "assunto": "Requer providências para servidor.", "situacao": "Aprovado", "indexacao": "/Região/Jequitinhonha-Mucuri/Teófilo Otoni"}]}}
(b, texto, a), = c.ler_assembleia(RQ)
assert b["t"] == "Requerimento de comissão 1/2026: Requer providências para servidor." and c.marcar(texto, P) == []
assert L("Projeto de lei 1/2026: x", "assembleia") == "projeto" and L("Projeto de lei 1/2026: x", "assembleia", a=True) == "aprovado"
print("ok")
