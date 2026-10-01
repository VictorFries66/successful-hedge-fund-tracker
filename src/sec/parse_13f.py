"""Parser for SEC Form 13F information-table XML and legacy TXT."""

from dataclasses import dataclass
import hashlib
import re

from bs4 import BeautifulSoup
from lxml import etree
from typing import Optional


@dataclass
class HoldingRecord:
    issuer_name: str
    title_of_class: Optional[str]
    cusip: Optional[str]
    figi: Optional[str]
    value_dollars: Optional[int]
    shares_or_principal: Optional[int]
    shares_or_principal_type: Optional[str]
    put_call: Optional[str]
    investment_discretion: Optional[str]
    other_manager: Optional[str]
    sole_voting: Optional[int]
    shared_voting: Optional[int]
    none_voting: Optional[int]
    raw_xml_hash: str


def local_name(tag: str) -> str:
    """Return an XML element's local name, ignoring an optional namespace."""
    if not isinstance(tag, str):
        return ""
    return tag.rsplit("}", 1)[-1]


def child_text(element, name: str) -> Optional[str]:
    for child in element.iter():
        if child is element:
            continue
        if local_name(child.tag) == name:
            return (child.text or "").strip() or None
    return None


def integer(value: Optional[str]) -> Optional[int]:
    if value is None or value == "":
        return None
    return int(value.replace(",", "").strip())


def _parse_root(xml_bytes: bytes):
    """Parse an SEC 13F XML document, recovering from malformed filer XML when needed."""
    try:
        return etree.fromstring(xml_bytes, etree.XMLParser(resolve_entities=False))
    except etree.XMLSyntaxError as strict_error:
        recovered_parser = etree.XMLParser(
            recover=True,
            resolve_entities=False,
            no_network=True,
            huge_tree=True,
        )
        root = etree.fromstring(xml_bytes, recovered_parser)
        if root is None:
            raise ValueError("SEC information-table XML could not be parsed") from strict_error

        expected_open = len(re.findall(rb"<\s*(?:[A-Za-z0-9_.-]+:)?infoTable\b", xml_bytes))
        parsed_count = len(root.xpath('.//*[local-name()="infoTable"]'))
        if expected_open and parsed_count != expected_open:
            raise ValueError(
                "Recovered SEC information-table XML lost records: "
                f"expected about {expected_open} infoTable elements, found {parsed_count}"
            ) from strict_error

        return root


def parse_information_table(xml_bytes: bytes, value_multiplier: int = 1) -> list[HoldingRecord]:
    root = _parse_root(xml_bytes)
    records = []
    raw_hash = hashlib.sha256(xml_bytes).hexdigest()

    for element in root.iter():
        if local_name(element.tag) != "infoTable":
            continue

        issuer_name = child_text(element, "nameOfIssuer") or ""
        if not issuer_name:
            raise ValueError("Encountered an infoTable record without nameOfIssuer")

        records.append(HoldingRecord(
            issuer_name=issuer_name,
            title_of_class=child_text(element, "titleOfClass"),
            cusip=child_text(element, "cusip"),
            figi=child_text(element, "figi"),
            value_dollars=(integer(child_text(element, "value")) * value_multiplier
                          if integer(child_text(element, "value")) is not None else None),
            shares_or_principal=integer(child_text(element, "sshPrnamt")),
            shares_or_principal_type=child_text(element, "sshPrnamtType"),
            put_call=child_text(element, "putCall"),
            investment_discretion=child_text(element, "investmentDiscretion"),
            other_manager=child_text(element, "otherManager"),
            sole_voting=integer(child_text(element, "Sole")),
            shared_voting=integer(child_text(element, "Shared")),
            none_voting=integer(child_text(element, "None")),
            raw_xml_hash=raw_hash,
        ))

    if not records:
        raise ValueError("No infoTable records found in 13F information-table XML")
    return records


_CUSIP_RE = re.compile(r"(?<![A-Z0-9])([A-Z0-9]{9})(?![A-Z0-9])", re.IGNORECASE)
_NUMBER_RE = re.compile(r"^[+-]?(?:\d{1,3}(?:,\d{3})+|\d+)$")

# Common legacy 13F class labels. The parser uses the longest matching suffix
# before the CUSIP so issuer names containing multiple words remain intact.
_CLASS_SUFFIXES = (
    "SPONSORED ADR",
    "SPONSORED ADS",
    "SPON ADR",
    "COMMON STOCK",
    "COM NEW",
    "COM PAR",
    "COM",
    "COMMON",
    "CL A",
    "CL B",
    "CL C",
    "CLASS A",
    "CLASS B",
    "CLASS C",
    "SHS A",
    "SHS B",
    "SHS",
    "ADR",
    "ETF",
    "ETN",
    "NOTE",
    "NOTES",
    "PFD",
    "PREF",
    "DEB",
    "DEBT",
    "WARRANT",
    "WTS",
    "UNIT",
    "UNITS",
)


def _number(token: str) -> Optional[int]:
    if not _NUMBER_RE.match(token):
        return None
    return int(token.replace(",", ""))


def _split_issuer_and_class(prefix: str) -> tuple[str, Optional[str]]:
    prefix = re.sub(r"\s+", " ", prefix.strip())
    upper = prefix.upper()

    for suffix in sorted(_CLASS_SUFFIXES, key=len, reverse=True):
        if upper == suffix:
            return prefix, suffix
        marker = " " + suffix
        if upper.endswith(marker):
            return prefix[: -len(marker)].strip(), prefix[-len(suffix):].strip()

    parts = prefix.split()
    if len(parts) >= 2:
        return " ".join(parts[:-1]), parts[-1]
    return prefix, None


def _legacy_table_sections(text: str) -> list[str]:
    sections = re.findall(
        r"<TABLE\b[^>]*>(.*?)</TABLE>",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if sections:
        return sections
    return [text]


def _legacy_data_blocks(section: str) -> list[str]:
    # Remove HTML-ish tags while preserving line boundaries. Older EDGAR
    # submissions often wrap long issuer names and voting columns onto the next
    # physical line, so accumulate lines until the next CUSIP appears.
    soup = BeautifulSoup(section, "html.parser")
    plain = soup.get_text("\n")
    lines = [re.sub(r"\s+", " ", line).strip() for line in plain.splitlines()]

    blocks = []
    current = []

    for line in lines:
        if not line:
            continue

        upper = line.upper()
        if (
            "NAME OF ISSUER" in upper
            or "TITLE OF CLASS" in upper
            or "COLUMN" in upper
            or "REPORT SUMMARY" in upper
            or upper.startswith("<S>")
            or upper.startswith("<C>")
            or set(line.replace(" ", "")) <= {"-", "_", "~"}
        ):
            continue

        if _CUSIP_RE.search(line):
            if current:
                blocks.append(" ".join(current))
            current = [line]
        elif current:
            current.append(line)

    if current:
        blocks.append(" ".join(current))

    return blocks


def parse_legacy_information_table(submission_bytes: bytes) -> list[HoldingRecord]:
    """Parse pre-2013 fixed-width/text 13F information tables.

    Before the SEC's 2013 XML transition, 13F-HR holdings were commonly filed
    as plaintext tables. The exact spacing varied by filer, but the CUSIP is a
    reliable anchor. This parser handles wrapped rows, SH/PRN and PUT/CALL
    fields, discretion/manager fields, and one-to-three voting-authority values.
    """
    text = submission_bytes.decode("latin-1", errors="replace")
    raw_hash = hashlib.sha256(submission_bytes).hexdigest()
    records = []

    for section in _legacy_table_sections(text):
        for block in _legacy_data_blocks(section):
            match = _CUSIP_RE.search(block)
            if not match:
                continue

            prefix = block[:match.start()].strip()
            suffix = block[match.end():].strip()
            issuer_name, title_of_class = _split_issuer_and_class(prefix)

            # A valid legacy row must have numeric value and position fields
            # immediately after the CUSIP. This excludes cover-page numbers and
            # other unrelated text containing nine-character identifiers.
            tokens = suffix.split()
            if len(tokens) < 2:
                continue

            value = _number(tokens[0])
            shares = _number(tokens[1])
            if value is None or shares is None:
                continue

            rest = tokens[2:]
            share_type = None
            put_call = None
            discretion = None
            other_manager = None
            numeric_tail = []

            for token in rest:
                upper = token.upper()
                if upper in {"SH", "PRN"} and share_type is None:
                    share_type = upper
                elif upper in {"PUT", "CALL"} and put_call is None:
                    put_call = upper
                elif (
                    discretion is None
                    and (
                        "SOLE" in upper
                        or "SHARED" in upper
                        or "DEFINED" in upper
                        or "OTHER" in upper
                    )
                    and not _number(token)
                ):
                    discretion = token
                elif _number(token) is not None:
                    numeric_tail.append(_number(token))
                elif other_manager is None:
                    other_manager = token
                elif other_manager:
                    other_manager += "," + token

            # Older tables may encode investment discretion as X in the
            # sole/shared/other columns rather than words. Preserve that signal.
            if discretion is None:
                x_tokens = [t.upper() for t in rest if t.upper() == "X"]
                if x_tokens:
                    discretion = "SOLE" if len(x_tokens) == 1 else "SHARED"

            # Some legacy filings use a dash for empty voting columns. After
            # filtering, the remaining numeric values are voting authority.
            sole = shared = none = None
            if len(numeric_tail) >= 3:
                sole, shared, none = numeric_tail[-3:]
            elif len(numeric_tail) == 2:
                sole, shared = numeric_tail[-2:]
            elif len(numeric_tail) == 1:
                sole = numeric_tail[0]

            records.append(HoldingRecord(
                issuer_name=issuer_name,
                title_of_class=title_of_class,
                cusip=match.group(1).upper(),
                figi=None,
                value_dollars=value * 1000,
                shares_or_principal=shares,
                shares_or_principal_type=share_type,
                put_call=put_call,
                investment_discretion=discretion,
                other_manager=other_manager,
                sole_voting=sole,
                shared_voting=shared,
                none_voting=none,
                raw_xml_hash=raw_hash,
            ))

    if not records:
        raise ValueError("No legacy 13F holdings records found in submission text")

    return records
