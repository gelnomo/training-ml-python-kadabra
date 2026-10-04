"""Download a movie poster and index its CLIP vector (scene search)."""
import io
import json
import logging
import urllib.parse
import urllib.request

from django.conf import settings
from PIL import Image

from apps.document.schema import MoviePosters

logger = logging.getLogger(__name__)


def poster_url(movie):
    """Poster URL from the stored OMDb payload, or fetched from OMDb by imdb id."""
    url = (movie.payload or {}).get("Poster")
    if (not url or url == "N/A") and movie.imdb_id and settings.IMDBID_APIKEY:
        query = urllib.parse.urlencode({"i": movie.imdb_id.strip(), "apikey": settings.IMDBID_APIKEY})
        with urllib.request.urlopen(f"http://www.omdbapi.com/?{query}", timeout=30) as response:
            url = json.load(response).get("Poster")
    return url if url and url != "N/A" else None


def download_image(url):
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(request, timeout=30) as response:
        return Image.open(io.BytesIO(response.read()))


def index_poster(row, movie, posters=None, index=None):
    """
    Index the poster of ``movie`` under document id ``row["id"]``.
    Returns False when the movie has no poster.
    """
    url = poster_url(movie)
    if not url:
        logger.info("No poster for %s", movie.imdb_id)
        return False

    posters = posters or MoviePosters()
    vector = posters.encode_images([download_image(url)])[0]
    posters.insert_one({**row, "poster_url": url}, vector, index=index)
    return True
