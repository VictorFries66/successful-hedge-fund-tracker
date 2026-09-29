"""Parser for SEC Form 13F information-table XML."""

from dataclasses import dataclass
import hashlib
import xml.etree.ElementTree as ET


@dataclass
class HoldingRecord:
    issuer_name: str
    title_of_class: str | None
    cusip: str | None
    figi: str | None
    value_dollars: int | None
    shares_or_principal: int | None
    shares_or_principal_type: str | None
    put_call: str | None
    investment_discretion: str | None
    other_manager: str | None
    sole_voting: int | None
    shared_voting: int | None
    none_voting: int | None
    raw_xml_hash: str


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def child_text(element, name: str) -> str | None:
    for child in element.iter():
        if child is element:
            continue
        if local_name(child.tag) == name:
            return (child.text or "").strip() or None
    return None


def integer(value: str | None) -> int | None:
    if value is None or value == "":
        return None
    return int(value.replace(",", "").strip())


def parse_information_table(xml_bytes: bytes) -> list[HoldingRecord]:
    root = ET.fromstring(xml_bytes)
    records = []
    raw_hash = hashlib.sha256(xml_bytes).hexdigest()

    for element in root.iter():
        if local_name(element.tag) != "infoTable":
            continue
        records.append(HoldingRecord(
            issuer_name=child_text(element, "nameOfIssuer") or "",
            title_of_class=child_text(element, "titleOfClass"),
            cusip=child_text(element, "cusip"),
            figi=child_text(element, "figi"),
            value_dollars=integer(child_text(element, "value")),
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
