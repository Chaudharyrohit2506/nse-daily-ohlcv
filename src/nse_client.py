import io
import zipfile
import time
from pathlib import Path
from datetime import datetime
import requests
import pandas as pd

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/140 Safari/537.36",
    "Accept": "*/*",
    "Referer": "https://www.nseindia.com/",
    "Connection": "keep-alive",
}

def build_url(template: str, date_obj):
    return template.format(date=date_obj.strftime("%Y%m%d"))

def download_udiff(date_obj, url_template, timeout=45, retries=4, raw_dir="data/raw"):
    url = build_url(url_template, date_obj)
    Path(raw_dir).mkdir(parents=True, exist_ok=True)

    session = requests.Session()
    session.headers.update(HEADERS)

    last_error = None
    for attempt in range(1, retries + 1):
        try:
            r = session.get(url, timeout=timeout)
            if r.status_code == 404:
                raise FileNotFoundError(f"NSE archive not found: {url}")
            r.raise_for_status()

            content = r.content
            if not content[:2] == b"PK":
                raise ValueError("NSE response is not a ZIP archive; endpoint or access may have changed.")

            zip_path = Path(raw_dir) / f"BhavCopy_NSE_CM_{date_obj:%Y%m%d}.zip"
            zip_path.write_bytes(content)

            with zipfile.ZipFile(io.BytesIO(content)) as z:
                names = z.namelist()
                csv_names = [n for n in names if n.lower().endswith(".csv")]
                if not csv_names:
                    raise ValueError(f"No CSV found inside archive: {names}")
                csv_name = csv_names[0]
                raw_csv = z.read(csv_name)

            return pd.read_csv(io.BytesIO(raw_csv)), url, csv_name

        except Exception as e:
            last_error = e
            if attempt < retries:
                time.sleep(2 ** attempt)

    raise last_error
