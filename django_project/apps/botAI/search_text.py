from apps.document.schema import Movies


class SearchText:
    def __init__(self, message, actors):
        self.message = message
        self.actors = actors

    def process(self):
        movies = Movies()
        films = movies.query_movie(self.message, self.actors)

        for hit in films["hits"]["hits"]:
            movie_name = hit["_source"]["title"]
            movie_year = hit["_source"]["year"]
            actors = f"\nCelebrities: \t<b>{ ','.join([item['name'] for item in self.actors])}</b>" if self.actors else ""
            movie_description = hit["_source"]["description"][:100]
            movie_url = f"https://www.imdb.com/title/{hit['_source']['imdb_id']}"
            text = f"Movie:\n\t<b>{movie_name}</b>{actors}" \
                   f"\nReleased:\n\t{movie_year}\n" \
                   f"\nSynopsis Sample:\n\t{movie_description}..." \
                   f"\nLink:\n\t<a href='{movie_url}'>IMDb</a>"
            return text
        return None
