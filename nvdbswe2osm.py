#!/usr/bin/env python3
# -*- coding: utf8

# nvdbswe2osm
# Converts NVDB data to OSM.
# Program loads geojson file for municipality.
# Order "homogeniserad" file from Lastkajen at Trafikverket and convert to geojson in QGIS or elsewehere.
# No dependencies beyond standard python for GeoJSON input.
# For FileGDB/GeoPackage/Shapefile: requires fiona and pyproj (pip install fiona pyproj).


import json
import sys
import copy
import math
import time
import argparse
import os
import glob
import concurrent.futures
import resource
from xml.etree import ElementTree as ET
from typing import Any, Optional, Union, Dict, List, Tuple, Callable

try:
    import osmium
    _has_osmium = True
except ImportError:
    _has_osmium = False


version = "0.5.0"

debug = False  # Add extra tags for debugging/testing
quiet = False  # Suppress output in worker processes

angle_margin = (
    45.0  # Maximum turn at intersection before highway is split into new way (degrees).
)

bridge_margin = 50.0  # Bridges over this length is always tagged as bridge, instead of tunnel duct for road underneath (meters)

coordinate_decimals = 7  # Number of decimals in coordinates

simplify_method = "refname"  # Options for generating long ways before output: "recursive", "route" or "refname"

simplify_factor = (
    0.2  # Minimum deviation permitted for node in segment polygons (meters).
)
# Set to 0 to avoid simplifying polygons.

segment_output = False  # When true: Output each highway segments as in input file, without creating longer ways


# Conversion table for nvdb attribute names, to make them more readable in code.
# Some of them are not used.

nvdb_attributes = {
    "Hogst_55_30": "Begränsat axel-boggitryck/Högsta tillåtna tryck",
    "L_Blandskydd_2": "Bländskydd(V)",
    "R_Blandskydd_2": "Bländskydd(H)",
    "Ident_191": "Bro och tunnel/Identitet",
    "Langd_192": "Bro och tunnel/Längd",
    "Namn_193": "Bro och tunnel/Namn",
    "konst_190": "Bro och tunnel/Konstruktion",
    "Brunn___Slamsugning_2": "Brunn-slamsugning",
    "L_Mater_301": "Bullerskydd-väg/Materialtyp(V)",
    "R_Mater_301": "Bullerskydd-väg/Materialtyp(H)",
    "Barig_64": "Bärighet/Bärighetsklass",
    "Barig_504": "Bärighet/Bärighetsklass vinterperiod",
    "Namn_457": "C-Cykelled/Namn",
    "C_Cykelled": "C-Cykelled",
    "C_Rekommenderad_bilvag_for_c": "C-Rekommenderad bilväg for cykel",
    "F_Cirkulationsplats": "Cirkulationsplats(F)",
    "B_Cirkulationsplats": "Cirkulationsplats(B)",
    "Vagde_10379": "Driftbidrag statligt/Vägdelsnr",
    "Vagnr_10370": "Driftbidrag statligt/Vägnr",
    "drift_2": "Driftområde/namn",
    "entre_380": "Driftområde/entreprenör",
    "Driftvandplats_2": "Driftvändplats",
    "LageF_83": "Farthinder/Läge",
    "TypAv_82": "Farthinder/Typ",
    "FPV_dagliga_personresor_2": "FPV-Dagliga personresor",
    "FPV_godstransporter_2": "FPV-Godstransporter",
    "FPV_kollektivtrafik_2": "FPV-Kollektivtrafik",
    "FPV_langvaga_personresor_2": "FPV-Långväga personresor",
    "FPV_k_309": "Funktionellt prioriterat vägnät/FPV-klass",
    "Framk_161": "Framkomlighet för vissa fordonskombinationer/Framkomlighetsklass",
    "Klass_181": "Funktionell vägklass/Klass",
    "Farjeled": "Färjeled",
    "Farje_139": "Färjeled/Färjeledsnamn",
    "F_ForbjudenFardriktning": "Förbjuden färdriktning(F)",
    "B_ForbjudenFardriktning": "Förbjuden färdriktning(B)",
    "F_ForbudTrafik": "Förbud mot trafik(F)",
    "B_ForbudTrafik": "Förbud mot trafik(B)",
    "F_Gallar_135": "Förbud mot trafik/Gäller fordon(F)",
    "B_Gallar_135": "Förbud mot trafik/Gäller fordon(B)",
    "F_Total_136": "Förbud mot trafik/Totalvikt(F)",
    "B_Total_136": "Förbud mot trafik/Totalvikt(B)",
    "Namn_130": "Gatunamn/Namn",
    "GCM_belyst_1": "GCM-belyst",
    "Trafi_86": "GCM-passage/Trafikanttyp",
    "Passa_85": "GCM-passage/Passagetyp",
    "GCM_passage_1": "GCM-passage",
    "L_Separ_500": "GCM-separation/Separation(V)",
    "R_Separ_500": "GCM-separation/Separation(H)",
    "GCM_t_502": "GCM-vägtyp/GCM-typ",
    "L_Gagata": "Gågata(V)",
    "R_Gagata": "Gågata(H)",
    "L_Gangfartsomrade": "Gångfartsområde(V)",
    "R_Gangfartsomrade": "Gångfartsområde(H)",
    "F_Hogst_225": "Hastighetsgräns/Högsta tillåtna hastighet(F)",
    "B_Hogst_225": "Hastighetsgräns/Högsta tillåtna hastighet(B)",
    "Hallplats_2": "Hållplats",
    "Hojdh_145": "Höjdhinder upp till 4,5 m/Höjdhinderidentitet",
    "Hojdh_144": "Höjdhinder upp till 4,5 m/Höjdhindertyp",
    "Fri_h_143": "Höjdhinder upp till 4,5 m/Fri höjd",
    "F_Beskr_124": "Inskränkningar för transport av farligt gods/Beskrivning(F)",
    "B_Beskr_124": "Inskränkningar för transport av farligt gods/Beskrivning(B)",
    "Plank_92": "Järnvägskorsning/Plankorsnings-Id",
    "Senas_107": "Järnvägskorsning/Senast ändrad",
    "X_koo_105": "Järnvägskorsning/X-koordinat",
    "Y_koo_106": "Järnvägskorsning/Y-koordinat",
    "Konta_103": "Järnvägskorsning/Kontaktledning",
    "Kort__104": "Järnvägskorsning/Kort magasin",
    "Antal_96": "Järnvägskorsning/Antal spår",
    "Jvg_b_93": "Järnvägskorsning/Jvg-bandel",
    "Vagpr_98": "Järnvägskorsning/Vägprofil tvär kurva",
    "Vagpr_99": "Järnvägskorsning/Vägprofil brant lutning",
    "Vagsk_100": "Järnvägskorsning/Vägskydd",
    "Porta_101": "Järnvägskorsning/Portalhöjd",
    "Tagfl_102": "Järnvägskorsning/Tågflöde",
    "Vagpr_97": "Järnvägskorsning/Vägprofil farligt vägkrön",
    "Jvg_k_94": "Järnvägskorsning/Jvg-kilometer",
    "Jvg_m_95": "Järnvägskorsning/Jvg-meter",
    "Katastrofoverfart_2": "Katastroföverfart",
    "F_Korfa_517": "Kollektivkörfält/Körfält-Körbana(F)",
    "B_Korfa_517": "Kollektivkörfält/Körfält-Körbana(B)",
    "Lever_292": "Leveranskvalitet DoU 2017/Leveranskvalitetsklass DoU 2017",
    "Miljozon": "Miljözon",
    "mittr_10": "Mittremsa/bredd",
    "Motortrafikled": "Motortrafikled",
    "Motorvag": "Motorväg",
    "F_Omkorningsforbud": "Omkörningsförbud(F)",
    "B_Omkorningsforbud": "Omkörningsförbud(B)",
    "L_Rastficka_2": "Rastficka(V)",
    "R_Rastficka_2": "Rastficka(H)",
    "Huvud_117": "Rastplats/Huvudman",
    "Rastp_118": "Rastplats/Rastplatsnamn",
    "Antal_124": "Rastplats/Antal markerade parkeringsplatser för buss",
    "Antal_123": "Rastplats/Antal markerade parkeringsplatser för husbil",
    "Antal_121": "Rastplats/Antal markerade parkeringsplatser för lastbil",
    "Antal_122": "Rastplats/Antal markerade parkeringsplatser för lastbil+släp",
    "Antal_120": "Rastplats/Antal markerade parkeringsplatser för personbil+släp",
    "Ovrig_125": "Rastplats/Övrig parkeringsmöjlighet",
    "Lanka_127": "Rastplats/Länkadress",
    "Resta_131": "Rastplats/Restaurang",
    "Serve_132": "Rastplats/Servering",
    "Hundr_133": "Rastplats/Hundrastgård",
    "Rastplats": "Rastplats",
    "Antal_119": "Rastplats/Antal markerade parkeringsplatser för personbil",
    "Dusch_126": "Rastplats/Duschmöjlighet",
    "Rekom_185": "Rekommenderad väg för farligt gods/Rekommendation",
    "L_Raffe_396": "Räffla/Räffeltyp(V)",
    "R_Raffe_396": "Räffla/Räffeltyp(H)",
    "Slitl_152": "Slitlager/Slitlagertyp",
    "F_Stigningsfalt": "Stigningsfält(F)",
    "B_Stigningsfalt": "Stigningsfält(B)",
    "Vagna_406": "Strategiskt vägnät för tyngre transporter/Vägnät för tyngre transporter",
    "TEN_T_489": "TEN-T Vägnät/TEN-T-Logisk-Länk-id",
    "TEN_T_488": "TEN-T Vägnät/TEN-T-Länk-id",
    "Tillg_169": "Tillgänglighet/Tillgänglighetsklass",
    "ADT_f_117": "Trafik/ÅDT fordon",
    "ADT_l_115": "Trafik/ÅDT lastbilar",
    "ADT_a_113": "Trafik/ÅDT axelpar",
    "Matar_121": "Trafik/Mätårsperiod",
    "Viltpassage_i_plan_2": "Viltpassage i plan",
    "L_Uppsa_320": "Viltstängsel/uppsättningsår(V)",
    "R_Uppsa_320": "Viltstängsel/uppsättningsår(H)",
    "L_Vilts_319": "Viltstängsel/viltstängselstyp(V)",
    "R_Vilts_319": "Viltstängsel/viltstängselstyp(H)",
    "L_Viltuthopp_2": "Viltuthopp(V)",
    "R_Viltuthopp_2": "Viltuthopp(H)",
    "drift_50": "Vinter2003/driftsklass",
    "L_VVIS": "VVIS(V)",  # Weather stations
    "R_VVIS": "VVIS(H)",
    "slitl_25": "VV-Slitlager/typ",
    "Bredd_156": "Vägbredd/Bredd",
    "Passe_73": "Väghinder/Passerbar bredd",
    "Hinde_72": "Väghinder/Hindertyp",
    "Vagha_7": "Väghållare/Väghållarnamn",
    "Forva_9": "Väghållare/Förvaltningsform",
    "Vagha_6": "Väghållare/Väghållartyp",
    "Kateg_380": "Vägkategori/Kategori",
    "VN_Europavag": "Europaväg",
    "F_Vagnummer": "Vägnummer(F)",
    "B_Vagnummer": "Vägnummer(B)",
    "Europ_16": "Vägnummer/Europaväg",
    "Huvud_13": "Vägnummer/Huvudnummer",
    "Under_14": "Vägnummer/Undernummer",
    "Lanst_15": "Vägnummer/Länstillhörighet",
    "L_vagra_282": "Vägräcke/vägräckstyp(V)",
    "R_vagra_282": "Vägräcke/vägräckstyp(H)",
    "L_gemen_283": "Vägräcke/gemensamt mitträcke(V)",
    "R_gemen_283": "Vägräcke/gemensamt mitträcke(H)",
    "L_vagra_277": "Vägräckesavslutning/vägräckesavslutningstyp(V)",
    "R_vagra_277": "Vägräckesavslutning/vägräckesavslutningstyp(H)",
    "Vagtr_474": "Vägtrafiknät/Nättyp",
    "korfa_52": "Vägtyp/körfältsbeskrivning",
    "vagty_41": "Vägtyp/typ",
    "Vandm_176": "Vändmöjlighet/Vändmöjlighetsklass",
    "Overledningsplats_2": "Överledningsplats",
    "Namns_133": "Övrigt vägnamn/Namnsättande organisation",
    "Namn_132": "Övrigt vägnamn/Namn",
    "Korfa_497": "Antal körfält/Körfältsantal",
    "F_ATK_Matplats_117": "ATK-Mätplats(F)",
    "B_ATK_Matplats_117": "ATK-Mätplats(B)",
    "F_ATK_Matplats": "ATK-Mätplats(F)",
    "B_ATK_Matplats": "ATK-Mätplats(B)",
    "F_Hogst_24": "Begränsad bruttovikt/Högsta tillåtna bruttovikt(F)",
    "B_Hogst_24": "Begränsad bruttovikt/Högsta tillåtna bruttovikt(B)",
    "F_Avser_28": "Begränsad bruttovikt/Avser även fordonståg(F)",
    "B_Avser_28": "Begränsad bruttovikt/Avser även fordonståg(B)",
    "Hogst_36": "Begränsad fordonsbredd/Högsta tillåtna fordonsbredd",
    "Hogst_46": "Begränsad fordonslängd/Högsta tillåtna fordonslängd",
    "F_Beskr_454": "Begränsad bruttovikt/Beskrivning(F)",
    "B_Beskr_454": "Begränsad bruttovikt/Beskrivning(B)",
    "FPV_dagliga_personresor": "FPV-Dagliga personresor",
    "FPV_godstransporter": "FPV-Godstransporter",
    "FPV_kollektivtrafik": "FPV-Kollektivtrafik",
    "FPV_langvaga_personresor": "FPV-Långväga personresor",
    "Funktionellt_priovagnat": "Funktionellt prioriterat vägnät",
    "GCM_belyst": "GCM-belyst",
    "GCM_passage": "GCM-passage",
    "Brunn___Slamsugning": "Brunn-slamsugning",
    "Hallplats": "Hållplats",
    "Katastrofoverfart": "Katastroföverfart",
    "C_Rekbilvagcykeltrafik": "C-Rekommenderad bilväg for cykel",
    "L_Kalib_195": "Kalibreringsväg(V)",
    "R_Kalib_195": "Kalibreringsväg(H)",
    "Korfa_524": "Körfältsinformation",
    "L_P_ficka": "P-ficka(V)",
    "R_P_ficka": "P-ficka(H)",
    "M_P_ficka": "P-ficka(M)",
    "Provisorisk_vag": "Provisorisk väg",
    "Avvik_540": "Avvikande vägtyp",
    "Kommu_141": "Kommunnr",
    "Vagkl_564": "Vägklass",
    "Kledn_417": "Körbanaledningsnät",
    "Kmaga_415": "Körbaneantagningsåtgärd",
    "PlkId_410": "Platskilsidentitet",
    "Phojd_411": "Profilhöjd",
    "Vlutn_412": "Väglutning",
    "Vkron_413": "Vägkrona",
    "Vkurv_414": "Vägkurvatur",
    "Vskyd_416": "Vägskydd",
    "Lroll_559": "Länkroll",
    "Forva_9": "Förvaltningsform",
    "nyaar_576": "Nybyggnadsår",
    "objnm_579": "Nybyggnadsår objektnamn",
    "omaar_566": "Ombyggnadsår",
    "objnm_573": "Ombyggnadsår objektnamn",
    "Konst_190": "Bro och tunnel/Konstruktion",
    "TattbebyggtOmrade": "Tättbebyggt område",
    "Viltpassage_i_plan": "Viltpassage i plan",
    "L_Viltuthopp": "Viltuthopp(V)",
    "R_Viltuthopp": "Viltuthopp(H)",
    "Evag_555": "Europaväg",
    "Huvnr_556_1": "Vägnummer/Huvudnummer",
    "Undnr_557": "Vägnummer/Undernummer",
    "Lan_558": "Länstillhörighet",
    "Under_397": "Vägnummer/Undernummer",
    "Typ_512": "Vägtyp",
    "Typ_369": "Vägtyp kod",
    "Typ_a_55_29": "Axeltyp",
    "ADT_l_122": "Trafik/ÅDT lätt lastbil",
    "ADT_l_123": "Trafik/ÅDT lätt lastbil+släp",
    "ADT_l_124": "Trafik/ÅDT tung lastbil",
    "ADT_m_125": "Trafik/ÅDT mellanlastbil",
    "ADT_m_126": "Trafik/ÅDT mellanlastbil+släp",
    "ADT_m_127": "Trafik/ÅDT tung lastbil+släp",
    "ADT_t_128": "Trafik/ÅDT totalt",
    "ADT_t_129": "Trafik/ÅDT totalt lätt",
    "ADT_t_130": "Trafik/ÅDT totalt tungt",
    "ROUTE_ID": "",
    "FROM_MEASURE": "MEASURE_FROM",
    "TO_MEASURE": "MEASURE_TO",
    "Shape_Length": "",
}


# Output message


def message(line: str) -> None:
    if quiet:
        return
    sys.stdout.write(line)
    sys.stdout.flush()


# Extension of dict class which returns an empty string if element does not exist


class Properties(dict):
    def __missing__(self, key: Any) -> Any:
        return None


# Convert tags


def osm_tags(segment: Dict[str, Any]) -> Dict[str, str]:
    prop = Properties(segment["properties"])

    tags = {}

    # 1. Tag nodes

    crossing = {
        # 1: {}	# planskild passage överfart  -->  Should create bridge on both neighbour segments
        # 2: {}	# planskild passage underfart
        3: {},  # övergångsställe och/eller cykelpassage/cykelöverfart i plan
        4: {
            "crossing": "traffic_signals"
        },  # signalreglerat övergångsställe och/eller signalreglerad cykelpassage/cykelöverfart i plan
        5: {},  # annan ordnad passage i plan
    }

    if prop["GCM-passage/Passagetyp"] in crossing:  # Foot/cycleway crossing highway
        tags["highway"] = "crossing"
        tags.update(crossing[prop["GCM-passage/Passagetyp"]])
        create_node(
            segment, tags, ["GCM-passage/Passagetyp", "GCM-passage/Trafikanttyp"]
        )

    railway_crossing = {
        1: {"crossing:barrier": "full"},  # Helbom
        2: {"crossing:barrier": "half"},  # Halvbom
        3: {"crossing:bell": "yes", "crossing:light": "yes"},  # Ljus och ljudsignal
        4: {"crossing:light": "yes"},  # Ljussignal
        5: {"crossing:bell": "yes"},  # Ljudsignal
        6: {"crossing:saltire": "yes"},  # Kryssmärke
        7: {"crossing": "uncontrolled"},  # Utan skydd
    }

    if prop["Järnvägskorsning/Vägskydd"] in railway_crossing:  # Railway crossing
        if prop["Vägtrafiknät/Nättyp"] == 1:
            tags["railway"] = "level_crossing"
        else:
            tags["railway"] = "crossing"
        tags.update(railway_crossing[prop["Järnvägskorsning/Vägskydd"]])
        create_node(segment, tags, ["Järnvägskorsning/Vägskydd", "Vägtrafiknät/Nättyp"])

    traffic_calming = {
        1: "choker",  # avsmalning till ett körfält
        2: "hump",  # gupp (cirkulärt gupp eller gupp med ramp utan gcm-passage)
        3: "chicane",  # sidoförskjutning - avsmalning
        4: "island",  # sidoförskjutning - refug
        5: "dip",  # väghåla
        6: "cushion",  # vägkudde
        7: "table",  # förhöjd genomgående gcm-passage
        8: "table",  # förhöjd korsning
        9: "yes",  # övrigt farthinder
    }

    if (
        prop["Farthinder/Typ"] in traffic_calming
    ):  # Speed humps and other traffic calming objects
        tags["traffic_calming"] = traffic_calming[prop["Farthinder/Typ"]]
        create_node(segment, tags, ["Farthinder/Typ"])

    barrier = {
        1: "bollard",  # pollare
        2: "swing_gate",  # eftergivlig grind
        3: "cycle_barrier",  # ej öppningsbar grind eller cykelfålla
        4: "lift_gate",  # låst grind eller bom
        5: "jersey_barrier",  # betonghinder    block?
        6: "bus_trap",  # spårviddshinder
        99: "yes",  # övrigt
    }

    if prop["Väghinder/Hindertyp"] in barrier:  # Barriers
        tags["barrier"] = barrier[prop["Väghinder/Hindertyp"]]
        if prop["Väghinder/Passerbar bredd"]:
            tags["maxwidth:physical"] = str(prop["Väghinder/Passerbar bredd"])
        create_node(segment, tags, ["Väghinder/Hindertyp", "Väghinder/Passerbar bredd"])

    if (
        prop["ATK-Mätplats(F)"] or prop["ATK-Mätplats(B)"]
    ):  # Speed camera (currently put on highway node)
        tags["highway"] = "speed_camera"

        if (
            prop["ATK-Mätplats(F)"]
            and prop["Hastighetsgräns/Högsta tillåtna hastighet(F)"]
        ):
            tags["maxspeed"] = str(prop["Hastighetsgräns/Högsta tillåtna hastighet(F)"])
        elif (
            prop["ATK-Mätplats(B)"]
            and prop["Hastighetsgräns/Högsta tillåtna hastighet(B)"]
        ):
            tags["maxspeed"] = str(prop["Hastighetsgräns/Högsta tillåtna hastighet(B)"])

        create_node(
            segment,
            tags,
            [
                "ATK-Mätplats(F)",
                "ATK-Mätplats(B)",
                "Hastighetsgräns/Högsta tillåtna hastighet(F)",
                "Hastighetsgräns/Högsta tillåtna hastighet(B)",
            ],
        )

    if prop["Rastplats"]:  # Rest area (currently put on highway node)
        tags["highway"] = "rest_area"
        tags["name"] = prop["Rastplats/Rastplatsnamn"].strip()

        if prop["Rastplats/Antal markerade parkeringsplatser för personbil"]:
            tags["capacity"] = str(
                prop["Rastplats/Antal markerade parkeringsplatser för personbil"]
            )
        if prop["Rastplats/Antal markerade parkeringsplatser för lastbil+släp"]:
            tags["capacity:hgv"] = str(
                prop["Rastplats/Antal markerade parkeringsplatser för lastbil+släp"]
            )

        create_node(
            segment,
            tags,
            [
                "Rastplats",
                "Rastplats/Rastplatsnamn",
                "Rastplats/Restaurang",
                "Rastplats/Antal markerade parkeringsplatser för personbil",
                "Rastplats/Antal markerade parkeringsplatser för lastbil+släp",
            ],
        )

    if (
        prop["Rastficka(V)"] or prop["Rastficka(H)"]
    ):  # Parking along highway (currently put on highway node)
        tags["amenity"] = "parking"
        create_node(segment, tags, ["Rastficka(V)", "Rastficka(H)"])

    tags = {}  # Reset tags for segments

    # 2. Tag ferries

    if prop["Färjeled"]:  # Ferry
        tags["route"] = "ferry"
        tags["foot"] = "yes"

        if prop["Vägtrafiknät/Nättyp"] == 1:
            tags["motor_vehicle"] = "yes"
        else:
            tags["motor_vehicle"] = "no"

        ferry = {
            1: "trunk",  # E road
            2: "trunk",  # National road
            3: "primary",  # Primary county road
            4: "secondary",  # Other county road
        }

        if prop["Vägkategori/Kategori"] in ferry:  # Road catagory
            tags["ferry"] = ferry[prop["Vägkategori/Kategori"]]

        if prop["Vägnummer/Huvudnummer"]:  # Road number
            if prop["Vägkategori/Kategori"] == 1:  # E road
                tags["ref"] = "E " + str(prop["Vägnummer/Huvudnummer"])
            else:
                tags["ref"] = str(prop["Vägnummer/Huvudnummer"])

        if prop["Färjeled/Färjeledsnamn"]:  # Ferry line name
            tags["name"] = prop["Färjeled/Färjeledsnamn"].strip()

        return tags

    # 3. Tag bridges and tunnels (common for vehicles and pedestrians)
    # If only a foot/cycleway is underneath a short bridge, then the foot/cycleway is tagged as tunnel and there is no bridge tag.
    # The bridges dict contains the results of initial analysis of bridges and tunnels.

    if prop["Bro och tunnel/Konstruktion"] in [1, 4] and (
        not prop["Bro och tunnel/Identitet"]
        or bridges[prop["Bro och tunnel/Identitet"]]["tag"] == "bridge"
        or prop["Shape_Length"] > bridge_margin
    ):
        tags["bridge"] = "yes"
        if prop["Bro och tunnel/Identitet"]:
            tags["layer"] = bridges[prop["Bro och tunnel/Identitet"]]["layer"]
        else:
            tags["layer"] = "1"

    elif (
        prop["Bro och tunnel/Konstruktion"] == 3
        or prop["Bro och tunnel/Konstruktion"] == 2
        and (
            prop["Bro och tunnel/Identitet"]
            and bridges[prop["Bro och tunnel/Identitet"]]["tag"] == "tunnel"
            or not prop["Bro och tunnel/Identitet"]
            and (
                prop["Vägtrafiknät/Nättyp"] != 1 or prop["Shape_Length"] > bridge_margin
            )
        )
    ):
        tags["tunnel"] = "yes"
        tags["layer"] = "-1"

    # Check oneway, used for other tags later

    if prop["Förbjuden färdriktning(B)"]:
        tags["oneway"] = "yes"
        oneway = "forward"
    elif prop["Förbjuden färdriktning(F)"]:
        tags["oneway"] = "yes"
        oneway = "backward"
        reverse_segment(segment, False)  # Reverse way nodes
        if debug:
            segment["properties"]["REVERSE"] = "yes"  # debug
    else:
        oneway = ""

    # 4. Tag cycleways/footways

    if prop["Vägtrafiknät/Nättyp"] in [2, 4]:  # 2: Cycleway, 4: footway
        cycleway = {
            1: {"highway": "cycleway"},  # cykelbana
            2: {"highway": "cycleway"},  # cykelfält
            3: {
                "highway": "cycleway"
            },  # 'cycleway': 'crossing', 'segregated': 'yes'},	# cykelöverfart i plan/cykelpassage
            4: {"highway": "footway"},  # 'footway': 'crossing'},	# övergångsställe
            5: {"highway": "cycleway"},  # gatupassage utan utmärkning
            8: {"highway": "cycleway"},  # koppling till annat
            9: {"highway": "cycleway"},  # annan cykelbar förbindelse
            10: {"highway": "footway"},  # annan ej cykelbar förbindelse
            11: {"highway": "footway"},  # gångbana
            12: {"highway": "footway", "footway": "sidewalk"},  # trottoar
            13: {"highway": "cycleway"},  # fortsättning i nätet
            14: {"highway": "footway", "covered": "yes"},  # passage genom byggnad
            15: {"highway": "cycleway"},  # ramp
            16: {"highway": "platform"},  # perrong
            17: {"highway": "steps"},  # trappa
            18: {"highway": "footway", "conveying": "yes"},  # rulltrappa
            19: {"highway": "footway", "conveying": "yes"},  # rullande trottoar
            20: {"highway": "elevator"},  # hiss
            21: {"highway": "elevator"},  # snedbanehiss
            22: {"aerialway": "cable_car"},  # linbana
            23: {"railway": "furnicular"},  # bergbana
            24: {"highway": "pedestrian"},  # torg
            25: {"highway": "footway"},  # kaj
            26: {"highway": "pedestrian"},  # öppen yta
            27: {"route": "ferry", "foot": "yes", "motor_vehicle": "no"},  # färja
            28: {
                "highway": "cycleway"
            },  # 'cycleway': 'crossing', 'segregated': 'yes'},	# cykelpassage och övergångsställe
            29: {"highway": "cycleway", "foot": "no"},  # cykelbana ej lämplig för gång
        }

        if (
            prop["GCM-separation/Separation(V)"]
            and prop["GCM-separation/Separation(V)"] == 1
            or prop["GCM-separation/Separation(H)"]
            and prop["GCM-separation/Separation(H)"] == 1
        ):  # Sidewalk
            tags["highway"] = "footway"
            tags["footway"] = "sidewalk"
        elif prop["GCM-vägtyp/GCM-typ"] in cycleway:
            tags.update(cycleway[prop["GCM-vägtyp/GCM-typ"]])
        else:
            tags["highway"] = "cycleway"

        # Swap cycleway to footway if footway network
        if (
            prop["Vägtrafiknät/Nättyp"] == 4
            and "highway" in tags
            and tags["highway"] == "cycleway"
        ):
            tags["highway"] = "footway"
            if "cycleway" in tags:
                tags["footway"] = tags["cycleway"]
                del tags["cycleway"]

        # Include street name only for pedestrian highway or if only used by cycleway/footway
        if prop["Gatunamn/Namn"] and (
            "highway" in tags
            and tags["highway"] == "pedestrian"
            or "stig" in prop["Gatunamn/Namn"].lower()
            or "gång" in prop["Gatunamn/Namn"].lower()
            or "park" in prop["Gatunamn/Namn"].lower()
            or prop["Gatunamn/Namn"].strip() not in street_names
        ):
            tags["name"] = prop["Gatunamn/Namn"].strip()

        if prop["GCM-belyst"] and "highway" in tags:  # Street light
            tags["lit"] = "yes"

        # Foot/cycleways only get name if marked as cycleway route
        if (
            prop["C-Cykelled/Namn"]
            and "highway" in tags
            and tags["highway"] == "cycleway"
        ):
            tags["cycleway:name"] = prop["C-Cykelled/Namn"].strip()  # Cycleway route

        if "bridge" in tags:
            if (
                prop["Övrigt vägnamn/Namn"] and "bron" in prop["Övrigt vägnamn/Namn"]
            ):  # Bridge name
                tags["bridge:name"] = prop["Övrigt vägnamn/Namn"].strip()
            if prop[
                "Bro och tunnel/Namn"
            ]:  # Description (may include bridge/tunnel name)
                tags["description"] = prop["Bro och tunnel/Namn"].strip()

        return tags

    # 5. Tag highways for motor vehicles
    # Follows official Swedish categories as used by Trafikverket and Lantmäteriet.
    # Sweden OSM has very strange category definitions for national and county roads which requires manual editing.

    if prop["Vägkategori/Kategori"] == 1:  # E road
        tags["highway"] = "trunk"

    elif prop["Vägkategori/Kategori"] == 2:  # National road
        tags["highway"] = "trunk"

    elif prop["Vägkategori/Kategori"] == 3:
        tags["highway"] = "primary"  # Primary county road

    elif prop["Vägkategori/Kategori"] == 4:
        tags["highway"] = "secondary"  # Other county road (alternative - use Lever_292)

    else:
        if prop["Gågata(V)"] or prop["Gågata(H)"]:
            tags["highway"] = "pedestrian"  # Pedestrian street

        elif prop["Gångfartsområde(V)"] or prop["Gångfartsområde(H)"]:  # Sign E9
            tags["highway"] = "living_street"

        elif (
            prop["Funktionell vägklass/Klass"]
            and prop["Funktionell vägklass/Klass"] < 6
        ):  # Functional road class
            tags["highway"] = "tertiary"

        # Private roads are tagged as residential/unclassified if they meet certain criteria (see below).
        # Otherwise tagged as service.

        elif prop["Väghållare/Väghållartyp"] == 3:  # Private road owner
            # if prop['Funktionell vägklass/Klass'] and prop['Funktionell vägklass/Klass'] < 9 or prop['Driftbidrag statligt/Vägnr']:
            if (
                prop["Funktionell vägklass/Klass"]
                and prop["Funktionell vägklass/Klass"] < 8
                or prop["Driftbidrag statligt/Vägnr"]
                or prop["Funktionell vägklass/Klass"] == 8
                and not prop["Tillgänglighet/Tillgänglighetsklass"]
            ):  # not in [3,4]:
                if prop["Tättbebyggt område"]:
                    tags["highway"] = "residential"  # Residential for urban areas
                else:
                    tags["highway"] = "unclassified"  # Unclassified for rural areas

            # elif prop['Tillgänglighet/Tillgänglighetsklass'] == 4:
            elif (
                prop["Tillgänglighet/Tillgänglighetsklass"]
                and not prop["Gatunamn/Namn"]
                and prop["Slitlager/Slitlagertyp"] != 1
            ):
                # and (prop['Funktionell vägklass/Klass'] == 9 or prop['Tillgänglighet/Tillgänglighetsklass'] in [3,4]):
                tags["highway"] = "track"
            else:
                tags["highway"] = "service"  # Service tag for functional road class 9
        else:
            tags["highway"] = (
                "residential"  # Municipality is owner, seems to exist mostly in urban areas
            )

    # Motorway/motorroad

    if prop["Motorväg"]:
        tags["highway"] = "motorway"

    elif prop["Motortrafikled"]:
        tags["motorroad"] = "yes"

    # Highway links are recognized indirectly by looking for the presence of FPV (functional priority road network) and
    # delivery class ("leveranskvalitetsklass") below 4. Roundabouts excluded.

    if (
        tags["highway"] in ["motorway", "trunk", "primary"]
        and prop["Funktionellt prioriterat vägnät/FPV-klass"] is None
        and prop["Leveranskvalitet DoU 2017/Leveranskvalitetsklass DoU 2017"]
        and prop["Leveranskvalitet DoU 2017/Leveranskvalitetsklass DoU 2017"] < 4
        and prop["Cirkulationsplats(F)"] is None
        and prop["Cirkulationsplats(B)"] is None
    ):
        tags["highway"] += "_link"

    # Highway ref

    county_refs = {
        1: "AB",  # Stockholms län
        3: "C",  # Uppsala län
        4: "D",  # Södermanlands län
        5: "E",  # Östergötlands län
        6: "F",  # Jönköpings län
        7: "G",  # Kronobergs län
        8: "H",  # Kalmar län
        9: "I",  # Gotlands län
        10: "K",  # Blekinge län
        11: "L",  # (f.d. Kristianstads län)
        12: "M",  # Skåne län (f.d. Malmöhus län)
        13: "N",  # Hallands län
        14: "O",  # Västra Götalands län (f.d. Götebors- och Bohus län)
        15: "P",  # (f.d. Älvsborgs län)
        16: "R",  # (f.d. Skaraborgs län)
        17: "S",  # Värmlands län
        18: "T",  # Örebro län
        19: "U",  # Västmanlands län
        20: "W",  # Dalarnas län (f.d. Kopparbergs län)
        21: "X",  # Gävleborgs län
        22: "Y",  # Västernorrlands län
        23: "Z",  # Jämtlands län
        24: "AC",  # Västerbottens län
        25: "BD",  # Norrbottens län
    }

    if prop["Vägkategori/Kategori"] == 1:  # E road
        tags["ref"] = "E " + str(prop["Vägnummer/Huvudnummer"])
    elif prop["Vägkategori/Kategori"] in [2, 3]:  # Trunk and primary
        tags["ref"] = str(prop["Vägnummer/Huvudnummer"])
    elif (
        prop["Vägkategori/Kategori"] == 4
        and prop["Kommunnr"]
        and prop["Vägnummer/Huvudnummer"]
    ):  # Secondary
        tags["ref"] = (
            county_refs[int(prop["Kommunnr"]) // 100]
            + " "
            + str(prop["Vägnummer/Huvudnummer"])
        )  # Include county letter

    # Backward/forward tags

    tag_direction(
        tags,
        "junction",
        "roundabout",
        prop["Cirkulationsplats(F)"],
        prop["Cirkulationsplats(B)"],
        oneway,
    )  # Roundabout

    if not (
        tags["highway"] == "track"
        and prop["Hastighetsgräns/Högsta tillåtna hastighet(F)"] == 70
        and prop["Hastighetsgräns/Högsta tillåtna hastighet(B)"] == 70
    ):
        tag_direction(
            tags,
            "maxspeed",
            None,
            prop["Hastighetsgräns/Högsta tillåtna hastighet(F)"],
            prop["Hastighetsgräns/Högsta tillåtna hastighet(B)"],
            oneway,
        )  # Maxspeed (exclude on service roads?, not signed?)

    tag_direction(
        tags,
        "motor_vehicle",
        "no",
        prop["Förbud mot trafik(F)"],
        prop["Förbud mot trafik(B)"],
        oneway,
    )  # Access restriction

    # Vehicle type restrictions from "Förbud mot trafik"
    # Maps NVDB vehicle type codes to OSM access tags
    vehicle_type_map = {
        10: "motorcar",  # bil
        20: "bus",  # buss
        30: "bicycle",  # cykel
        40: "vehicle",  # fordon (all vehicles)
        90: "hgv",  # lastbil (heavy goods vehicle)
        100: "goods",  # lätt lastbil (light truck)
        120: "moped",  # moped
        130: "moped",  # moped klass I
        140: "moped",  # moped klass II
        150: "motorcycle",  # motorcykel
        170: "motor_vehicle",  # motordrivna fordon
        180: "motor_vehicle",  # motorredskap
        210: "motorcar",  # personbil (passenger car)
        230: "atv",  # terrängmotorfordon
        270: "tractor",  # traktor
        280: "hgv",  # tung lastbil (heavy truck)
    }

    # Apply vehicle type restrictions
    for direction, suffix in [("F", "(F)"), ("B", "(B)")]:
        vehicle_type = prop[f"Förbud mot trafik/Gäller fordon{suffix}"]
        if vehicle_type and vehicle_type in vehicle_type_map:
            osm_tag = vehicle_type_map[vehicle_type]
            weight_limit = prop[f"Förbud mot trafik/Totalvikt{suffix}"]

            if weight_limit:
                # If weight limit is specified, use maxweight or conditional tag
                if osm_tag == "hgv":
                    tags[f"maxweight{suffix.replace('(', ':').replace(')', '')}"] = str(
                        weight_limit
                    )
                else:
                    # For other vehicle types with weight, use conditional restriction
                    tag_key = f"{osm_tag}:conditional"
                    tag_value = f"no @ (weight>{weight_limit})"
                    if direction == "F":
                        if oneway != "backward":
                            if oneway == "forward":
                                tags[tag_key] = tag_value
                            else:
                                tags[f"{osm_tag}:forward:conditional"] = tag_value
                    else:  # direction == "B"
                        if oneway != "forward":
                            if oneway == "backward":
                                tags[tag_key] = tag_value
                            else:
                                tags[f"{osm_tag}:backward:conditional"] = tag_value
            else:
                # No weight limit - simple vehicle restriction
                if direction == "F":
                    if oneway != "backward":
                        if oneway == "forward":
                            tags[osm_tag] = "no"
                        else:
                            tags[f"{osm_tag}:forward"] = "no"
                else:  # direction == "B"
                    if oneway != "forward":
                        if oneway == "backward":
                            tags[osm_tag] = "no"
                        else:
                            tags[f"{osm_tag}:backward"] = "no"

    # Hazmat transport restrictions
    if prop["Rekommenderad väg för farligt gods/Rekommendation"]:
        tags["hazmat"] = "designated"

    hazmat_f = prop["Inskränkningar för transport av farligt gods/Beskrivning(F)"]
    hazmat_b = prop["Inskränkningar för transport av farligt gods/Beskrivning(B)"]
    if hazmat_f or hazmat_b:
        tag_direction(
            tags,
            "hazmat",
            "no",
            1 if hazmat_f else None,
            1 if hazmat_b else None,
            oneway,
        )

    tag_direction(
        tags,
        "overtaking",
        "no",
        prop["Omkörningsförbud(F)"],
        prop["Omkörningsförbud(B)"],
        oneway,
    )  # Overtaking

    # Lanes

    if prop["Antal körfält/Körfältsantal"] and (
        prop["Antal körfält/Körfältsantal"] > 2
        or oneway
        and prop["Antal körfält/Körfältsantal"] > 1
    ):
        tags["lanes"] = str(prop["Antal körfält/Körfältsantal"])  # Lanes

    tag_direction(
        tags,
        "psv",
        "yes",
        prop["Kollektivkörfält/Körfält-Körbana(F)"] == 2,
        prop["Kollektivkörfält/Körfält-Körbana(B)"] == 2,
        oneway,
    )  # PSV lanes

    tag_direction(
        tags,
        "motor_vehicle",
        "no",
        prop["Kollektivkörfält/Körfält-Körbana(F)"] == 2,
        prop["Kollektivkörfält/Körfält-Körbana(B)"] == 2,
        oneway,
    )  # PSV lanes

    tag_direction(
        tags,
        "lanes:psv",
        "1",
        prop["Kollektivkörfält/Körfält-Körbana(F)"] == 1,
        prop["Kollektivkörfält/Körfält-Körbana(B)"] == 1,
        oneway,
    )  # PSV lanes

    # Other highway tags

    if prop["Slitlager/Slitlagertyp"] == 1:  # Surface
        tags["surface"] = "paved"
    elif prop["Slitlager/Slitlagertyp"] == 2:
        tags["surface"] = "unpaved"

    if prop["Vägbredd/Bredd"]:  # Road width
        tags["width"] = str(prop["Vägbredd/Bredd"])

    if prop["Vägnummer/Huvudnummer"]:  # Priority road
        tags["priority_road"] = "designated"

    if prop["C-Rekommenderad bilväg for cykel"]:  # Highway recommended for bikes
        tags["bicycle"] = "designated"

    if prop["Miljözon"]:  # Environmental zone (LEZ)
        if prop["Miljözon"] == 1:
            tags["low_emission_zone"] = "yes"
        else:
            tags["low_emission_zone"] = str(prop["Miljözon"])

    # Names

    if (
        not prop["Cirkulationsplats(F)"] and not prop["Cirkulationsplats(B)"]
    ):  # Street name
        if prop["Gatunamn/Namn"]:
            tags["name"] = prop["Gatunamn/Namn"].strip()
        elif prop["Övrigt vägnamn/Namn"]:
            tags["name"] = prop["Övrigt vägnamn/Namn"].strip()

    if prop["Övrigt vägnamn/Namn"]:  # Bridge/tunnel name
        if "tunnel" in tags and "tunneln" in prop["Övrigt vägnamn/Namn"]:
            tags["tunnel:name"] = prop["Övrigt vägnamn/Namn"].strip()
        elif "bridge" in tags and "bron" in prop["Övrigt vägnamn/Namn"]:
            tags["bridge:name"] = prop["Övrigt vägnamn/Namn"].strip()

    if prop["Bro och tunnel/Namn"] and (
        "bridge" in tags or "tunnel" in tags
    ):  # Description (may include bridge/tunnel name)
        tags["description"] = prop["Bro och tunnel/Namn"].strip()

    # Restrictions

    # HGV restrictions for forest roads (class 4 = not accessible for heavy vehicle combinations)
    if prop["Framkomlighet för vissa fordonskombinationer/Framkomlighetsklass"] == 4:
        tags["hgv"] = "no"

    if prop["Höjdhinder upp till 4,5 m/Fri höjd"]:
        tags["maxheight"] = str(
            prop["Höjdhinder upp till 4,5 m/Fri höjd"]
        )  # Maxh height

    if prop["Begränsad fordonslängd/Högsta tillåtna fordonslängd"]:
        tags["maxlength"] = str(
            prop["Begränsad fordonslängd/Högsta tillåtna fordonslängd"]
        )  # Max length

    if prop["Begränsad fordonsbredd/Högsta tillåtna fordonsbredd"]:
        tags["maxwidth"] = str(
            prop["Begränsad fordonsbredd/Högsta tillåtna fordonsbredd"]
        )  # Max width

    if prop["Begränsat axel-boggitryck/Högsta tillåtna tryck"]:
        tags["maxaxleload"] = str(
            prop["Begränsat axel-boggitryck/Högsta tillåtna tryck"]
        )  # Max legal load weight per axle

    # Sign-based directional gross weight limit
    tag_direction(
        tags,
        "maxweight",
        None,
        prop["Begränsad bruttovikt/Högsta tillåtna bruttovikt(F)"],
        prop["Begränsad bruttovikt/Högsta tillåtna bruttovikt(B)"],
        oneway,
    )

    maxweight = {
        1: "64.0",  # BK1
        2: "51.4",  # Bk2
        3: "37.5",  # BK3
        4: "74.0",  # BK4
        5: "74.0",  # BK4 särskilda vilkor
    }

    if prop["Bärighet/Bärighetsklass"] and "bridge" in tags:
        if "maxweight" not in tags:
            tags["maxweight"] = maxweight[
                prop["Bärighet/Bärighetsklass"]
            ]  # Max total weight (fallback for bridges without sign-based limit)

    return tags


# Add tagged node to list of nodes
# Use coordinate from short way segment


def create_node(way, tags, nvdb_properties):
    node = {
        "type": "feature",
        "properties": {},
        "tags": tags.copy(),  # Shallow copy is safe for dict of strings
        "geometry": {
            "type": "Point",
            "coordinates": list(way["geometry"]["coordinates"][0][0]),  # Copy coordinate pair
        },
    }

    for prop in nvdb_properties:
        if prop in way["properties"]:
            value = way["properties"][prop]
            # Primitives do not need deepcopy.
            if isinstance(value, (str, int, float, bool, type(None))):
                node["properties"][prop] = value
            else:
                node["properties"][prop] = copy.deepcopy(value)

    nodes.append(node)


# Tag way with different forward and backward direction
# Adjust for possible oneway direction
# Paramters:
# - tags: will be update
# - tag: tag key to be used
# - value: if set, this is the tag value to be used
# - prop_forward/backward: if 1, use tag value paramter
# - oneway: direction of onway road (forward, backward), if any


def tag_direction(
    tags: Dict[str, str],
    tag: str,
    value: Optional[str],
    prop_forward: Any,
    prop_backward: Any,
    oneway: str,
) -> None:
    if prop_forward or prop_backward:
        if value and prop_forward == 1:
            prop_forward = value
        if value and prop_backward == 1:
            prop_backward = value

        if prop_forward == prop_backward:
            tags[tag] = str(
                prop_forward
            )  # Same tag for both directions, so no forwrd/backward suffix needed
        else:
            if prop_forward and oneway != "backward":
                if oneway == "forward":
                    tags[tag] = str(
                        prop_forward
                    )  # Forward suffix not needed on oneway street
                else:
                    tags[tag + ":forward"] = str(prop_forward)
            if prop_backward and oneway != "forward":
                if oneway == "backward":
                    tags[tag] = str(
                        prop_backward
                    )  # Backward suffix not needed on oneway street
                else:
                    tags[tag + ":backward"] = str(prop_backward)


# Tag segments and nodes in road network


def tag_network() -> None:
    message("Converting tags ... ")

    global bridges, street_names

    for segment in segments["features"]:
        segment["tags"] = {}

    # First build bridge/tunnel dict for the named structures

    bridges = {}
    bridge_segments = []

    for segment in segments["features"]:
        prop = segment["properties"]

        if (
            "Bro och tunnel/Identitet" in prop and "Bro och tunnel/Konstruktion" in prop
        ):  # Unique id of structure
            bridge_id = prop["Bro och tunnel/Identitet"]

            if bridge_id not in bridges:
                bridges[bridge_id] = {
                    "car": 0,  # Will contain number of car highways underneath bridge
                    "cycle": 0,  # Will contain number of foot/cycleways underneath bridge
                    "length": 0,  # Length of bridge
                    "layer": "1",  # Which layer to use
                }

            if prop["Bro och tunnel/Konstruktion"] in [
                2,
                3,
                4,
            ]:  # Current segment is under bridge
                if (
                    prop["Vägtrafiknät/Nättyp"] == 1
                    and prop["Bro och tunnel/Konstruktion"] != 3
                ):
                    bridges[bridge_id]["car"] += 1  # Highway is for cars
                else:
                    bridges[bridge_id]["cycle"] += 1  # Foot/cycleways

            if (
                prop["Bro och tunnel/Konstruktion"] == 1
            ):  # Current segment is over bridge
                bridges[bridge_id]["length"] = max(
                    bridges[bridge_id]["length"], prop["Shape_Length"]
                )
            elif prop["Bro och tunnel/Konstruktion"] == 4:  # Middel layer bridge
                bridges[bridge_id]["layer"] = "2"

        if (
            "Bro och tunnel/Konstruktion" in prop
        ):  # Build list of bridge segments for next iteration
            bridge_segments.append(segment)

    # Discover missing bridge segments (without any bridge id) for the named structures and update

    # Loop all identified bridge segments (over and under)
    for segment1 in bridge_segments:
        prop1 = segment1["properties"]
        if "Bro och tunnel/Identitet" not in prop1 and prop1[
            "Bro och tunnel/Konstruktion"
        ] in [2, 3, 4]:  # Under bridge, segment without structure
            # Then try to find intersecting highways over, i.e. a bridge
            for segment2 in bridge_segments:
                prop2 = segment2["properties"]
                if debug:
                    segment1["tags"]["intersects"] = str(
                        prop1["Bro och tunnel/Konstruktion"]
                    )
                    segment2["tags"]["intersects"] = str(
                        prop2["Bro och tunnel/Konstruktion"]
                    )

                if (
                    prop2["Bro och tunnel/Konstruktion"] == 1
                    and segment1 != segment2
                    and intersects(segment1, segment2)
                ):  # Intersecting bridge found
                    if (
                        "Bro och tunnel/Identitet" in prop2
                    ):  # Over bridge, segment with structure
                        if (
                            prop1["Vägtrafiknät/Nättyp"] == 1
                            and prop1["Bro och tunnel/Konstruktion"] != 3
                        ):
                            bridges[prop2["Bro och tunnel/Identitet"]]["car"] += 1
                        else:
                            bridges[prop2["Bro och tunnel/Identitet"]]["cycle"] += 1
                    elif debug:
                        segment1["tags"]["intersection"] = "yes"

    # Tag according to highways over/under structure

    for bridge_id, bridge in bridges.items():
        if bridge["car"] > 0 or bridge["length"] > bridge_margin:
            bridges[bridge_id]["tag"] = (
                "bridge"  # Always tag bridge if highway underneath is for cars
            )
        elif bridge["cycle"] > 0:
            bridges[bridge_id]["tag"] = (
                "tunnel"  # Tag tunnel underneath instead of bridge on top if only foot/cycleway underneath
            )
        else:
            bridges[bridge_id]["tag"] = "bridge"  # Catch all

    message("\n\t%i bridge/tunnel structures\n" % len(bridges))

    # Build set of street names. Used for cycleways later.
    # Also get urban/rural statistics.

    street_names = set()
    urban_streets = 0
    rural_streets = 0

    for segment in segments["features"]:
        if (
            "Vägtrafiknät/Nättyp" in segment["properties"]
            and segment["properties"]["Vägtrafiknät/Nättyp"] == 1
        ):
            if (
                "Gatunamn/Namn" in segment["properties"]
                and segment["properties"]["Gatunamn/Namn"].strip()
            ):
                street_names.add(segment["properties"]["Gatunamn/Namn"].strip())

            if "Tättbebyggt område" in segment["properties"]:
                urban_streets += 1
            else:
                rural_streets += 1

    message("\t%i street names\n" % len(street_names))
    message(
        "\t%i %% urban vs rural streets\n"
        % (100 * urban_streets / (rural_streets + urban_streets))
    )

    # Loop all features and tag

    for segment in segments["features"]:
        segment["tags"].update(osm_tags(segment))

    message("\t%i tagged nodes\n" % len(nodes))


# Identify intersecting segments
# Assumes line segments are stored in the format [(x0,y0),(x1,y1)]


def intersects(s0, s1):
    dx0 = s0["end_node"][0] - s0["start_node"][0]
    dx1 = s1["end_node"][0] - s1["start_node"][0]
    dy0 = s0["end_node"][1] - s0["start_node"][1]
    dy1 = s1["end_node"][1] - s1["start_node"][1]

    p0 = dy1 * (s1["end_node"][0] - s0["start_node"][0]) - dx1 * (
        s1["end_node"][1] - s0["start_node"][1]
    )
    p1 = dy1 * (s1["end_node"][0] - s0["end_node"][0]) - dx1 * (
        s1["end_node"][1] - s0["end_node"][1]
    )
    p2 = dy0 * (s0["end_node"][0] - s1["start_node"][0]) - dx0 * (
        s0["end_node"][1] - s1["start_node"][1]
    )
    p3 = dy0 * (s0["end_node"][0] - s1["end_node"][0]) - dx0 * (
        s0["end_node"][1] - s1["end_node"][1]
    )

    return (p0 * p1 <= 0) and (p2 * p3 <= 0)


# Return bearing in degrees of line between two points (longitude, latitude)


def compute_bearing(point1: List[float], point2: List[float]) -> float:
    lon1, lat1, lon2, lat2 = map(
        math.radians, [point1[0], point1[1], point2[0], point2[1]]
    )
    dLon = lon2 - lon1
    y = math.sin(dLon) * math.cos(lat2)
    x = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(
        dLon
    )
    angle = (math.degrees(math.atan2(y, x)) + 360) % 360
    return angle


# Compute change in bearing at intersection between two segments
# Used to determine if way should be split at intersection


def compute_junction_angle(segment1: Dict[str, Any], segment2: Dict[str, Any]) -> float:
    line1 = segment1["geometry"]["coordinates"][0]
    line2 = segment2["geometry"]["coordinates"][0]

    if segment1["end_node"] == segment2["start_node"]:
        angle1 = compute_bearing(line1[-2], line1[-1])
        angle2 = compute_bearing(line2[0], line2[1])
    elif segment1["start_node"] == segment2["end_node"]:
        angle1 = compute_bearing(line1[1], line1[0])
        angle2 = compute_bearing(line2[-1], line2[-2])
    elif segment1["start_node"] == segment2["start_node"]:
        angle1 = compute_bearing(line1[1], line1[0])
        angle2 = compute_bearing(line2[0], line2[1])
    else:  # elif segment1['end_node'] == segment2['end_node']:
        angle1 = compute_bearing(line1[-2], line1[-1])
        angle2 = compute_bearing(line2[-1], line2[-2])

    delta_angle = (angle2 - angle1 + 360) % 360

    if delta_angle > 180:
        delta_angle = delta_angle - 360

    return delta_angle


# Compute closest distance from point p3 to line segment [s1, s2].
# Works for short distances.


def line_distance(s1: List[float], s2: List[float], p3: List[float]) -> float:
    x1, y1, x2, y2, x3, y3 = map(
        math.radians, [s1[0], s1[1], s2[0], s2[1], p3[0], p3[1]]
    )

    # Simplified reprojection of latitude
    x1 = x1 * math.cos(y1)
    x2 = x2 * math.cos(y2)
    x3 = x3 * math.cos(y3)

    A = x3 - x1
    B = y3 - y1
    dx = x2 - x1
    dy = y2 - y1

    dot = (x3 - x1) * dx + (y3 - y1) * dy
    len_sq = dx * dx + dy * dy

    if len_sq != 0:  # in case of zero length line
        param = dot / len_sq
    else:
        param = -1

    if param < 0:
        x4 = x1
        y4 = y1
    elif param > 1:
        x4 = x2
        y4 = y2
    else:
        x4 = x1 + param * dx
        y4 = y1 + param * dy

    # Also compute distance from p to segment

    x = x4 - x3
    y = y4 - y3
    distance = 6371000 * math.sqrt(x * x + y * y)  # In meters

    """
	# Project back to longitude/latitude

	x4 = x4 / math.cos(y4)

	lon = math.degrees(x4)
	lat = math.degrees(y4)

	return (lon, lat, distance)
	"""

    return distance


# Simplify polygon, i.e. reduce nodes within epsilon distance.
# Ramer-Douglas-Peucker method: https://en.wikipedia.org/wiki/Ramer–Douglas–Peucker_algorithm


def simplify_polygon(polygon: List[List[float]], epsilon: float) -> List[List[float]]:
    dmax = 0.0
    index = 0
    for i in range(1, len(polygon) - 1):
        d = line_distance(polygon[0], polygon[-1], polygon[i])
        if d > dmax:
            index = i
            dmax = d

    if dmax >= epsilon:
        new_polygon = simplify_polygon(polygon[: index + 1], epsilon)[
            :-1
        ] + simplify_polygon(polygon[index:], epsilon)
    else:
        new_polygon = [polygon[0], polygon[-1]]

    return new_polygon


# Travel recursively in highway network to identify connected service highways which are not connected to anythin but tracks.
# Then retag to highway=track.
# Current limitation: If a group of service roads are not connected to anything at all, it will be retagged to track.
# Paramters:
# - segment: To check.
# - tested_segments: Already tested segments, do not traverse.
# - tested_junctions: Already tested junctions do not traverse.
# - remaining_segments: Select test segments from this list (only service roads).
# Returns True if no connected service roads are connected to anything else than tracks.
# - Also updates tested_segments and tested_junctions


def connected_track(
    segment: Dict[str, Any],
    tested_segments: set,  # Changed to set of ids
    tested_junctions: set,
    remaining_lookup: Dict[int, Dict[str, Any]],  # Changed to id(seg) lookup dict
) -> bool:
    # Tested segments are accumulating as we traverse
    tested_segments.add(id(segment))

    track = True

    # Test segments connected to both start and end nodes of segment.
    for node in [segment["start_node"], segment["end_node"]]:
        if node not in tested_junctions:
            tested_junctions.add(node)

            # Iterate connected ways at junction. Check segments starting from next junction node.
            for test_segment in junctions[node]["segments"]:
                if "highway" in test_segment["tags"] and test_segment["tags"][
                    "highway"
                ] not in ["service", "track"]:
                    track = False

                # New segment must not already have been used and must be available
                ts_id = id(test_segment)
                if ts_id not in tested_segments and ts_id in remaining_lookup:
                    if not connected_track(
                        test_segment,
                        tested_segments,
                        tested_junctions,
                        remaining_lookup,
                    ):
                        track = False

    return track


# Tests all connected groups of service roads to check if they could be retagged to track.
# Retag to track only if group of service roads are not connected to anything else but track.
# This function may be called after junctions have been created.


def tag_isolated_tracks():
    # Build lookup of service ways; candidates for track
    # Use id(seg) as key to avoid O(n) list operations while preserving order in iterative extraction
    remaining_lookup = {}
    for segment in segments["features"]:
        if "highway" in segment["tags"] and segment["tags"]["highway"] == "service":
            remaining_lookup[id(segment)] = segment

    count = 0

    # Repeat checking groups of connected service roads until all segments have been tested
    while remaining_lookup:
        # Get the first available segment (deterministic selection)
        segment_id = next(iter(remaining_lookup))
        segment = remaining_lookup[segment_id]
        
        tested_segments = set()  # Store ids of segments in this connected group
        tested_junctions = set()

        # Check if service roads are isolated
        if connected_track(
            segment, tested_segments, tested_junctions, remaining_lookup
        ):
            # Change highway=service to track
            for seg_id in tested_segments:
                seg = remaining_lookup[seg_id]
                if seg["tags"]["highway"] == "service":
                    seg["tags"]["highway"] = "track"
                    seg["properties"]["TRACK"] = "yes"
                    count += 1

        # Remove processed segments from candidate pool
        for seg_id in tested_segments:
            remaining_lookup.pop(seg_id, None)

    message("\r\t%i isolated service roads retagged to track\n" % count)


# Travel recursively in highway network to identify longest connected segments with identical tags.
# Will build long ways, however with no logical grouping beyond the highway tags.
# Paramters:
# - segment: To be tested for inclusion
# - node: Next node for traversion
# - test_way: Connected segments so far, including segment (should be avoided)
# - test_junctions: Junctions traversed so far, including node (should be avoided)
# - remaining_segments: Segments available for testing, excluding segments in test_way
# Returns longest connected way:
# - Legnth of that way
# - List of included segments, in sequence
# - List of junctions passed


def connected_way(segment, node, test_way, test_junctions, remaining_segments):
    if node == segment["start_node"]:
        next_node = segment["end_node"]
    else:
        next_node = segment["start_node"]

    if (
        segment["start_node"] == segment["end_node"] or next_node in test_junctions
    ):  # Loop
        return (segment["properties"]["Shape_Length"], [segment], [])

    # Iterate connected ways at junction

    best_length = 0
    best_sequence = []
    best_junctions = []

    # Check segments starting from next junction node
    for test_segment in junctions[next_node]["segments"]:
        # New segment must not already have been used, must be available, must have the same tags, and oneways must have the same direction
        if (
            test_segment not in test_way
            and test_segment in remaining_segments
            and test_segment["tags"] == segment["tags"]
            and not (
                "oneway" in segment
                and "oneway" in test_segment
                and segment["end_node"] != test_segment["start_node"]
                and segment["start_node"] != test_segment["end_node"]
            )
        ):
            angle = compute_junction_angle(segment, test_segment)

            if abs(angle) < angle_margin:  # Avoid sharp angels
                length, sequence, used_junctions = connected_way(
                    test_segment,
                    next_node,
                    test_way + [test_segment],
                    test_junctions + [next_node],
                    remaining_segments,
                )
                if length > best_length:  # Keep best segment
                    best_length = length
                    best_sequence = sequence
                    best_junctions = used_junctions

    total_length = segment["properties"]["Shape_Length"] + best_length
    total_sequence = [segment] + best_sequence
    total_junctions = test_junctions + [next_node]

    return (total_length, total_sequence, total_junctions)


# Reverse direction of segment
# Swap direction tags (forward/backward) if selected and if present


def reverse_segment(segment, swap_tags):
    segment["start_node"], segment["end_node"] = (
        segment["end_node"],
        segment["start_node"],
    )
    segment["geometry"]["coordinates"][0].reverse()

    if swap_tags:
        new_tags = {}
        for tag in segment["tags"]:
            if ":forward" in tag:
                new_tags[tag.replace(":forward", ":backward")] = segment["tags"][tag]
            elif ":backward" in tag:
                new_tags[tag.replace(":backward", ":forward")] = segment["tags"][tag]
            else:
                new_tags[tag] = segment["tags"][tag]

        segment["tags"] = new_tags


# Sinmplify highway network, i.e. create sequences of longer ways, using recursive method.
# The road network is traversed, testing all available branches to find the longest way with identical tags.
# Groups contain list of segments to be handled separately, i.e. not mixed in a connected way.
# Acceptable performance (depending on grouping).
# Parameter:
# - groups: Predefined list of segments to be handled separately, i.e. not mixed in a way.


def simplify_network_recursive(groups):
    count = len(segments["features"])

    for group in groups.values():
        remaining_segments = group

        # Reapeat building sequences of longer ways until all segments have been used
        while remaining_segments:
            segment = remaining_segments[0]

            # First build sequence forward
            length_forward, sequence_forward, used_junctions = connected_way(
                segment, segment["start_node"], [segment], [], remaining_segments
            )

            # Then try to building connecgted sequence backward
            length_backward, sequence_backward, used_junctions = connected_way(
                segment,
                segment["end_node"],
                sequence_forward,
                used_junctions,
                remaining_segments,
            )

            # Add the two
            sequence_backward.reverse()
            sequence = sequence_backward + sequence_forward[1:]

            # Add to collection of (longer) ways. May be only one segment if no match found
            ways.append(sequence)
            for segment in sequence:
                remaining_segments.remove(segment)

            message("\r\t%i " % count)
            count -= len(sequence)

    # Check if any segments in a sequence needs to be reversed to get all segments in sequence in the same direction

    for way in ways:
        if len(way) > 1:
            last_segment = None
            for segment in way:
                if last_segment:
                    if (
                        last_segment["end_node"] == segment["end_node"]
                        or last_segment["start_node"] == segment["start_node"]
                    ):
                        reverse_segment(segment, True)
                last_segment = segment

            if way[0]["end_node"] != way[1]["start_node"]:
                way.reverse()


# Alternative algorithm for identifying connected segments, from Norwegian nvdb2osm.
# Linear approach in which the next available segment is added as long as it has is connected and has identical tags.
# Very quick method.
# Parameter:
# - groups: Predefined list of segments to be handled separately, i.e. not to be mixed in a way.


def simplify_network_linear(groups):
    # Build connected ways within each group

    count = len(groups)

    for group_id, group_segments in iter(groups.items()):
        message("\r\t%i " % count)
        count -= 1

        # Use dict instead of deepcopy list to preserve order and allow O(1) removal
        remaining_segments = {id(seg): seg for seg in group_segments}

        # Build O(1) lookup dicts for this group
        by_start = {}  # start_node -> list of segment ids
        by_end = {}    # end_node -> list of segment ids
        for seg_id, seg in remaining_segments.items():
            by_start.setdefault(seg["start_node"], []).append(seg_id)
            by_end.setdefault(seg["end_node"], []).append(seg_id)

        # Repeat building sequences of longer ways until all segments have been used
        while remaining_segments:
            # Get first available segment (deterministic)
            segment_id = next(iter(remaining_segments))
            segment = remaining_segments.pop(segment_id)
            # Remove from lookup dicts
            by_start[segment["start_node"]].remove(segment_id)
            by_end[segment["end_node"]].remove(segment_id)

            way = [segment]

            first_node = segment["start_node"]
            last_node = segment["end_node"]

            # Build way forward — O(1) lookup
            found = True
            while found:
                found = False
                for seg_id in list(by_start.get(last_node, [])):
                    seg = remaining_segments.get(seg_id)
                    if seg is None:
                        continue
                    angle = compute_junction_angle(way[-1], seg)
                    if abs(angle) < angle_margin:
                        last_node = seg["end_node"]
                        way.append(seg)
                        remaining_segments.pop(seg_id)
                        by_start[seg["start_node"]].remove(seg_id)
                        by_end[seg["end_node"]].remove(seg_id)
                        found = True
                        break

            # Build way backward — O(1) lookup
            found = True
            while found:
                found = False
                for seg_id in list(by_end.get(first_node, [])):
                    seg = remaining_segments.get(seg_id)
                    if seg is None:
                        continue
                    angle = compute_junction_angle(seg, way[0])
                    if abs(angle) < angle_margin:
                        first_node = seg["start_node"]
                        way.insert(0, seg)
                        remaining_segments.pop(seg_id)
                        by_start[seg["start_node"]].remove(seg_id)
                        by_end[seg["end_node"]].remove(seg_id)
                        found = True
                        break

            # Create new ways, each with identical segment tags

            new_way = []
            way_tags = {}

            if not way_tags:
                way_tags = way[0]["tags"]

            for segment in way:
                if segment["tags"] == way_tags:
                    new_way.append(segment)
                else:
                    ways.append(new_way)
                    new_way = [segment]
                    way_tags = segment["tags"]

            ways.append(new_way)


# Prepare for output
# Paramter option:
# - route: "Roud id" provided from NVDB (sequence of segments, but often quite short).
# - refname: Hash/grouping based on highway ref, street name and highway category. Linear method which adds next connected segment.
# - recursive: Same hash/grouping as refname, but recursively traverses road network to find longest way.


def simplify_network(option):
    message("Simplify network ...\n")

    # Simplify segment polygons, i.e. remove redundant nodes

    if simplify_factor != 0:
        for segment in segments["features"]:
            segment["geometry"]["coordinates"][0] = simplify_polygon(
                segment["geometry"]["coordinates"][0], simplify_factor
            )

    # Build network junction structure.
    # They are the only nodes wich are shared between ways, and the only nodes with tagging.

    for segment in segments["features"]:
        if segment["start_node"] not in junctions:
            junctions[segment["start_node"]] = {
                "tags": {},
                "properties": {},
                "segments": [segment],  # Pointer
            }
        else:
            junctions[segment["start_node"]]["segments"].append(segment)

        if segment["end_node"] not in junctions:
            junctions[segment["end_node"]] = {
                "tags": {},
                "properties": {},
                "segments": [segment],  # Pointer
            }
        else:
            junctions[segment["end_node"]]["segments"].append(segment)

    tag_isolated_tracks()

    # Copy tags and properties from nodes to junctions

    for node in nodes:
        coordinate = (
            node["geometry"]["coordinates"][0],
            node["geometry"]["coordinates"][1],
        )  # tuple
        if coordinate in junctions:
            junctions[coordinate]["tags"].update(node["tags"])
            junctions[coordinate]["properties"].update(node["properties"])

    # Build groups of segments for output

    groups = {}
    for segment in segments["features"]:
        group_id = ""

        if option == "route":  #
            if "ROUTE_ID" in segment["properties"]:
                group_id = segment["properties"]["ROUTE_ID"]
                segment["tags"]["ROUTE"] = group_id

        elif option in ["refname", "recursive"]:
            if "ref" in segment["tags"]:
                group_id += segment["tags"]["ref"]
            if (
                "Driftbidrag statligt/Vägnr" in segment["properties"]
            ):  # Road number for countryside
                group_id += str(segment["properties"]["Driftbidrag statligt/Vägnr"])
            if "name" in segment["tags"]:
                group_id += segment["tags"]["name"]
            if "highway" in segment["tags"]:
                group_id += segment["tags"]["highway"]

        if group_id not in groups:
            groups[group_id] = [segment]  # Pointer
        else:
            groups[group_id].append(segment)  # Pointer

    # Use selected method

    if option == "recursive":
        simplify_network_recursive(groups)
    elif option in ["route", "refname"]:
        simplify_network_linear(groups)
    else:  # Segment only output, no longer ways
        for segment in segments["features"]:
            ways.append([segment])

    message("\r\tSimplified into %i ways\n" % len(ways))


# Generate one osm tag for output


def tag_property(osm_element: ET.Element, tag_key: str, tag_value: str) -> None:
    tag_value = tag_value.strip()
    if tag_value:
        osm_element.append(ET.Element("tag", k=tag_key, v=tag_value))


# Output road network or objects to OSM file


def output_network(filename: str, output_filename: Optional[str] = None,
                   start_node_id: int = 1, start_way_id: int = 1) -> Tuple[int, int]:
    message("Saving file... ")

    node_id = start_node_id
    way_id = start_way_id
    count = 0

    osm_root = ET.Element(
        "osm", version="0.6", generator="nvdb2osm_sweden", upload="false"
    )

    # Pass 1: Junction nodes

    for node_coordinate, node in iter(junctions.items()):
        osm_node = ET.Element(
            "node",
            id=str(node_id),
            action="modify",
            lat=str(node_coordinate[1]),
            lon=str(node_coordinate[0]),
        )
        osm_root.append(osm_node)
        for key, value in iter(node["tags"].items()):
            tag_property(osm_node, key, value)
        if segment_output:
            for key, value in iter(node["properties"].items()):
                tag_property(
                    osm_node,
                    "NVDB_"
                    + key.replace(" ", "_")
                    .replace("-", "_")
                    .replace("(", "_")
                    .replace(")", ""),
                    str(value),
                )

        node["osmid"] = node_id
        node_id += 1

    # Pass 2: Internal nodes

    for way_segments in ways:
        for segment in way_segments:
            segment["internal_node_ids"] = []
            line_geometry = segment["geometry"]["coordinates"][0][1:-1]
            for node in line_geometry:
                osm_node = ET.Element(
                    "node",
                    id=str(node_id),
                    action="modify",
                    lat=str(node[1]),
                    lon=str(node[0]),
                )
                osm_root.append(osm_node)
                segment["internal_node_ids"].append(node_id)
                node_id += 1

    # Pass 3: Ways

    for way_segments in ways:
        segment = way_segments[0]
        count += 1
        osm_way = ET.Element("way", id=str(way_id), action="modify")
        osm_root.append(osm_way)

        # All tags are identical for the connected segments

        for key, value in iter(segment["tags"].items()):
            tag_property(osm_way, key, value)
        if segment_output:
            for prop_key, prop_value in iter(segment["properties"].items()):
                tag_property(
                    osm_way,
                    "NVDB_"
                    + prop_key.replace(" ", "_")
                    .replace("-", "_")
                    .replace("(", "_")
                    .replace(")", ""),
                    str(prop_value),
                )

        osm_way.append(
            ET.Element("nd", ref=str(junctions[segment["start_node"]]["osmid"]))
        )

        # Loop all segments in connected way

        for segment in way_segments:
            segment["osmid"] = way_id

            for nid in segment["internal_node_ids"]:
                osm_way.append(ET.Element("nd", ref=str(nid)))

            osm_way.append(
                ET.Element("nd", ref=str(junctions[segment["end_node"]]["osmid"]))
            )

        way_id += 1

    # Produce OSM/XML file

    if output_filename:
        filename = output_filename
    else:
        # Strip known geospatial extensions for output filename
        base = filename
        for ext in [".geojson", ".json", ".gpkg", ".shp"]:
            if base.lower().endswith(ext):
                base = base[: -len(ext)]
                break
        else:
            # Handle .gdb directories
            if base.lower().endswith(".gdb"):
                base = base[: -len(".gdb")]

        if segment_output:
            filename = base + "_segment.osm"
        else:
            filename = base + ".osm"

    # Ensure parent directory exists
    parent_dir = os.path.dirname(filename)
    if parent_dir:
        os.makedirs(parent_dir, exist_ok=True)

    osm_tree = ET.ElementTree(osm_root)
    osm_tree.write(filename, encoding="utf-8", method="xml", xml_declaration=True)

    message("\n\tSaved %i elements in file '%s'\n" % (count, filename))
    return (node_id, way_id)


# Output road network to OSM PBF file using pyosmium


def output_pbf(filename: str, output_filename: Optional[str] = None,
               start_node_id: int = 1, start_way_id: int = 1) -> Tuple[int, int]:
    message("Saving PBF file... ")

    if output_filename:
        filename = output_filename
    else:
        base = filename
        for ext in [".geojson", ".json", ".gpkg", ".shp"]:
            if base.lower().endswith(ext):
                base = base[: -len(ext)]
                break
        else:
            if base.lower().endswith(".gdb"):
                base = base[: -len(".gdb")]

        if segment_output:
            filename = base + "_segment.osm.pbf"
        else:
            filename = base + ".osm.pbf"

    # Ensure parent directory exists
    parent_dir = os.path.dirname(filename)
    if parent_dir:
        os.makedirs(parent_dir, exist_ok=True)

    if os.path.exists(filename):
        os.remove(filename)

    writer = osmium.SimpleWriter(filename)
    node_id = start_node_id
    way_id = start_way_id
    count = 0

    # Pass 1: Write all junction nodes

    for coord, junc in iter(junctions.items()):
        writer.add_node(
            osmium.osm.mutable.Node(id=node_id, location=coord, tags=junc["tags"])
        )
        junc["osmid"] = node_id
        node_id += 1

    # Pass 2: Write all internal nodes (must come before ways for osmium merge)

    for way_segs in ways:
        for seg in way_segs:
            seg["internal_node_ids"] = []
            internal_coords = seg["geometry"]["coordinates"][0][1:-1]
            for c in internal_coords:
                writer.add_node(
                    osmium.osm.mutable.Node(id=node_id, location=(c[0], c[1]))
                )
                seg["internal_node_ids"].append(node_id)
                node_id += 1

    # Pass 3: Write all ways

    for way_segs in ways:
        count += 1
        way_node_ids = []

        # Start junction
        way_node_ids.append(junctions[way_segs[0]["start_node"]]["osmid"])

        # Loop all segments in connected way
        for seg in way_segs:
            for nid in seg["internal_node_ids"]:
                way_node_ids.append(nid)
            way_node_ids.append(junctions[seg["end_node"]]["osmid"])

        writer.add_way(
            osmium.osm.mutable.Way(
                id=way_id, nodes=way_node_ids, tags=way_segs[0]["tags"]
            )
        )
        way_id += 1

    writer.close()
    message("\n\tSaved %i elements in file '%s'\n" % (count, filename))
    return (node_id, way_id)


# Check if coordinates in a GeoJSON FeatureCollection look like WGS84.
# WGS84: |lon| <= 180, |lat| <= 90. Swedish EPSG:3006 has values > 100,000.


def _guess_wgs84(segments: Dict[str, Any]) -> bool:
    if not segments.get("features"):
        return False
    coords = segments["features"][0]["geometry"]["coordinates"]
    if coords and coords[0]:
        x, y = coords[0][0][0], coords[0][0][1]
        if abs(x) <= 180 and abs(y) <= 90:
            return True
    return False


# Transform coordinates from source CRS to WGS84 (EPSG:4326).
# Returns list of [lon, lat, elevation] lists.


def transform_coordinates(
    coordinates: List[List[float]], transformer: Any
) -> List[List[float]]:
    result = []
    for coord in coordinates:
        lon, lat = transformer.transform(coord[0], coord[1])
        elevation = float(coord[2]) if len(coord) > 2 else 0.0
        result.append([lon, lat, elevation])
    return result


# Load geospatial file using Fiona (supports FileGDB, GeoPackage, Shapefile, etc.).
# Returns (feature_collection_dict, crs_string).


def load_file_fiona(
    filename: str, layer: Optional[str] = None, where: Optional[str] = None
) -> Tuple[Dict[str, Any], str]:
    try:
        import fiona
    except ImportError:
        sys.exit("Error: 'fiona' package is required for non-GeoJSON files. Install with: pip install fiona")

    # Determine layer for multi-layer files
    if layer is None:
        layers = fiona.listlayers(filename)
        if len(layers) == 1:
            layer = layers[0]
        elif "TNE_FT_VAGDATA" in layers:
            layer = "TNE_FT_VAGDATA"
            message("(auto-selected layer '%s') " % layer)
        else:
            message("\nAvailable layers: %s\n" % ", ".join(layers))
            sys.exit("Multiple layers found. Use --layer to specify.")
    else:
        message("(layer: %s) " % layer)

    features = []
    with fiona.open(filename, layer=layer) as src:
        source_crs = str(src.crs) if src.crs else "EPSG:3006"
        message("(CRS: %s) " % source_crs)

        iterator = src.filter(where=where) if where else src
        for fiona_feature in iterator:
            geometry = dict(fiona_feature["geometry"])
            properties = dict(fiona_feature["properties"])

            # Convert coordinate tuples to lists
            if geometry["type"] == "MultiLineString":
                geometry["coordinates"] = [
                    [[float(c) for c in coord] for coord in linestring]
                    for linestring in geometry["coordinates"]
                ]
            else:
                message("WARNING: Skipping feature with geometry type %s\n" % geometry["type"])
                continue

            features.append({
                "type": "Feature",
                "properties": properties,
                "geometry": geometry,
            })

    return {"type": "FeatureCollection", "features": features}, source_crs


# Load geospatial file and process for conversion.
# Supports GeoJSON (.geojson/.json) via json module, and any other format via Fiona.
# Coordinates are transformed from source CRS to WGS84 (EPSG:4326).


def load_file(
    filename: str, source_crs: Optional[str] = None, layer: Optional[str] = None,
    county: Optional[str] = None, municipality: Optional[str] = None
) -> None:
    global segments

    # Build OGR SQL where clause for filtering by county or municipality
    where = None
    if municipality:
        where = "Kommu_141 = '%s'" % municipality
    elif county:
        where = "Kommu_141 LIKE '%s%%'" % county

    if where:
        message("Loading file '%s' (filter: %s) ... " % (filename, where))
    else:
        message("Loading file '%s' ... " % filename)

    file_lower = filename.lower()

    if file_lower.endswith(".geojson") or file_lower.endswith(".json"):
        with open(filename) as f:
            segments = json.load(f)

        # Python-side filtering for GeoJSON (uses raw field name before rename)
        if municipality:
            segments["features"] = [
                f for f in segments["features"]
                if str(f["properties"].get("Kommu_141", "")) == municipality
            ]
        elif county:
            segments["features"] = [
                f for f in segments["features"]
                if str(f["properties"].get("Kommu_141", "")).startswith(county)
            ]

        if source_crs is None:
            if _guess_wgs84(segments):
                source_crs = "EPSG:4326"
                message("(coordinates appear to be WGS84) ")
            else:
                source_crs = "EPSG:3006"
        message("(CRS: %s) " % source_crs)
    else:
        segments, detected_crs = load_file_fiona(filename, layer=layer, where=where)
        if source_crs is None:
            source_crs = detected_crs

    # Transform coordinates to WGS84

    if source_crs and source_crs != "EPSG:4326":
        try:
            from pyproj import Transformer
        except ImportError:
            # Build a suggested output filename for the ogr2ogr hint
            base = filename
            for ext in [".geojson", ".json", ".gpkg", ".shp"]:
                if base.lower().endswith(ext):
                    base = base[: -len(ext)]
                    break
            else:
                if base.lower().endswith(".gdb"):
                    base = base[: -len(".gdb")]
            suggested = base + "_wgs84.geojson"
            sys.exit(
                "Error: 'pyproj' package is required for CRS transformation. Install with: pip install pyproj\n"
                "Or reproject to WGS84 first, e.g.:\n"
                "  ogr2ogr -f GeoJSON -t_srs EPSG:4326 %s %s" % (suggested, filename)
            )
        message("transforming to WGS84... ")
        transformer = Transformer.from_crs(source_crs, "EPSG:4326", always_xy=True)
        for segment in segments["features"]:
            segment["geometry"]["coordinates"][0] = transform_coordinates(
                segment["geometry"]["coordinates"][0], transformer
            )

    for segment in segments["features"]:
        # Remove empty properties and rename to more readable names

        for key in list(segment["properties"]):
            if segment["properties"][key] is None:
                del segment["properties"][key]
            else:
                if key in nvdb_attributes:
                    if nvdb_attributes[key]:
                        segment["properties"][nvdb_attributes[key]] = segment[
                            "properties"
                        ].pop(key)
                else:
                    message("*** Attribute %s not recognised\n" % key)

        # Round coordinates and get start/end nodes

        for coordinate in segment["geometry"]["coordinates"][0]:
            coordinate[0] = round(coordinate[0], coordinate_decimals)
            coordinate[1] = round(coordinate[1], coordinate_decimals)
            coordinate[2] = round(coordinate[2], coordinate_decimals)

        segment["start_node"] = (
            segment["geometry"]["coordinates"][0][0][0],
            segment["geometry"]["coordinates"][0][0][1],
        )  # tuple
        segment["end_node"] = (
            segment["geometry"]["coordinates"][0][-1][0],
            segment["geometry"]["coordinates"][0][-1][1],
        )  # tuple

    # Normalize boolean values (-1 means true in NVDB GeoJSON, convert to 1)
    boolean_fields = [
        "Förbud mot trafik(F)",
        "Förbud mot trafik(B)",
        "Förbjuden färdriktning(F)",
        "Förbjuden färdriktning(B)",
        "Cirkulationsplats(F)",
        "Cirkulationsplats(B)",
        "Tättbebyggt område",
        "Färjeled",
        "Motorväg",
        "Motortrafikled",
        "GCM-belyst",
        "GCM-passage",
        "Hållplats",
        "Katastroföverfart",
        "Viltpassage i plan",
        "Viltuthopp(V)",
        "Viltuthopp(H)",
        "Omkörningsförbud(F)",
        "Omkörningsförbud(B)",
        "Stigningsfält(F)",
        "Stigningsfält(B)",
        "Gågata(V)",
        "Gågata(H)",
        "Gångfartsområde(V)",
        "Gångfartsområde(H)",
        "Provisorisk väg",
        "Miljözon",
        "C-Rekommenderad bilväg for cykel",
        "P-ficka(V)",
        "P-ficka(H)",
        "P-ficka(M)",
        "Rastplats",
        "Driftvändplats",
        "Brunn-slamsugning",
    ]
    for segment in segments["features"]:
        for field in boolean_fields:
            if field in segment["properties"] and segment["properties"][field] == -1:
                segment["properties"][field] = 1

    message("\n\t%i highway segments loaded\n" % len(segments["features"]))


# Reset global state for processing a new chunk

def reset_globals():
    global segments, nodes, junctions, ways
    segments = []
    nodes = []
    junctions = {}
    ways = []


# Process one chunk (county or municipality)

def process_one(filename, output_file, output_format, source_crs, layer,
                county=None, municipality=None,
                start_node_id=1, start_way_id=1):
    reset_globals()
    load_file(filename, source_crs=source_crs, layer=layer, county=county, municipality=municipality)
    if not segments or not segments.get("features"):
        message("\tNo segments found, skipping.\n")
        return 0, start_node_id, start_way_id
    count = len(segments["features"])
    tag_network()
    simplify_network(simplify_method)
    if output_format == "pbf":
        next_node_id, next_way_id = output_pbf(
            filename, output_filename=output_file,
            start_node_id=start_node_id, start_way_id=start_way_id)
    else:
        next_node_id, next_way_id = output_network(
            filename, output_filename=output_file,
            start_node_id=start_node_id, start_way_id=start_way_id)
    return count, next_node_id, next_way_id


# Memory reporting helpers

def _get_peak_mb():
    """Return current peak RSS in MB (works on Linux and macOS)."""
    ru = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    # macOS reports bytes, Linux reports kilobytes
    return ru / 1024 if sys.platform != "darwin" else ru / 1024 / 1024

def _fmt_mem(mb):
    """Format memory in MB or GB."""
    if mb >= 1024:
        return "%.1f GB" % (mb / 1024)
    return "%.0f MB" % mb


# Worker function for parallel --split processing (runs in spawned subprocess)

def _process_chunk(filename, chunk_file, output_format, source_crs, layer,
                   county, municipality, start_node_id, start_way_id, config):
    global simplify_method, segment_output, debug, quiet
    simplify_method = config["simplify_method"]
    segment_output = config["segment_output"]
    debug = config["debug"]
    quiet = True

    chunk_label = county or municipality
    t0 = time.time()
    count, _, _ = process_one(
        filename, chunk_file, output_format, source_crs, layer,
        county=county, municipality=municipality,
        start_node_id=start_node_id, start_way_id=start_way_id)
    elapsed = time.time() - t0
    peak_mb = _get_peak_mb()
    return (chunk_label, count, elapsed, peak_mb)


# Main program

if __name__ == "__main__":
    start_time = time.time()

    parser = argparse.ArgumentParser(description="Converts NVDB data to OSM or PBF.")
    parser.add_argument("filename", help="Input GeoJSON/FileGDB/GeoPackage file")
    parser.add_argument(
        "-o", "--output", help="Output file path (optional)", default=None
    )
    parser.add_argument(
        "--format",
        choices=["osm", "pbf"],
        default=None,
        help="Output format: 'osm' (XML) or 'pbf'. Auto-detected from output filename if not specified.",
    )
    parser.add_argument(
        "-segment",
        action="store_true",
        help="Output each highway segments as in input file, without creating longer ways",
    )
    parser.add_argument("-debug", action="store_true", help="Add extra tags for debugging/testing")
    parser.add_argument("--layer", help="Layer name for FileGDB/GeoPackage/Shapefile")
    parser.add_argument("--source-crs", help="Source CRS (e.g. EPSG:3006)")
    parser.add_argument(
        "--county",
        help="Process only one county (e.g. 25 for Norrbotten)",
    )
    parser.add_argument(
        "--municipality",
        help="Process only one municipality (e.g. 2580 for Umea)",
    )
    parser.add_argument(
        "--split",
        nargs="?",
        const="county",
        choices=["county", "municipality"],
        help="Process entire file by splitting into chunks. Default: county. Output goes to a folder.",
    )
    parser.add_argument(
        "--no-merge",
        action="store_true",
        help="With --split: skip auto-merge, keep only individual chunk files.",
    )
    parser.add_argument(
        "--jobs", "-j",
        type=int,
        default=1,
        help="Number of parallel workers for --split mode (default: 1 = sequential).",
    )
    parser.add_argument(
        "--all-county-codes",
        action="store_true",
        help="Try all county codes 01-25 instead of the 21 known valid codes. "
             "Use if county boundaries have been reorganized.",
    )

    args = parser.parse_args()

    filename = args.filename
    output_file = args.output

    # Determine output format
    output_format = args.format
    if output_format is None:
        if output_file and output_file.lower().endswith(".pbf"):
            output_format = "pbf"
        else:
            output_format = "osm"

    if output_format == "pbf" and not _has_osmium:
        sys.exit(
            "Error: 'osmium' package is required for PBF output. Install with: pip install osmium"
        )

    message(
        "\nConverting Swedish NVDB to %s\n\n" % ("PBF" if output_format == "pbf" else "OSM")
    )

    if args.segment:
        segment_output = True
        simplify_method = "segment"

    if args.debug:
        debug = True
        segment_output = True
        simplify_method = "segment"

    # Optional arguments
    layer = args.layer
    source_crs = args.source_crs

    segments = []  # To store all highway segments
    nodes = []  # To store all tagged nodes
    junctions = {}  # To store all junctions
    ways = []  # To store connected ways for output

    ext = ".osm.pbf" if output_format == "pbf" else ".osm"

    # Determine base name for output
    base = filename
    for strip_ext in [".geojson", ".json", ".gpkg", ".shp"]:
        if base.lower().endswith(strip_ext):
            base = base[: -len(strip_ext)]
            break
    else:
        if base.lower().endswith(".gdb"):
            base = base[: -len(".gdb")]

    if args.split:
        # --split county or --split municipality
        if args.no_merge:
            # -o is the folder
            output_dir = output_file if output_file else base + "_split"
            merged_file = None
        else:
            # -o is the merged output file
            merged_file = output_file if output_file else base + ext
            merge_base = merged_file
            for strip_ext in [".osm.pbf", ".osm"]:
                if merge_base.lower().endswith(strip_ext):
                    merge_base = merge_base[:-len(strip_ext)]
                    break
            output_dir = merge_base + "_split"
        os.makedirs(output_dir, exist_ok=True)

        total_segments = 0
        num_jobs = args.jobs

        if args.split == "county":
            if args.all_county_codes:
                codes = ['%02d' % i for i in range(1, 26)]
            else:
                # 21 current Swedish counties (codes 02, 11, 15, 16 were merged into other counties)
                codes = ['01', '03', '04', '05', '06', '07', '08', '09', '10',
                         '12', '13', '14', '17', '18', '19', '20', '21', '22', '23', '24', '25']

            if num_jobs > 1:
                config = {
                    "simplify_method": simplify_method,
                    "segment_output": segment_output,
                    "debug": debug,
                }
                message("Processing %i counties with %i workers...\n" % (len(codes), num_jobs))
                futures = {}
                try:
                    with concurrent.futures.ProcessPoolExecutor(max_workers=num_jobs) as executor:
                        for i, code in enumerate(codes):
                            chunk_file = os.path.join(output_dir, "county_%s%s" % (code, ext))
                            start_id = i * 10_000_000 + 1
                            future = executor.submit(
                                _process_chunk,
                                filename, chunk_file, output_format, source_crs, layer,
                                code, None, start_id, start_id, config)
                            futures[future] = code
                        done_count = 0
                        for future in concurrent.futures.as_completed(futures):
                            code = futures[future]
                            try:
                                chunk_label, count, elapsed_chunk, peak_mb = future.result()
                            except Exception as e:
                                message("ERROR: County %s failed: %s\n" % (code, e))
                                raise
                            done_count += 1
                            total_segments += count
                            if count:
                                message("[%2d/%d done] County %s: %s segments (%.0fs, %s peak) | Total: %s segments\n" % (
                                    done_count, len(codes), chunk_label,
                                    "{:,}".format(count), elapsed_chunk, _fmt_mem(peak_mb),
                                    "{:,}".format(total_segments)))
                            else:
                                message("[%2d/%d done] County %s: skipped (no segments)\n" % (
                                    done_count, len(codes), chunk_label))
                except concurrent.futures.process.BrokenProcessPool:
                    message("\nERROR: A worker process was killed (likely out of memory).\n"
                            "Try reducing --jobs (e.g. -j %d) to lower memory usage.\n"
                            % max(1, num_jobs // 2))
                    sys.exit(1)
            else:
                for i, code in enumerate(codes):
                    chunk_file = os.path.join(output_dir, "county_%s%s" % (code, ext))
                    start_id = i * 10_000_000 + 1
                    message("\n=== County %s ===\n" % code)
                    chunk_time = time.time()
                    count, _, _ = process_one(
                        filename, chunk_file, output_format, source_crs, layer,
                        county=code, start_node_id=start_id, start_way_id=start_id)
                    total_segments += count
                    if count:
                        peak_mb = _get_peak_mb()
                        message("County %s: %i segments in %i seconds (peak %s)\n" % (code, count, time.time() - chunk_time, _fmt_mem(peak_mb)))

        elif args.split == "municipality":
            # Discover municipality codes
            message("Scanning for municipality codes...\n")
            file_lower = filename.lower()
            if file_lower.endswith(".geojson") or file_lower.endswith(".json"):
                with open(filename) as f:
                    data = json.load(f)
                codes = sorted(set(
                    str(f["properties"].get("Kommu_141", ""))
                    for f in data["features"]
                    if f["properties"].get("Kommu_141")
                ))
                del data
            else:
                try:
                    import fiona
                except ImportError:
                    sys.exit("Error: 'fiona' package is required. Install with: pip install fiona")
                with fiona.open(filename, layer=layer or "TNE_FT_VAGDATA") as src:
                    codes = sorted(set(
                        str(f["properties"]["Kommu_141"])
                        for f in src
                        if f["properties"].get("Kommu_141")
                    ))
            message("Found %i municipality codes\n" % len(codes))

            if num_jobs > 1:
                config = {
                    "simplify_method": simplify_method,
                    "segment_output": segment_output,
                    "debug": debug,
                }
                message("Processing %i municipalities with %i workers...\n" % (len(codes), num_jobs))
                futures = {}
                try:
                    with concurrent.futures.ProcessPoolExecutor(max_workers=num_jobs) as executor:
                        for i, code in enumerate(codes):
                            chunk_file = os.path.join(output_dir, "municipality_%s%s" % (code, ext))
                            start_id = i * 10_000_000 + 1
                            future = executor.submit(
                                _process_chunk,
                                filename, chunk_file, output_format, source_crs, layer,
                                None, code, start_id, start_id, config)
                            futures[future] = code
                        done_count = 0
                        for future in concurrent.futures.as_completed(futures):
                            code = futures[future]
                            try:
                                chunk_label, count, elapsed_chunk, peak_mb = future.result()
                            except Exception as e:
                                message("ERROR: Municipality %s failed: %s\n" % (code, e))
                                raise
                            done_count += 1
                            total_segments += count
                            if count:
                                message("[%3d/%d done] Municipality %s: %s segments (%.0fs, %s peak) | Total: %s segments\n" % (
                                    done_count, len(codes), chunk_label,
                                    "{:,}".format(count), elapsed_chunk, _fmt_mem(peak_mb),
                                    "{:,}".format(total_segments)))
                            else:
                                message("[%3d/%d done] Municipality %s: skipped (no segments)\n" % (
                                    done_count, len(codes), chunk_label))
                except concurrent.futures.process.BrokenProcessPool:
                    message("\nERROR: A worker process was killed (likely out of memory).\n"
                            "Try reducing --jobs (e.g. -j %d) to lower memory usage.\n"
                            % max(1, num_jobs // 2))
                    sys.exit(1)
            else:
                for i, code in enumerate(codes):
                    chunk_file = os.path.join(output_dir, "municipality_%s%s" % (code, ext))
                    start_id = i * 10_000_000 + 1
                    message("\n=== Municipality %s ===\n" % code)
                    chunk_time = time.time()
                    count, _, _ = process_one(
                        filename, chunk_file, output_format, source_crs, layer,
                        municipality=code, start_node_id=start_id, start_way_id=start_id)
                    total_segments += count
                    if count:
                        peak_mb = _get_peak_mb()
                        message("Municipality %s: %i segments in %i seconds (peak %s)\n" % (code, count, time.time() - chunk_time, _fmt_mem(peak_mb)))

        elapsed = time.time() - start_time
        message("\nTotal: %i segments in %i seconds" % (total_segments, elapsed))
        if total_segments:
            message(" (%i segments per second)" % (total_segments / elapsed))
        message("\n")

        # Auto-merge chunk files
        if merged_file:
            chunk_pattern = os.path.join(output_dir, "%s_*%s" % (args.split, ext))
            chunk_files = sorted(glob.glob(chunk_pattern))
            if len(chunk_files) > 1:
                message("\nMerging %i files into '%s'... " % (len(chunk_files), merged_file))
                pre_merge_mb = _get_peak_mb()
                merge_time = time.time()
                merger = osmium.MergeInputReader()
                for cf in chunk_files:
                    merger.add_file(cf)
                with osmium.SimpleWriter(merged_file) as writer:
                    merger.apply(writer, simplify=False)
                post_merge_mb = _get_peak_mb()
                merge_elapsed = time.time() - merge_time
                merge_delta = post_merge_mb - pre_merge_mb
                if merge_delta > 0:
                    message("done in %is (merge used %s, total peak %s)\n" % (merge_elapsed, _fmt_mem(merge_delta), _fmt_mem(post_merge_mb)))
                else:
                    message("done in %is (peak %s)\n" % (merge_elapsed, _fmt_mem(post_merge_mb)))
            elif len(chunk_files) == 1:
                message("\nSingle output file: %s\n" % chunk_files[0])

    elif args.county or args.municipality:
        # Single region
        count, _, _ = process_one(
            filename, output_file, output_format, source_crs, layer,
            county=args.county, municipality=args.municipality,
        )
        elapsed = time.time() - start_time
        if count:
            message("Time: %i seconds (%i segments per second)\n\n" % (elapsed, count / elapsed))

    else:
        # Existing behavior: process entire file at once
        load_file(filename, source_crs=source_crs, layer=layer)

        if segments and segments.get("features") and len(segments["features"]) > 500000:
            message(
                "WARNING: Large dataset (%i segments). Consider using --split county for country-wide data.\n"
                % len(segments["features"])
            )

        tag_network()
        simplify_network(simplify_method)

        if output_format == "pbf":
            output_pbf(filename, output_filename=output_file)
        else:
            output_network(filename, output_filename=output_file)

        elapsed = time.time() - start_time
        message(
            "Time: %i seconds (%i segments per second)\n\n"
            % (elapsed, len(segments["features"]) / elapsed)
        )

    message("Peak memory: %s\n" % _fmt_mem(_get_peak_mb()))
