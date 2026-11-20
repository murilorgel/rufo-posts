#!/usr/bin/env python3
"""Publicador da Rufo: publica no Instagram os posts do calendario.json que já venceram.

Usa a API do Instagram com login do Instagram (graph.instagram.com).
O token NÃO fica aqui: o ambiente injeta o header Authorization (network secret).

Uso:
  python3 publicar.py checar            # testa o token e mostra a conta
  python3 publicar.py pendentes         # lista o que falta publicar
  python3 publicar.py vencidos          # publica tudo que já passou do horário
  python3 publicar.py post 02           # publica um post específico agora
  python3 publicar.py checar-midia      # confere se as imagens estão acessíveis no link público
"""
import json, sys, time, urllib.request, urllib.parse, urllib.error, datetime, pathlib
from zoneinfo import ZoneInfo

API = "https://graph.instagram.com/v23.0"
AQUI = pathlib.Path(__file__).resolve().parent
CAL = AQUI / "calendario.json"
LOG = AQUI / "log.txt"


def log(msg):
    linha = f"{datetime.datetime.now(ZoneInfo('America/Sao_Paulo')):%Y-%m-%d %H:%M:%S} {msg}"
    print(linha)
    with open(LOG, "a") as f:
        f.write(linha + "\n")


def api(method, path, **params):
    url = f"{API}/{path}"
    data = None
    if method == "GET":
        if params:
            url += "?" + urllib.parse.urlencode(params)
    else:
        data = urllib.parse.urlencode(params).encode()
    req = urllib.request.Request(url, data=data, method=method)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"{method} {path}: {e.code} {e.read().decode()[:500]}")


def conta():
    me = api("GET", "me", fields="user_id,username,account_type")
    return me


def esperar_pronto(container_id, limite=180):
    t0 = time.time()
    while time.time() - t0 < limite:
        st = api("GET", container_id, fields="status_code").get("status_code")
        if st == "FINISHED":
            return
        if st in ("ERROR", "EXPIRED"):
            raise RuntimeError(f"container {container_id} com status {st}")
        time.sleep(4)
    raise RuntimeError(f"container {container_id} não ficou pronto em {limite}s")


def publicar(post, cal, ig_id):
    base = cal["midia_base_url"]
    urls = [base + img for img in post["imagens"]]
    if len(urls) == 1:
        c = api("POST", f"{ig_id}/media", image_url=urls[0], caption=post["legenda"])["id"]
    else:
        filhos = []
        for u in urls:
            filhos.append(api("POST", f"{ig_id}/media", image_url=u, is_carousel_item="true")["id"])
        for f in filhos:
            esperar_pronto(f)
        c = api("POST", f"{ig_id}/media", media_type="CAROUSEL", children=",".join(filhos), caption=post["legenda"])["id"]
    esperar_pronto(c)
    media_id = api("POST", f"{ig_id}/media_publish", creation_id=c)["id"]
    link = api("GET", media_id, fields="permalink").get("permalink", "")
    return media_id, link


def carregar():
    return json.loads(CAL.read_text())


def salvar(cal):
    CAL.write_text(json.dumps(cal, ensure_ascii=False, indent=2) + "\n")


def quando(post, cal):
    return datetime.datetime.fromisoformat(post["quando"]).replace(tzinfo=ZoneInfo(cal["fuso"]))


def rodar(posts_alvo, cal):
    me = conta()
    ig_id = me["user_id"]
    for p in posts_alvo:
        log(f"post {p['id']}: publicando ({len(p['imagens'])} imagem(ns)) em @{me['username']}")
        try:
            mid, link = publicar(p, cal, ig_id)
            p["status"] = "publicado"
            p["media_id"] = mid
            p["link"] = link
            p["publicado_em"] = datetime.datetime.now(ZoneInfo(cal["fuso"])).isoformat(timespec="minutes")
            log(f"post {p['id']}: OK {link}")
        except Exception as e:
            p["status"] = "erro"
            p["erro"] = str(e)
            log(f"post {p['id']}: ERRO {e}")
        salvar(cal)


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "pendentes"
    cal = carregar()
    agora = datetime.datetime.now(ZoneInfo(cal["fuso"]))
    if cmd == "checar":
        print(conta())
    elif cmd == "pendentes":
        for p in cal["posts"]:
            if p["status"] in ("pendente", "erro"):
                print(p["id"], p["quando"], p["status"], len(p["imagens"]), "imagem(ns)")
    elif cmd == "checar-midia":
        ok = True
        for p in cal["posts"]:
            for img in p["imagens"]:
                u = cal["midia_base_url"] + img
                try:
                    with urllib.request.urlopen(urllib.request.Request(u, method="HEAD"), timeout=30) as r:
                        tipo = r.headers.get("Content-Type")
                    print("ok ", u, tipo)
                except Exception as e:
                    ok = False
                    print("FALHA", u, e)
        sys.exit(0 if ok else 1)
    elif cmd == "vencidos":
        alvo = [p for p in cal["posts"] if p["status"] == "pendente" and quando(p, cal) <= agora]
        if not alvo:
            print("nada vencido")
        rodar(alvo, cal)
    elif cmd == "post":
        alvo = [p for p in cal["posts"] if p["id"] == sys.argv[2]]
        rodar(alvo, cal)
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
