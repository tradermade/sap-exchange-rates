# SAP S/4HANA Cloud Exchange Rates — TraderMade + Market Rates Management

Load TraderMade's daily closing exchange rates into **SAP S/4HANA Cloud, Public Edition**, automatically. One Python script fetches the day's close from the TraderMade REST API and uploads it to **SAP Market Rates Management (Bring Your Own Rates)**. S/4HANA's own import job then picks it up.

**Full walkthrough:** [How to Load Exchange Rates into SAP S/4HANA Cloud with an API](https://tradermade.com/tutorials/sap-s4hana-cloud-exchange-rates-api)

```text
TraderMade API  →  s4hana_cloud_rates.py  →  Market Rates Management  →  S/4HANA import job  →  Exchange rates
   (22:00 UTC close)      (your server)              (SAP BTP)                (S/4HANA Cloud)
```

## What's inside

| File | Purpose |
| --- | --- |
| `s4hana_cloud_rates.py` | The loader: fetches the daily close, checks it, and uploads it to Market Rates Management |
| `.env.example` | Template for your TraderMade and SAP credentials |
| `LICENSE` | MIT licence |

## Features

- **The daily close, done properly:** the mid rate at 22:00 UTC, fixed all year with no daylight saving drift.
- **Only finished days:** it never requests a day that hasn't closed yet.
- **Weekends handled:** TraderMade returns Friday's rates for a Saturday, so the script detects this and uploads nothing.
- **All or nothing:** missing pairs, duplicates or invalid rates stop the run, so a half-loaded month-end can't happen.
- **Clear errors:** if SAP rejects the upload, the script prints SAP's reason. Server errors and network failures are retried up to three times.
- **No dependencies:** Python standard library only.

## Prerequisites

- **Python 3.9+**
- **A TraderMade REST API key** with historical data access. [Get one here](https://tradermade.com/tutorials/how-to-signup-for-a-rest-plan-and-get-your-api-key).
- **SAP S/4HANA Cloud, Public Edition** with Market Rates Management switched on (scope item 83C, or 1S4 on older setups).
- **A Market Rates Management, Bring Your Own Rates subscription**, plus its upload credentials. The free plan is fine for testing; a daily feed needs the paid plan.
- **The currency pairs set up in S/4HANA** under *Assign Currency Notations – Datafeed*. See [Step 1 of the tutorial](https://tradermade.com/tutorials/sap-s4hana-cloud-exchange-rates-api).

## Quick start

```bash
git clone https://github.com/tradermade/sap-exchange-rates.git
cd sap-exchange-rates
cp .env.example .env        # then edit .env and add your values
```

**macOS / Linux**

```bash
set -a; source .env; set +a
python3 s4hana_cloud_rates.py
```

**Windows (PowerShell)**

```powershell
Get-Content .env | Where-Object { $_ -match '^\w+=.+' } | ForEach-Object { $k, $v = $_ -split '=', 2; Set-Item "env:$k" $v }
python s4hana_cloud_rates.py
```

## Configuration

### Credentials (`.env`)

| Variable | Description |
| --- | --- |
| `TRADERMADE_API_KEY` | Your TraderMade REST API key |
| `MRM_UPLOAD_URL` | Market Rates Management upload URL |
| `MRM_TOKEN_URL` | OAuth token URL, usually your auth URL followed by `/oauth/token` |
| `MRM_CLIENT_ID` | Client ID from your Market Rates Management credentials |
| `MRM_CLIENT_SECRET` | Client secret from the same credentials |
| `MRM_RESOURCE` | Only if your credentials came from SAP Cloud Identity Services; otherwise leave it empty |

### Settings (top of `s4hana_cloud_rates.py`)

| Setting | Default | Description |
| --- | --- | --- |
| `PAIRS` | `EURUSD, GBPUSD, USDJPY, USDTRY, USDIDR` | Currency pairs to load, as TraderMade quotes them |
| `PROVIDER_CODE` | `Y001` | Must match the data provider in S/4HANA |
| `DATA_SOURCE` | `BYOR` | Required by S/4HANA Cloud |
| `PROPERTY` | `C` | Must match the property S/4HANA maps to your rate type, for example `M` |

To add a currency, add it to `PAIRS` **and** add a matching row in *Assign Currency Notations – Datafeed* in S/4HANA. Both are needed.

## Example output

```text
$ python3 s4hana_cloud_rates.py
MRM upload HTTP 201 for 5 rates dated 2026-09-30
```

On a weekend:

```text
Market closed on 2026-10-03; nothing to upload
```

When SAP rejects the upload, the script exits with code `1` and prints SAP's reason:

```text
MRM upload failed: HTTP 400
{ ...SAP's explanation... }
```

## Scheduling

Run the script after the 22:00 UTC close, Monday to Friday. Example crontab, with the server clock on UTC:

```cron
15 22 * * 1-5 cd /opt/sap-exchange-rates && set -a && . ./.env && set +a && /usr/bin/python3 s4hana_cloud_rates.py >> rates.log 2>&1
```

Then, in S/4HANA Cloud, create a daily job from the template **Import Exchange Rates from MRM** in *Schedule Treasury Back Office Jobs*. S/4HANA schedules in local time, so pick a time that's after the upload all year round, for example 02:00 for Central Europe, running Tuesday to Saturday.

The script exits with `1` on any failure, so you can alert on it.

## Troubleshooting

| Problem | Check this |
| --- | --- |
| `401 Unauthorized` | Client ID, secret, and that `MRM_TOKEN_URL` ends in `/oauth/token` |
| Upload succeeds but nothing appears in S/4HANA | `DATA_SOURCE` is `BYOR`, and the pairs, provider code and property match the datafeed settings |
| Rates out by 100 times | The datafeed ratio in S/4HANA isn't 1:1. TraderMade quotes per 1 unit, and S/4HANA ignores uploaded factors |
| An old or odd rate keeps coming back | A test record with a future date was uploaded. Never test with future dates on the instance production reads from |

## Notes

- This is a general integration pattern, not a packaged SAP connector. SAP app names and setup screens vary between releases, so check the SAP configuration against your own system.
- `.env` is git-ignored. Never commit real keys.

## Resources

- [Tutorial: How to Load Exchange Rates into SAP S/4HANA Cloud with an API](https://tradermade.com/tutorials/sap-s4hana-cloud-exchange-rates-api)
- [TraderMade REST API documentation](https://tradermade.com/docs/restful-api)
- [SAP Market Rates Management, Bring Your Own Rates documentation](https://help.sap.com/docs/mrm-byor)

## License

MIT. See [LICENSE](LICENSE).
