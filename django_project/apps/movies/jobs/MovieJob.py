import random

from overrides import override
import urllib.request
import time
from apps.celebrity.models import Actor
from ms_data_mining.get_html import download_page
from ms_data_mining.inteface import InterfaceJob
from apps.celebrity.enums import StatusEnum
from apps.movies.models import Movie, MovieActor, ElasticSearchMovie
from django.conf import settings
import json
from django.utils.text import slugify
import re


class MovieJob(InterfaceJob):
    JOB_MODEL = Movie
    SPECIAL_CHAR = [
        "E SuB xRG",
        ".avi",
        "1.4",
        "5.1",
        "-",
        "DVDRip",
        "BRRip",
        "XviD",
        "1CDRip",
        "aXXo",
        "[",
        "]",
        "(",
        ")",
        "{",
        "}",
        "{{",
        "}}",
        "x264",
        "720p",
        "DvDScr",
        "MP3",
        "HDRip",
        "WebRip",
        "ETRG",
        "YIFY",
        "StyLishSaLH",
        "StyLish Release",
        "TrippleAudio",
        "EngHindiIndonesian",
        "385MB",
        "CooL GuY",
        "a2zRG",
        "x264",
        "Hindi",
        "AAC",
        "AC3",
        "MP3",
        " R6",
        "HDRip",
        "H264",
        "ESub",
        "AQOS",
        "ALLiANCE",
        "UNRATED",
        "ExtraTorrentRG",
        "BrRip",
        "mkv",
        "mpg",
        "DiAMOND",
        "UsaBitcom",
        "AMIABLE",
        "BRRIP",
        "XVID",
        "AbSurdiTy",
        "DvD",
        "mp3",
        "MPEG4",
        "CRYS",
        "DVDRiP",
        "TASTE",
        "BluRay",
        "HR",
        "COCAIN",
        "_",
        ".",
        "BestDivX",
        "MAXSPEED",
        "mediafiremoviez",
        "Eng",
        "500MB",
        "FXG",
        "Ac3",
        "Feel",
        "Subs",
        "S4A",
        "BDRip",
        "FTW",
        "Xvid",
        "Noir",
        "1337x",
        "ReVoTT",
        "GlowGaze",
        "mp4",
        "Unrated",
        "hdrip",
        "ARCHiViST",
        "TheWretched",
        "www",
        "torrentfive",
        "1080p",
        "201 080p",
        "1080",
        "WEB DL",
        "JYK",
        "SecretMyth",
        "Kingdom",
        "Release",
        "RISES",
        "DvDrip",
        "eXceSs",
        "ViP3R",
        "RISES",
        "BiDA",
        "READNFO",
        "lish",
        "NimitMak",
        "SilverRG",
        "sujaidr",
        "HELLRAZ0R",
        "tots",
        "BeStDivX",
        "UsaBit",
        "FASM",
        "NeroZ",
        "576p",
        "LiMiTED",
        "Series",
        "ExtraTorrent",
        "DVDRIP",
        "~",
        "BRRiP",
        "699MB",
        "700MB",
        "greenbud",
        "B89",
        "480p",
        "AMX",
        "007",
        "DVDrip",
        "h264",
        "phrax",
        "ENG",
        "TODE",
        "LiNE",
        "XVid",
        "sC0rp",
        "PTpower",
        "OSCARS",
        "DXVA",
        "MXMG",
        "3LT0N",
        "TiTAN",
        "4PlayHD",
        "HQ",
        "HDRiP",
        "MoH",
        "MP4",
        "BadMeetsEvil",
        "XViD",
        "3Li",
        "PTpOWeR",
        "3D",
        "HSBS",
        "CC",
        "RiPS",
        "WEBRip",
        "R5",
        "PSiG",
        "'GokU61",
        "GB",
        "GokU61",
        "NL",
        "EE",
        "NL",
        "PSEUDO",
        "DVD",
        "Rip",
        "NeRoZ",
        "EXTENDED",
        "DVDScr",
        "DVDSCR",
        "xvid",
        "WarrLord",
        "SCREAM",
        "MERRY",
        "XMAS",
        "iMB",
        "7o9",
        "Exclusive",
        "171",
        "DiDee",
        "v2",
        "Scr",
        "SaM",
        "MOV",
        "BRrip",
        "CharmeLeon",
        "Silver RG",
        "1xCD",
        "DDR",
        "1CD",
        "X264",
        "ExtraTorrenRG",
        "Srkfan",
        "UNiQUE",
        "Dvd",
        "Dual Audio",
        "crazy torrent",
        "Blackjesus",
        "RIP",
        "NEO",
        "Mr  KickASS",
        "Mr KickASS",
        "MicroStar RG",
        "Spidy",
        "PRiSTiNE",
        "HD",
        "Ganool",
        "TS",
        "BiTo",
        "ARiGOLD",
        "rip",
        "Rets",
        "teh",
        "ChivveZ",
        "song4",
        "playXD",
        "LIMITED",
        "600MB",
        "700MB",
        "900MB",
        "350MB",
        "375MB",
        "380MB",
        "395MB",
        "2015",
        "2014",
        "Manudil",
        "P2PDL",
        "juggs",
        "RLSM",
        "WiLDFYRE",
        "prisak",
        "HKRG",
        "FANTASTiC",
        "MZON3",
        "BlackStaticRG",
        "Subtitles",
        "+",
        "PDvD",
        "MyDownloadCity",
        "GooN",
        "Ali Baloch",
        "dvd",
        "- ",
        "DUB",
        "BDRIP",
        "6CH",
        "KIKS",
        "HC",
        "EVO",
        "Maxillion",
        "BHATTI87",
        "2 0",
        "lish",
        "Lokioddin",
        "PimpRG",
        "AG",
        "BUZZccd",
        "WBRG",
        "GECKOS",
        "H 264",
        "TheFalcon",
        "PLAYNOW",
        "DUBBED",
        "OCW",
        "mSD",
        "AliBaloch",
        "Mediafiremoviez",
        "BlueRay",
        "EVO",
        "IceBane",
        "RyD3R",
        "Zwartboek",
        "CODY",
        "MiCRO",
        "Dual",
        "R@J@T",
        "cam",
        "Demonuk",
        "NIKONRG",
        "AbhinavRocks",
        "HKRG",
        "FLAWL3SS",
        "Jalucian",
        "DTS",
        "DVDRip",
        "XviD",
        "MAXSPEED",
        "www.torentz.3xforum.ro",
        "iTALiAN",
        "MD",
        "Dual",
        "TrTd",
        "TeaM",
        "KiNGDOM",
        "KumaR",
        "UNCUT",
        "BHATTI87",
        "P2PDL",
        "Antitrust",
        "26K",
        "Dias",
        "Rus  Junoon",
        "RARBG",
        "PA",
        "GreatMagician",
        "4 G",
        "ChattChitto",
        "RG",
        "BD  D",
        "6ch",
        "Tornster",
        "Atlas47",
        "480P",
        "DUAL AUDIO",
        "HINDI",
        "PRINCEOFDHEMP",
        "DD",
        "EN",
        "SCR",
        "IMAX EDITION",
        "COD",
        "cam",
        "1080P",
        "AraGon",
        "BD",
        "6Chn Cody's",
        "YTS.AG",
        "KickASS",
        "DUBBED",
        "Mediafiremoviez.com",
        "mediafiremoviez.com",
    ]

    @override
    def internal_process(self, item_id: str) -> bool:
        is_completed = True
        obj_movie = self.JOB_MODEL.objects.get(id=item_id)
        print(f"Processing: {obj_movie.name}")
        self.__download_movie_info(obj_movie)
        self.__get_credits(obj_movie)
        self.__get_synopsis(obj_movie)
        self.__create_actors(obj_movie)
        return is_completed

    @staticmethod
    def __create_actors(obj_movie):
        imdb_ids = obj_movie.starts_id.split(",")
        celebrities = obj_movie.starts_name.split(",")

        for key, value in enumerate(celebrities):
            imdb_id = None
            if key <= len(imdb_ids):
                imdb_id = imdb_ids[key]
            try:
                obj_actor, created = Actor.objects.get_or_create(
                    name=value.strip(), slug=slugify(value.strip()), imdb_id=imdb_id
                )
                MovieActor.objects.get_or_create(movie=obj_movie, actor=obj_actor)
            except Exception as ex:
                print(ex)

    @staticmethod
    def __get_info_movie(year, name, obj_movie):
        movie_url, payload = None, None

        if obj_movie.imdb_id:
            filters = f"i={obj_movie.imdb_id}"
        else:
            filters = f"t={name}"

        if year != 0:
            url = f"http://www.omdbapi.com/?{filters}&y={str(year)}&apikey={settings.IMDBID_APIKEY}"
            with urllib.request.urlopen(url) as response:
                payload = json.load(response)
            if payload["Response"] == "True":
                movie_url = f"www.imdb.com/title/{payload['imdbID']}"
        else:
            url = f"http://www.omdbapi.com/?{filters}&apikey={settings.IMDBID_APIKEY}"
            with urllib.request.urlopen(url) as response:
                payload = json.load(response)
            if payload["Response"] == "True":
                movie_url = f"www.imdb.com/title/{payload.get('imdbID', None)}"

        return movie_url, payload

    @staticmethod
    def __change_chars(obj_str):
        # Remove/replace special chars
        value = obj_str.replace(r"\n", "")
        value = value.replace(r"\'", "'")
        value = value.replace(r'\xc2\x80', '')
        value = value.replace(r'\xc2\x81', '')
        value = value.replace(r'\xc2\x82', '')
        value = value.replace(r'\xc2\x83', '')
        value = value.replace(r'\xc2\x84', '')
        value = value.replace(r'\xc2\x85', '')
        value = value.replace(r'\xc2\x86', '')
        value = value.replace(r'\xc2\x87', '')
        value = value.replace(r'\xc2\x88', '')
        value = value.replace(r'\xc2\x89', '')
        value = value.replace(r'\xc2\x8a', '')
        value = value.replace(r'\xc2\x8b', '')
        value = value.replace(r'\xc2\x8c', '')
        value = value.replace(r'\xc2\x8d', '')
        value = value.replace(r'\xc2\x8e', '')
        value = value.replace(r'\xc2\x8f', '')
        value = value.replace(r'\xc2\x90', '')
        value = value.replace(r'\xc2\x91', '')
        value = value.replace(r'\xc2\x92', '')
        value = value.replace(r'\xc2\x93', '')
        value = value.replace(r'\xc2\x94', '')
        value = value.replace(r'\xc2\x95', '')
        value = value.replace(r'\xc2\x96', '')
        value = value.replace(r'\xc2\x97', '')
        value = value.replace(r'\xc2\x98', '')
        value = value.replace(r'\xc2\x99', '')
        value = value.replace(r'\xc2\x9a', '')
        value = value.replace(r'\xc2\x9b', '')
        value = value.replace(r'\xc2\x9c', '')
        value = value.replace(r'\xc2\x9d', '')
        value = value.replace(r'\xc2\x9e', '')
        value = value.replace(r'\xc2\x9f', '')
        value = value.replace(r'\xc2\xa0', '')
        value = value.replace(r'\xc2\xa1', '¡')
        value = value.replace(r'\xc2\xa2', '¢')
        value = value.replace(r'\xc2\xa3', '£')
        value = value.replace(r'\xc2\xa4', '¤')
        value = value.replace(r'\xc2\xa5', '¥')
        value = value.replace(r'\xc2\xa6', '¦')
        value = value.replace(r'\xc2\xa7', '§')
        value = value.replace(r'\xc2\xa8', '¨')
        value = value.replace(r'\xc2\xa9', '©')
        value = value.replace(r'\xc2\xaa', 'ª')
        value = value.replace(r'\xc2\xab', '«')
        value = value.replace(r'\xc2\xac', '¬')
        value = value.replace(r'\xc2\xad', '­')
        value = value.replace(r'\xc2\xae', '®')
        value = value.replace(r'\xc2\xaf', '¯')
        value = value.replace(r'\xc2\xb0', '°')
        value = value.replace(r'\xc2\xb1', '±')
        value = value.replace(r'\xc2\xb2', '²')
        value = value.replace(r'\xc2\xb3', '³')
        value = value.replace(r'\xc2\xb4', '´')
        value = value.replace(r'\xc2\xb5', 'µ')
        value = value.replace(r'\xc2\xb6', '¶')
        value = value.replace(r'\xc2\xb7', '·')
        value = value.replace(r'\xc2\xb8', '¸')
        value = value.replace(r'\xc2\xb9', '¹')
        value = value.replace(r'\xc2\xba', 'º')
        value = value.replace(r'\xc2\xbb', '»')
        value = value.replace(r'\xc2\xbc', '¼')
        value = value.replace(r'\xc2\xbd', '½')
        value = value.replace(r'\xc2\xbe', '¾')
        value = value.replace(r'\xc2\xbf', '¿')
        value = value.replace(r'\xc3\x80', 'À')
        value = value.replace(r'\xc3\x81', 'Á')
        value = value.replace(r'\xc3\x82', 'Â')
        value = value.replace(r'\xc3\x83', 'Ã')
        value = value.replace(r'\xc3\x84', 'Ä')
        value = value.replace(r'\xc3\x85', 'Å')
        value = value.replace(r'\xc3\x86', 'Æ')
        value = value.replace(r'\xc3\x87', 'Ç')
        value = value.replace(r'\xc3\x88', 'È')
        value = value.replace(r'\xc3\x89', 'É')
        value = value.replace(r'\xc3\x8a', 'Ê')
        value = value.replace(r'\xc3\x8b', 'Ë')
        value = value.replace(r'\xc3\x8c', 'Ì')
        value = value.replace(r'\xc3\x8d', 'Í')
        value = value.replace(r'\xc3\x8e', 'Î')
        value = value.replace(r'\xc3\x8f', 'Ï')
        value = value.replace(r'\xc3\x90', 'Ð')
        value = value.replace(r'\xc3\x91', 'Ñ')
        value = value.replace(r'\xc3\x92', 'Ò')
        value = value.replace(r'\xc3\x93', 'Ó')
        value = value.replace(r'\xc3\x94', 'Ô')
        value = value.replace(r'\xc3\x95', 'Õ')
        value = value.replace(r'\xc3\x96', 'Ö')
        value = value.replace(r'\xc3\x97', '×')
        value = value.replace(r'\xc3\x98', 'Ø')
        value = value.replace(r'\xc3\x99', 'Ù')
        value = value.replace(r'\xc3\x9a', 'Ú')
        value = value.replace(r'\xc3\x9b', 'Û')
        value = value.replace(r'\xc3\x9c', 'Ü')
        value = value.replace(r'\xc3\x9d', 'Ý')
        value = value.replace(r'\xc3\x9e', 'Þ')
        value = value.replace(r'\xc3\x9f', 'ß')
        value = value.replace(r'\xc3\xa0', 'à')
        value = value.replace(r'\xc3\xa1', 'á')
        value = value.replace(r'\xc3\xa2', 'â')
        value = value.replace(r'\xc3\xa3', 'ã')
        value = value.replace(r'\xc3\xa4', 'ä')
        value = value.replace(r'\xc3\xa5', 'å')
        value = value.replace(r'\xc3\xa6', 'æ')
        value = value.replace(r'\xc3\xa7', 'ç')
        value = value.replace(r'\xc3\xa8', 'è')
        value = value.replace(r'\xc3\xa9', 'é')
        value = value.replace(r'\xc3\xaa', 'ê')
        value = value.replace(r'\xc3\xab', 'ë')
        value = value.replace(r'\xc3\xac', 'ì')
        value = value.replace(r'\xc3\xad', 'í')
        value = value.replace(r'\xc3\xae', 'î')
        value = value.replace(r'\xc3\xaf', 'ï')
        value = value.replace(r'\xc3\xb0', 'ð')
        value = value.replace(r'\xc3\xb1', 'ñ')
        value = value.replace(r'\xc3\xb2', 'ò')
        value = value.replace(r'\xc3\xb3', 'ó')
        value = value.replace(r'\xc3\xb4', 'ô')
        value = value.replace(r'\xc3\xb5', 'õ')
        value = value.replace(r'\xc3\xb6', 'ö')
        value = value.replace(r'\xc3\xb7', '÷')
        value = value.replace(r'\xc3\xb8', 'ø')
        value = value.replace(r'\xc3\xb9', 'ù')
        value = value.replace(r'\xc3\xba', 'ú')
        value = value.replace(r'\xc3\xbb', 'û')
        value = value.replace(r'\xc3\xbc', 'ü')
        value = value.replace(r'\xc3\xbd', 'ý')
        value = value.replace(r'\xc3\xbe', 'þ')
        value = value.replace(r'\xc3\xbf', 'ÿ')

        return value

    def __get_credits(self, obj_movie):
        try:
            url = f"https://www.imdb.com/title/{obj_movie.imdb_id.strip()}/fullcredits"
            raw_html = download_page(url)
            time.sleep(random.randint(1, 4))
            items = [
                content.find_all("a")
                for content in raw_html.find_all("table", class_="cast_list")
            ]
            if items:
                items = items[0]

            starts_id = []
            starts_name = []

            for item in items:
                text_id = re.findall(r"\/name\/\w+", item.get("href"))
                if text_id:
                    a_id = text_id[0].replace("/name/", "")
                    if a_id not in starts_id:
                        starts_id.append(a_id)

                        img_start = item.find_all("img")
                        if img_start:
                            img_start = self.__change_chars(
                                item.find_all("img")[0].get("title")
                            )
                        else:
                            img_start = self.__change_chars(item.text)

                        if img_start.strip() not in starts_name:
                            starts_name.append(img_start)

            obj_movie.starts_id = ",".join(starts_id)
            obj_movie.starts_name = ",".join(starts_name)
            obj_movie.save()
        except Exception as ex:
            print(ex)

    def __download_movie_info(self, obj_movie):
        year = 0
        name = obj_movie.name
        for y in range(1900, 2014):
            if str(y) in obj_movie.name:
                name = obj_movie.name.replace(str(y), " ")
                year = y
                break

        for value in self.SPECIAL_CHAR:
            name = name.replace(value, " ")

        name = name.strip()
        name = name.replace(" ", "%20")

        movie_url, payload = self.__get_info_movie(year, name, obj_movie)

        if (
                payload.get("imdbID", "").lower().strip()
                != obj_movie.imdb_id.lower().strip()
        ):
            obj_movie.payload = payload
            obj_movie.save()
            return

        obj_movie.name = payload.get("Title", None)
        obj_movie.payload = payload
        obj_movie.imdb_id = payload.get("imdbID", None)
        obj_movie.year = payload.get("Year", None)
        obj_movie.rating = payload.get("imdbRating", None)
        obj_movie.duration = payload.get("Runtime", None)
        obj_movie.genre = payload.get("Genre", None)
        obj_movie.votes = payload.get("imdbVotes", None)
        obj_movie.gross_income = payload.get("gross_income", None)
        obj_movie.director_name = payload.get("Director", None)
        obj_movie.starts_name = payload.get("Actors", None)
        obj_movie.description = payload.get("Plot", None)
        obj_movie.payload = payload.get("payload", None)
        obj_movie.url = movie_url
        obj_movie.save()

    def __get_synopsis(self, obj_movie):
        try:
            url = f"https://www.imdb.com/title/{obj_movie.imdb_id.strip()}/plotsummary"
            raw_html = download_page(url)
            time.sleep(random.randint(1, 4))

            items = [
                detail.find_all("div", "ipc-html-content-inner-div")[0]
                for content in raw_html.find_all("div", class_="sc-f65f65be-0 fVkLRr")
                if content.get("data-testid") == "sub-section-synopsis"
                for detail in content.find_all(
                    "div", "ipc-html-content ipc-html-content--base"
                )
                if detail.find_all("div", "ipc-html-content-inner-div")
            ]
            if items:
                obj_movie.description += f"\n{items[0].text}"
                obj_movie.description = self.__change_chars(obj_movie.description)
            obj_movie.save()

            ElasticSearchMovie.objects.update_or_create(
                movie=obj_movie,
                defaults={"status": StatusEnum.READY, "attempt": 0},
            )
        except Exception as ex:
            print(ex)
