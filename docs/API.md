# REST API

Bazowy adres: `http://localhost:8000`. Interaktywna dokumentacja OpenAPI: **`/docs`** (Swagger UI), `/redoc`,
schemat: `/openapi.json`. Błędy: `404 {"detail": …}` (brak zasobu), `422 {"detail": …}` (walidacja domenowa/schematu).

## System
| Metoda | Ścieżka | Opis |
|---|---|---|
| GET | `/api/health` | status, aktywny dostawca LLM, model, transport sandboksa |

## Artykuły
| Metoda | Ścieżka | Opis |
|---|---|---|
| GET | `/api/articles?status=draft\|in_review\|verified` | lista z licznikami werdyktów (`claim_counts`, wg werdyktu efektywnego) |
| POST | `/api/articles` | `{title, body, author}` → 201 |
| GET | `/api/articles/{id}` | artykuł z treścią |
| PATCH | `/api/articles/{id}` | `{title?, body?, author?, status?}` — zmiana treści usuwa twierdzenia (offsety przestałyby pasować) |
| DELETE | `/api/articles/{id}` | 204 |
| GET | `/api/articles/{id}/claims` | twierdzenia ze źródłami, cytatami, ocenami i historią decyzji |
| POST | `/api/articles/{id}/claims` | ręczne dodanie twierdzeń `[{text, start_offset, end_offset, category}]` |
| GET | `/api/articles/{id}/report?format=md\|json` | raport weryfikacji (Markdown do pobrania albo JSON) |

## Twierdzenia, źródła, decyzje redaktora
| Metoda | Ścieżka | Opis |
|---|---|---|
| GET / PATCH / DELETE | `/api/claims/{id}` | szczegóły / zmiana treści lub kategorii / usunięcie |
| GET | `/api/claims/{id}/decisions` | historia decyzji redaktora |
| POST | `/api/claims/{id}/decisions` | `{editor, override_verdict: potwierdzone\|wątpliwe\|fałszywe\|null, note}` — nadpisanie werdyktu |
| GET | `/api/sources`, `/api/sources/{id}` | źródła z rozpisaniem oceny i flagami injection |

## Agent i audyt
| Metoda | Ścieżka | Opis |
|---|---|---|
| POST | `/api/articles/{id}/verify` | uruchamia weryfikację w tle → 202 `AgentRun`. Body opcjonalne `{idempotency_key}`; trwający przebieg albo ten sam klucz zwraca istniejący przebieg |
| POST | `/api/claims/{id}/reverify` | ponowna weryfikacja jednego twierdzenia (źródła agenta czyszczone, decyzje redaktora zostają) |
| GET | `/api/runs?article_id=&limit=` | przebiegi (najnowsze pierwsze) |
| GET | `/api/runs/{run_id}` | status (`queued`, `running`, `completed`, `failed`, `budget_exceeded`), postęp, tokeny, koszt, liczba narzędzi |
| GET | `/api/runs/{run_id}/events?after_id=` | zdarzenia audytu (prompty, wywołania narzędzi, odrzucone próby, werdykty) |
| GET | `/api/runs/{run_id}/stream` | **Server-Sent Events**: `event: agent` (zdarzenie) … `event: end` (stan końcowy przebiegu) |

## Przykłady
```bash
# nowy artykuł i weryfikacja
curl -s -X POST localhost:8000/api/articles -H 'Content-Type: application/json' \
  -d '{"title":"Test","author":"Redakcja","body":"Do NATO Polska wstąpiła w 2001 roku."}'
curl -s -X POST localhost:8000/api/articles/5/verify -H 'Content-Type: application/json' -d '{"idempotency_key":"art5-v1"}'
curl -N localhost:8000/api/runs/<run_id>/stream            # postęp na żywo
curl -s localhost:8000/api/articles/5/claims | python -m json.tool
curl -s -X POST localhost:8000/api/claims/12/decisions -H 'Content-Type: application/json' \
  -d '{"editor":"red. Nowak","override_verdict":"wątpliwe","note":"czekamy na komentarz MON"}'
curl -s 'localhost:8000/api/articles/5/report?format=md' -o raport.md
```

Fragment odpowiedzi `GET /api/articles/2/claims`:
```json
{"id": 6, "text": "Do NATO Polska wstąpiła w 2001 roku.", "start_offset": 114, "end_offset": 150,
 "category": "datowe", "verdict": "fałszywe", "effective_verdict": "fałszywe", "confidence": 0.807,
 "rationale": "Wiarygodne źródło podaje inne dane niż twierdzenie ([S1]).",
 "sources": [{"relation": "contradicts", "quote_verified": true,
   "quote": "Polska jest członkiem Sojuszu Północnoatlantyckiego (NATO) od 12 marca 1999 r.",
   "source": {"final_url": "https://www.gov.pl/web/obrona-narodowa/polska-w-nato", "credibility_score": 85,
              "source_type": "government", "injection_flags": [],
              "credibility_breakdown": {"deterministic_score": 85, "llm_adjustment": 0, "corroboration": 0}}}],
 "decisions": []}
```
