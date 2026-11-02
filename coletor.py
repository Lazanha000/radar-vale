"""Radar do Vale: junta notícias do Vale do Jequitinhonha em painel/noticias.js.

Fontes: Google Notícias (uma busca por cidade), feeds de prefeituras e câmaras,
API SAPL das câmaras (normas jurídicas) e feeds regionais.
Uso: python coletor.py [--dias 30]   (precisa de: pip install defusedxml)
"""
import argparse, hashlib, html, json, os, re, sys, time, unicodedata, urllib.parse, urllib.request
from defusedxml import ElementTree as ET  # feeds são de terceiros: pip install defusedxml
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

AQUI = Path(__file__).parent
SAIDA = AQUI / "painel" / "noticias.js"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"}
REGIAO = "Vale do Jequitinhonha"
PROPRIOS = {"prefeitura", "camara", "lei", "proposicao"}  # id pelo link: títulos genéricos se repetem entre cidades
# nomes que também são palavra, sobrenome ou lugar de outro estado: só valem com contexto de MG
AMBIGUOS = {"Datas", "Jacinto", "Bandeira", "Gouveia", "Rubim", "Medina", "Mata Verde", "Berilo", "Turmalina",
            "Carbonita", "Jordânia", "Aricanduva", "Presidente Kubitschek", "Pedra Azul", "Itinga", "Caraí"}
SITE_DIAS = 365  # janela do site: (Google limita a 100 itens por busca)
NOTICIA_URL = re.compile(r"/noticias?/(detalhe/\d+|[^/]*\d[^/]*)$")  # exclui as listagens /noticia e /noticias
# resultado de eleição por cidade (G1/UOL geram centenas); notícia política comum não entra
ELEICAO = re.compile(r"zona eleitoral|apuracao|mais votad|como (a cidade |o municipio )?votou|\d o? ?turno|(primeiro|segundo) turno"
                     r"|local de votacao|boletim de urna|resultado (da |das |do )?(eleic|votac)|vence (a )?eleicao"
                     r"|eleicao presidencial|dos votos|votos validos|quem foi eleito|escolhe .* para (presidente|governador)")
# aba Câmaras: o que é projeto em tramitação e o que é sessão/reunião
PROJETO = re.compile(r"projeto de (lei|resolucao|decreto|emenda)|proposic|indicacao|requerimento|mocao|\bveto\b|emenda")
SESSAO = re.compile(r"reuniao (ordinaria|extraordinaria|extra ordinaria|solene|especial)|\d+ reuniao|sessao|audiencia publica"
                    r"|\bpauta\b|\bata\b|tribuna livre|mesa diretora|\bposse\b|comissao")
SOBRE_CAMARA = re.compile(r"camara (municipal|de vereadores)|vereador")
APROV = re.compile(r"aprov|sancion|promulg")
# assuntos por palavra-chave no título e resumo (texto já sem acento); uma notícia pode ter vários
ASSUNTOS = {
    "saude": ("Saúde", r"saude|hospita\w*|vacin\w*|ubs|posto de saude|medic[oa]s?|sus|dengue|chikungunya|samu|doencas?|epidemia"
                       r"|odontolog\w*|oncolog\w*|enfermag\w*|covid|gripe|cancer|outubro rosa|novembro azul"),
    "educacao": ("Educação", r"escola\w*|educa\w*|ensino|alunos?|estudantes?|professor\w*|creches?|ufvjm|ifnmg|universidade\w*"
                            r"|faculdade\w*|enem|matriculas?|alfabetiza\w*|merenda|transporte escolar"),
    "obras": ("Obras e infraestrutura", r"obras?|pavimenta\w*|asfalt\w*|estradas?|rodovias?|br \d{3}|mgc? \d{3}|pontes?|calcamento"
                                       r"|saneamento|esgoto|iluminacao|reformas?|construc\w*|habitac\w*|moradias?|energia eletrica|cemig|apagao"),
    "seguranca": ("Segurança e acidentes", r"policia\w*|pm|presos?|prisao|crimes?|criminos\w*|homicidios?|assassin\w*|assaltos?"
                                          r"|roubos?|furtos?|drogas?|trafico|apreen\w*|violencia|mort[oa]s?|morre\w*|acidentes?"
                                          r"|bombeiros?|afogad\w*|tiros?|armas?|feridos?"),
    "agua": ("Água, seca e clima", r"seca|estiagem|chuvas?|agua(?! boa)|copasa|copanor|barragens?|represas?|rio (jequitinhonha|aracuai|vermelho)"
                                  r"|nascentes?|meio ambiente|ambienta\w*|desmatamento|queimadas?|incendios?|clima\w*|calor|temporal|sismo|tremor de terra"),
    "mineracao": ("Mineração", r"minera\w*|litio|lithium|sigma|garimp\w*|minerio|minerais|jazidas?|diamantes?|pedras preciosas"),
    "economia": ("Economia e emprego", r"empregos?|vagas?|econom\w*|empresas?|empreend\w*|comercio|investiment\w*|renda|salari\w*"
                                      r"|negocios?|impostos?|iptu|credito|sebrae|turismo"),
    "cultura": ("Cultura e turismo", r"cultura\w*|festivais|festival|festas?|artesanato|artesa\w*|musica\w*|shows?|turis\w*"
                                    r"|patrimonio|carnaval|teatro|cinema|livros?|bibliotecas?|tradic\w*|folclor\w*|religios\w*"),
    "esporte": ("Esporte", r"esportes?|esportiv\w*|futebol|campeonatos?|torneios?|atletas?|corridas?|olimpiadas?|ginasio|futsal|libertadores"),
    "agro": ("Agro e zona rural", r"agricult\w*|agro\w*|rural|produtor\w*|lavouras?|safras?|cafe|leite|gado|pecuaria|emater"
                                 r"|hortas?|irrigacao|sementes?|colheita"),
    "social": ("Assistência social", r"assistencia social|cras|creas|bolsa familia|cadunico|cadastro unico|vulnerab\w*|idosos?"
                                    r"|crianc\w*|violencia domestica|fome|cestas? basicas?|auxilio\w*|apae|deficien\w*"),
    "concursos": ("Concursos e seleções", r"concursos?|processo seletivo|seletivo|editais|edital|inscric\w*|convocac\w*|nomeac\w*"),
    "politica": ("Política", r"prefeit[oa]s?|vereador\w*|deputad\w*|governador\w*|eleic\w*|eleit\w*|camara municipal|assembleia"
                            r"|senador\w*|presidente|partidos?|mandato|zema|lula|bolsonaro"),
}
ASSUNTOS_RX = {k: re.compile(rf"\b({rx})\b") for k, (_, rx) in ASSUNTOS.items()}


def assuntos(texto):
    t = norm(texto)
    return [k for k, rx in ASSUNTOS_RX.items() if rx.search(t)]
NORMA_APROVADA = re.compile(r"(lei|decreto legislativo|resolucao|emenda|proposicao de lei|ato de promulgacao)( |$)")  # portaria e decreto do executivo não são aprovação
# "Vale do Jequitinhonha" e "rio Jequitinhonha" não são a cidade; "Chapada Diamantina" é na Bahia
EXCETO = {"jequitinhonha": r"(?<!vale do )(?<!rio )(?<!alto )(?<!medio )(?<!baixo )(?<!bacia do )(?<!regiao do )",
          "diamantina": r"(?<!chapada )"}


def norm(s):
    s = unicodedata.normalize("NFD", s.lower())
    return re.sub(r"[^a-z0-9]+", " ", "".join(c for c in s if unicodedata.category(c) != "Mn")).strip()


def tem_contexto(base, n):
    """Nome ambíguo só vale colado em MG/Minas ou em 'prefeitura/câmara/cidade de'; ou com 'Jequitinhonha' no texto."""
    return bool(re.search(rf"(^| ){n} (de minas|minas gerais|mg)( |$)|(prefeitura|camara|municipio|cidade|prefeito|vereadores?) (de |do |da )?{n}( |$)", base)
                or "jequitinhonha" in base)


def padroes(municipios):
    # nomes longos primeiro: "Santo Antônio do Jacinto" é consumido antes de "Jacinto"
    out = []
    for nome in sorted(municipios, key=len, reverse=True):
        n = norm(nome)
        out.append((nome, re.compile(EXCETO.get(n, "") + r"\b" + re.escape(n) + r"\b")))
    return out


def marcar(texto, pads, forcado=None, confiavel=False, regiao=False):
    """Municípios citados no texto (+ o da fonte, se houver). Vazio = descartar."""
    base = t = norm(texto)
    achados = set()
    for nome, rx in pads:
        if rx.search(t):
            t = rx.sub(" ", t)
            if nome not in AMBIGUOS or tem_contexto(base, norm(nome)):
                achados.add(nome)
    if forcado and (confiavel or forcado not in AMBIGUOS or tem_contexto(base, norm(forcado))):
        achados.add(forcado)
    if not achados and regiao and "jequitinhonha" in base:
        achados.add(REGIAO)
    return sorted(achados)


def data_iso(s):
    if not s:
        return None
    try:
        d = parsedate_to_datetime(s)
    except (TypeError, ValueError):
        try:
            d = datetime.fromisoformat(s.replace("Z", "+00:00"))
        except ValueError:
            return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return d.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def limpa(s):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", s or ""))).strip()


def parse_feed(xml):
    """RSS 2.0 ou Atom -> [{t,u,d,r,f}]. ValueError se não for feed (ex.: página HTML)."""
    try:
        raiz = ET.fromstring(xml)
    except Exception as e:  # ParseError (HTML) ou entidade bloqueada pelo defusedxml
        raise ValueError("não é feed") from e
    itens = []
    for el in raiz.iter():
        if el.tag.split("}")[-1] not in ("item", "entry"):
            continue
        c = {}
        for f in el:
            k = f.tag.split("}")[-1]
            c.setdefault(k, f)
        link = c.get("link")
        link = (link.get("href") or link.text or "") if link is not None else ""
        txt = lambda k: (c[k].text or "") if k in c else ""
        itens.append({"t": limpa(txt("title")), "u": link.strip(),
                      "d": data_iso(txt("pubDate") or txt("updated") or txt("published")),
                      "r": limpa(txt("description") or txt("summary")),
                      "f": limpa(txt("source"))})
    if not itens and raiz.tag.split("}")[-1] not in ("rss", "feed", "RDF"):
        raise ValueError("não é feed")
    return itens


def baixar(url):
    return urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=20).read()


def monta(bruto, fonte, kind, pads, mun=None, confiavel=False, regiao=False, aprov=False):
    r = bruto["r"] if not bruto["r"].startswith(bruto["t"][:40]) else ""  # Google repete o título
    titulo = bruto["t"]
    if bruto["f"] and titulo.endswith(" - " + bruto["f"]):
        titulo = titulo[: -len(bruto["f"]) - 3]
    titulo = titulo.strip(" -|")
    ms = marcar(f"{titulo} {r}", pads, mun, confiavel, regiao)
    if not ms or not titulo or not bruto["u"].startswith("http"):
        return None
    return {"t": titulo, "u": bruto["u"], "d": bruto["d"], "r": r[:300], "f": bruto["f"] or fonte,
            "k": kind, "o": mun or "", "m": ms, "a": aprov if kind in ("lei", "proposicao") else bool(APROV.search(norm(titulo)))}


def tarefa_feed(rotulo, urls, kind, pads, mun=None, confiavel=False, regiao=False):
    erro = "sem feed"
    for url in urls:
        try:
            brutos = parse_feed(baixar(url))
        except Exception as e:
            erro = f"{type(e).__name__}: {e}"[:80]
            continue
        return rotulo, [i for i in (monta(b, rotulo, kind, pads, mun, confiavel, regiao) for b in brutos) if i], None
    return rotulo, [], erro


def url_google(consulta):
    return "https://news.google.com/rss/search?q=" + urllib.parse.quote(consulta) + "&hl=pt-BR&gl=BR&ceid=BR:pt-419"


def tarefa_veiculo(nome, site, dias, pads):
    """Veículo regional sem feed útil: o que o Google indexou dele, só o que cita o Vale."""
    time.sleep(0.3)
    return tarefa_feed(nome, [url_google(f"site:{site} when:{dias}d")], "imprensa", pads, regiao=True)


def tarefa_google(consulta, mun, pads):
    time.sleep(0.3)
    url = url_google(consulta)
    return tarefa_feed(f"Google: {mun}", [url], "imprensa", pads, mun, confiavel=mun == REGIAO)


def tarefa_sapl(mun, host, pads):
    try:
        res = json.loads(baixar(f"https://{host}/api/norma/normajuridica/?o=-data&page_size=50"))["results"]
    except Exception as e:
        return f"SAPL: {mun}", [], f"{type(e).__name__}"
    itens = []
    for r in res:
        b = {"t": f"{r['__str__']}: {limpa(r.get('ementa'))}", "u": f"https://{host}/norma/{r['id']}",
             "d": data_iso(r.get("data")), "r": "", "f": ""}
        i = monta(b, f"Câmara de {mun} (SAPL)", "lei", pads, mun, confiavel=True,
                  aprov=bool(NORMA_APROVADA.match(norm(r["__str__"]))))
        if i:
            itens.append(i)
    return f"SAPL: {mun}", itens, None


def ler_leis(dados, host):
    """JSON de /legislacoes/get/todas (modelo de site usado por 18 câmaras) -> itens brutos com aprovação."""
    out = []
    for r in dados["data"]:
        tipo = limpa(r.get("titulo"))
        criado = (r.get("arquivo") or {}).get("created_at")
        out.append(({"t": f"{tipo} nº {r.get('identificacao')}: {limpa(r.get('ementa'))}", "u": f"https://{host}/legislacoes/{r['id']}",
                     "d": data_iso(criado) or data_iso(f"{r.get('ano')}-01-01"), "r": "", "f": ""},
                    bool(NORMA_APROVADA.match(norm(tipo)))))
    return out


SITUACAO_APROVADA = {"aprovada", "aprovado", "sancionada", "promulgada"}
PR_CAMPOS = {"tipo": r'pr-item-tipo">([^<]+)<', "num": r'pr-item-num"[^>]*>([^<]+)<', "link": r'pr-item-num" href="([^"]+)"',
             "ementa": r'pr-item-ementa"><a[^>]*>(.*?)</a>', "autor": r'pr-item-autor">(.*?)</span>', "sit": r'lg-badge[^"]*">([^<]+)<'}


def ler_proposicoes(pagina):
    """Página /legislativo/proposicoes (modelo de Almenara, Mata Verde e Rio do Prado) -> itens brutos com situação."""
    out = []
    for art in re.findall(r'<article class="pr-item">(.*?)</article>', pagina, re.S):
        c = {k: limpa((re.search(rx, art, re.S) or [None, ""])[1]) for k, rx in PR_CAMPOS.items()}
        dt = re.search(r"Protocolo em (\d\d)/(\d\d)/(\d{4})", art)
        out.append(({"t": f"{c['tipo']} {c['num']}: {c['ementa']}", "u": c["link"],
                     "d": f"{dt[3]}-{dt[2]}-{dt[1]}T12:00:00Z" if dt else None,
                     "r": f"Situação: {c['sit']} · Autor: {c['autor']}", "f": ""},
                    norm(c["sit"]) in SITUACAO_APROVADA))
    return out


def tarefa_leis(mun, host, pads):
    try:
        brutos = ler_leis(json.loads(baixar(f"https://{host}/legislacoes/get/todas?draw=1&start=0&length=40")), host)
    except Exception as e:
        return f"Leis: {mun}", [], type(e).__name__
    itens = [monta(b, f"Câmara de {mun}", "lei", pads, mun, confiavel=True, aprov=a) for b, a in brutos]
    return f"Leis: {mun}", [i for i in itens if i], None


def tarefa_proposicoes(mun, host, pads):
    brutos, erro = {}, None
    for filtro in ("", "?status=aprovada"):  # as mais recentes e, à parte, as aprovadas
        try:
            for b, a in ler_proposicoes(baixar(f"https://{host}/legislativo/proposicoes{filtro}").decode("utf-8", "ignore")):
                brutos[b["u"]] = (b, a)
        except Exception as e:
            erro = type(e).__name__
    itens = [monta(b, f"Câmara de {mun}", "proposicao", pads, mun, confiavel=True, aprov=a) for b, a in brutos.values()]
    return f"Proposições: {mun}", [i for i in itens if i], None if brutos else erro or "sem proposições"


def tarefa_site(rotulo, host, kind, mun, pads):
    """Site sem feed: o que o Google Notícias indexou dele (site:host)."""
    time.sleep(0.3)
    url = url_google(f"site:{host} when:{SITE_DIAS}d")
    r, itens, erro = tarefa_feed(f"{rotulo} (via Google)", [url], kind, pads, mun, confiavel=True)
    itens = [i for i in itens if len(i["t"].split()) >= 2]  # o Google também traz páginas fixas ("Transparência")
    return r, itens, erro or (None if itens else "Google sem notícias do site")


def meta(pagina, *props):
    for p in props:
        m = re.search(rf'(?:property|name)="{p}" content="([^"]*)"', pagina)
        if m:
            return limpa(m[1])
    return ""


def tarefa_sitemap(rotulo, host, kind, mun, pads, conhecidos, limite=40):
    """Site sem feed: as `limite` notícias mais novas do sitemap.xml ainda não coletadas; o título vem da página.
    shortcut: só sitemap simples (não índice de sitemaps) e só as mais novas, para não martelar o servidor da prefeitura."""
    rotulo = f"{rotulo} (sitemap)"
    try:
        raiz = ET.fromstring(baixar(f"https://{host}/sitemap.xml"))
    except Exception as e:
        return rotulo, [], type(e).__name__
    urls = []
    for el in raiz.iter():
        if el.tag.split("}")[-1] == "url":
            c = {x.tag.split("}")[-1]: (x.text or "").strip() for x in el}
            loc = c.get("loc", "")
            if NOTICIA_URL.search(loc) and loc not in conhecidos:
                urls.append((c.get("lastmod", ""), int(re.findall(r"\d+", loc)[-1]), loc))
    itens = []
    for lastmod, _, loc in sorted(urls, reverse=True)[:limite]:
        time.sleep(0.2)
        try:
            pag = baixar(loc)[:80000].decode("utf-8", "ignore")
        except Exception:
            continue
        titulo = re.sub(r"\s+-\s+(Prefeitura|Câmara)[^-]*$", "", meta(pag, "og:title"))
        if titulo:
            b = {"t": titulo, "u": loc, "d": data_iso(lastmod), "r": meta(pag, "og:description", "description"), "f": ""}
            i = monta(b, rotulo, kind, pads, mun, confiavel=True)
            if i:
                itens.append(i)
    return rotulo, itens, None if itens else "sitemap sem notícias novas"


def confirmada(i, pads):
    """Imprensa: alguma cidade do item aparece no título/resumo? Se não, o Google achou só no corpo da matéria (pode ser ruído).
    Fontes próprias (prefeitura, câmara) são sempre confirmadas."""
    return i["k"] != "imprensa" or bool(set(marcar(f"{i['t']} {i['r']}", pads, regiao=True)) & set(i["m"]))


def legislativo(i):
    """Categoria da aba Câmaras (aprovado/projeto/sessao/norma/outro) ou None se o item não é do legislativo."""
    t = norm(i["t"])
    if i["k"] == "imprensa" and (i.get("e") or not SOBRE_CAMARA.search(t)):
        return None
    if i["k"] == "prefeitura" and not (i["a"] and re.search(r"\blei\b|projeto|camara", t)):
        return None  # da prefeitura só entra "prefeito sanciona lei"
    if i["a"]:
        return "aprovado"
    if i["k"] in ("lei", "proposicao"):
        return "projeto" if i["k"] == "proposicao" or t.startswith("projeto") else "norma"
    return "projeto" if PROJETO.search(t) else "sessao" if SESSAO.search(t) else "outro"


def chave(it):
    # site próprio: título + cidade de origem ("NOTA DE PESAR" existe em várias); imprensa: só o título
    base = f"p|{norm(it['t'])}|{it.get('o', '')}" if it["k"] in PROPRIOS else f"i|{norm(it['t'])}"
    return hashlib.sha1(base.encode()).hexdigest()[:12]


def juntar(itens):
    """Junta repetidos (mesma notícia via feed, sitemap e Google): soma cidades, fica a data mais antiga e o link direto."""
    out = {}
    for it in itens:
        it["id"] = chave(it)
        it["d"] = it["d"] or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        v = out.get(it["id"])
        if not v:
            out[it["id"]] = it
            continue
        v["m"] = sorted(set(v["m"]) | set(it["m"]))
        # resumo mais novo vale: nas proposições ele traz a situação, que muda ("Em tramitação" -> "Aprovada")
        v["d"], v["r"], v["a"] = min(v["d"], it["d"]), it["r"] or v["r"], v["a"] or it["a"]
        if "news.google." in v["u"] and "news.google." not in it["u"]:
            v["u"], v["f"] = it["u"], it["f"]
    return out


def sem_paginas_fixas(itens):
    """Tira páginas institucionais que o Google indexa ("Portal da Transparência"): mesmo título em 3+ sites próprios.
    shortcut: um aviso genérico igual em 3+ cidades ("Feliz Natal") também sai."""
    origens = {}
    for i in itens:
        if i["k"] in PROPRIOS:
            origens.setdefault(norm(i["t"]), set()).add(i.get("o", ""))
    return [i for i in itens if i["k"] not in PROPRIOS or len(origens[norm(i["t"])]) < 3]


def carregar_anterior():
    """Itens (por id) e saúde das fontes gravados na coleta anterior."""
    if not SAIDA.exists():
        return {}, {}
    txt = SAIDA.read_text(encoding="utf-8")
    d = json.loads(txt[txt.index("{"): txt.rindex("}") + 1])
    return {i["id"]: i for i in d["itens"]}, d.get("saude", {})


def atualizar_saude(antiga, resultados, resgate, agora, onde):
    """Por fonte: quando funcionou pela última vez (e onde: PC ou nuvem), último erro e a notícia mais nova já vista.
    Fonte sem feed salva pelo Google/sitemap (resgate) conta como funcionando."""
    nova = {}
    for r, its, erro in resultados:
        s = dict(antiga.get(r, {}))
        its = its + resgate.get(r, [])
        if erro is None or its:
            s.update(ok=agora, onde=onde, itens=len(its), erro=None)
        else:
            s.update(falha=agora, erro=erro)
        datas = [i["d"] for i in its if i.get("d")] + ([s["recente"]] if s.get("recente") else [])
        s["recente"] = max(datas) if datas else None
        nova[r] = s
    return nova


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--dias", type=int, default=30, help="janela do Google Notícias (máx. 100 itens por busca)")
    dias = ap.parse_args().dias
    muns = json.loads((AQUI / "municipios.json").read_text(encoding="utf-8"))
    fontes = json.loads((AQUI / "fontes.json").read_text(encoding="utf-8"))
    pads = padroes(muns)

    google = [(f'"{m}" MG when:{dias}d', m) for m in muns]
    google += [(f'"{r}" when:{dias}d', REGIAO) for r in ("Vale do Jequitinhonha", "Alto Jequitinhonha", "Médio Jequitinhonha", "Baixo Jequitinhonha", "Codevale")]
    feeds, proprios = [], {}
    for tipo, kind, rot in (("prefeituras", "prefeitura", "Prefeitura de"), ("camaras", "camara", "Câmara de")):
        for m, host in fontes[tipo].items():
            feeds.append((f"{rot} {m}", [f"https://{host}/noticias.rss", f"https://{host}/feed/"], kind, m, True, False))
            proprios[f"{rot} {m}"] = (host, kind, m)
    for r in fontes["regionais"]:
        feeds.append((r["nome"], [r["url"]], "imprensa", None, False, True))

    with ThreadPoolExecutor(3) as pg, ThreadPoolExecutor(12) as pf:
        fut = [pg.submit(tarefa_google, q, m, pads) for q, m in google]
        fut += [pf.submit(tarefa_feed, r, u, k, pads, m, c, g) for r, u, k, m, c, g in feeds]
        fut += [pf.submit(tarefa_sapl, m, h, pads) for m, h in fontes["sapl"].items()]
        fut += [pf.submit(tarefa_leis, m, h, pads) for m, h in fontes["leis_json"].items()]
        fut += [pf.submit(tarefa_proposicoes, m, h, pads) for m, h in fontes["proposicoes_html"].items()]
        fut += [pg.submit(tarefa_veiculo, v["nome"], v["site"], dias, pads) for v in fontes["veiculos_site"]]
        resultados = [f.result() for f in fut]

    # sites próprios sem feed: Google site: e, se o Google trouxe pouco (<20), também o sitemap
    antigos, saude = carregar_anterior()
    conhecidos = {i["u"] for i in antigos.values() if i["k"] in PROPRIOS}
    sem_feed = [(r, *proprios[r]) for r, _, e in resultados if e and r in proprios]
    with ThreadPoolExecutor(3) as pg, ThreadPoolExecutor(8) as pf:
        pelo_google = {r: pg.submit(tarefa_site, r, h, k, m, pads) for r, h, k, m in sem_feed}
        pelo_google = {r: f.result() for r, f in pelo_google.items()}
        pelo_mapa = {r: pf.submit(tarefa_sitemap, r, h, k, m, pads, conhecidos)
                     for r, h, k, m in sem_feed if len(pelo_google[r][1]) < 20}
        pelo_mapa = {r: f.result() for r, f in pelo_mapa.items()}
    extras = [x for d in (pelo_google, pelo_mapa) for x in d.values()]
    resgate = {r: pelo_google[r][1] + pelo_mapa.get(r, (None, [], None))[1] for r in pelo_google}
    resgatadas = {r for r, its in resgate.items() if its}
    agora = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    saude = atualizar_saude(saude, resultados, resgate, agora, "nuvem" if os.environ.get("GITHUB_ACTIONS") else "PC")

    novos = [i for _, itens, _ in resultados + extras for i in itens]
    # veículos que repetem nomes de cidades em toda página: só vale a cidade citada no título/resumo
    so_texto = set(fontes.get("so_com_cidade_no_texto", []))
    for i in novos:
        if i["f"] in so_texto:
            i["m"] = marcar(f"{i['t']} {i['r']}", pads, regiao=True)
    novos = [i for i in novos if i["m"]]
    todos = juntar(list(antigos.values()) + novos)  # re-junta tudo: regra nova vale também para o que já existia
    itens = sorted(sem_paginas_fixas(list(todos.values())), key=lambda i: i["d"], reverse=True)[:30000]
    for i in itens:
        i["e"] = i["k"] == "imprensa" and bool(ELEICAO.search(norm(i["t"])))
        i["lg"] = legislativo(i)
        i["as"] = assuntos(f"{i['t']} {i['r']}")
        i["c"] = confirmada(i, pads)
    falhas = [{"fonte": r, "erro": e} for r, _, e in resultados if e and r not in resgatadas]
    dados = {"gerado": agora, "saude": saude, "assuntos": {k: nome for k, (nome, _) in ASSUNTOS.items()},
             "municipios": sorted(muns) + [REGIAO],
             "fontes": {"total": len(resultados), "com_itens": sum(1 for _, i, _ in resultados if i) + len(resgatadas), "falhas": falhas},
             "itens": itens}
    SAIDA.parent.mkdir(exist_ok=True)
    # uma notícia por linha: o histórico do git guarda só as linhas que mudaram
    cabeca = json.dumps({k: v for k, v in dados.items() if k != "itens"}, ensure_ascii=False)[:-1]
    linhas = ",\n".join(json.dumps(i, ensure_ascii=False) for i in itens)
    SAIDA.write_text(f'window.RADAR = {cabeca}, "itens": [\n{linhas}\n]}};\n', encoding="utf-8")
    print(f"{len(novos)} itens coletados, {len(itens)} no painel; fontes: {dados['fontes']['com_itens']}/{len(resultados)} com itens")
    for f in falhas:
        print("  falha:", f["fonte"], "-", f["erro"])


if __name__ == "__main__":
    main()
