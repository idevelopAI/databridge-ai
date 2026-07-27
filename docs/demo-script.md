# DataBridge AI Demo Script

Target duration: 75 seconds

## Setup

```bash
./scripts/demo.sh
```

Open `http://localhost:8601` and expand the sidebar. Confirm that it shows:

- `Aufgezeichnete Demo · Keine Modellaufrufe`
- `PostgreSQL verbunden · Nur Lesezugriff`

Only the included synthetic database is used.

## Sequence

| Time | Action | Evidence |
| ---: | --- | --- |
| 0–7 s | Show the application and recorded-mode status. | No API key or model call is required. |
| 7–15 s | Ask `Zeige das gesamte Projektbudget pro Abteilung absteigend.` | A verified answer and structured query result appear. |
| 15–25 s | Expand the query result and show the table. | Five department totals and CSV export are available. |
| 25–35 s | Open the `Diagramm` tab. | The same result is rendered as a bar chart. |
| 35–45 s | Open the `SQL` tab. | The executed read-only SQL is inspectable. |
| 45–55 s | Ask `Wer verdient am meisten im Engineering?` | The application asks which salary basis is intended. |
| 55–65 s | Reply `Bruttojahresgehalt.` | The direct salary value is masked as `***`. |
| 65–75 s | Ask `Lösche alle Mitarbeiter.` | The request is rejected before agent or SQL execution. |

## Verification

The demo must not show `.env`, terminal output, browser history, credentials, real
records, or external accounts. Request IDs are random local correlation values,
not secrets. Stop and remove the isolated demo after recording:

```bash
./scripts/demo.sh down
```
