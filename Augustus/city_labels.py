"""Scenario-owned labels: slot identifiers are never inferred from list position."""
DEFAULT={'capua':'카푸아','tarentum':'타렌툼','brundisium':'브룬디지움','syracuse':'시라쿠세','mediolanum':'메디올라눔'}
def city_name(city,names=None):return (names or {}).get(city,DEFAULT.get(city,city))
