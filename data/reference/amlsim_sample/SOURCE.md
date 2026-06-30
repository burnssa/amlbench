# AMLSim reference sample (vendored)

These files are **verbatim sample output and parameters from IBM AMLSim**, vendored
here as the reference fixture for the fidelity check in `tools/amlsim_fidelity.py`.

- Source: https://github.com/IBM/AMLSim (`sample/outputs/` and `sample/paramFiles/`)
- Upstream commit: `7338a4bcb1af9bcfea2201ad7daccfe2a4d569ca`
- License: Apache-2.0 (see repository `NOTICE` for attribution + citation)

| file | what it is |
|---|---|
| `tx.csv` | real AMLSim Java/MASON non-cash transaction log (WIRE/CREDIT/CHECK/DEPOSIT) |
| `cash_tx.csv` | real AMLSim cash transaction log (CASH-IN/CASH-OUT) |
| `accounts.csv` | real AMLSim account table (balance, country, business, suspicious, isFraud) |
| `alerts.csv` | real AMLSim alert output (typology in `CHECK_NAME`, `Escalated_To_Case_Investigation`) |
| `alertPatterns.csv` | the AMLSim typology-generation contract (type, accounts, amount, period, is_sar) |

These are **genuine AMLSim Java/MASON output** — not produced by Cupel — so the
fidelity check compares Cupel's pure-Python substrate against the real thing
without needing a JVM or a legacy `networkx==1.11` environment.
