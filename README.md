# V26 Web v1

Interface web simples para usar a **V26 Core API** pelo Safari/iPhone.

## O que esta versão faz

- Configura a URL da V26 Core API.
- Testa conexão com `/health`.
- Testa parser em `/parse`.
- Roda análise em `/analyze`.
- Roda benchmarks em `/benchmarks/run`.
- Inclui botões de preenchimento para os 4 benchmarks oficiais:
  - Criciúma
  - Operário x América-MG
  - Novorizontino x Vila Nova
  - Athletic x Avaí

## Como usar localmente

Abra `index.html` no navegador e informe a URL da API.

Para API local:

```text
http://127.0.0.1:8000
```

No iPhone, a API precisa estar publicada online, por exemplo:

```text
https://sua-api.onrender.com
```

## Como publicar no Netlify Drop pelo celular

1. Envie este ZIP no Netlify Drop.
2. Abra o link `.netlify.app` no Safari.
3. Informe a URL da V26 Core API.
4. Toque em **Salvar API**.
5. Toque em **Testar conexão**.
6. Rode os benchmarks.

## Observação importante

Esta interface não contém a Engine dentro dela. Ela conversa com a V26 Core API. A Browser Lite roda sozinha no Safari, mas a V26 Web v1 precisa da API online.
