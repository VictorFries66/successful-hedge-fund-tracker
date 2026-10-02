"""Parser for SEC Form 13F cover-page manager metadata."""

from dataclasses import dataclass
from typing import Optional

from lxml import etree


@dataclass
class OtherManagerRecord:
    relationship_type: str
    sequence_number: Optional[int]
    manager_name: str
    cik: Optional[str]
    form_13f_file_number: Optional[str]
    crd_number: Optional[str]
    sec_file_number: Optional[str]


@dataclass
class CoverPageRecord:
    report_type: Optional[str]
    filing_manager_name: Optional[str]
    form_13f_file_number: Optional[str]
    other_managers: list[OtherManagerRecord]


def local_name(tag: str) -> str:
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
    try:
        return int(value.strip())
    except ValueError:
        return None


def _manager_record(element, relationship_type: str) -> Optional[OtherManagerRecord]:
    name = child_text(element, "name")
    sequence = child_text(element, "sequenceNumber")
    if not name or sequence is None:
        return None

    return OtherManagerRecord(
        relationship_type=relationship_type,
        sequence_number=integer(sequence),
        manager_name=name,
        cik=child_text(element, "cik"),
        form_13f_file_number=child_text(element, "form13FFileNumber"),
        crd_number=child_text(element, "crdNumber"),
        sec_file_number=child_text(element, "secFileNumber"),
    )


def parse_cover_page(xml_bytes: bytes) -> CoverPageRecord:
    root = etree.fromstring(
        xml_bytes,
        etree.XMLParser(resolve_entities=False, recover=True, no_network=True, huge_tree=True),
    )

    report_type = child_text(root, "reportType")
    filing_manager_name = None
    form_13f_file_number = None

    for element in root.iter():
        if local_name(element.tag) == "filingManager":
            filing_manager_name = child_text(element, "name")
            form_13f_file_number = child_text(element, "form13FFileNumber")
            break

    managers = []
    seen = set()

    for element in root.iter():
        tag = local_name(element.tag).lower()
        if not (tag.startswith("othermanager") or tag.startswith("otherincludedmanager")):
            continue

        ancestor_tags = [
            local_name(parent.tag).lower()
            for parent in element.iterancestors()
        ]
        context = " ".join([tag, *ancestor_tags])

        relationship_type = None
        if "otherincludedmanager" in context:
            relationship_type = "included"
        elif "othermanager" in context:
            relationship_type = "reporting_for"

        if relationship_type:
            record = _manager_record(element, relationship_type)
            if record:
                key = (
                    record.relationship_type,
                    record.sequence_number,
                    record.manager_name,
                )
                if key not in seen:
                    seen.add(key)
                    managers.append(record)

    return CoverPageRecord(
        report_type=report_type,
        filing_manager_name=filing_manager_name,
        form_13f_file_number=form_13f_file_number,
        other_managers=managers,
    )
