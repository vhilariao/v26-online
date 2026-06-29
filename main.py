from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from v26_core import AnalysisInput, analyze
from v26_core.benchmark_loader import load_benchmarks
from v26_core.parser import parse_odds
from v26_core.providers import ManualContextProvider, TheSportsDBContextProvider
from v26_core.context_scanner import ContextScanner
from v26_core.context_blocks import ContextBlocksAnalyzer
from v26_core.web_scanner import WebScanner
from v26_core.context_v26_reasoner import ContextV26Reasoner
from v26_core.v26_doctrine import build_v26_prompt_context, build_v26_ia_spec
from v26_core.ia_v26_orchestrator import build_ia_v26_output
from v26_core.odds_cleaner import clean_pinnacle_odds_text
from v26_core.vision_odds_extractor import extract_pinnacle_odds_with_vision
from v26_core.message_intake import parse_initial_message
from v26_core.gpt_context_v26 import build_gpt_context_v26
from v26_core.odds_structure_v26 import build_odds_structure_context
from v26_core.anti_induction_audit import anti_induction_report
from v26_core.football_data_agenda import FootballDataAgendaProvider
from v26_core.odds_api_provider import OddsApiProvider
from v26_core.source_weights import explain_matrix, source_table_for_api

from schemas import (
    AnalyzeRequest,
    BenchmarkCaseResult,
    BenchmarkRunResponse,
    ContextSearchRequest,
    ContextSearchResponse,
    ContextScanRequest,
    ContextScanResponse,
    ContextBlocksRequest,
    ContextBlocksResponse,
    ContextWebScanRequest,
    ContextWebScanResponse,
    AgendaResponse,
    ParseRequest,
)

VERSION = "v26-core-api-v3.9.4.1"
ROOT = Path(__file__).resolve().parent
BENCHMARKS_PATH = ROOT / "benchmarks.json"

app = FastAPI(
    title="V26 Core API",
    description="API do V26 Core: parser, análise pré-live/live, contexto assistido, varredura IA-guided e validação por benchmarks.",
    version="3.9.4.1",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # MVP/dev. Na versão online, trocar para o domínio da V26 Web.
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

manual_context_provider = ManualContextProvider()
context_provider = TheSportsDBContextProvider(fallback_provider=manual_context_provider)
context_scanner = ContextScanner(auxiliary_provider=context_provider)
context_blocks_analyzer = ContextBlocksAnalyzer()
web_scanner = WebScanner(blocks_analyzer=context_blocks_analyzer)
v26_reasoner = ContextV26Reasoner()
agenda_provider = FootballDataAgendaProvider()
odds_provider = OddsApiProvider()


@app.get("/")
def root() -> Dict[str, str]:
    return {
        "service": "V26 Core API",
        "version": VERSION,
        "docs": "/docs",
        "health": "/health",
    }


@app.get("/health")
def health() -> Dict[str, str]:
    return {"status": "ok", "version": VERSION}




@app.get("/audit/anti-induction")
def audit_anti_induction() -> Dict[str, Any]:
    """Verifica se o motor de decisão contém gatilhos por nome de jogo/time."""
    return anti_induction_report(ROOT)


@app.post("/parse")
def parse(payload: ParseRequest) -> Dict[str, Any]:
    markets = parse_odds(payload.odds_text)
    return {
        "recognized_markets": len(markets),
        "markets": [m.__dict__ for m in markets],
    }


@app.post("/context/search", response_model=ContextSearchResponse)
def search_context(payload: ContextSearchRequest) -> Dict[str, Any]:
    """Gera contexto assistido sem alterar a engine V26.

    O texto retornado deve ser revisado pelo usuário antes de rodar /analyze.
    """
    return context_provider.search(payload)






@app.get("/context/source-weights")
def context_source_weights() -> Dict[str, Any]:
    """Retorna a matriz oficial de pesos das fontes v1.6."""
    return {
        "status": "ok",
        "version": "source_weights_v1.6",
        "description": "Peso mede força do contexto/fonte, não valor da aposta.",
        "rules_text": explain_matrix(),
        "sources": source_table_for_api(),
    }










@app.get("/agenda/competitions")
def get_agenda_competitions() -> Dict[str, Any]:
    """Lista competições acessíveis pelo token football-data.org."""
    return agenda_provider.competitions()


@app.get("/agenda", response_model=AgendaResponse)
def get_agenda(date: str = "", competition: str = "", limit: int = 80) -> Dict[str, Any]:
    """Lista jogos do dia via football-data.org.

    Requer FOOTBALL_DATA_TOKEN no Render.
    Serve para selecionar jogo e padronizar times/competição antes da IA/V26.
    """
    return agenda_provider.agenda(target_date=date or None, competition=competition, limit=limit)




@app.get("/odds/sports")
def get_odds_sports(all: bool = False) -> Dict[str, Any]:
    """Lista esportes/chaves disponíveis na The Odds API."""
    return odds_provider.sports(all_sports=all)


@app.get("/odds/events")
def get_odds_events(
    sport_key: str = "",
    competition: str = "",
    regions: str = "eu,uk,us",
    markets: str = "h2h,spreads,totals",
    bookmakers: str = "",
    limit: int = 60,
) -> Dict[str, Any]:
    """Lista eventos com odds para um sport_key/competição."""
    return odds_provider.events(
        sport_key=sport_key,
        competition=competition,
        regions=regions,
        markets=markets,
        bookmakers=bookmakers,
        limit=limit,
    )


@app.get("/odds/match")
def get_odds_match(
    home: str,
    away: str,
    sport_key: str = "",
    competition: str = "",
    regions: str = "eu,uk,us",
    markets: str = "h2h,spreads,totals",
    bookmakers: str = "",
    advanced: bool = False,
    advanced_markets: str = "h2h,spreads,totals,btts,draw_no_bet,alternate_spreads,alternate_totals",
) -> Dict[str, Any]:
    """Busca odds do jogo selecionado e converte para texto V26."""
    return odds_provider.match(
        home=home,
        away=away,
        sport_key=sport_key,
        competition=competition,
        regions=regions,
        markets=markets,
        bookmakers=bookmakers,
        advanced=advanced,
        advanced_markets=advanced_markets,
    )


@app.get("/odds/event")
def get_odds_event(
    event_id: str,
    sport_key: str,
    regions: str = "eu,uk,us",
    markets: str = "h2h,spreads,totals,btts,draw_no_bet,alternate_spreads,alternate_totals",
    bookmakers: str = "",
) -> Dict[str, Any]:
    """Busca odds avançadas por event_id."""
    return odds_provider.event_odds(
        event_id=event_id,
        sport_key=sport_key,
        regions=regions,
        markets=markets,
        bookmakers=bookmakers,
    )






@app.get("/context/v26-doctrine")
def get_v26_doctrine() -> Dict[str, Any]:
    """Mostra a doutrina que guia a IA contextual V26."""
    return build_v26_prompt_context()




@app.get("/context/v26-ia-spec")
def get_v26_ia_spec() -> Dict[str, Any]:
    """Mostra exatamente o papel da IA dentro do V26."""
    return build_v26_ia_spec()


@app.post("/context/v26-think")
def v26_context_think(payload: ContextWebScanRequest) -> Dict[str, Any]:
    """Executa varredura web e organiza o Contexto IA no padrão V26.

    A IA coleta e organiza; V26 Core continua decidindo EV/classe/stake.
    """
    # Força varredura mais ampla na camada V26, para não virar só perguntas.
    try:
        payload.max_queries = max(int(payload.max_queries or 0), 8)
        payload.max_results_per_query = max(int(payload.max_results_per_query or 0), 5)
    except Exception:
        pass
    scan = web_scanner.scan_web(payload)
    return v26_reasoner.think(payload, scan)


@app.post("/context/scan-web", response_model=ContextWebScanResponse)
def scan_web_context(payload: ContextWebScanRequest) -> Dict[str, Any]:
    """Executa varredura web real/semi-automática via Tavily.

    Requer TAVILY_API_KEY no Render. Sem chave, retorna setup_required com
    consultas sugeridas. A engine V26 permanece intocada.
    """
    return web_scanner.scan_web(payload)


@app.post("/context/blocks/analyze", response_model=ContextBlocksResponse)
def analyze_context_blocks(payload: ContextBlocksRequest) -> Dict[str, Any]:
    """Analisa blocos coletados por fonte usando a matriz de pesos V26 v1.7.

    Esta rota não altera a engine V26. Ela transforma achados de pesquisa em
    contexto ponderado, detecta conflitos e gera teto contextual.
    """
    return context_blocks_analyzer.analyze(payload)


@app.post("/context/scan", response_model=ContextScanResponse)
def scan_context(payload: ContextScanRequest) -> Dict[str, Any]:
    """Gera plano de varredura IA-guided e Contexto Mestre v1.5.

    Esta rota não altera a engine V26. Ela organiza perguntas, links e contexto
    para revisão humana antes de /analyze.
    """
    return context_scanner.scan(payload)






@app.post("/odds/clean-pinnacle")
def clean_pinnacle_odds(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Limpa odds OCR/manual da Pinnacle antes do V26."""
    return clean_pinnacle_odds_text(str(payload.get("odds_text", "")))




@app.post("/message/parse-initial")
def parse_initial(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Extrai times/competição/contexto de uma mensagem inicial em português."""
    return parse_initial_message(str(payload.get("message", "")))


@app.post("/vision/pinnacle/extract")
def vision_pinnacle_extract(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Extrai odds limpas da Pinnacle usando IA Vision + OCR auxiliar."""
    return extract_pinnacle_odds_with_vision(payload)




@app.post("/gpt/context-v26")
def gpt_context_v26(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Gera contexto V26 com GPT + web search. Não classifica aposta."""
    return build_gpt_context_v26(payload)


@app.post("/analyze/ia-v26")
def analyze_match_with_ia(payload: AnalyzeRequest) -> Dict[str, Any]:
    """Roda IA contextual junto com o V26 Core.

    Fluxo:
    1. IA lê odds como mercado/preço.
    2. IA faz varredura contextual e monta leitura V26.
    3. Contexto IA é enviado ao Core junto da leitura manual.
    4. Core decide EV/classe/stake.
    """
    try:
        cleaned_odds = clean_pinnacle_odds_text(payload.odds_text or "")
        clean_odds_text = cleaned_odds.get("clean_text") or payload.odds_text

        odds_structure = build_odds_structure_context(payload.home_team, payload.away_team, clean_odds_text)
        odds_structure_context = odds_structure.get("context", "")
        detected_ref_team = odds_structure.get("reference_team") or ""
        detected_ref_role = odds_structure.get("reference_role") or ""
        favorite_tag = ""
        if detected_ref_team and "favorito" in str(detected_ref_role).lower():
            favorite_tag = f"FAVORITO_DETECTADO_V26: {detected_ref_team}"
        manual_plus_structure = "\n\n".join([payload.context or "", odds_structure_context or "", favorite_tag]).strip()

        gpt_payload = {
            "home_team": payload.home_team,
            "away_team": payload.away_team,
            "competition": payload.competition,
            "mode": payload.mode,
            "odds_text": clean_odds_text,
            "manual_context": manual_plus_structure,
            "context": manual_plus_structure,
            "odds_structure_context": odds_structure_context,
        }
        think = build_gpt_context_v26(gpt_payload)

        # GPT é a camada principal. Tavily/varredura antiga só entra como fallback se GPT não executar.
        if think.get("status") == "fallback":
            context_payload = ContextWebScanRequest(
                home_team=payload.home_team,
                away_team=payload.away_team,
                competition=payload.competition,
                mode=payload.mode,
                odds_text=clean_odds_text,
                market_focus="odds + contexto + vantagem + EV",
                manual_context=manual_plus_structure,
                current_context_master=manual_plus_structure,
                max_queries=8,
                max_results_per_query=5,
            )
            scan = web_scanner.scan_web(context_payload)
            legacy_think = v26_reasoner.think(context_payload, scan)
            legacy_context = legacy_think.get("context_master", "")
            think["legacy_context"] = legacy_think
            think["context_master"] = "\n\n".join([think.get("context_master", ""), legacy_context or ""]).strip()

        ia_context = think.get("context_master", "")
        merged_context = "\n\n".join([manual_plus_structure or "", ia_context or ""]).strip()

        result = analyze(AnalysisInput(
            home_team=payload.home_team,
            away_team=payload.away_team,
            competition=payload.competition,
            mode=payload.mode,
            odds_text=clean_odds_text,
            context=merged_context,
        ))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    core = result.to_dict()
    best = core.get("best", {})
    stake = float(best.get("stake_units") or 0)
    classification = str(best.get("classification") or "")
    if stake <= 0 or classification in {"C", "D"}:
        core["decision"] = "NO_BET"
        core["decision_label"] = "NÃO APOSTAR"
        core["operational_alert"] = "IA leu o contexto, mas o Core não liberou mercado com stake."
    else:
        core["decision"] = "BET_CANDIDATE"
        core["decision_label"] = "CANDIDATO À ENTRADA"
        core["operational_alert"] = "Validar odd real da Pinnacle antes da entrada."

    strategy = build_ia_v26_output(payload, think, core)
    strategy_decision = (strategy.get("decision") or {}).get("decision")
    strategy_label = (strategy.get("decision") or {}).get("label")
    strategy_alert = strategy.get("operational_decision")

    return {
        "status": "ok",
        "version": VERSION,
        "strategy": strategy,
        "context_ia": think,
        "core": core,
        "decision": strategy_decision,
        "decision_label": strategy_label,
        "operational_alert": strategy_alert,
        "odds_cleaning": cleaned_odds,
        "odds_structure": odds_structure,
        "metadata": {
            "flow": "single_v26_flow_gpt_context_core_classification_v381_consistency",
            "engine_changed": False,
            "gpt_context_runs_with_core": True,
            "single_main_button": True,
        },
    }


@app.post("/analyze")
def analyze_match(payload: AnalyzeRequest) -> Dict[str, Any]:
    try:
        result = analyze(AnalysisInput(
            home_team=payload.home_team,
            away_team=payload.away_team,
            competition=payload.competition,
            mode=payload.mode,
            odds_text=payload.odds_text,
            context=payload.context,
        ))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    data = result.to_dict()
    best = data.get("best", {})
    stake = float(best.get("stake_units") or 0)
    classification = str(best.get("classification") or "")
    if stake <= 0 or classification in {"C", "D"}:
        data["decision"] = "NO_BET"
        data["decision_label"] = "NÃO APOSTAR"
        data["operational_alert"] = "Nenhum mercado passou nas travas V26 para entrada com stake."
    else:
        data["decision"] = "BET_CANDIDATE"
        data["decision_label"] = "CANDIDATO À ENTRADA"
        data["operational_alert"] = "Validar odd real da Pinnacle antes da entrada."
    return data


@app.get("/benchmarks")
def list_benchmarks() -> Dict[str, Any]:
    benchmarks = load_benchmarks(BENCHMARKS_PATH)
    return {
        "total": len(benchmarks),
        "benchmarks": [
            {
                "id": bm["id"],
                "name": bm["name"],
                "mode": bm["mode"],
                "expected_best_market_contains": bm["expected_best_market_contains"],
                "expected_class": bm["expected_class"],
            }
            for bm in benchmarks
        ],
    }


@app.get("/benchmarks/run", response_model=BenchmarkRunResponse)
def run_benchmarks() -> BenchmarkRunResponse:
    cases: List[BenchmarkCaseResult] = []
    for bm in load_benchmarks(BENCHMARKS_PATH):
        result = analyze(AnalysisInput(
            home_team=bm["home_team"],
            away_team=bm["away_team"],
            competition=bm["competition"],
            mode=bm["mode"],
            odds_text=bm["odds_text"],
            context=bm["context"],
        ))
        best = result.best
        notes: List[str] = []
        expected_market_ok = bm["expected_best_market_contains"].lower() in best.market.name.lower()
        expected_class_ok = best.classification == bm["expected_class"]
        passed = expected_market_ok and expected_class_ok

        if not expected_market_ok:
            notes.append("Mercado principal diferente do esperado.")
        if not expected_class_ok:
            notes.append("Classe diferente do esperado.")
        if "expected_ev" in bm and abs(best.ev_percent - bm["expected_ev"]) > 0.5:
            passed = False
            notes.append("EV fora da tolerância.")
        if "expected_ic" in bm and abs(best.ic - bm["expected_ic"]) > 2:
            passed = False
            notes.append("IC fora da tolerância.")
        if "expected_confidence" in bm and abs(best.confidence - bm["expected_confidence"]) > 2:
            passed = False
            notes.append("Confidence fora da tolerância.")
        if "expected_risk" in bm and abs(best.risk - bm["expected_risk"]) > 2:
            passed = False
            notes.append("Risk fora da tolerância.")

        cases.append(BenchmarkCaseResult(
            id=bm["id"],
            name=bm["name"],
            passed=passed,
            expected_best_market_contains=bm["expected_best_market_contains"],
            expected_class=bm["expected_class"],
            actual_best_market=best.market.name,
            actual_class=best.classification,
            actual_ev=best.ev_percent,
            actual_ic=best.ic,
            actual_confidence=best.confidence,
            actual_risk=best.risk,
            notes=notes,
        ))

    passed_count = sum(1 for c in cases if c.passed)
    total = len(cases)
    return BenchmarkRunResponse(
        passed=passed_count == total,
        total=total,
        passed_count=passed_count,
        failed_count=total - passed_count,
        cases=cases,
    )
