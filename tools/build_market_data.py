from __future__ import annotations

import argparse
import json
import math
import re
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "static" / "data"
CATALOG_PATH = DATA_DIR / "catalog.json"
MARKET_DATA_PATH = DATA_DIR / "market_data.json"

SEC_USER_AGENT = "hellozip us-stock-fundamental-dashboard contact@example.com"
YAHOO_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
NASDAQ_HEADERS = {
    "User-Agent": YAHOO_UA,
    "Accept": "application/json, text/plain, */*",
    "Origin": "https://www.nasdaq.com",
    "Referer": "https://www.nasdaq.com/",
}


CONCEPTS = {
    "revenue": {
        "labels": ["营收TTM", "Revenue TTM"],
        "candidates": [
            ("us-gaap", "RevenueFromContractWithCustomerExcludingAssessedTax"),
            ("us-gaap", "RevenueFromContractWithCustomerIncludingAssessedTax"),
            ("us-gaap", "Revenues"),
            ("us-gaap", "SalesRevenueNet"),
            ("ifrs-full", "Revenue"),
            ("ifrs-full", "RevenueFromContractsWithCustomers"),
        ],
    },
    "gross_profit": {
        "labels": ["毛利润TTM", "Gross Profit TTM"],
        "candidates": [("us-gaap", "GrossProfit"), ("ifrs-full", "GrossProfit")],
    },
    "operating_income": {
        "labels": ["经营利润TTM", "Operating Income TTM"],
        "candidates": [("us-gaap", "OperatingIncomeLoss"), ("ifrs-full", "OperatingProfitLoss")],
    },
    "net_income": {
        "labels": ["净利润TTM", "Net Income TTM"],
        "candidates": [
            ("us-gaap", "NetIncomeLoss"),
            ("us-gaap", "ProfitLoss"),
            ("us-gaap", "NetIncomeLossAvailableToCommonStockholdersBasic"),
            ("ifrs-full", "ProfitLoss"),
            ("ifrs-full", "ProfitLossAttributableToOwnersOfParent"),
        ],
    },
    "operating_cash_flow": {
        "labels": ["经营现金流TTM", "Operating Cash Flow TTM"],
        "candidates": [
            ("us-gaap", "NetCashProvidedByUsedInOperatingActivities"),
            ("ifrs-full", "CashFlowsFromUsedInOperatingActivities"),
        ],
    },
    "capex": {
        "labels": ["资本开支TTM", "Capex TTM"],
        "candidates": [
            ("us-gaap", "PaymentsToAcquirePropertyPlantAndEquipment"),
            ("ifrs-full", "PurchaseOfPropertyPlantAndEquipment"),
        ],
    },
    "assets": {
        "labels": ["总资产", "Assets"],
        "candidates": [("us-gaap", "Assets"), ("ifrs-full", "Assets")],
    },
    "equity": {
        "labels": ["股东权益", "Equity"],
        "candidates": [
            ("us-gaap", "StockholdersEquity"),
            ("us-gaap", "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"),
            ("ifrs-full", "Equity"),
            ("ifrs-full", "EquityAttributableToOwnersOfParent"),
        ],
    },
    "shares": {
        "labels": ["股本/流通股", "Shares"],
        "candidates": [
            ("dei", "EntityCommonStockSharesOutstanding"),
            ("us-gaap", "WeightedAverageNumberOfDilutedSharesOutstanding"),
            ("us-gaap", "WeightedAverageNumberOfSharesOutstandingBasic"),
            ("ifrs-full", "WeightedAverageNumberOfOrdinarySharesOutstandingBasic"),
        ],
    },
    "eps_diluted": {
        "labels": ["摊薄EPS", "Diluted EPS"],
        "candidates": [
            ("us-gaap", "EarningsPerShareDiluted"),
            ("ifrs-full", "DilutedEarningsLossPerShare"),
        ],
    },
}


def request_json(url: str, headers: dict[str, str] | None = None, timeout: int = 30) -> Any:
    req = Request(url, headers=headers or {"User-Agent": YAHOO_UA})
    with urlopen(req, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def parse_number(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if not text or text.upper() in {"N/A", "NA", "--"}:
        return None
    text = text.replace("$", "").replace(",", "").replace("%", "").strip()
    match = re.search(r"-?\d+(?:\.\d+)?", text)
    if not match:
        return None
    return float(match.group(0))


def safe_divide(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator in (None, 0):
        return None
    return numerator / denominator


def pct(value: float | None) -> float | None:
    if value is None:
        return None
    return round(value * 100, 2)


def amount(value: float | None) -> float | None:
    if value is None:
        return None
    return round(value, 2)


def fmt_amount(value: float | None) -> str:
    if value is None:
        return "-"
    abs_value = abs(value)
    if abs_value >= 1e12:
        return f"{value / 1e12:.2f}万亿"
    if abs_value >= 1e8:
        return f"{value / 1e8:.2f}亿"
    if abs_value >= 1e6:
        return f"{value / 1e6:.2f}百万"
    return f"{value:,.0f}"


def fmt_ratio(value: float | None) -> str:
    if value is None or not math.isfinite(value):
        return "-"
    return f"{value:.2f}x"


def load_ticker_map(cache_dir: Path, refresh: bool = False) -> dict[str, dict[str, Any]]:
    cache_path = cache_dir / "sec_company_tickers.json"
    if cache_path.exists() and not refresh:
        raw = json.loads(cache_path.read_text(encoding="utf-8"))
    else:
        raw = request_json(
            "https://www.sec.gov/files/company_tickers.json",
            headers={"User-Agent": SEC_USER_AGENT, "Accept-Encoding": "identity"},
            timeout=45,
        )
        cache_path.write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")
    mapping: dict[str, dict[str, Any]] = {}
    for item in raw.values():
        ticker = str(item.get("ticker", "")).upper()
        if ticker:
            mapping[ticker] = item
    return mapping


def cik_to_str(cik: int | str) -> str:
    return str(cik).zfill(10)


def sec_get(cache_dir: Path, kind: str, cik: str, refresh: bool = False) -> dict[str, Any]:
    cache_path = cache_dir / f"sec_{kind}_{cik}.json"
    if cache_path.exists() and not refresh:
        return json.loads(cache_path.read_text(encoding="utf-8"))
    if kind == "facts":
        url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
    elif kind == "submissions":
        url = f"https://data.sec.gov/submissions/CIK{cik}.json"
    else:
        raise ValueError(kind)
    payload = request_json(url, headers={"User-Agent": SEC_USER_AGENT, "Accept-Encoding": "identity"}, timeout=60)
    cache_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    time.sleep(0.12)
    return payload


def concept_entries(facts: dict[str, Any], candidates: list[tuple[str, str]]) -> list[dict[str, Any]]:
    available: list[list[dict[str, Any]]] = []
    for taxonomy, concept in candidates:
        node = facts.get("facts", {}).get(taxonomy, {}).get(concept)
        if not node:
            continue
        units = node.get("units", {})
        for unit_name in ["USD", "USD/shares", "shares"]:
            if unit_name in units:
                entries = [dict(entry, taxonomy=taxonomy, concept=concept, unit=unit_name) for entry in units[unit_name]]
                entries = [entry for entry in entries if entry.get("val") is not None and entry.get("end")]
                if entries:
                    available.append(entries)
                    break
        for unit_name, unit_entries in units.items():
            if any(unit_name == entries[0].get("unit") for entries in available if entries):
                continue
            entries = [dict(entry, taxonomy=taxonomy, concept=concept, unit=unit_name) for entry in unit_entries]
            entries = [entry for entry in entries if entry.get("val") is not None and entry.get("end")]
            if entries:
                available.append(entries)
                break
    if not available:
        return []
    return sorted(available, key=lambda entries: entry_rank(latest_point(entries) or {}))[-1]


def days_between(start: str | None, end: str | None) -> int | None:
    if not start or not end:
        return None
    try:
        a = datetime.fromisoformat(start)
        b = datetime.fromisoformat(end)
    except ValueError:
        return None
    return (b - a).days


def entry_rank(entry: dict[str, Any]) -> tuple[str, str, str]:
    return (entry.get("end", ""), entry.get("filed", ""), entry.get("accn", ""))


def latest_point(entries: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not entries:
        return None
    return sorted(entries, key=entry_rank)[-1]


def latest_annual(entries: list[dict[str, Any]]) -> dict[str, Any] | None:
    annual: list[dict[str, Any]] = []
    for entry in entries:
        duration = days_between(entry.get("start"), entry.get("end"))
        form = entry.get("form", "")
        fp = entry.get("fp", "")
        if duration and 290 <= duration <= 430:
            annual.append(entry)
        elif fp == "FY" or form in {"10-K", "20-F", "40-F"}:
            annual.append(entry)
    if not annual:
        return latest_point(entries)
    return sorted(annual, key=entry_rank)[-1]


def latest_ttm(entries: list[dict[str, Any]]) -> dict[str, Any] | None:
    duration_entries = [entry for entry in entries if days_between(entry.get("start"), entry.get("end"))]
    quarterlies = []
    for entry in duration_entries:
        duration = days_between(entry.get("start"), entry.get("end"))
        if duration and 45 <= duration <= 140:
            quarterlies.append(entry)
    quarterlies = sorted(quarterlies, key=entry_rank)
    deduped: dict[str, dict[str, Any]] = {}
    for entry in quarterlies:
        deduped[entry["end"]] = entry
    quarterlies = sorted(deduped.values(), key=entry_rank)
    if len(quarterlies) >= 4:
        recent = quarterlies[-4:]
        return {
            "val": sum(float(entry["val"]) for entry in recent),
            "start": recent[0].get("start"),
            "end": recent[-1].get("end"),
            "filed": recent[-1].get("filed"),
            "form": "TTM",
            "source_concepts": list({entry.get("concept") for entry in recent}),
            "unit": recent[-1].get("unit"),
        }
    annual = latest_annual(entries)
    if annual:
        result = dict(annual)
        result["form"] = f"{annual.get('form', '')} annual".strip()
        return result
    return None


def latest_filing(submissions: dict[str, Any]) -> dict[str, Any] | None:
    recent = submissions.get("filings", {}).get("recent", {})
    forms = recent.get("form", [])
    dates = recent.get("filingDate", [])
    reports = recent.get("reportDate", [])
    accession = recent.get("accessionNumber", [])
    docs = recent.get("primaryDocument", [])
    wanted = {"10-Q", "10-K", "20-F", "40-F", "6-K"}
    for index, form in enumerate(forms):
        if form not in wanted:
            continue
        accn = accession[index] if index < len(accession) else ""
        cik = str(submissions.get("cik", "")).lstrip("0")
        doc = docs[index] if index < len(docs) else ""
        accession_clean = accn.replace("-", "")
        url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession_clean}/{doc}" if cik and accn and doc else ""
        return {
            "form": form,
            "filing_date": dates[index] if index < len(dates) else "",
            "report_date": reports[index] if index < len(reports) else "",
            "accession": accn,
            "url": url,
        }
    return None


def yahoo_chart(ticker: str, range_value: str = "1y") -> dict[str, Any] | None:
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{quote(ticker)}?range={range_value}&interval=1d&events=history"
    try:
        payload = request_json(url, headers={"User-Agent": YAHOO_UA}, timeout=45)
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError):
        return None
    results = payload.get("chart", {}).get("result") or []
    return results[0] if results else None


def nasdaq_summary(ticker: str) -> dict[str, Any]:
    url = f"https://api.nasdaq.com/api/quote/{quote(ticker)}/summary?assetclass=stocks"
    try:
        payload = request_json(url, headers=NASDAQ_HEADERS, timeout=45)
    except Exception:
        return {}
    data = payload.get("data", {})
    summary = data.get("summaryData", {}) or {}
    out: dict[str, Any] = {"symbol": data.get("symbol")}
    for key, node in summary.items():
        out[key] = parse_number(node.get("value") if isinstance(node, dict) else node)
    out["raw"] = {
        key: (node.get("value") if isinstance(node, dict) else node)
        for key, node in summary.items()
    }
    return out


def volatility_from_chart(chart: dict[str, Any] | None) -> dict[str, Any]:
    if not chart:
        return {"price": None, "currency": "USD", "history": [], "volatility": {}}
    meta = chart.get("meta", {})
    timestamps = chart.get("timestamp") or []
    quote_data = (chart.get("indicators", {}).get("quote") or [{}])[0]
    closes = quote_data.get("close") or []
    volumes = quote_data.get("volume") or []
    history = []
    for ts, close, volume in zip(timestamps, closes, volumes):
        if close is None:
            continue
        history.append(
            {
                "date": datetime.fromtimestamp(ts, timezone.utc).date().isoformat(),
                "close": round(float(close), 4),
                "volume": int(volume or 0),
            }
        )
    price = meta.get("regularMarketPrice") or (history[-1]["close"] if history else None)

    def calc_vol(days: int) -> float | None:
        subset = history[-(days + 1) :]
        if len(subset) < max(10, min(days, 30)):
            return None
        returns = []
        for prev, cur in zip(subset, subset[1:]):
            if prev["close"] > 0 and cur["close"] > 0:
                returns.append(math.log(cur["close"] / prev["close"]))
        if len(returns) < 2:
            return None
        return statistics.stdev(returns) * math.sqrt(252)

    def max_drawdown(days: int) -> float | None:
        subset = history[-days:]
        if not subset:
            return None
        peak = subset[0]["close"]
        worst = 0.0
        for item in subset:
            peak = max(peak, item["close"])
            if peak:
                worst = min(worst, item["close"] / peak - 1)
        return worst

    def volume_ratio(days: int = 20) -> float | None:
        subset = history[-days:]
        if len(subset) < 5:
            return None
        vols = [item["volume"] for item in subset if item["volume"]]
        if len(vols) < 5:
            return None
        avg = statistics.mean(vols[:-1]) if len(vols) > 1 else None
        if not avg:
            return None
        return vols[-1] / avg

    return {
        "price": amount(price),
        "currency": meta.get("currency", "USD"),
        "exchange": meta.get("exchangeName"),
        "regular_market_time": meta.get("regularMarketTime"),
        "history": history[-130:],
        "volatility": {
            "30日年化波动率": pct(calc_vol(30)),
            "90日年化波动率": pct(calc_vol(90)),
            "90日最大回撤": pct(max_drawdown(90)),
            "20日成交量倍率": amount(volume_ratio(20)),
        },
    }


def sec_financials_for_ticker(ticker: str, cache_dir: Path, ticker_map: dict[str, dict[str, Any]], refresh: bool) -> dict[str, Any]:
    item = ticker_map.get(ticker.upper())
    if not item:
        return {"ticker": ticker, "error": "SEC CIK 未找到"}
    cik = cik_to_str(item["cik_str"])
    submissions = sec_get(cache_dir, "submissions", cik, refresh=refresh)
    facts = sec_get(cache_dir, "facts", cik, refresh=refresh)
    result: dict[str, Any] = {
        "ticker": ticker,
        "cik": cik,
        "sec_name": item.get("title"),
        "latest_filing": latest_filing(submissions),
        "metrics": {},
        "raw_sources": {
            "sec_submissions": f"https://data.sec.gov/submissions/CIK{cik}.json",
            "sec_companyfacts": f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json",
        },
    }

    for metric, config in CONCEPTS.items():
        entries = concept_entries(facts, config["candidates"])
        if metric in {"assets", "equity", "shares", "eps_diluted"}:
            entry = latest_point(entries)
        else:
            entry = latest_ttm(entries)
        if not entry:
            result["metrics"][metric] = {"value": None}
            continue
        result["metrics"][metric] = {
            "value": amount(float(entry["val"])),
            "end": entry.get("end"),
            "filed": entry.get("filed"),
            "form": entry.get("form"),
            "unit": entry.get("unit"),
            "concept": entry.get("concept") or (entry.get("source_concepts") or [None])[0],
        }
    return result


def build_company_market_data(ticker: str, cache_dir: Path, ticker_map: dict[str, dict[str, Any]], refresh: bool) -> dict[str, Any]:
    sec = sec_financials_for_ticker(ticker, cache_dir, ticker_map, refresh)
    chart = volatility_from_chart(yahoo_chart(ticker, "1y"))
    nasdaq = nasdaq_summary(ticker)

    metrics = sec.get("metrics", {})
    revenue = metrics.get("revenue", {}).get("value")
    gross_profit = metrics.get("gross_profit", {}).get("value")
    operating_income = metrics.get("operating_income", {}).get("value")
    net_income = metrics.get("net_income", {}).get("value")
    ocf = metrics.get("operating_cash_flow", {}).get("value")
    capex = metrics.get("capex", {}).get("value")
    equity = metrics.get("equity", {}).get("value")
    shares = metrics.get("shares", {}).get("value")
    price = chart.get("price")
    units = {key: (metrics.get(key, {}) or {}).get("unit") for key in metrics}

    def same_unit(*keys: str) -> bool:
        present = [units.get(key) for key in keys if metrics.get(key, {}).get("value") is not None]
        return bool(present) and len(set(present)) == 1

    def usd_unit(key: str) -> bool:
        return units.get(key) == "USD"

    market_cap = nasdaq.get("MarketCap")
    if market_cap is None and price is not None and shares:
        market_cap = price * shares
    free_cash_flow = None
    free_cash_flow_unit = units.get("operating_cash_flow")
    if ocf is not None and capex is not None and same_unit("operating_cash_flow", "capex"):
        free_cash_flow = ocf - abs(capex)

    profitability = {
        "毛利率": pct(safe_divide(gross_profit, revenue)) if same_unit("gross_profit", "revenue") else None,
        "经营利润率": pct(safe_divide(operating_income, revenue)) if same_unit("operating_income", "revenue") else None,
        "净利率": pct(safe_divide(net_income, revenue)) if same_unit("net_income", "revenue") else None,
        "自由现金流率": pct(safe_divide(free_cash_flow, revenue)) if free_cash_flow is not None and free_cash_flow_unit == units.get("revenue") else None,
        "ROE": pct(safe_divide(net_income, equity)) if same_unit("net_income", "equity") else None,
    }
    valuation = {
        "市值": amount(market_cap),
        "P/S": amount(safe_divide(market_cap, revenue)) if usd_unit("revenue") else None,
        "P/E": amount(safe_divide(market_cap, net_income)) if usd_unit("net_income") else None,
        "P/FCF": amount(safe_divide(market_cap, free_cash_flow)) if free_cash_flow is not None and free_cash_flow_unit == "USD" else None,
        "价格": price,
        "52周高点": nasdaq.get("FiftTwoWeekHighLow"),
        "估值来源": "Nasdaq市值 + SEC TTM财务；缺失时使用Yahoo价格×SEC股本估算",
    }

    return {
        "ticker": ticker,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "latest_report": sec.get("latest_filing"),
        "financials": {
            "营收TTM": amount(revenue),
            "毛利润TTM": amount(gross_profit),
            "经营利润TTM": amount(operating_income),
            "净利润TTM": amount(net_income),
            "经营现金流TTM": amount(ocf),
            "自由现金流TTM": amount(free_cash_flow),
            "股东权益": amount(equity),
            "股本/流通股": amount(shares),
        },
        "financial_units": {key: unit for key, unit in units.items() if unit},
        "profitability": profitability,
        "valuation": valuation,
        "volatility": chart.get("volatility", {}),
        "price_history": chart.get("history", []),
        "source_notes": {
            "sec_name": sec.get("sec_name"),
            "sec_error": sec.get("error"),
            "sec_sources": sec.get("raw_sources"),
            "price_source": "Yahoo Finance chart API",
            "nasdaq_source": f"https://api.nasdaq.com/api/quote/{ticker}/summary?assetclass=stocks",
        },
        "display_metrics": [
            {"label": "最新价格", "value": f"${price:.2f}" if price is not None else "-", "group": "行情"},
            {"label": "市值", "value": fmt_amount(market_cap), "group": "估值"},
            {"label": "P/S", "value": fmt_ratio(valuation["P/S"]), "group": "估值"},
            {"label": "P/E", "value": fmt_ratio(valuation["P/E"]), "group": "估值"},
            {"label": "毛利率", "value": f"{profitability['毛利率']:.2f}%" if profitability["毛利率"] is not None else "-", "group": "盈利率"},
            {"label": "净利率", "value": f"{profitability['净利率']:.2f}%" if profitability["净利率"] is not None else "-", "group": "盈利率"},
            {"label": "30日波动率", "value": f"{chart['volatility'].get('30日年化波动率'):.2f}%" if chart["volatility"].get("30日年化波动率") is not None else "-", "group": "波动率"},
            {"label": "90日回撤", "value": f"{chart['volatility'].get('90日最大回撤'):.2f}%" if chart["volatility"].get("90日最大回撤") is not None else "-", "group": "波动率"},
        ],
    }


def enrich_catalog(catalog: dict[str, Any], market: dict[str, Any]) -> None:
    by_ticker = market.get("companies", {})
    for company in catalog.get("companies", []):
        ticker = company.get("ticker")
        if ticker and ticker in by_ticker:
            company["market_data"] = by_ticker[ticker]
    catalog["market_data_generated_at"] = market.get("generated_at")
    catalog.setdefault("stats", {})["market_company_count"] = len(by_ticker)


def load_previous_market_data(output: Path) -> dict[str, Any]:
    if not output.exists():
        return {}
    try:
        return json.loads(output.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def merge_previous_chart_data(ticker: str, current: dict[str, Any], previous: dict[str, Any]) -> dict[str, Any]:
    previous_company = (previous.get("companies") or {}).get(ticker)
    if not previous_company or previous_company.get("error"):
        return current
    if current.get("price_history") or not previous_company.get("price_history"):
        return current

    current["price_history"] = previous_company.get("price_history", [])
    current["volatility"] = previous_company.get("volatility", {})
    current.setdefault("source_notes", {})["price_history_fallback"] = (
        "Previous successful Yahoo chart data reused because the latest chart response was empty."
    )
    current.setdefault("fallbacks", {})["price_history"] = previous_company.get("updated_at")

    previous_valuation = previous_company.get("valuation") or {}
    valuation = current.setdefault("valuation", {})
    for key in ["价格", "浠锋牸"]:
        if valuation.get(key) is None and previous_valuation.get(key) is not None:
            valuation[key] = previous_valuation.get(key)
    return current


def main() -> int:
    parser = argparse.ArgumentParser(description="抓取最新财报、估值和波动率数据并写入仪表盘")
    parser.add_argument("--catalog", default=str(CATALOG_PATH), help="catalog.json 路径")
    parser.add_argument("--output", default=str(MARKET_DATA_PATH), help="market_data.json 输出路径")
    parser.add_argument("--refresh", action="store_true", help="忽略 SEC 缓存重新抓取")
    args = parser.parse_args()

    catalog_path = Path(args.catalog)
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    tickers = sorted({company.get("ticker") for company in catalog.get("companies", []) if company.get("ticker")})
    cache_dir = DATA_DIR / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    output = Path(args.output)
    previous_market = load_previous_market_data(output)
    ticker_map = load_ticker_map(cache_dir, refresh=args.refresh)

    companies: dict[str, Any] = {}
    errors: dict[str, str] = {}
    for ticker in tickers:
        try:
            print(f"Fetching {ticker}...", file=sys.stderr)
            companies[ticker] = merge_previous_chart_data(
                ticker,
                build_company_market_data(ticker, cache_dir, ticker_map, args.refresh),
                previous_market,
            )
        except Exception as exc:  # keep the dashboard usable
            errors[ticker] = str(exc)
            previous_company = (previous_market.get("companies") or {}).get(ticker)
            if previous_company and not previous_company.get("error"):
                companies[ticker] = dict(previous_company)
                companies[ticker].setdefault("fallbacks", {})["latest_refresh_error"] = str(exc)
                companies[ticker]["fallback_updated_at"] = datetime.now(timezone.utc).isoformat()
            else:
                companies[ticker] = {"ticker": ticker, "error": str(exc), "updated_at": datetime.now(timezone.utc).isoformat()}

    market = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "tickers": tickers,
        "companies": companies,
        "errors": errors,
        "sources": {
            "SEC submissions": "https://data.sec.gov/submissions/",
            "SEC companyfacts": "https://data.sec.gov/api/xbrl/companyfacts/",
            "Yahoo chart": "https://query1.finance.yahoo.com/v8/finance/chart/{ticker}",
            "Nasdaq summary": "https://api.nasdaq.com/api/quote/{ticker}/summary?assetclass=stocks",
        },
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(market, ensure_ascii=False, indent=2), encoding="utf-8")
    enrich_catalog(catalog, market)
    catalog_path.write_text(json.dumps(catalog, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"ok": True, "tickers": len(tickers), "errors": errors, "output": str(output)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
