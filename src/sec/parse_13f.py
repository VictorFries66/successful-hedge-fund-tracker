"""Parser for SEC Form 13F information-table XML."""

from dataclasses import dataclass
import hashlib
import re

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

