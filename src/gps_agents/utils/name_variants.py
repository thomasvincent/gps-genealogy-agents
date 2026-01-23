"""Name variant generation for genealogical research.

Provides utilities for generating spelling variants, phonetic matches,
and common historical name variations to improve genealogy search results.

Key features:
- Soundex algorithm for phonetic matching
- Common spelling variant database
- Genealogy-specific variant patterns (maiden names, nicknames)
- Historical spelling normalization
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import ClassVar


def soundex(name: str) -> str:
    """Generate Soundex code for a name.

    Soundex is a phonetic algorithm that indexes names by sound,
    as pronounced in English. Names that sound similar get the same code.

    Examples:
        soundex("Robert") -> "R163"
        soundex("Rupert") -> "R163"  # Same as Robert
        soundex("Sorrell") -> "S640"
        soundex("Sorrel") -> "S640"  # Same as Sorrell
        soundex("Manley") -> "M540"
        soundex("Madden") -> "M350"  # Different!

    Args:
        name: Name to encode

    Returns:
        4-character Soundex code (letter + 3 digits)
    """
    if not name:
        return ""

    # Convert to uppercase and remove non-alpha characters
    name = re.sub(r'[^A-Za-z]', '', name.upper())
    if not name:
        return ""

    # Soundex coding
    # Letters that sound similar are grouped together
    soundex_map = {
        'B': '1', 'F': '1', 'P': '1', 'V': '1',
        'C': '2', 'G': '2', 'J': '2', 'K': '2', 'Q': '2', 'S': '2', 'X': '2', 'Z': '2',
        'D': '3', 'T': '3',
        'L': '4',
        'M': '5', 'N': '5',
        'R': '6',
        # A, E, I, O, U, H, W, Y are not coded
    }

    # Keep first letter
    code = name[0]

    # Convert rest to digits
    prev_digit = soundex_map.get(name[0], '0')

    for char in name[1:]:
        digit = soundex_map.get(char, '0')
        # Skip duplicates and vowels/H/W/Y
        if digit != '0' and digit != prev_digit:
            code += digit
        prev_digit = digit if digit != '0' else prev_digit

    # Pad with zeros or truncate to length 4
    code = (code + '000')[:4]

    return code


def metaphone(name: str) -> str:
    """Generate Metaphone code for a name.

    Metaphone is more accurate than Soundex for English names,
    handling more pronunciation rules.

    This is a simplified implementation covering common cases.

    Args:
        name: Name to encode

    Returns:
        Metaphone code (variable length)
    """
    if not name:
        return ""

    name = name.upper()
    name = re.sub(r'[^A-Z]', '', name)
    if not name:
        return ""

    # Common transformations
    # Drop duplicate adjacent letters
    result = name[0]
    for char in name[1:]:
        if char != result[-1]:
            result += char
    name = result

    # Transformations
    transforms = [
        (r'^KN', 'N'),
        (r'^GN', 'N'),
        (r'^PN', 'N'),
        (r'^AE', 'E'),
        (r'^WR', 'R'),
        (r'^WH', 'W'),
        (r'MB$', 'M'),
        (r'GH', ''),
        (r'PH', 'F'),
        (r'SCH', 'SK'),
        (r'SH', 'X'),
        (r'TH', '0'),  # 0 represents 'th' sound
        (r'TCH', 'X'),
        (r'CH', 'X'),
        (r'CK', 'K'),
        (r'C([IEY])', r'S\1'),
        (r'C', 'K'),
        (r'DG([IEY])', r'J\1'),
        (r'D', 'T'),
        (r'G([IEY])', r'J\1'),
        (r'GN', 'N'),
        (r'G', 'K'),
        (r'Q', 'K'),
        (r'X', 'KS'),
        (r'Z', 'S'),
        (r'V', 'F'),
        (r'[AEIOU]', ''),  # Remove vowels (except initial)
        (r'[HWY]', ''),  # Remove H, W, Y
    ]

    # Keep first letter if it's a vowel
    first = name[0]
    rest = name[1:] if len(name) > 1 else ""

    for pattern, replacement in transforms:
        rest = re.sub(pattern, replacement, rest)

    # Combine and clean up
    result = first + rest
    result = re.sub(r'(.)\1+', r'\1', result)  # Remove duplicates

    return result[:6]  # Limit length


# Common surname spelling variants database
# Organized by soundex/phonetic similarity
SURNAME_VARIANTS: dict[str, list[str]] = {
    # Sorrell variants
    "sorrell": ["sorrel", "sorel", "sorril", "sorell", "sorrells", "sorrels"],
    "sorrel": ["sorrell", "sorel", "sorril", "sorell"],

    # Madden/Manley - these DON'T sound alike but are confused in records
    "madden": ["maden", "maddin", "maddon", "maddyn"],
    "manley": ["manly", "manlee", "mannley", "manly"],

    # Common African American surname variants
    "johnson": ["jonson", "johnsen", "johnston", "johnstone"],
    "williams": ["william", "willams", "wiliams", "willaims"],
    "smith": ["smyth", "smithe", "smythe"],
    "brown": ["browne", "braun"],
    "jackson": ["jacson", "jaxon", "jaxson"],
    "davis": ["davies", "davys"],
    "wilson": ["willson", "wilsen"],
    "moore": ["more", "moor", "mohr"],
    "taylor": ["tailor", "tayler"],
    "thomas": ["tomas", "thoms"],

    # Cherokee/Native American name variants
    "tinnon": ["tinnin", "tinnen", "tennen", "tennon"],
    "rogers": ["rodgers", "roger"],
    "ross": ["rose"],
    "fields": ["field", "feilds"],
    "walker": ["walcker"],

    # Common general variants
    "miller": ["mueller", "muller", "millar"],
    "anderson": ["andersen", "andreson"],
    "martin": ["marten", "martyn"],
    "thompson": ["thomson", "tomson", "tompson"],
    "white": ["whyte", "wite"],
    "harris": ["haris", "harriss"],
    "clark": ["clarke", "clerke"],
    "lewis": ["louis", "lewes"],
    "robinson": ["robison", "robertson"],
    "hall": ["hale", "haul"],
    "young": ["yung", "younge"],
    "king": ["kinge"],
    "wright": ["write", "right"],
    "hill": ["hil", "hull"],
    "scott": ["scot", "skott"],
    "green": ["greene", "grene"],
    "baker": ["backer", "baeker"],
    "adams": ["adam", "addams"],
    "nelson": ["nelsen", "nielson", "nielsen"],
    "carter": ["cartar", "kartar"],
    "mitchell": ["mitchel", "michell"],
    "roberts": ["robert", "robberts"],
    "turner": ["tourner"],
    "phillips": ["philips", "philip", "philipp"],
    "campbell": ["cambell", "cambel"],
    "parker": ["parkar"],
    "evans": ["evens", "evan"],
    "edwards": ["edward", "edwardes"],
    "collins": ["colins", "collens"],
    "stewart": ["stuart", "steward"],
    "morris": ["moris", "maurice", "morriss"],
    "murphy": ["murphey", "murfy"],
    "cook": ["cooke", "koch"],
    "rogers": ["rodgers", "roger"],
    "morgan": ["morgen"],
    "cooper": ["couper", "cowper"],
    "peterson": ["petersen", "pederson", "pedersen"],
    "reed": ["read", "reid", "reade"],
    "bailey": ["baley", "bayley", "bayly"],
    "bell": ["bel", "belle"],
    "howard": ["haward", "howarth"],
    "ward": ["warde"],
    "cox": ["coxe", "cocks"],
    "richardson": ["richerson", "richason"],
    "wood": ["woods", "woode"],
    "watson": ["wattson", "watsen"],
    "brooks": ["brook", "brookes"],
    "bennett": ["bennet", "benet"],
    "gray": ["grey", "graye"],
    "james": ["jemes", "jaymes"],
    "sanders": ["saunders", "sandars"],
    "price": ["pryce", "prise"],
    "powell": ["powel", "powall"],
    "long": ["longe", "lang"],
    "hughes": ["hues", "hughs", "hewes"],
    "flores": ["florez", "flors"],
    "washington": ["washingten"],
    "butler": ["buttler", "buetler"],
    "simmons": ["simons", "symons", "symmons"],
    "foster": ["forster"],
    "gonzales": ["gonzalez", "gonsales"],
    "bryant": ["briant", "bryan"],
    "russell": ["russel", "russle"],
    "griffin": ["griffen", "griffon"],
    "hayes": ["hays", "haies"],
    "myers": ["meyers", "miers", "mayers"],
    "ford": ["forde"],
    "hamilton": ["hamilten"],
    "graham": ["graeme", "grahame"],
    "sullivan": ["sulivan", "o'sullivan"],
    "wallace": ["wallis", "walace"],
    "woods": ["wood", "woodes"],
    "cole": ["coal", "coale"],
    "west": ["weste"],
    "jordan": ["jorden", "jurdan"],
    "owens": ["owen", "owings"],
    "reynolds": ["renolds", "reynalds"],
    "fisher": ["fischer"],
    "freeman": ["freemon"],
    "wells": ["welles", "well"],
    "webb": ["web", "webbe"],
    "simpson": ["simson", "sympson"],
    "stevens": ["stephens", "steven", "stephen"],
    "tucker": ["tuker"],
    "porter": ["portar"],
    "hunter": ["huntar"],
    "hicks": ["hickes", "hix"],
    "crawford": ["crawfurd"],
    "henry": ["hendry", "henri"],
    "boyd": ["boyde"],
    "mason": ["masen", "mayson"],
    "morales": ["moralez"],
    "kennedy": ["kenedy", "kannedy"],
    "warren": ["warrin", "warin"],
    "dixon": ["dickson", "dicksen"],
    "ramos": ["ramoz"],
    "reyes": ["rayes"],
    "burns": ["burnes", "byrnes"],
    "gordon": ["gorden"],
    "shaw": ["shawe"],
    "holmes": ["holms"],
    "rice": ["ryce"],
    "robertson": ["roberson", "robinson"],
    "hunt": ["hunte"],
    "black": ["blacke"],
    "daniels": ["daniel", "danials"],
    "palmer": ["palmar"],
    "mills": ["mils", "milles"],
    "nichols": ["nickols", "nickles", "nicolas"],
    "grant": ["grante"],
    "knight": ["night", "nite"],
    "ferguson": ["furguson", "fergeson"],
    "rose": ["ross"],
    "stone": ["stoner"],
    "hawkins": ["hawkens", "haukins"],
    "dunn": ["dun", "dunne"],
    "perkins": ["perkens"],
    "hudson": ["hutson"],
    "spencer": ["spenser"],
    "gardner": ["gardener", "garner"],
    "stephens": ["stevens", "stefens"],
    "payne": ["paine", "pain"],
    "pierce": ["peirce", "pearce"],
    "berry": ["berrie", "bery"],
    "matthews": ["mathews", "mathes"],
    "arnold": ["arnauld"],
    "wagner": ["wagener", "waggoner"],
    "willis": ["wilis", "willice"],
    "ray": ["rae", "wray"],
    "watkins": ["watkens"],
    "olson": ["olsen", "olsson"],
    "carroll": ["carol", "carrol"],
    "duncan": ["dunkin"],
    "snyder": ["snider", "schneider"],
    "hart": ["harte"],
    "cunningham": ["cuningham"],
    "bradley": ["bradly"],
    "lane": ["laine"],
    "andrews": ["andrew"],
    "ruiz": ["ruis"],
    "harper": ["harpar"],
    "fox": ["foxe"],
    "riley": ["reilly", "riely", "o'riley"],
    "armstrong": ["armstong"],
    "carpenter": ["carpentar"],
    "weaver": ["wever", "weever"],
    "greene": ["green", "grene"],
    "lawrence": ["laurence", "lawerence"],
    "elliott": ["eliot", "elliot", "eliott"],
    "chavez": ["chaves"],
    "sims": ["simms", "syms"],
    "austin": ["austen"],
    "peters": ["peter", "peeters"],
    "kelley": ["kelly", "kely"],
    "franklin": ["franklyne"],
    "lawson": ["lawsen"],
    "fields": ["field", "feild"],
    "ryan": ["rian", "o'ryan"],
    "schmidt": ["smith", "schmit"],
    "carr": ["kar", "carre"],
    "vasquez": ["vasques", "vazquez"],
    "castillo": ["costillo"],
    "wheeler": ["whealer"],
    "chapman": ["chapmen"],
    "oliver": ["olivar", "olivier"],
    "montgomery": ["montgomerie"],
    "richards": ["richard", "richars"],
    "williamson": ["willamson"],
    "johnston": ["johnson", "jonston"],
    "banks": ["bankes"],
    "meyer": ["meier", "myer", "mayer"],
    "bishop": ["bishopp"],
    "mccoy": ["mckoy", "macoy"],
    "howell": ["howel"],
    "alvarez": ["alverez"],
    "morrison": ["morison", "morrisen"],
    "hansen": ["hanson", "hanssen"],
    "fernandez": ["fernandes"],
    "garza": ["garsa"],
    "harvey": ["harvie"],
    "little": ["litle", "lytle"],
    "burton": ["burten"],
    "stanley": ["stanly"],
    "nguyen": ["nguen"],
    "george": ["gorge"],
    "jacobs": ["jacobes"],
    "reid": ["read", "reed"],
    "kim": ["kym"],
    "fuller": ["fuler"],
    "lynch": ["linch"],
    "dean": ["deane"],
    "gilbert": ["gilbart"],
    "garrett": ["garret", "garrette"],
    "romero": ["romaro"],
    "welch": ["welsh", "walch"],
    "larson": ["larsen", "larsson"],
    "frazier": ["frazer", "fraser"],
    "burke": ["burk", "bourke"],
    "hanson": ["hansen", "hanssen"],
    "mendoza": ["mendosa"],
    "moreno": ["morino"],
    "bowman": ["boman"],
    "medina": ["madina"],
    "fowler": ["fouler"],
    "brewer": ["brewar"],
    "hoffman": ["hofman", "huffman"],
    "carlson": ["carlsen", "karlson"],
    "silva": ["sylva"],
    "pearson": ["peirson", "pierson"],
    "holland": ["holand"],
    "douglas": ["douglass"],
    "fleming": ["flemming"],
    "jensen": ["jenson", "janson"],
    "vargas": ["vergas"],
    "byrd": ["bird", "burd"],
    "davidson": ["davison"],
    "hopkins": ["hopkens"],
    "may": ["mae", "maye"],
    "terry": ["terrie"],
    "herrera": ["herera"],
    "wade": ["waide"],
    "soto": ["sotto"],
    "walters": ["walter"],
    "curtis": ["curtiss"],
    "neal": ["neil", "neale", "o'neal"],
    "caldwell": ["colwell", "coldwell"],
    "lowe": ["low"],
    "jennings": ["jenings"],
    "barnett": ["barnet"],
    "graves": ["greves"],
    "jimenez": ["jiminez"],
    "horton": ["horten"],
    "shelton": ["sheltone"],
    "barrett": ["barret"],
    "obrien": ["o'brien", "brian"],
    "castro": ["kastro"],
    "sutton": ["sutten"],
    "gregory": ["gregorie"],
    "mckinney": ["mckiney", "mckinnay"],
    "lucas": ["lukas"],
    "miles": ["myles"],
    "craig": ["craige"],
    "rodriquez": ["rodriguez", "rodriguiz"],
    "chambers": ["chambars"],
    "holt": ["holte"],
    "lambert": ["lambart"],
    "fletcher": ["flecher"],
    "watts": ["wats"],
    "bates": ["baits"],
    "hale": ["haile", "hail"],
    "rhodes": ["rodes", "roads"],
    "pena": ["pina"],
    "beck": ["bek"],
    "newman": ["numan"],
    "haynes": ["haines", "hayns"],
    "mcdaniel": ["mcdonald", "mcdanial"],
    "mendez": ["mendes"],
    "bush": ["busch"],
    "vaughn": ["vaughan", "vawn"],
    "parks": ["parkes"],
    "dawson": ["dauson"],
    "santiago": ["santyago"],
    "norris": ["noris"],
    "hardy": ["hardie"],
    "love": ["lov"],
    "steele": ["steel", "stele"],
    "curry": ["currie"],
    "powers": ["power"],
    "schultz": ["schulz", "shultz"],
    "barker": ["barkar"],
    "guzman": ["gusman"],
    "page": ["paige"],
    "munoz": ["munos"],
    "ball": ["bal"],
    "keller": ["kellar"],
    "chandler": ["chandlar"],
    "weber": ["webar"],
    "leonard": ["lennard"],
    "walsh": ["welch", "welsh"],
    "lyons": ["lions", "lyon"],
    "ramsey": ["ramsay"],
    "wolfe": ["wolf", "wulf"],
    "schneider": ["snyder", "snider"],
    "mullins": ["mullens", "mullen"],
    "benson": ["bensen"],
    "sharp": ["sharpe"],
    "bowen": ["bowin"],
    "daniel": ["daniell"],
    "barber": ["barbar"],
    "cummings": ["cumings", "cummins"],
    "hines": ["hynes", "hinds"],
    "baldwin": ["baldwyn"],
    "griffith": ["griffiths"],
    "valdez": ["valdes"],
    "hubbard": ["hubard"],
    "salazar": ["salasar"],
    "reeves": ["reves", "reaves"],
    "warner": ["warnar"],
    "stevenson": ["stephenson"],
    "burgess": ["burges"],
    "santos": ["santoz"],
    "tate": ["tait"],
    "cross": ["crosse"],
    "garner": ["gardner"],
    "mann": ["man"],
    "mack": ["mac", "mak"],
    "moss": ["mosse"],
    "thornton": ["thorton"],
    "dennis": ["denis"],
    "mcgee": ["magee", "mcghee"],
    "farmer": ["farmar"],
    "delgado": ["delgada"],
    "aguilar": ["agular"],
    "vega": ["vaga"],
    "glover": ["glovar"],
    "manning": ["maning"],
    "cohen": ["cohn", "cohan"],
    "harmon": ["harman"],
    "rodgers": ["rogers"],
    "robbins": ["robins", "robens"],
    "newton": ["nuton"],
    "todd": ["tod"],
    "blair": ["blaire"],
    "higgins": ["higins"],
    "ingram": ["ingrim"],
    "reese": ["rees", "rhees"],
    "cannon": ["canon", "canan"],
    "strickland": ["stricland"],
    "townsend": ["townsen"],
    "schroeder": ["schroder", "shrader"],
    "joseph": ["josef"],
    "baker": ["backer"],
    "osborne": ["osborn"],
    "patterson": ["paterson"],
    "goodwin": ["godwin"],
    "franks": ["frank"],
    "bowden": ["boden"],
    "bradford": ["bradfurd"],
    "thornton": ["thorton"],
    "moran": ["moren"],
    "gibbs": ["gibs"],
    "parsons": ["parson"],
    "mccarthy": ["mccarty", "macarthy"],
}


# Given name variants (nicknames, formal/informal)
GIVEN_NAME_VARIANTS: dict[str, list[str]] = {
    # Female names
    "ruby": ["rubie", "rube"],
    "ida": ["idy", "idie"],
    "kate": ["katherine", "catherine", "katy", "katie", "cathy", "catie"],
    "sarah": ["sara", "sadie", "sally"],
    "elizabeth": ["eliza", "beth", "betsy", "betty", "liz", "lizzie", "bess", "bessie"],
    "margaret": ["maggie", "peggy", "marge", "margie", "meg", "greta"],
    "mary": ["marie", "maria", "molly", "polly", "mae", "mamie"],
    "dorothy": ["dot", "dotty", "dottie", "dolly"],
    "eva": ["eve", "evie"],
    "julia": ["julie", "jules"],
    "lillian": ["lily", "lilly", "lillie", "lil"],
    "emma": ["em", "emmy"],
    "anna": ["annie", "ann", "anne", "nan", "nancy"],
    "helen": ["ellen", "ellie", "nellie"],
    "frances": ["fanny", "fran", "frankie"],
    "alice": ["allie"],
    "ruth": ["ruthie"],
    "rose": ["rosie", "rosa"],
    "martha": ["mattie", "patty"],
    "louise": ["lou", "louisa"],
    "edith": ["edie"],
    "grace": ["gracie"],
    "clara": ["clare", "claire"],
    "ethel": ["etty"],
    "agnes": ["aggie", "nessie"],
    "beatrice": ["bea", "beattie", "trixie"],
    "florence": ["flora", "flo", "florrie"],
    "hazel": ["haze"],
    "mildred": ["millie", "milly"],
    "virginia": ["ginny", "ginger"],
    "harriet": ["hattie"],
    "josephine": ["josie", "jo"],
    "catherine": ["kate", "katie", "kathy", "cathy", "kitty"],
    "rebecca": ["becky", "becca"],
    "abigail": ["abby", "abbie", "gail"],
    "priscilla": ["prissy", "cilla"],
    "susanna": ["susan", "sue", "susie", "sukey"],
    "deborah": ["debbie", "deb"],
    "constance": ["connie"],
    "patience": ["patty"],

    # Male names
    "morris": ["maurice", "morrie"],
    "william": ["will", "bill", "billy", "willie", "willy", "liam"],
    "robert": ["rob", "bob", "bobby", "robbie", "bert"],
    "james": ["jim", "jimmy", "jamie", "jem"],
    "john": ["jack", "johnny", "jock"],
    "charles": ["charlie", "chuck", "chas"],
    "george": ["georgie"],
    "thomas": ["tom", "tommy", "thom"],
    "joseph": ["joe", "joey", "jos"],
    "edward": ["ed", "eddie", "ted", "teddy", "ned"],
    "henry": ["harry", "hank", "hal"],
    "richard": ["rick", "dick", "ricky", "rich"],
    "michael": ["mike", "mickey", "mick"],
    "david": ["dave", "davey"],
    "frank": ["frankie", "francis"],
    "daniel": ["dan", "danny"],
    "samuel": ["sam", "sammy"],
    "benjamin": ["ben", "benny", "benji"],
    "frederick": ["fred", "freddie", "fritz"],
    "albert": ["al", "bert", "bertie"],
    "arthur": ["art", "artie"],
    "walter": ["walt", "wally"],
    "raymond": ["ray"],
    "lawrence": ["larry", "laurie"],
    "theodore": ["ted", "teddy", "theo"],
    "leonard": ["leo", "len", "lenny"],
    "harold": ["harry", "hal"],
    "ernest": ["ernie"],
    "eugene": ["gene"],
    "ralph": ["rafe"],
    "anthony": ["tony"],
    "andrew": ["andy", "drew"],
    "patrick": ["pat", "paddy"],
    "peter": ["pete"],
    "nicholas": ["nick", "nicky"],
    "alexander": ["alex", "sandy"],
    "nathaniel": ["nathan", "nat", "nate"],
    "jonathan": ["jon", "johnny"],
    "christopher": ["chris", "kit"],
    "matthew": ["matt", "matty"],
    "timothy": ["tim", "timmy"],
    "stephen": ["steve", "steven"],
    "phillip": ["phil"],
    "abraham": ["abe"],
    "isaac": ["ike"],
    "jacob": ["jake"],
    "archibald": ["archie"],
    "bartholomew": ["bart"],
    "cornelius": ["corny", "neil"],
    "ebenezer": ["eben"],
    "ezekiel": ["zeke"],
    "jeremiah": ["jerry"],
    "obadiah": ["obie"],
    "zachariah": ["zach", "zachary"],
}


@dataclass
class NameVariants:
    """Container for name variants and their sources."""
    original: str
    soundex_code: str
    metaphone_code: str
    spelling_variants: list[str]
    nickname_variants: list[str]
    all_variants: list[str]


def generate_surname_variants(surname: str, include_soundex_matches: bool = True) -> NameVariants:
    """Generate all variants of a surname for genealogy search.

    Args:
        surname: The surname to generate variants for
        include_soundex_matches: Whether to include phonetically similar names

    Returns:
        NameVariants object with all generated variants
    """
    surname_lower = surname.lower().strip()
    surname_normalized = surname_lower.replace("'", "").replace("-", "")

    # Get soundex and metaphone
    sx = soundex(surname)
    mp = metaphone(surname)

    # Start with known spelling variants
    spelling_variants = set()
    if surname_lower in SURNAME_VARIANTS:
        spelling_variants.update(SURNAME_VARIANTS[surname_lower])

    # Check if any known variant matches this surname
    for base_name, variants in SURNAME_VARIANTS.items():
        if surname_lower in variants:
            spelling_variants.add(base_name)
            spelling_variants.update(variants)

    # Add common letter substitutions
    substitutions = [
        (surname_lower, "ll", "l"),
        (surname_lower, "l", "ll"),
        (surname_lower, "tt", "t"),
        (surname_lower, "t", "tt"),
        (surname_lower, "ss", "s"),
        (surname_lower, "s", "ss"),
        (surname_lower, "nn", "n"),
        (surname_lower, "n", "nn"),
        (surname_lower, "mm", "m"),
        (surname_lower, "m", "mm"),
        (surname_lower, "dd", "d"),
        (surname_lower, "d", "dd"),
        (surname_lower, "ff", "f"),
        (surname_lower, "f", "ff"),
        (surname_lower, "ey", "y"),
        (surname_lower, "y", "ey"),
        (surname_lower, "ie", "y"),
        (surname_lower, "y", "ie"),
        (surname_lower, "ei", "ie"),
        (surname_lower, "ie", "ei"),
        (surname_lower, "ea", "ee"),
        (surname_lower, "ee", "ea"),
        (surname_lower, "ow", "ou"),
        (surname_lower, "ou", "ow"),
        (surname_lower, "c", "k"),
        (surname_lower, "k", "c"),
        (surname_lower, "ph", "f"),
        (surname_lower, "f", "ph"),
    ]

    for original, old, new in substitutions:
        if old in original:
            spelling_variants.add(original.replace(old, new, 1))

    # Remove the original from variants
    spelling_variants.discard(surname_lower)

    # Combine all variants
    all_variants = list(spelling_variants)

    # Add soundex matches if requested (this would require a database lookup in practice)
    # For now, just return what we have

    return NameVariants(
        original=surname,
        soundex_code=sx,
        metaphone_code=mp,
        spelling_variants=sorted(spelling_variants),
        nickname_variants=[],  # Surnames don't have nicknames
        all_variants=sorted(set(all_variants))
    )


def generate_given_name_variants(given_name: str) -> NameVariants:
    """Generate all variants of a given name for genealogy search.

    Args:
        given_name: The given name to generate variants for

    Returns:
        NameVariants object with all generated variants
    """
    name_lower = given_name.lower().strip()

    # Get soundex and metaphone
    sx = soundex(given_name)
    mp = metaphone(given_name)

    # Get nickname variants
    nickname_variants = set()
    if name_lower in GIVEN_NAME_VARIANTS:
        nickname_variants.update(GIVEN_NAME_VARIANTS[name_lower])

    # Check if this is a nickname and get the formal name
    for formal_name, nicknames in GIVEN_NAME_VARIANTS.items():
        if name_lower in nicknames:
            nickname_variants.add(formal_name)
            nickname_variants.update(nicknames)

    # Remove the original
    nickname_variants.discard(name_lower)

    # Add spelling variants
    spelling_variants = set()
    substitutions = [
        (name_lower, "y", "ie"),
        (name_lower, "ie", "y"),
        (name_lower, "ey", "y"),
        (name_lower, "y", "ey"),
        (name_lower, "i", "y"),
        (name_lower, "y", "i"),
    ]

    for original, old, new in substitutions:
        if old in original:
            spelling_variants.add(original.replace(old, new, 1))

    spelling_variants.discard(name_lower)

    # Combine all
    all_variants = list(nickname_variants | spelling_variants)

    return NameVariants(
        original=given_name,
        soundex_code=sx,
        metaphone_code=mp,
        spelling_variants=sorted(spelling_variants),
        nickname_variants=sorted(nickname_variants),
        all_variants=sorted(set(all_variants))
    )


def get_all_search_names(surname: str, given_name: str | None = None) -> dict[str, list[str]]:
    """Get all name variants to use in genealogy searches.

    This is the main entry point for generating search variants.

    Args:
        surname: Surname to search
        given_name: Optional given name

    Returns:
        Dictionary with 'surnames' and 'given_names' lists to search
    """
    result = {"surnames": [surname], "given_names": []}

    # Generate surname variants
    surname_variants = generate_surname_variants(surname)
    result["surnames"].extend(surname_variants.all_variants)
    result["surnames"] = list(dict.fromkeys(result["surnames"]))  # Dedupe preserving order

    # Generate given name variants
    if given_name:
        result["given_names"] = [given_name]
        given_variants = generate_given_name_variants(given_name)
        result["given_names"].extend(given_variants.all_variants)
        result["given_names"] = list(dict.fromkeys(result["given_names"]))

    return result
