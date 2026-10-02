"""SEC filer mappings for the eight tracked fund entities.

A website fund is a conceptual entity. One fund may have more than one SEC CIK,
and a filing may itself be a combination report involving affiliated managers.
The CIK list therefore lives separately from the fund table.
"""

SEC_ENTITIES = {
    "citadel": [
        {"cik": "0001423053", "legal_name": "Citadel Advisors LLC", "role": "primary", "include_in_13f": True},
    ],
    "de-shaw": [
        {"cik": "0001009207", "legal_name": "D. E. Shaw & Co., Inc.", "role": "primary", "include_in_13f": True},
    ],
    "millennium": [
        {"cik": "0001273087", "legal_name": "Millennium Management LLC", "role": "primary", "include_in_13f": True},
    ],
    "tci": [
        {"cik": "0001647251", "legal_name": "TCI Fund Management Ltd", "role": "primary", "include_in_13f": True},
    ],
    "pershing-square": [
        {"cik": "0002026053", "legal_name": "Pershing Square Inc.", "role": "primary", "include_in_13f": True},
        {"cik": "0001336528", "legal_name": "Pershing Square Capital Management, L.P.", "role": "related", "include_in_13f": True},
    ],
    "elliott": [
        {"cik": "0001791786", "legal_name": "Elliott Investment Management L.P.", "role": "primary", "include_in_13f": True},
    ],
    "aqr": [
        {"cik": "0001167557", "legal_name": "AQR Capital Management LLC", "role": "primary", "include_in_13f": True},
    ],
    "lone-pine": [
        {"cik": "0001061165", "legal_name": "Lone Pine Capital LLC", "role": "primary", "include_in_13f": True},
    ],
}
