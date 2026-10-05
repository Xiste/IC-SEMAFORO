"""Valida infraestrutura comprovada, continuação física e alterações limitadas."""

from contextlib import redirect_stderr, redirect_stdout
import hashlib
import io
import math
from pathlib import Path
import tempfile
import unittest
import xml.etree.ElementTree as ET

from scripts import correct_signal_infrastructure as infrastructure


EXPECTED_CONTROLS = {
    "FAM_RONDON_BENJAMIM": {"1156717163#3": 6, "152937136#3": 6,
                           "666324302#5": 3, "853751181#0": 3},
    "FAM_CESARIO_PARANA": {"154252437#1": 1, "602306713#21": 2, "665897556#1": 2},
    "FAM_RONDON_BELEM": {"331577750#1": 4, "576876311#3": 3, "965367673#0": 3},
    "FAM_RONDON_ANSELMO": {"462991286": 3, "576014296#2": 5},
    "FAM_RONDON_PORTO_ALEGRE": {"299471494#2": 3, "30664532#2": 2, "331577748#4": 5},
    "FAM_RONDON_NITEROI": {"30622933#11": 5, "930831032#1": 5, "931572689": 7},
    "FAM_RONDON_BATALHAO_7962385968": {"331577749#0": 4},
    "FAM_RONDON_BATALHAO_7962499397": {"1156717173#3": 4},
}
EXPECTED_STATES = {
    "FAM_RONDON_BENJAMIM": "OOOOoooooOOOOOoooo", "FAM_CESARIO_PARANA": "ooooo",
    "FAM_RONDON_BELEM": "OOOOOOOooo", "FAM_RONDON_ANSELMO": "OOOOOOOO",
    "FAM_RONDON_PORTO_ALEGRE": "OOOooOOOOO", "FAM_RONDON_NITEROI": "OOOOooooOOOOooooo",
    "FAM_RONDON_BATALHAO_7962385968": "GGGG",
    "FAM_RONDON_BATALHAO_7962499397": "GGGG",
}
# Manifesto explícito do recorte comprovado; não deriva permissões da rede em teste.
# Edges incidentes abrangem somente o fechamento geométrico dos nós listados.
APPROVED_NODES = set(
    """
    13738551275 13738551275.ped.0 13738551275.ped.1 13738551276 13738551276.ped.0 13738551276.ped.1
    1412958615 1561880261 1561880547 1561880676 1668155076 1668155077 2042691678 2042691919 2042693016
    2042693062 2042693080 2042693107 2042693128 258368105 2651934389 2651934389.ped.0 2651934389.ped.1
    2669335035 2669335036 2783757296 2783757296.ped.0 2783757296.ped.1 2963614071 2963614077 3050739565
    3050739566 3050739567 3050739568 3050739569 3050739571 3050739572 3050739574 3050739575 3050739577
    3050739578 3050761411 3050761411.ped.0 3050761411.ped.1 3050767735 3050767830 3050804948 3082132857
    3175865971 3371628024 338648822 338653529 338654991 338654991.ped.0 338654991.ped.1 3386573294
    3386573294.ped.0 3386573294.ped.1 3386573296 3386573296.ped.0 3386573296.ped.1 3386573297
    3386573297.ped.0 3386573297.ped.1 3386573298 3386573298.ped.0 3386573298.ped.1 3386573305
    3386573305.ped.0 3386573305.ped.1 3386573306 3386573306.ped.0 3386573306.ped.1 338660524 338663851
    338664406 338685838 338686240 338942567 338955633 339113979 339113980 339114019 339114019.ped.0
    339114019.ped.1 339121000 339121007 4025923697 4125318255 4125318256 4353419588 4353431089 5494111589
    5494111589.ped.0 5494111589.ped.1 5494111590 5494111590.ped.0 5494111590.ped.1 5494111593 5494111594
    5494111594.ped.0 5494111594.ped.1 5494111596 5494111596.ped.0 5494111596.ped.1 5494111597
    5494111597.ped.0 5494111597.ped.1 5494111602 5494111603 5494111603.ped.0 5494111603.ped.1 5525723567
    5525815656 5525815656.ped.0 5525815656.ped.1 597213239 597213583 597213618 597213676 597213702 6501300016
    7678971919 7678971922 7962385968 7962499397 7963056109 7963056109.ped.0 7963056109.ped.1 7963056110
    7963056110.ped.0 7963056110.ped.1 7963074868 8062374303 8064774394 8064774395 8622218071 8622218071.ped.0
    8622218071.ped.1 8622218072 8622218072.ped.0 8622218072.ped.1 8622218073 8622218073.ped.0
    8622218073.ped.1 8998419511 8998470609 9013115030 9438164307 AFRICA_HOLANDA FAM_RIO_ACCESS FAM_RIO_NE
    FAM_RIO_NE.ped.0 FAM_RIO_NE.ped.1 FAM_RIO_SW FAM_RIO_SW.ped.0 FAM_RIO_SW.ped.1
    FAM_RONDON_BENJAMIM_JUNCTION FAM_RONDON_PARANA SALOMAO_JOAO_PEREIRA
    """.split()
)
APPROVED_EDGES = set(
    """
    -261301887#1 -261301889#2 -300965440 -300965442 -300965443 -300965444 -303789425#3 -30649092#1
    -30664709#0 -30665251#0 -330210597#0 -330210597#1 -463005565#0 -616180216 -616971271#0 -616971271#1
    -647043773#0 -647043774#0 -647043774#1 -659117881 -659117905#1 -659117905#2 -659117933#east
    -659117933#west -853694507 -863742169 1156272391#0 1156272391#1 1156272391#2 1156272391#3 1156272392
    1156272393#0 1156272393#1 1156272393#2 1156272393#3 1156272393#4 1156272393#5 1156272393#5.rio
    1156272393#6 1156272393#7 1156272394 1156272395#0 1156272395#1 1156717163#0 1156717163#1 1156717163#1.rio
    1156717163#2 1156717163#3 1156717164 1156717165 1156717166#0 1156717168 1156717170#0 1156717170#1
    1156717171 1156717172#0 1156717173#0 1156717173#1 1156717173#2 1156717173#3 1156717173#4 1156717173#5
    1156717174 1156717175#0 1156717175#1 1156717175#2 1156717175#3 1156717175#4 1156717175#5 1156717176
    1156717177#0 1171563461 13738551275.ped.0 13738551275.ped.1 13738551276.ped.0 13738551276.ped.1
    142719720#11 142719720#12 152937010#3 152937136#0 152937136#1 152937136#2 152937136#3 154252437#0
    154252437#1 154252438 261301887#1 261301889#2 261432318 2651934389.ped.0 2651934389.ped.1 274995593#0
    2783757296.ped.0 2783757296.ped.1 292932042#0 292932042#1 299471494#0 299471494#1 299471494#2 300965440
    300965441 300965442 300965443 300965444 300965445 300965447#1 300965448 300965451#0 303101571#0
    303789425#3 3050761411.ped.0 3050761411.ped.1 30621940#12 30621943#0 30621947#12 30621958#0 30622933#12
    30648920#3 30648920#4 30648920#5 30649092#1 30664520#0 30664521#0 30664532#3 30664709#0 30665251#0
    330210597#0 330210597#1 331577748#0 331577748#1 331577748#2 331577748#3 331577748#4 331577749#0
    331577749#1 331577750#0 331577750#1 331577751#0 331577751#1 331577753#0 331577754 331577755 331577756#0
    331577756#1 338654991.ped.0 338654991.ped.1 3386573294.ped.0 3386573294.ped.1 3386573296.ped.0
    3386573296.ped.1 3386573297.ped.0 3386573297.ped.1 3386573298.ped.0 3386573298.ped.1 3386573305.ped.0
    3386573305.ped.1 3386573306.ped.0 3386573306.ped.1 339114019.ped.0 339114019.ped.1 399928437#6
    399928437#7 402968122#0 402968122#1 402968122#2 402968128#0 402968128#1 402968128#2 403166935#0
    403166940#2 403166940#3 403166940#4 462991286 462991287 462993308#0 462993308#1 462993308#2 462993309
    462993310 463005565#0 463014795#0 463014795#1 46711471#0 5494111589.ped.0 5494111589.ped.1
    5494111590.ped.0 5494111590.ped.1 5494111594.ped.0 5494111594.ped.1 5494111596.ped.0 5494111596.ped.1
    5494111597.ped.0 5494111597.ped.1 5494111603.ped.0 5494111603.ped.1 5525815656.ped.0 5525815656.ped.1
    576014290#0 576014290#1 576014295 576014296#0 576014296#1 576014296#2 576014297 576014298 576014299
    576014301#0 576014301#1 576876311#3 602306713#21 602306713#22 616180216 616971271#0 616971271#1
    625668273#2 625668273#3 647043773#0 647043774#0 647043774#1 659117881 659117905#1 659117905#2
    659117933#east 659117933#west 665897556#1 665897572 666324280 666324302#5 666324302#6 789705871#13
    7963056109.ped.0 7963056109.ped.1 7963056110.ped.0 7963056110.ped.1 853694507 853749385 853749386
    853751181#0 853751181#1 8622218071.ped.0 8622218071.ped.1 8622218072.ped.0 8622218072.ped.1
    8622218073.ped.0 8622218073.ped.1 863742169 901328279#0 901328279#1 901328279#2 916048066#1 930831032#0
    930831032#1 930831033#0 930831033#1 930831034 931572689 965367671 965367672#0 965367672#1 965367672#2
    965367672#3 965367673#1 :2651934389_5 :2651934389_6 :2783757296_3 :2783757296_5 :3050761411_0
    :597213583_0 :597213583_2 :7962385968_4 :7962385968_5 :7962385968_7 :7962499397_2 :7962499397_3
    :7962499397_4 FAM_RIO_NE.ped.0 FAM_RIO_NE.ped.1 FAM_RIO_SW.ped.0 FAM_RIO_SW.ped.1
    """.split()
)
APPROVED_NODES.update("""
    3050767812 3034565314 3050767816 4125318258 4125318259 1561880748 2042691990
    AFRICA_SUICA 2042693363 2042693385 2042693399 2042693444 3370282693 6051154708
    954823567 FAM_MARIA_SEGISMUNDO 5525723568
""".split())
APPROVED_EDGES.update("""
    30622933#11 30664532#2 965367673#0
    299469392#2 299469392#3 299469392#4 30648920#0 30648920#1 30648920#2
    307152129#3 307152129#4 307152129#5 402968122#3 402968122#4 402968122#5
    616971270#east 931172668#west 398537158#east 616971268#west
    154562663#north -154562663#north 30649096 -30649096 577166561#0
    :2042693107_1 :2042693107_7 :954823567_0 :954823567_1
""".split())

APPROVED_PROGRAMS = set(
    """
    2042693016 2042693107 2042693363 2963614071 338654991 3386573305 3386573306 5494111589 5494111590 5494111593
    5494111594 5494111596 5494111597 5494111602 5494111603 FAM_CESARIO_PARANA FAM_RONDON_ANSELMO
    FAM_RONDON_BATALHAO_7962385968 FAM_RONDON_BATALHAO_7962499397 FAM_RONDON_BELEM FAM_RONDON_BENJAMIM
    FAM_RONDON_NITEROI FAM_RONDON_PARANA FAM_RONDON_PORTO_ALEGRE FAM_RONDON_RIO_DE_JANEIRO
    FAM_RONDON_ROTARY_CLUB
    """.split()
)
DOCUMENTED_CROSSINGS = (
    ('FAM_RONDON_BENJAMIM_JUNCTION', '1156717163#3'),
    ('FAM_RONDON_BENJAMIM_JUNCTION', '152937136#3'),
    ('FAM_RONDON_BENJAMIM_JUNCTION', '1156272391#0'),
    ('FAM_RONDON_BENJAMIM_JUNCTION', '1156272393#0'),
    ('FAM_RONDON_BENJAMIM_JUNCTION', '853751181#0'),
    ('FAM_RONDON_BENJAMIM_JUNCTION', '666324302#5 1156272395#1'),
    ('5494111589', '576014290#0'),
    ('5494111590', '1156717175#5'),
    ('5494111594', '576014301#0'),
    ('5525815656', '462993308#1'),
    ('5494111596', '1156717175#0'),
    ('5494111597', '930831032#0'),
    ('3386573305', '331577748#2'),
    ('3386573306', '299471494#1'),
    ('5494111603', '1156717170#0'),
    ('2042691678', '30664532#2'),
    ('339121007', '1156717172#0'),
    ('338686240', '30622933#11'),
    ('597213618', '1156717177#0'),
    ('3386573294', '1156272393#6'),
    ('3386573296', '901328279#0'),
    ('3386573297', '1156717168'),
    ('3386573298', '1156717173#4'),
    ('8622218071', '463014795#0'),
    ('8622218072', '930831033#0'),
    ('8622218073', '965367672#2'),
    ('13738551275', '331577750#0'),
    ('13738551276', '299471494#0'),
    ('339114019', '154252437#1'),
    ('7963056109', '665897556#1'),
    ('7963056110', '602306713#21'),
    ('2651934389', '576014296#2'),
    ('2783757296', '462991286'),
    ('338654991', '625668273#2'),
    ('3050761411', '292932042#0'),
    ('FAM_RIO_SW', '1156272393#5'),
    ('FAM_RIO_NE', '1156717163#1'),
    ('3391594553', '30620737#14'),
    ('3391594554', '261533405#17'),
)
# Os quatro acessos locais de Segismundo atendem às quatro zebras documentadas.
SEGISMUNDO_CROSSINGS = (
    "-616971271#0 616971271#0", "154562663#north -154562663#north",
    "931172668#west 616971268#west", "616971270#east 398537158#east",
)
PEDESTRIAN_IDS = {f"{node}.ped.{roads.split()[0]}.{side}"
                  for node, roads in DOCUMENTED_CROSSINGS for side in range(2)}
PEDESTRIAN_IDS.update(f"FAM_MARIA_SEGISMUNDO.ped.{side}" for side in range(4))
# Remove os nomes do protótipo antigo; só o recorte explicitamente aprovado acima vale.
APPROVED_NODES = {i for i in APPROVED_NODES if ".ped." not in i} | PEDESTRIAN_IDS
APPROVED_EDGES = {i for i in APPROVED_EDGES if ".ped." not in i} | PEDESTRIAN_IDS

LEGACY_PHASES = {'1561879771': (('42', 'GGrr'), ('3', 'yyrr'), ('42', 'rrGG'), ('3', 'rryy')),
 '1561879807': (('42', 'GGGrr'), ('3', 'yyyrr'), ('42', 'rrrGG'), ('3', 'rrryy')),
 '1561879940': (('40', 'GGrr'), ('5', 'yyrr'), ('40', 'rrGG'), ('5', 'rryy')),
 '1561879989': (('40', 'GGrr'), ('5', 'yyrr'), ('40', 'rrGG'), ('5', 'rryy')),
 '1561880076': (('42', 'GGrr'), ('3', 'yyrr'), ('42', 'rrGG'), ('3', 'rryy')),
 '2042692453': (('42', 'GGggrrrrGGggrrrr'),
                ('3', 'yyyyrrrryyyyrrrr'),
                ('42', 'rrrrGGggrrrrGGgg'),
                ('3', 'rrrryyyyrrrryyyy')),
 '2042692877': (('26', 'rrrGGrr'),
                ('4', 'rrryGrr'),
                ('26', 'GGGrGrr'),
                ('4', 'yyyryrr'),
                ('26', 'rrrrrGG'),
                ('4', 'rrrrryy')),
 '2042692883': (('42', 'GGggrrrrGGggrrrr'),
                ('3', 'yyyyrrrryyyyrrrr'),
                ('42', 'rrrrGGggrrrrGGgg'),
                ('3', 'rrrryyyyrrrryyyy')),
 '2042692896': (('26', 'GGrrr'),
                ('4', 'yyrrr'),
                ('26', 'rrGrG'),
                ('4', 'rryrG'),
                ('26', 'rrrGG'),
                ('4', 'rrryy')),
 '338654991': (('41', 'GG'), ('4', 'yy'), ('45', 'rr')),
 '3386573305': (('81', 'GGGG'), ('4', 'yyyy'), ('5', 'rrrr')),
 '3386573306': (('81', 'GG'), ('4', 'yy'), ('5', 'rr')),
 '5494111589': (('79', 'GGGG'), ('6', 'yyyy'), ('5', 'rrrr')),
 '5494111590': (('81', 'GGGGG'), ('4', 'yyyyy'), ('5', 'rrrrr')),
 '5494111593': (('79', 'GG'), ('6', 'yy'), ('5', 'rr')),
 '5494111594': (('79', 'GGGG'), ('6', 'yyyy'), ('5', 'rrrr')),
 '5494111596': (('81', 'GGGG'), ('4', 'yyyy'), ('5', 'rrrr')),
 '5494111597': (('79', 'GGGG'), ('6', 'yyyy'), ('5', 'rrrr')),
 '5494111603': (('81', 'GG'), ('4', 'yy'), ('5', 'rr')),
 'FAM_MARANHAO_MONSENHOR_EDUARDO': (('41', 'Grr'),
                                    ('3', 'yrr'),
                                    ('1', 'rrr'),
                                    ('41', 'rGG'),
                                    ('3', 'ryy'),
                                    ('1', 'rrr')),
 'FAM_RONDON_PARANA': (('41', 'GGGGrrr'),
                       ('3', 'yyyyrrr'),
                       ('1', 'rrrrrrr'),
                       ('41', 'rrrrGGG'),
                       ('3', 'rrrryyy'),
                       ('1', 'rrrrrrr')),
 'FAM_RONDON_ROTARY_CLUB': (('41', 'Grrrrrrrr'),
                            ('3', 'yrrrrrrrr'),
                            ('1', 'rrrrrrrrr'),
                            ('41', 'rGGGGGGGG'),
                            ('3', 'ryyyyyyyy'),
                            ('1', 'rrrrrrrrr'))}
EXPECTED_TLS_IDS = set(
    """
    1561879771 1561879807 1561879940 1561879989 1561880076 2042692453 2042692877 2042692883 2042692896
    2042693016 2042693107 2042693363 2963614071 338654991 3386573305 3386573306 5494111589 5494111590
    5494111593 5494111594 5494111596 5494111597 5494111603 8947803947 FAM_CESARIO_PARANA
    FAM_MARANHAO_MONSENHOR_EDUARDO FAM_RONDON_ANSELMO FAM_RONDON_BATALHAO_7962385968
    FAM_RONDON_BATALHAO_7962499397 FAM_RONDON_BELEM FAM_RONDON_BENJAMIM FAM_RONDON_NITEROI FAM_RONDON_PARANA
    FAM_RONDON_PORTO_ALEGRE FAM_RONDON_RIO_DE_JANEIRO FAM_RONDON_ROTARY_CLUB
    """.split()
)
REINDEXED_PARANA_MOVEMENTS = {('1156272393#6', '1156272393#7', '0', '0'): 0,
 ('1156272393#6', '1156272393#7', '1', '1'): 1,
 ('1156717168', '331577756#0', '0', '0'): 5,
 ('1156717168', '331577756#0', '1', '1'): 6,
 ('1156717173#4', '1156717173#5', '0', '0'): 2,
 ('1156717173#4', '1156717173#5', '1', '1'): 3,
 ('901328279#0', '901328279#1', '0', '0'): 4}
# Fecho geométrico/permissões nos extremos dos roads corrigidos. Cada interna
# foi conferida nas connections V1 com origem ou destino no recorte acima.
# O restante de cada nó vizinho continua protegido pelo fingerprint.
APPROVED_EDGES.update("""
    :10756697425_0 :10756697426_1 :1414446754_1 :1414447399_0 :1561879702_1
    :1561879702_3 :1561879723_0 :1561879723_1 :1561879834_0 :1561879834_2
    :1561880232_0 :1561880232_10 :1561880232_4 :1561880232_7 :2651934380_3
    :2783757276_0 :2783757276_1 :3050761420_0 :3050761426_0 :3050761426_1
    :3050761428_0 :3050761428_1 :3050761429_0 :3050761429_1 :3050761430_0
    :3050761431_0 :3050761432_0 :3050767817_0 :3050767820_0 :3050767823_0
    :3050767824_0 :3080535334_2 :3080535334_3 :3122223185_0 :3175865983_0
    :3175865983_1 :3386573300_0 :3386573302_0 :338685919_0 :338686577_0
    :338686644_0 :338686644_1 :338686695_0 :338686695_1 :338686704_0
    :338686704_1 :339114170_0 :4583137452_2 :4583137454_0 :4583137460_0
    :4583137460_4 :5525815522_0 :597213596_2 :7961826927_1 :7961826927_3
    :7963074869_1 :7963162192_0 :7963162196_0 :7963162196_1 :8630574940_2
    :8630574940_3 :8630574941_0 :9438164308_0 :9438164308_1
""".split())

# Europa × Benjamim e três miolos Suíça: recorte adicional confirmado.
APPROVED_NODES.update("""
    1561880196 1561880602 1561880700 1671075991 2042691601 2042691708
    2042691942 2744514583 2744514589 2744514592 4053646850 4053646858
    4053646862 4053646870 4055449701 4086937778 4125318226 4125318230
    7961952649 7961952650 8947803941 8947803942 8947803944 8947803946
    8947803947 ATENAS_SUICA AUSTRALIA_SUICA EUROPA_SUICA FAM_EUROPA_BENJAMIM
""".split())
APPROVED_EDGES.update("""
    -30648041#10 -30648041#11 -30648041#9 1167877348#west 269160814#west 269160815#3
    269160815#4 269160815#5 299469392#0 299469392#1 299469392#2 30621478#east
    30648041#10 30648041#11 30648041#9 30648910#1 30648910#2 30648910#3
    307152129#5 307152129#6 307152129#7 402968127#west 402968133#west 402968134
    402968135#0 402968135#1 402968135#2 402968136#0 402968136#8 402968136#9
    402968137 402968138 402968141#1 402968141#10 402968141#2 403166945#2
    403166945#3 602306725#east 602306729 602306733#west 602306736 602306739
    602306742 602306745#west 602306749#0 602306752 665897545 665897547
    665897583
""".split())
APPROVED_PROGRAMS.add("8947803947")
# Primeiro encontro real da saída Praça das Nações ajusta o início da lane.
APPROVED_EDGES.add("269160815#0")
SUICA_V1_MOVEMENTS = {'ATENAS_SUICA': (('-30648041#11', '-30648041#9', '0', '0'),
                  ('-30648041#11', '30648041#11', '0', '0'),
                  ('-30648041#11', '402968136#9', '0', '0'),
                  ('-30648041#11', '402968141#2', '0', '0'),
                  ('30648041#9', '-30648041#9', '0', '0'),
                  ('30648041#9', '30648041#11', '0', '0'),
                  ('30648041#9', '402968136#9', '0', '0'),
                  ('30648041#9', '402968141#2', '0', '0'),
                  ('402968136#8', '-30648041#9', '0', '0'),
                  ('402968136#8', '30648041#11', '0', '0'),
                  ('402968136#8', '402968136#9', '0', '0'),
                  ('402968136#8', '402968141#2', '0', '0'),
                  ('402968141#1', '-30648041#9', '0', '0'),
                  ('402968141#1', '30648041#11', '0', '0'),
                  ('402968141#1', '402968136#9', '0', '0'),
                  ('402968141#1', '402968141#2', '0', '0')),
 'AUSTRALIA_SUICA': (('269160815#3', '269160815#5', '0', '0'),
                     ('269160815#3', '299469392#2', '0', '0'),
                     ('269160815#3', '30648910#3', '0', '1'),
                     ('269160815#3', '307152129#7', '0', '0'),
                     ('299469392#0', '269160815#5', '0', '0'),
                     ('299469392#0', '299469392#2', '0', '0'),
                     ('299469392#0', '30648910#3', '0', '1'),
                     ('299469392#0', '307152129#7', '0', '0'),
                     ('30648910#1', '269160815#5', '1', '0'),
                     ('30648910#1', '299469392#2', '0', '0'),
                     ('30648910#1', '299469392#2', '1', '0'),
                     ('30648910#1', '30648910#3', '0', '0'),
                     ('30648910#1', '30648910#3', '1', '1'),
                     ('30648910#1', '307152129#7', '1', '0'),
                     ('307152129#5', '269160815#5', '0', '0'),
                     ('307152129#5', '299469392#2', '0', '0'),
                     ('307152129#5', '30648910#3', '0', '0'),
                     ('307152129#5', '30648910#3', '0', '1'),
                     ('307152129#5', '307152129#7', '0', '0')),
 'EUROPA_SUICA': (('307152129#7', '299469392#0', '0', '0'),
                  ('307152129#7', '402968135#2', '0', '0'),
                  ('307152129#7', '402968136#0', '0', '0'),
                  ('307152129#7', '402968137', '0', '0'),
                  ('402968135#0', '299469392#0', '0', '0'),
                  ('402968135#0', '402968135#2', '0', '0'),
                  ('402968135#0', '402968136#0', '0', '0'),
                  ('402968141#10', '299469392#0', '0', '0'),
                  ('402968141#10', '402968135#2', '0', '0'),
                  ('665897547', '299469392#0', '0', '0'),
                  ('665897547', '402968135#2', '0', '0'),
                  ('665897547', '402968136#0', '0', '0'),
                  ('665897547', '402968137', '0', '0'))}
SUICA_REMOVED_FRAGMENTS = {'ATENAS_SUICA': ('-30648041#10', '30648041#10'),
 'AUSTRALIA_SUICA': ('269160815#4', '299469392#1', '30648910#2', '307152129#6'),
 'EUROPA_SUICA': ('402968135#1', '402968138', '665897545', '665897583')}
EUROPA_BENJAMIM_MOVEMENTS = (('403166945#2', '602306733#west', '0', '0'),
 ('403166945#2', '602306725#east', '0', '1'),
 ('403166945#2', '602306745#west', '0', '0'),
 ('403166945#2', '1167877348#west', '0', '0'),
 ('402968133#west', '602306749#0', '0', '0'),
 ('402968133#west', '602306725#east', '0', '0'),
 ('402968133#west', '602306745#west', '0', '1'),
 ('402968133#west', '1167877348#west', '0', '0'),
 ('30621478#east', '602306749#0', '0', '0'),
 ('30621478#east', '602306745#west', '0', '0'),
 ('30621478#east', '602306745#west', '1', '1'),
 ('30621478#east', '1167877348#west', '0', '0'),
 ('402968127#west', '602306733#west', '0', '0'),
 ('402968127#west', '602306725#east', '0', '0'),
 ('402968127#west', '602306725#east', '1', '1'),
 ('269160814#west', '602306733#west', '0', '0'),
 ('269160814#west', '602306725#east', '0', '0'))

# Viena × Suíça: duas pistas do mesmo cruzamento sem armazenamento no miolo.
APPROVED_NODES.update({"1561880529", "4125318252", "VIENA_SUICA"})
APPROVED_EDGES.update("""
    -30648048#0 -30648048#1 -30648048#2 30648048#0 30648048#1 30648048#2
    402968136#0 402968136#1 402968141#9 402968141#10
""".split())

# Cesário × Paraná: três retenções físicas, reunidas sem ruas internas externas.
APPROVED_NODES.add("FAM_CESARIO_PARANA_JUNCTION")
CESARIO_CROSSING_NODES = {"339114019", "7963056109", "7963056110"}
VIENA_V1_MOVEMENTS = {
    ("-30648048#2", "-30648048#0", "0", "0"),
    ("-30648048#2", "30648048#2", "0", "0"),
    ("-30648048#2", "402968136#1", "0", "0"),
    ("-30648048#2", "402968141#10", "0", "0"),
    ("30648048#0", "-30648048#0", "0", "0"),
    ("30648048#0", "30648048#2", "0", "0"),
    ("30648048#0", "402968136#1", "0", "0"),
    ("30648048#0", "402968141#10", "0", "0"),
    ("402968136#0", "-30648048#0", "0", "0"),
    ("402968136#0", "30648048#2", "0", "0"),
    ("402968136#0", "402968136#1", "0", "0"),
    ("402968136#0", "402968141#10", "0", "0"),
    ("402968141#9", "-30648048#0", "0", "0"),
    ("402968141#9", "30648048#2", "0", "0"),
    ("402968141#9", "402968136#1", "0", "0"),
    ("402968141#9", "402968141#10", "0", "0"),
}

# Niterói: continuidade física e expansão dos ramos alcançáveis na fonte.
APPROVED_NODES.add("FAM_RONDON_NITEROI_JUNCTION")
JOINED_CROSSING_NODES = {old: "FAM_CESARIO_PARANA_JUNCTION" for old in CESARIO_CROSSING_NODES}
JOINED_CROSSING_NODES.update({old: "FAM_RONDON_NITEROI_JUNCTION" for old in ("338686240", "597213618")})
NITEROI_V1_MOVEMENTS = {
    ("30622933#11", "1156717175#0", "0", "0"),
    ("30622933#11", "1156717175#0", "0", "1"),
    ("30622933#11", "1156717177#0", "0", "0"),
    ("30622933#11", "1156717176", "0", "2"),
    ("30622933#11", "1156717176", "0", "3"),
    ("930831032#1", "1156717177#0", "0", "0"),
    ("930831032#1", "1156717176", "0", "0"),
    ("930831032#1", "1156717176", "1", "1"),
    ("930831032#1", "1156717176", "2", "2"),
    ("930831032#1", "1156717176", "3", "3"),
    ("931572689", "1156717175#0", "0", "0"),
    ("931572689", "1156717175#0", "1", "1"),
    ("931572689", "1156717175#0", "2", "2"),
    ("931572689", "1156717175#0", "3", "3"),
    ("931572689", "1156717177#0", "3", "0"),
    ("931572689", "1156717176", "3", "2"),
    ("931572689", "1156717176", "3", "3"),
}

# Europa × Rotary Club, abertura única independente de Europa × Suíça.
APPROVED_NODES.update({"338677202", "4055449706", "EUROPA_ROTARY_CLUB"})
APPROVED_EDGES.update({"-30622679#0", "30622679#0", "-665897549", "665897549",
                       "402968139#0", "402968147#2"})
ROTARY_V1_CURVE = (
    "4194.46,2693.92", "4197.10,2696.05", "4198.49,2697.80", "4198.61,2699.16",
    "4197.47,2700.13", "4197.29,2700.22", "4193.22,2701.31", "4188.37,2701.72",
    "4183.43,2701.66", "4179.14,2701.37",
)

# Maranhão × Monsenhor: duas zebras documentadas, sem tempo pedestre presumido.
APPROVED_NODES.update({"3391594553", "3391594554"})
APPROVED_EDGES.update({"30620737#13", "30620737#14", "261533405#16", "261533405#17",
                       ":3122205661_0", ":3122205661_1", ":3122205661_2", ":3122205661_4",
                       ":1561879534_0", ":1561879534_2", ":3391594556_0", ":3391594556_2"})
APPROVED_PROGRAMS.add("FAM_MARANHAO_MONSENHOR_EDUARDO")

PROTECTED_FINGERPRINT = "239a244b7e5446b4f7f9de0b5665a003ee235d767c66009dd2013ee9ddba87e9"


def connection_key(connection):
    return tuple(connection.get(field) for field in ("from", "to", "fromLane", "toLane"))


def approved_internal(identifier):
    return any(identifier.startswith(f":{node}_") for node in APPROVED_NODES)


class SignalInfrastructureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = infrastructure.NETWORK.read_text(encoding="utf-8")
        cls.root = ET.fromstring(cls.text)
        cls.edges = {edge.get("id"): edge for edge in cls.root.findall("edge")}
        cls.nodes = {node.get("id"): node for node in cls.root.findall("junction")}
        cls.connections = {connection_key(c): c for c in cls.root.findall("connection")}

    def test_content_outside_the_approved_area_remains_unchanged(self):
        digest = hashlib.sha256()
        for element in ET.fromstring(self.text):
            key = element.get('id', '')
            if element.tag == 'edge' and (key in APPROVED_EDGES or approved_internal(key)):
                continue
            if element.tag == 'junction' and (key in APPROVED_NODES or approved_internal(key)):
                continue
            if element.tag == 'tlLogic' and key in APPROVED_PROGRAMS:
                continue
            if element.tag == 'connection' and (element.get('from') in APPROVED_EDGES
                                                or approved_internal(element.get('from', ''))):
                continue
            if element.tag == 'roundabout' and set(element.get('nodes', '').split()) & {
                    '3371628024', 'SALOMAO_JOAO_PEREIRA'}:
                continue
            if element.tag == "location":
                element.attrib.pop("convBoundary", None)
            element.tail = None
            digest.update(ET.tostring(element))
            digest.update(b'\n')
        self.assertEqual(digest.hexdigest(), PROTECTED_FINGERPRINT)

    def test_projected_boundary_only_extends_to_the_restored_maria_approach(self):
        boundary = tuple(map(float, self.root.find("location").get("convBoundary").split(',')))
        self.assertEqual(boundary, (1708.09, 1490.49, 5558.45, 5205.87))
        for node in self.nodes.values():
            if node.get("id").startswith(":"):
                continue
            self.assertGreaterEqual(float(node.get("x")), boundary[0])
            self.assertGreaterEqual(float(node.get("y")), boundary[1])
            self.assertLessEqual(float(node.get("x")), boundary[2])
            self.assertLessEqual(float(node.get("y")), boundary[3])

    def test_all_controlled_links_are_external_and_have_complete_indices(self):
        controlled = set()
        for tls_id, expected in EXPECTED_CONTROLS.items():
            with self.subTest(tls=tls_id):
                links = [c for c in self.connections.values() if c.get("tl") == tls_id
                         and self.edges[c.get("from")].get("function") is None]
                counts = {}
                for connection in links:
                    origin = connection.get("from")
                    counts[origin] = counts.get(origin, 0) + 1
                    self.assertNotIn(connection_key(connection), controlled)
                    controlled.add(connection_key(connection))
                self.assertEqual(counts, expected)
                self.assertEqual(sorted(int(c.get("linkIndex")) for c in links),
                                 list(range(sum(expected.values()))))
        self.assertEqual(len(controlled), sum(sum(group.values()) for group in EXPECTED_CONTROLS.values()))
        unregulated = {"1156272392", "1156272394", "666324280", "965367671",
                       "1156717171", "1156717174", "602306713#22",
                       "853749385", "853749386", "462991287"}
        for c in self.connections.values():
            if c.get("from") in unregulated:
                self.assertIsNone(c.get("tl"))

    def test_reference_programs_and_special_normal_open_programs(self):
        self.assertEqual({t.get("id") for t in self.root.findall("tlLogic")}, EXPECTED_TLS_IDS)
        self.assertFalse(any(t.get("id") == "5494111602" for t in self.root.findall("tlLogic")))
        for tls_id, state in EXPECTED_STATES.items():
            with self.subTest(tls=tls_id):
                programs = [t for t in self.root.findall("tlLogic") if t.get("id") == tls_id]
                self.assertEqual(len(programs), 1)
                self.assertEqual(programs[0].get("programID"), "current")
                self.assertEqual(programs[0].get("offset"), "0")
                phases = programs[0].findall("phase")
                self.assertEqual(len(phases), 1)
                self.assertEqual(phases[0].get("duration"), "1")
                self.assertEqual(phases[0].get("state")[:len(state)], state)
                self.assertEqual(set(phases[0].get("state")[len(state):]) - {"r"}, set())

    def test_cesario_controls_the_five_physical_movements_at_three_retention_lines(self):
        joined = "FAM_CESARIO_PARANA_JUNCTION"
        expected = (
            ("154252437#1", "665897572", "0", "0"),
            ("602306713#21", "901328279#0", "0", "0"),
            ("602306713#21", "665897572", "0", "0"),
            ("665897556#1", "901328279#0", "0", "0"),
            ("665897556#1", "665897572", "0", "0"),
        )
        controls = [c for c in self.connections.values() if c.get("tl") == "FAM_CESARIO_PARANA"]
        vehicle_controls = [c for c in controls if self.edges[c.get("from")].get("function") is None]
        self.assertEqual({connection_key(c) for c in vehicle_controls}, set(expected))
        self.assertEqual(len(controls), 8)
        for index, movement in enumerate(expected):
            c = self.connections[movement]
            self.assertEqual(c.get("linkIndex"), str(index))
            self.assertEqual(self.edges[c.get("from")].get("to"), joined)
            self.assertEqual(self.edges[c.get("to")].get("from"), joined)
        for old in CESARIO_CROSSING_NODES:
            self.assertNotIn(old, self.nodes)
        for fragment in ("853749385", "853749386", "602306713#22"):
            self.assertNotIn(fragment, self.edges)
        crossing_map = {frozenset(e.get("crossingEdges").split()): e for e in self.edges.values()
                        if e.get("function") == "crossing" and e.get("id").startswith(f":{joined}_c")}
        self.assertEqual(set(crossing_map), {frozenset({road}) for road in
                         ("154252437#1", "602306713#21", "665897556#1")})
        for old, road in (("339114019", "154252437#1"), ("7963056110", "602306713#21"),
                          ("7963056109", "665897556#1")):
            for side in range(2):
                foot = f"{old}.ped.{road}.{side}"
                self.assertEqual(self.edges[foot].get("to"), joined)
        program = self.root.find("tlLogic[@id='FAM_CESARIO_PARANA']")
        self.assertEqual([(p.get("duration"), p.get("state")) for p in program.findall("phase")],
                         [("1", "ooooorrr")])

    def test_anselmo_has_three_continuous_lanes_and_the_documented_limit(self):
        lanes = self.edges["462991286"].findall("lane")
        self.assertEqual([lane.get("index") for lane in lanes], ["0", "1", "2"])
        self.assertEqual({lane.get("speed") for lane in lanes}, {"16.67"})
        for lane in range(3):
            self.assertIn(("1171563461", "462991286", str(lane + 1), str(lane)),
                          self.connections)
            through = self.connections[("462991286", "46711471#0", str(lane), str(lane + 1))]
            self.assertEqual(through.get("tl"), "FAM_RONDON_ANSELMO")
            self.assertEqual(through.get("linkIndex"), str(lane))
        # Ramo direito mantém duas faixas; sua zebra física não confirma novo TLS.
        self.assertEqual(len(self.edges["292932042#0"].findall("lane")), 2)
        for lane in range(2):
            self.assertIn(("1171563461", "292932042#0", str(lane), str(lane)),
                          self.connections)
        self.assertEqual(self.nodes["3050761411"].get("type"), "priority")

    def request_index(self, connection):
        node = self.nodes[self.edges[connection.get("from")].get("to")]
        via = connection.get("via")
        final_lanes = node.get("intLanes").split()
        # Conversões longas possuem uma junction interna intermediária. O request
        # usa a última parte da trajetória, mantendo o mesmo destino físico.
        for _ in range(20):
            if via in final_lanes:
                return node, final_lanes.index(via)
            internal_edge, internal_lane = via.rsplit("_", 1)
            following = [c for c in self.connections.values()
                         if c.get("from") == internal_edge and c.get("fromLane") == internal_lane
                         and c.get("to") == connection.get("to")
                         and c.get("toLane") == connection.get("toLane")]
            self.assertEqual(len(following), 1, connection.attrib)
            via = following[0].get("via")
            self.assertIsNotNone(via, connection.attrib)
        self.fail(f"Trajetória interna cíclica: {connection.attrib}")

    def test_recomputed_anselmo_conflicts_cover_all_three_through_lanes(self):
        through = [self.connections[("462991286", "46711471#0", str(i), str(i + 1))]
                   for i in range(3)]
        transverse = [c for c in self.connections.values()
                      if c.get("from") == "625668273#3"]
        self.assertEqual(len(through), 3)
        self.assertEqual(len(transverse), 5)
        for straight in through:
            node, i = self.request_index(straight)
            requests = node.findall("request")
            self.assertTrue(all(len(q.get("foes")) == len(requests) and
                                len(q.get("response")) == len(requests) for q in requests))
            for crossing in transverse:
                other_node, j = self.request_index(crossing)
                self.assertEqual(node.get("id"), other_node.get("id"))
                self.assertEqual(requests[i].get("foes")[-1 - j], "1")
                self.assertEqual(requests[j].get("foes")[-1 - i], "1")

    def test_batalhao_normal_open_signals_and_emergency_only_return(self):
        for tls_id in ("FAM_RONDON_BATALHAO_7962385968", "FAM_RONDON_BATALHAO_7962499397"):
            for c in self.connections.values():
                if c.get("tl") == tls_id:
                    self.assertEqual(c.get("dir"), "s")
        restricted = {"853694507", "-853694507"}
        for edge_id in restricted:
            for lane in self.edges[edge_id].findall("lane"):
                self.assertEqual(lane.get("allow"), "emergency")
                self.assertIsNone(lane.get("disallow"))
        protected_paths = set()
        for connection in self.connections.values():
            if not restricted.intersection({connection.get("from"), connection.get("to")}):
                continue
            via = connection.get("via")
            if not via:
                continue
            edge_id, lane_index = via.rsplit("_", 1)
            lane = self.edges[edge_id].find(f"lane[@index='{lane_index}']")
            self.assertEqual(lane.get("allow"), "emergency", connection.attrib)
            self.assertIsNone(lane.get("disallow"), connection.attrib)
            protected_paths.add(via)
        self.assertGreaterEqual(len(protected_paths), 7)

    def test_duplicate_porto_control_is_removed_without_removing_the_road(self):
        self.assertEqual(self.nodes["5494111602"].get("type"), "priority")
        self.assertEqual(len(self.edges["331577748#4"].findall("lane")), 4)
        for lane in range(4):
            connection = self.connections[("331577748#3", "331577748#4", str(lane), str(lane))]
            self.assertIsNone(connection.get("tl"))
            self.assertEqual(connection.get("state"), "M")
        self.assertTrue(any(c.get("tl") == "3386573305" for c in self.connections.values()))

    def test_benjamim_has_four_lanes_and_all_twelve_original_road_pairs(self):
        main = {"1156717163#3", "152937136#3"}
        side = {"666324302#5", "853751181#0"}
        exits = {"1156272391#0", "1156272393#0", "1156272395#1"}
        links = [c for c in self.connections.values()
                 if c.get("tl") == "FAM_RONDON_BENJAMIM"
                 and self.edges[c.get("from")].get("function") is None]
        self.assertEqual({(c.get("from"), c.get("to")) for c in links},
                         {(origin, destination) for origin in main | side for destination in exits})
        self.assertEqual(len(links), 18)
        for edge in main | {"1156272391#0", "1156272393#0"}:
            lanes = self.edges[edge].findall("lane")
            self.assertEqual(len(lanes), 4)
            self.assertEqual({float(l.get("width", "3.2")) for l in lanes}, {3.2})
        for origin, destination in (("1156717163#3", "1156272391#0"),
                                    ("152937136#3", "1156272393#0")):
            for lane in range(4):
                self.assertIn((origin, destination, str(lane), str(lane)), self.connections)
        for removed in ("1156272392", "1156272394", "666324280", "853751181#1",
                        "666324302#6", "1156272395#0"):
            self.assertNotIn(removed, self.edges)
        for approach in main | side:
            self.assertEqual(self.edges[approach].get("to"), "FAM_RONDON_BENJAMIM_JUNCTION")

    def test_benjamim_lane_expansion_preserves_documented_source_speeds(self):
        source_speeds = {
            "16.67": ("1156717163#2", "1156717163#3", "1156272391#0", "1156272391#1",
                      "1156272391#2", "1156272391#3"),
            "27.78": ("152937136#0", "152937136#1", "152937136#2", "152937136#3",
                      "1156272393#0", "1156272393#1", "1156272393#2"),
        }
        # Não foi obtida fonte específica que autorize trocar o limite legado
        # neste cruzamento. Expandir faixas não transfere o limite de Anselmo.
        for speed, roads in source_speeds.items():
            for road in roads:
                self.assertEqual({lane.get("speed") for lane in self.edges[road].findall("lane")},
                                 {speed}, road)

    def test_benjamim_turns_use_the_corresponding_outer_lanes(self):
        for origin, destination, lane_from, lane_to in (
                ("1156717163#3", "1156272395#1", "0", "0"),
                ("1156717163#3", "1156272393#0", "3", "3"),
                ("152937136#3", "1156272395#1", "3", "0"),
                ("152937136#3", "1156272391#0", "3", "3"),
                ("666324302#5", "1156272391#0", "0", "0"),
                ("666324302#5", "1156272393#0", "0", "3"),
                ("853751181#0", "1156272393#0", "0", "0"),
                ("853751181#0", "1156272391#0", "0", "3")):
            with self.subTest(origin=origin, destination=destination):
                self.assertIn((origin, destination, lane_from, lane_to), self.connections)

    def test_niteroi_join_preserves_seventeen_lane_pairs_and_both_crossings(self):
        joined = "FAM_RONDON_NITEROI_JUNCTION"
        links = [c for c in self.connections.values() if c.get("tl") == "FAM_RONDON_NITEROI"]
        vehicles = [c for c in links if self.edges[c.get("from")].get("function") is None]
        self.assertEqual({connection_key(c) for c in vehicles}, NITEROI_V1_MOVEMENTS)
        self.assertEqual(len(vehicles), 17)
        self.assertEqual(len(links), 19)
        for old in ("338686240", "597213618"):
            self.assertNotIn(old, self.nodes)
        self.assertNotIn("1156717174", self.edges)
        for c in vehicles:
            self.assertEqual(self.edges[c.get("from")].get("to"), joined)
            self.assertEqual(self.edges[c.get("to")].get("from"), joined)
            self.assertEqual(float(c.get("contPos")), 0)
            self.assertNotEqual(c.get("keepClear"), "0")
        crossings = [e for e in self.edges.values() if e.get("function") == "crossing"
                     and e.get("id").startswith(f":{joined}_c")]
        self.assertEqual({frozenset(e.get("crossingEdges").split()) for e in crossings},
                         {frozenset({"30622933#11"}), frozenset({"1156717177#0"})})
        for old, road in (("338686240", "30622933#11"), ("597213618", "1156717177#0")):
            for side in range(2):
                self.assertEqual(self.edges[f"{old}.ped.{road}.{side}"].get("to"), joined)
        # Os sinais fora da abertura continuam em suas próprias retenções.
        self.assertEqual(self.connections[("1156717175#0", "1156717175#1", "0", "0")].get("tl"), "5494111596")
        self.assertEqual(self.connections[("930831032#0", "930831032#1", "0", "0")].get("tl"), "5494111597")

    def test_niteroi_current_priorities_yield_at_conflicting_conversions(self):
        program = self.root.find("tlLogic[@id='FAM_RONDON_NITEROI']")
        self.assertEqual(len(program.findall("phase")), 1)
        state = program.find("phase").get("state")
        vehicles = [c for c in self.connections.values() if c.get("tl") == "FAM_RONDON_NITEROI"
                    and self.edges[c.get("from")].get("function") is None]
        for c in vehicles:
            node, index = self.request_index(c)
            request = node.find(f"request[@index='{index}']")
            self.assertEqual(state[int(c.get("linkIndex"))],
                             "o" if "1" in request.get("response") else "O")
            self.assertEqual(c.get("state"), state[int(c.get("linkIndex"))])
        protected = [c for c in vehicles if state[int(c.get("linkIndex"))] == "O"]
        self.assertEqual(len(protected), 8)
        self.assertEqual({c.get("dir") for c in protected}, {"s"})
        for first in protected:
            node, i = self.request_index(first)
            for second in protected:
                _, j = self.request_index(second)
                self.assertEqual(node.find(f"request[@index='{i}']").get("foes")[-1-j], "0")
        self.assertEqual(state[-2:], "rr")

    def test_northeast_ramp_adds_the_right_lane_without_artificial_merging(self):
        self.assertEqual(len(self.edges["152937136#0"].findall("lane")), 3)
        self.assertEqual(len(self.edges["152937136#1"].findall("lane")), 4)
        for lane in range(3):
            self.assertIn(("152937136#0", "152937136#1", str(lane), str(lane + 1)),
                          self.connections)
        self.assertIn(("152937010#3", "152937136#1", "0", "0"), self.connections)
        for before, after in (("152937136#1", "152937136#2"),
                              ("152937136#2", "152937136#3"),
                              ("1156272391#0", "1156272391#1"),
                              ("1156272391#1", "1156272391#2"),
                              ("1156272391#2", "1156272391#3")):
            for lane in range(4):
                self.assertIn((before, after, str(lane), str(lane)), self.connections)

    def test_restored_auxiliary_tls_control_all_four_physical_approaches(self):
        groups = {
            "2042693016": {"-647043773#0", "-647043774#0", "659117881", "616180216"},
            "2963614071": {"-659117905#2", "659117905#1", "-647043774#1", "647043774#0"},
            "2042693107": {"-616971271#1", "616971271#0", "-659117933#east", "659117933#west"},
        }
        for tls, approaches in groups.items():
            with self.subTest(tls=tls):
                links = [c for c in self.connections.values() if c.get("tl") == tls
                         and self.edges[c.get("from")].get("function") is None]
                self.assertEqual({c.get("from") for c in links}, approaches)
                self.assertEqual(len(links), 12)
                for origin in approaches:
                    self.assertEqual(self.edges[origin].get("to"), tls)
                    turns = [c.get("dir") for c in links if c.get("from") == origin]
                    self.assertEqual(set(turns), {"s", "r", "l"})
                self.assertFalse(any(c.get("dir") == "t" for c in links))
                phases = self.root.find(f"tlLogic[@id='{tls}']").findall("phase")
                self.assertEqual(sum(float(p.get("duration")) for p in phases), 90)
                self.assertEqual([p.get("duration") for p in phases if "y" in p.get("state")], ["3"] * 4)
                self.assertEqual([p.get("duration") for p in phases if set(p.get("state")) == {"r"}], ["5"] * 4)
                greens = [p.get("state") for p in phases if "G" in p.get("state")]
                self.assertEqual(len(greens), 4)
                for state in greens:
                    allowed = [c for c in links if state[int(c.get("linkIndex"))] == "G"]
                    self.assertEqual(len(allowed), 3)
                    self.assertEqual(len({c.get("from") for c in allowed}), 1)
                self.assertEqual({c.get("from") for c in links
                                  if any(state[int(c.get("linkIndex"))] == "G" for state in greens)}, approaches)

    def test_joined_junctions_preserve_road_pairs_without_artificial_storage(self):
        groups = {
            "VIENA_SUICA": (
                {"-30648048#2", "30648048#0", "402968136#0", "402968141#9"},
                {"-30648048#0", "30648048#2", "402968136#1", "402968141#10"},
                {"30648048#1", "-30648048#1"}),
            "FAM_RONDON_PARANA": (
                {"1156272393#7", "1156717173#5", "331577756#1", "901328279#2"},
                {"1156717163#0", "1156717166#0", "154252437#0", "331577749#0"},
                {"1156717164", "1156717165", "154252438", "331577755"}),
            "AFRICA_SUICA": (
                {"299469392#2", "30648920#0", "307152129#3", "402968122#3"},
                {"299469392#4", "30648920#2", "307152129#5", "402968122#5"},
                {"299469392#3", "30648920#1", "307152129#4", "402968122#4"}),
            "AFRICA_HOLANDA": (
                {"30648920#3", "402968122#0", "402968128#0", "403166940#2"},
                {"30648920#5", "402968122#2", "402968128#2", "403166940#4"},
                {"30648920#4", "402968122#1", "402968128#1", "403166940#3"}),
        }
        for node, (approaches, exits, removed) in groups.items():
            with self.subTest(junction=node):
                self.assertIn(node, self.nodes)
                for edge in removed:
                    self.assertNotIn(edge, self.edges)
                links = [c for c in self.connections.values() if c.get("from") in approaches]
                self.assertEqual({(c.get("from"), c.get("to")) for c in links},
                                 {(origin, destination) for origin in approaches for destination in exits})
                for c in links:
                    self.assertEqual(self.edges[c.get("from")].get("to"), node)
                    self.assertEqual(self.edges[c.get("to")].get("from"), node)
                    self.assertNotEqual(c.get("keepClear"), "0")
                requests = self.nodes[node].findall("request")
                self.assertEqual(len(requests), len(links))
                self.assertTrue(all(len(q.get("foes")) == len(requests) and
                                    len(q.get("response")) == len(requests) for q in requests))
                if node == "VIENA_SUICA":
                    self.assertEqual({connection_key(c) for c in links}, VIENA_V1_MOVEMENTS)
                    self.assertEqual(len(links), 16)

    def test_salomao_returns_follow_the_existing_roundabout(self):
        self.assertNotIn("330210597#0", self.edges)
        self.assertNotIn("-330210597#0", self.edges)
        self.assertNotIn("3371628024", self.nodes)
        self.assertNotIn("4025923697", self.nodes)
        roundabouts = [r for r in self.root.findall("roundabout")
                       if "SALOMAO_JOAO_PEREIRA" in r.get("nodes", "").split()]
        self.assertEqual(len(roundabouts), 1)
        circle = [f"399928437#{i}" for i in (7, 0, 1, 2, 3, 4, 5, 6)]
        for approach, destination in (("-330210597#1", "330210597#1"),
                                      ("30649092#1", "-30649092#1")):
            path = [approach, *circle, destination]
            for before, after in zip(path, path[1:]):
                self.assertTrue(any(c.get("from") == before and c.get("to") == after
                                    for c in self.connections.values()), (before, after))
            self.assertFalse(any(c.get("from") == approach and c.get("to") == destination
                                 for c in self.connections.values()))

    def test_previous_vehicle_phase_times_and_colours_are_preserved(self):
        for tls, expected in LEGACY_PHASES.items():
            with self.subTest(tls=tls):
                program = self.root.find(f"tlLogic[@id='{tls}']")
                self.assertIsNotNone(program)
                self.assertEqual(program.get("type"), "static")
                self.assertEqual(program.get("offset"), "0")
                self.assertEqual(program.get("programID"), "1624" if tls.startswith("FAM_") else "0")
                phases = program.findall("phase")
                self.assertEqual(len(phases), len(expected))
                for phase, (duration, original_state) in zip(phases, expected):
                    self.assertEqual(phase.get("duration"), duration)
                    if tls == "FAM_RONDON_PARANA":
                        for key, old_index in REINDEXED_PARANA_MOVEMENTS.items():
                            c = self.connections[key]
                            self.assertEqual(c.get("tl"), tls)
                            self.assertEqual(phase.get("state")[int(c.get("linkIndex"))],
                                             original_state[old_index])
                    else:
                        self.assertEqual(phase.get("state")[:len(original_state)], original_state)
                        self.assertEqual(set(phase.get("state")[len(original_state):]) - {"r"}, set())

    def test_short_transverse_fragments_are_collapsed_without_moving_retention(self):
        groups = (
            ("FAM_RONDON_NITEROI", "FAM_RONDON_NITEROI_JUNCTION", "3050767812", "30622933#12", "30622933#11", 90),
            ("FAM_RONDON_PORTO_ALEGRE", "2042691678", "3034565314", "30664532#3", "30664532#2", 110),
            ("FAM_RONDON_BELEM", "338685838", "3050767816", "965367673#1", "965367673#0", 3),
        )
        for tls, node, marker, removed, approach, minimum in groups:
            with self.subTest(tls=tls):
                self.assertNotIn(marker, self.nodes)
                self.assertNotIn(removed, self.edges)
                self.assertEqual(self.edges[approach].get("to"), node)
                self.assertGreater(float(self.edges[approach].find("lane").get("length")), minimum)
                controls = [c for c in self.connections.values() if c.get("from") == approach]
                self.assertTrue(controls)
                self.assertEqual({c.get("tl") for c in controls}, {tls})
        # Argentina e Belém convergem fisicamente antes do sinal. Não se inventa
        # armazenamento juntando a convergência real ao cruzamento com a Rondon.
        self.assertIn("339121104", self.nodes)
        self.assertEqual(self.edges["965367673#0"].get("from"), "339121104")
        self.assertLess(float(self.edges["965367673#0"].find("lane").get("length")), 10)

    def test_uncontrolled_median_connectors_yield_when_the_request_requires(self):
        found = set()
        for connection in self.connections.values():
            origin = connection.get("from")
            if origin not in {"1156717174", "1156717171", "965367671", "853749385", "853749386", "602306713#22"}:
                continue
            self.assertIsNone(connection.get("tl"))
            if not connection.get("via"):
                continue
            node, index = self.request_index(connection)
            response = node.find(f"request[@index='{index}']").get("response")
            if "1" in response:
                self.assertNotEqual(connection.get("state"), "M", connection.attrib)
                found.add(origin)
        self.assertEqual(found, {"1156717171", "965367671"})
        for removed in {"1156717174", "853749385", "853749386", "602306713#22"}:
            self.assertNotIn(removed, self.edges)

    def test_segismundo_has_four_approaches_bus_lanes_and_permitted_turns(self):
        approaches = {"-616971271#0", "154562663#north", "931172668#west", "398537158#east"}
        links = [c for c in self.connections.values() if c.get("tl") == "2042693363"
                 and self.edges[c.get("from")].get("function") is None]
        self.assertEqual({c.get("from") for c in links}, approaches)
        self.assertEqual(len(links), 16)
        self.assertNotIn("2042693363", self.nodes)
        self.assertNotIn("2042693385", self.nodes)
        for origin in approaches:
            self.assertEqual(self.edges[origin].get("to"), "FAM_MARIA_SEGISMUNDO")
        for road in ("616971270#east", "931172668#west", "398537158#east", "616971268#west"):
            lanes = self.edges[road].findall("lane")
            self.assertEqual(len(lanes), 2)
            self.assertEqual(lanes[1].get("allow"), "bus")
            self.assertEqual({lane.get("width") for lane in lanes}, {"3.20"})
        # Esquerdas da avenida são proibidas; Maria conserva suas conversões.
        self.assertFalse(any(c.get("dir") == "l" for c in links
                             if c.get("from") in {"931172668#west", "398537158#east"}))
        for road in {"-616971271#0", "154562663#north"}:
            self.assertTrue(any(c.get("from") == road and c.get("dir") == "l" for c in links))
        self.assertNotIn(("-616971271#0", "616971271#0", "0", "0"), self.connections)

    def test_documented_crossings_and_local_footpaths_are_complete(self):
        expected = {(JOINED_CROSSING_NODES.get(node, node),
                     frozenset(roads.split())) for node, roads in DOCUMENTED_CROSSINGS}
        expected.update(("FAM_MARIA_SEGISMUNDO", frozenset(roads.split()))
                        for roads in SEGISMUNDO_CROSSINGS)
        crossings = [e for e in self.edges.values() if e.get("function") == "crossing"]
        actual = {(e.get("id")[1:].rsplit("_c", 1)[0],
                   frozenset(e.get("crossingEdges").split())) for e in crossings}
        self.assertEqual(actual, expected)
        self.assertEqual(len(crossings), 43)
        physical_nodes = {node for node, _ in expected}
        for edge in self.edges.values():
            if edge.get("function") == "walkingarea":
                self.assertIn(edge.get("id")[1:].rsplit("_w", 1)[0], physical_nodes)
        for identifier in PEDESTRIAN_IDS:
            self.assertIn(identifier, self.nodes)
            self.assertIn(identifier, self.edges)
            self.assertEqual(self.edges[identifier].find("lane").get("allow"), "pedestrian")
        tls = "FAM_MARANHAO_MONSENHOR_EDUARDO"
        # Os três links veiculares e seus índices não mudam; só as duas zebras
        # ganham sua representação física, com atendimento r pendente.
        for road, next_road, lanes, first_index in (
                ("30620737#13", "30620737#14", 1, 0),
                ("261533405#16", "261533405#17", 2, 1)):
            for lane in range(lanes):
                link = self.connections[(road, next_road, str(lane), str(lane))]
                self.assertEqual((link.get("tl"), link.get("linkIndex")), (tls, str(first_index + lane)))
        for node_id, road, expected_index in (("3391594553", "30620737#14", "3"),
                                               ("3391594554", "261533405#17", "4")):
            crossing = self.edges[f":{node_id}_c0"]
            self.assertEqual(crossing.get("crossingEdges"), road)
            self.assertEqual(float(crossing.find("lane").get("width")), 4)
            controlled = [c for c in self.connections.values()
                          if crossing.get("id") in (c.get("from"), c.get("to")) and c.get("tl") == tls]
            self.assertEqual(len(controlled), 2)
            self.assertEqual({c.get("from") == crossing.get("id") for c in controlled}, {False, True})
            for link in controlled:
                self.assertEqual((link.get("tl"), link.get("linkIndex")), (tls, expected_index))
            for side in range(2):
                self.assertEqual(self.edges[f"{node_id}.ped.{road}.{side}"].get("to"), node_id)
        for connection in self.connections.values():
            if self.edges[connection.get("from")].get("function") != "crossing" or not connection.get("tl"):
                continue
            program = self.root.find(f"tlLogic[@id='{connection.get('tl')}']")
            index = int(connection.get("linkIndex"))
            self.assertTrue(all(p.get("state")[index] == "r" for p in program.findall("phase")))

    def test_isolated_crossing_accesses_preserve_the_physical_retention(self):
        heads = {
            "13738551275", "13738551276", "3050761411", "338654991",
            "3386573294", "3386573296", "3386573297", "3386573298",
            "3386573305", "3386573306", "5494111589", "5494111594",
            "5494111596", "5494111597", "5494111603", "5525815656",
            "8622218071", "8622218072", "8622218073", "FAM_RIO_NE", "FAM_RIO_SW",
        }
        for node_id in heads:
            node = self.nodes[node_id]
            self.assertEqual(node.get("customShape"), "1", node_id)
            position = (float(node.get("x")), float(node.get("y")))
            roads = [e for e in self.edges.values() if e.get("to") == node_id
                     and e.get("function") is None and ".ped." not in e.get("id")]
            self.assertEqual(len(roads), 1)
            for lane in roads[0].findall("lane"):
                start, end = [tuple(map(float, p.split(','))) for p in lane.get("shape").split()[-2:]]
                distance = math.dist(start, end)
                longitudinal = sum((position[i] - end[i]) * (end[i] - start[i]) for i in range(2)) / distance
                # O nó documenta a retenção/zebra; acessos artificiais não devem
                # deslocar o fim das faixas 9–20 m para montante dessa posição.
                self.assertLessEqual(abs(longitudinal), 4.1, (node_id, lane.attrib))
        # Os três contornos multi-aproximação também conservam os comprimentos
        # da referência recompilada com as mesmas roads/faixas/zebras, sem
        # usar o pedestre como uma aproximação veicular adicional.
        for node_id, road, lane_count, expected_length in (
                ("2651934389", "576014296#2", 4, 61.60),
                ("2783757296", "462991286", 3, 5.24),
                ("5494111590", "1156717175#5", 4, 14.45)):
            self.assertEqual(self.nodes[node_id].get("customShape"), "1")
            self.assertEqual(self.edges[road].get("to"), node_id)
            lanes = self.edges[road].findall("lane")
            self.assertEqual(len(lanes), lane_count)
            for lane in lanes:
                self.assertAlmostEqual(float(lane.get("length")), expected_length, delta=.03)
        self.assertEqual(len(self.edges["292932042#0"].findall("lane")), 2)
        self.assertEqual(len(self.edges["462991287"].findall("lane")), 2)
        self.assertEqual(self.edges["-300965440"].get("to"), "2651934389")
        self.assertEqual(self.edges["625668273#3"].get("to"), "2783757296")
        crossing_link = next(c for c in self.connections.values()
                             if c.get("to") == ":5494111590_c0" and c.get("tl") == "5494111590")
        self.assertEqual(crossing_link.get("linkIndex"), "5")
        self.assertTrue(all(p.get("state")[5] == "r" for p in
                            self.root.find("tlLogic[@id='5494111590']").findall("phase")))
        head = self.nodes["5494111590"]
        a = self.nodes[self.edges["1156717175#5"].get("from")]
        dx, dy = float(head.get("x")) - float(a.get("x")), float(head.get("y")) - float(a.get("y"))
        for side in range(2):
            foot = self.nodes[f"5494111590.ped.1156717175#5.{side}"]
            shift = ((float(foot.get("x")) - float(head.get("x"))) * dx +
                     (float(foot.get("y")) - float(head.get("y"))) * dy) / math.hypot(dx, dy)
            self.assertLess(abs(shift), .02)
        self.assertEqual(self.edges["463014795#0"].get("from"), "7963162192")
        self.assertEqual(self.edges["463014795#0"].get("to"), "8622218071")
        self.assertAlmostEqual(float(self.edges["463014795#0"].find("lane").get("length")), 9.40, delta=.02)
        self.assertGreaterEqual(float(self.edges["463014795#1"].find("lane").get("length")), 1.9)
        self.assertIn("853760488#1", self.edges)
        self.assertEqual(self.edges["853760488#1"].get("to"), "7963162192")
        self.assertEqual(self.nodes["7963162192"].get("type"), "priority")
        self.assertIn("8630574941", self.nodes)
        crossing = next(e for e in self.edges.values() if e.get("function") == "crossing"
                        and e.get("id").startswith(":8622218071_c"))
        self.assertEqual(crossing.get("crossingEdges"), "463014795#0")
        self.assertEqual(float(crossing.find("lane").get("width")), 4)

    def test_no_conflicting_vehicle_movements_have_simultaneous_protected_green(self):
        groups = {}
        for connection in self.connections.values():
            if not connection.get("tl") or self.edges[connection.get("from")].get("function"):
                continue
            node, index = self.request_index(connection)
            groups.setdefault((connection.get("tl"), node.get("id")), []).append((connection, index))
        for (tls, node_id), links in groups.items():
            program = self.root.find(f"tlLogic[@id='{tls}']")
            requests = {int(q.get("index")): q for q in self.nodes[node_id].findall("request")}
            for phase in program.findall("phase"):
                state = phase.get("state")
                for first, i in links:
                    if state[int(first.get("linkIndex"))] != "G":
                        continue
                    for second, j in links:
                        if j <= i or state[int(second.get("linkIndex"))] != "G":
                            continue
                        self.assertEqual(requests[i].get("foes")[-1 - j], "0",
                                         (tls, first.attrib, second.attrib))

    def test_suica_joins_keep_all_forty_eight_original_lane_pairs(self):
        total = 0
        for node, movements in SUICA_V1_MOVEMENTS.items():
            expected = set(movements)
            actual = {connection_key(c) for c in self.connections.values()
                      if self.edges[c.get("from")].get("to") == node
                      and self.edges[c.get("from")].get("function") is None}
            self.assertEqual(actual, expected, node)
            for removed in SUICA_REMOVED_FRAGMENTS[node]:
                self.assertNotIn(removed, self.edges)
            for key in actual:
                self.assertEqual(self.edges[key[1]].get("from"), node)
            total += len(actual)
        self.assertEqual(total, 48)

    def test_europa_benjamim_covers_five_approaches_and_respects_turn_restrictions(self):
        links = [c for c in self.connections.values() if c.get("tl") == "8947803947"
                 and self.edges[c.get("from")].get("function") is None]
        self.assertEqual({connection_key(c) for c in links}, set(EUROPA_BENJAMIM_MOVEMENTS))
        self.assertEqual(len(links), 17)
        self.assertEqual(len({c.get("from") for c in links}), 5)
        for c in links:
            self.assertEqual(self.edges[c.get("from")].get("to"), "FAM_EUROPA_BENJAMIM")
            self.assertEqual(self.edges[c.get("to")].get("from"), "FAM_EUROPA_BENJAMIM")
        self.assertFalse(any(c.get("from") == "30621478#east" and c.get("to") == "602306733#west" for c in links))
        self.assertFalse(any(c.get("from") == "402968127#west" and c.get("to") == "602306749#0" for c in links))
        for road in ("30621478#east", "602306725#east", "402968127#west", "602306745#west"):
            self.assertEqual(len(self.edges[road].findall("lane")), 2)
        for removed in ("403166945#3", "402968134", "602306729", "602306736", "602306739", "602306742", "602306752"):
            self.assertNotIn(removed, self.edges)

    def test_rotary_join_keeps_nine_movements_the_source_curve_and_external_waits(self):
        node = "EUROPA_ROTARY_CLUB"
        origins = {"402968135#2", "402968147#2", "-30622679#0"}
        destinations = {"665897547", "402968139#0", "30622679#0"}
        expected = {(origin, last, "0", "0") for origin in origins for last in destinations}
        links = [c for c in self.connections.values() if c.get("from") in origins]
        self.assertEqual({connection_key(c) for c in links}, expected)
        self.assertEqual(len(links), 9)
        for old in ("338677202", "4055449706"):
            self.assertNotIn(old, self.nodes)
        for fragment in ("665897549", "-665897549"):
            self.assertNotIn(fragment, self.edges)
        for c in links:
            self.assertEqual(self.edges[c.get("from")].get("to"), node)
            self.assertEqual(self.edges[c.get("to")].get("from"), node)
            self.assertIsNone(c.get("tl"))
        self.assertIn("EUROPA_SUICA", self.nodes)
        self.assertNotEqual(self.nodes[node].get("x"), self.nodes["EUROPA_SUICA"].get("x"))
        for origin, last in (("-30622679#0", "30622679#0"), ("402968135#2", "665897547")):
            c = self.connections[(origin, last, "0", "0")]
            self.assertEqual(float(c.get("contPos")), 0)
            self.assertNotEqual(c.get("keepClear"), "0")
        # O traçado atravessa exatamente os vértices da curva composta V1,
        # sem a diagonal curta produzida pelo heurístico de join.
        turn = self.connections[("402968147#2", "30622679#0", "0", "0")]
        internal, lane_index = turn.get("via").rsplit("_", 1)
        curve = self.edges[internal].find(f"lane[@index='{lane_index}']").get("shape").split()
        cursor = 0
        for point in ROTARY_V1_CURVE:
            self.assertIn(point, curve[cursor:])
            cursor = curve.index(point, cursor) + 1
        requests = self.nodes[node].findall("request")
        self.assertEqual(len(requests), 9)
        self.assertTrue(all(len(q.get("response")) == 9 and len(q.get("foes")) == 9 for q in requests))

    def test_every_tls_has_complete_indices_and_phase_states(self):
        programs = {p.get("id"): p for p in self.root.findall("tlLogic")}
        links = {}
        for c in self.connections.values():
            if c.get("tl") is not None:
                self.assertIn(c.get("tl"), programs)
                links.setdefault(c.get("tl"), set()).add(int(c.get("linkIndex")))
        self.assertEqual(set(links), set(programs))
        for tls, indices in links.items():
            self.assertEqual(indices, set(range(max(indices) + 1)), tls)
            for phase in programs[tls].findall("phase"):
                self.assertEqual(len(phase.get("state")), max(indices) + 1, tls)

    def test_joao_retention_is_at_the_documented_crossing(self):
        self.assertEqual(self.nodes["5494111593"].get("type"), "priority")
        self.assertEqual(self.nodes["5525815656"].get("type"), "traffic_light")
        for lane in range(2):
            relocated = self.connections[("462993308#1", "462993308#2", str(lane), str(lane))]
            self.assertEqual(relocated.get("tl"), "5494111593")
            self.assertIsNone(self.connections[("462993308#0", "462993308#1",
                                               str(lane), str(lane))].get("tl"))

    def test_real_rio_tls_exists_without_a_fabricated_settran_plan(self):
        tls = "FAM_RONDON_RIO_DE_JANEIRO"
        links = [c for c in self.connections.values() if c.get("tl") == tls
                 and self.edges[c.get("from")].get("function") is None]
        self.assertEqual({c.get("from") for c in links}, {"1156272393#5", "1156717163#1"})
        self.assertEqual(len(links), 8)
        self.assertEqual(self.edges["1156272393#5"].get("to"), "FAM_RIO_SW")
        self.assertEqual(self.edges["1156717163#1"].get("to"), "FAM_RIO_NE")
        for origin in ("1156272393#5", "1156717163#1"):
            for lane in range(4):
                self.assertEqual(self.connections[(origin, origin + ".rio", str(lane), str(lane))].get("tl"), tls)

    def test_idempotence_and_check_do_not_write(self):
        self.assertEqual(infrastructure.corrected_network_text(self.text), self.text)
        with tempfile.TemporaryDirectory() as directory:
            network = Path(directory) / "network.net.xml"
            network.write_text(self.text, encoding="utf-8")
            stat = network.stat()
            with redirect_stdout(io.StringIO()):
                self.assertEqual(infrastructure.main(["--net-file", str(network)]), 0)
                self.assertEqual(infrastructure.main(["--net-file", str(network), "--check"]), 0)
            self.assertEqual(network.read_text(encoding="utf-8"), self.text)
            self.assertEqual(network.stat().st_mtime_ns, stat.st_mtime_ns)

    def test_unknown_revision_is_rejected_before_writing(self):
        altered = self.text.replace('speed="13.89"', 'speed="13.88"', 1)
        with tempfile.TemporaryDirectory() as directory:
            network = Path(directory) / "network.net.xml"
            network.write_text(altered, encoding="utf-8")
            stat = network.stat()
            with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as stopped:
                infrastructure.main(["--net-file", str(network)])
            self.assertEqual(stopped.exception.code, 1)
            self.assertEqual(network.read_text(encoding="utf-8"), altered)
            self.assertEqual(network.stat().st_mtime_ns, stat.st_mtime_ns)


if __name__ == "__main__":
    unittest.main()
