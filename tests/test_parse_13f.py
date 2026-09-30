import unittest

from src.sec.parse_13f import parse_information_table


class Parse13FTests(unittest.TestCase):
    def test_parses_valid_xml(self):
        xml = b'''<?xml version="1.0"?>
<informationTable>
  <infoTable>
    <nameOfIssuer>Example Corp</nameOfIssuer>
    <titleOfClass>COM</titleOfClass>
    <cusip>123456789</cusip>
    <value>1000</value>
    <shrsOrPrnAmt><sshPrnamt>25</sshPrnamt><sshPrnamtType>SH</sshPrnamtType></shrsOrPrnAmt>
    <investmentDiscretion>SOLE</investmentDiscretion>
    <votingAuthority><Sole>25</Sole><Shared>0</Shared><None>0</None></votingAuthority>
  </infoTable>
</informationTable>'''
        records = parse_information_table(xml)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].issuer_name, "Example Corp")
        self.assertEqual(records[0].shares_or_principal, 25)

    def test_recovers_malformed_filer_xml_without_losing_info_tables(self):
        # Mirrors the kind of malformed XML syntax error that can cause
        # ElementTree's strict parser to fail on an as-filed SEC document.
        xml = b'''<?xml version="1.0"?>
<informationTable>
  <infoTable>
    <nameOfIssuer>Example One</nameOfIssuer>
    <titleOfClass>COM</titleOfClass>
  </infoTable>
  <infoTable>
    <nameOfIssuer>Example Two</nameOfIssuer>
    <titleOfClass>COM</titleOfClass>
  </wrongTag>
</informationTable>'''
        records = parse_information_table(xml)
        self.assertEqual(len(records), 2)
        self.assertEqual([r.issuer_name for r in records], ["Example One", "Example Two"])


if __name__ == "__main__":
    unittest.main()
