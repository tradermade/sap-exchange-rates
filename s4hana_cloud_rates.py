import base64
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from decimal import Decimal

TM_URL = "https://marketdata.tradermade.com/api/v1/historical"

# Pairs as TraderMade quotes them: 1 base = rate x quote
PAIRS = ["EURUSD", "GBPUSD", "USDJPY", "USDTRY", "USDIDR"]

# These three must match "Assign Currency Notations - Datafeed" in S/4HANA Cloud
PROVIDER_CODE = "Y001"
DATA_SOURCE = "BYOR"   # S/4HANA Cloud only accepts BYOR here
PROPERTY = "C"         # the property your datafeed maps to rate type M

CLOSE_TIME = "22:00:00"       # MRM wants GMT, and the close is 22:00 UTC
MAX_RECORDS_PER_UPLOAD = 100  # free plan; the default plan allows 1,500


def last_closed_day():
    """The most recent date whose 22:00 UTC close has already happened."""
    now = datetime.now(timezone.utc)
    if now.hour >= 22:
        return now.date()
    return now.date() - timedelta(days=1)


def fetch_rates(day):
    params = urllib.parse.urlencode({
        "currency": ",".join(PAIRS),
        "date": day.isoformat(),
        "api_key": os.environ["TRADERMADE_API_KEY"],
    })
    with urllib.request.urlopen(f"{TM_URL}?{params}", timeout=30) as response:
        return json.load(response)


def build_records(payload, day):
    """Turn a TraderMade /historical response into MRM upload records."""
    records = []
    returned_pairs = set()

    for quote in payload.get("quotes", []):
        if "error" in quote:
            raise ValueError(f"TraderMade error: {quote}")

        base = quote["base_currency"]
        quote_cur = quote["quote_currency"]
        pair = base + quote_cur

        if pair not in PAIRS:
            raise ValueError(f"Unexpected pair: {pair}")
        if pair in returned_pairs:
            raise ValueError(f"Duplicate quote for {pair}")

        rate = Decimal(str(quote["close"]))
        if not rate.is_finite() or rate <= 0:
            raise ValueError(f"Invalid rate for {pair}: {rate}")

        returned_pairs.add(pair)
        records.append({
            "providerCode": PROVIDER_CODE,
            "marketDataSource": DATA_SOURCE,
            "marketDataCategory": "01",  # 01 = exchange rates
            "key1": base,
            "key2": quote_cur,
            "marketDataProperty": PROPERTY,
            "effectiveDate": day.isoformat(),
            "effectiveTime": CLOSE_TIME,
            "marketDataValue": float(rate),
            "securityCurrency": None,
            "fromFactor": None,
            "toFactor": None,
        })

    missing = set(PAIRS) - returned_pairs
    if missing:
        raise ValueError(f"Missing pairs: {', '.join(sorted(missing))}")
    if len(records) > MAX_RECORDS_PER_UPLOAD:
        raise ValueError(f"{len(records)} records is over the per-upload limit")

    return records


def get_token():
    """Swap the client ID and secret for a short-lived access token."""
    form = {"grant_type": "client_credentials"}
    if os.environ.get("MRM_RESOURCE"):  # only for SAP Cloud Identity Services
        form["resource"] = os.environ["MRM_RESOURCE"]

    credentials = f"{os.environ['MRM_CLIENT_ID']}:{os.environ['MRM_CLIENT_SECRET']}"
    request = urllib.request.Request(
        os.environ["MRM_TOKEN_URL"],
        data=urllib.parse.urlencode(form).encode(),
        headers={
            "Authorization": "Basic " + base64.b64encode(credentials.encode()).decode(),
            "Content-Type": "application/x-www-form-urlencoded",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)["access_token"]


def upload_rates(records, token):
    """POST the records to MRM. Returns (status, body), including on errors."""
    request = urllib.request.Request(
        os.environ["MRM_UPLOAD_URL"],
        data=json.dumps(records).encode("utf-8"),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return response.status, response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8")  # keep SAP's explanation


def main():
    day = last_closed_day()

    try:
        payload = fetch_rates(day)

        # Weekend: TraderMade returns Friday's bar, so the dates won't match
        if payload.get("date") != day.isoformat():
            print(f"Market closed on {day}; nothing to upload")
            return

        records = build_records(payload, day)
        token = get_token()

        last_error = ""
        for attempt in range(3):
            try:
                status, body = upload_rates(records, token)
            except urllib.error.URLError as error:  # network failure: retry
                status, body = None, str(error)

            if status in (200, 201):
                print(f"MRM upload HTTP {status} for {len(records)} rates dated {day}")
                if body:
                    print(body)
                return

            if status is not None and 400 <= status < 500:
                print(f"MRM upload failed: HTTP {status}", file=sys.stderr)
                if body:
                    print(body, file=sys.stderr)
                sys.exit(1)

            # 5xx or network error: SAP doesn't count these against your quota
            last_error = f"HTTP {status}: {body}" if status else body
            if attempt < 2:
                time.sleep(2 ** attempt)

        print(f"MRM upload failed after 3 attempts. Last error: {last_error}", file=sys.stderr)
        sys.exit(1)

    except (urllib.error.URLError, ValueError, KeyError, json.JSONDecodeError) as error:
        print(f"Failed: {error}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
