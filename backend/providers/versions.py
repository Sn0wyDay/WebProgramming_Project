import re


def is_instrumental(title,disambiguation=''):
    title=title if isinstance(title,str) else ''
    disambiguation=disambiguation if isinstance(disambiguation,str) else ''
    # A version qualifier, not an arbitrary title containing "instrumental".
    return bool(re.search(r'[\[(]\s*(?:instrumental(?:\s+(?:version|mix))?|inst\.?|반주|연주곡)\s*[\])]|\s[-–]\s*(?:instrumental|inst\.?)\s*$',title,re.I) or disambiguation.strip().casefold() in ('instrumental','instrumental version','instrumental mix'))
