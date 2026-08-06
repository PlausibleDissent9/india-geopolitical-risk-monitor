# Data-platform listing bundles (V16)

Everything below is prepared to the point where the founder's part is
one account login and one upload/submission each. Per the hard
limits, no account is ever created and no listing is ever submitted
by a machine — these bundles are the machine's half of the deal.

| Platform | Bundle | Founder's step |
|---|---|---|
| Kaggle | `kaggle_dataset_metadata.json` + upload `docs/data/history.csv` | Create dataset at kaggle.com/datasets, paste metadata, upload CSV, set weekly update reminder |
| DBnomics | `dbnomics_submission.md` | Open a provider request per their contribution guide, paste the text |
| Nasdaq Data Link | `nasdaq_data_link_pitch.md` | Submit via their contributor form |
| R users | `../r/igrm.R` (single-file client, no package bureaucracy) | Nothing — it ships in the repo; CRAN packaging can follow if demand appears |

Shared facts every listing states: data CC BY 4.0, code MIT, daily
refresh by ~06:00 IST, series since 2017, salience-not-risk construct
definition verbatim, citation string, DOI when minted.
