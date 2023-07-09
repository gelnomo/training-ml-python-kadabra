import numpy as np
from elasticsearch import Elasticsearch
from django.conf import settings
from elasticsearch import helpers
import tensorflow as tf

from apps.botAI.load_model import LoadModel


def elastic_connection():
    return Elasticsearch(
        settings.ELASTICSEARCH_HOST,
        basic_auth=(settings.ELASTICSEARCH_USER, settings.ELASTICSEARCH_PWD),
        verify_certs=settings.ELASTICSEARCH_VERIFY_CERTS,
    )


class Faces:
    INDEX = "celebrity"

    def __init__(self):
        self.es = elastic_connection()

    def __check_index(self):
        if not self.es.indices.exists(index=self.INDEX):
            self.__create_index()

    def __create_index(self):
        index_body = {
            "mappings": {
                "properties": {
                    "face_encoding": {"type": "dense_vector", "dims": 128},
                    "image_id": {"type": "keyword"},
                    "actor_id": {"type": "keyword"},
                    "name": {"type": "keyword"},
                }
            },
            "settings": {
                "index": {
                    "routing": {
                        "allocation": {"include": {"_tier_preference": "data_content"}}
                    },
                    "number_of_shards": settings.ELASTICSEARCH_NUM_SHARDS,
                    "number_of_replicas": settings.ELASTICSEARCH_NUM_REPLICAS,
                }
            },
        }

        print(f"creating '{self.INDEX}' index...")
        self.es.indices.create(index=self.INDEX, body=index_body)

    def update_one(self, row):
        self.__check_index()

        data_dict = {
            "name": row["name"],
            "image_id": row["image_id"],
            "actor_id": row["actor_id"],
            "face_encoding": row["face_encoding"],
        }

        result = self.es.update(index=self.INDEX, id=row["id"], body={"doc": data_dict})
        print(result)

    def insert_one(self, row):
        self.__check_index()

        data_dict = {
            "name": row["name"],
            "image_id": row["image_id"],
            "actor_id": row["actor_id"],
            "face_encoding": row["face_encoding"],
        }
        result = self.es.index(index=self.INDEX, id=row["id"], document=data_dict)
        print(result)

    def insert_many(self, data):
        self.__check_index()

        bulk_data = []

        for index, row in data.iterrows():
            data_dict = {
                "name": row["name"],
                "image_id": row["image_id"],
                "actor_id": row["actor_id"],
                "face_encoding": row["face_encoding"],
            }
            op_dict = {"index": {"_index": self.INDEX, "_id": row["id"]}}
            bulk_data.append(op_dict)
            bulk_data.append(data_dict)

        res = self.es.bulk(index=self.INDEX, body=bulk_data)
        print(res)

    def delete_by_document_id(self, document_id):
        try:
            return self.es.delete(index=self.INDEX, id=document_id)
        except Exception as ex:
            print(ex)

    def get_by_document_id(self, document_id):
        return self.es.get(index=self.INDEX, id=document_id)

    def check_by_document_id(self, document_id):
        return self.es.exists(index=self.INDEX, id=document_id)

    def query(self):
        return self.es.search(body={"query": {"match_all": {}}}, index=self.INDEX)

    def query_face(self, face_encodings, size=1):
        result = []
        for face_encoding in face_encodings:
            query = {
                "function_score": {
                    "functions": [
                        {
                            "script_score": {
                                "script": {
                                    "source": "cosineSimilarity(params.query_vector, 'face_encoding')",
                                    "params": {"query_vector": face_encoding.tolist()},
                                }
                            }
                        }
                    ],
                    "query": {"bool": {"must": [{"match_all": {}}]}},
                }
            }

            resp = self.es.search(
                index=self.INDEX,
                query=query,
                size=size,
                _source=["name", "image_id", "actor_id"],
            )
            result.append(resp)
        return result

    def get_mapping(self):
        return self.es.indices.get_mapping(index=self.INDEX)


class Movies:
    INDEX = "movies_search"

    def __init__(self):
        self.es = elastic_connection()

    def __check_index(self):
        if not self.es.indices.exists(index=self.INDEX):
            self.__create_index()

    def __create_index(self):
        _settings = {
            "number_of_shards": settings.ELASTICSEARCH_NUM_SHARDS,
            "number_of_replicas": settings.ELASTICSEARCH_NUM_REPLICAS,
        }

        _mappings = {
            "dynamic": "true",
            "_source": {
                "enabled": "true"
            },
            "properties": {
                "title": {
                    "type": "text"
                },
                "year": {
                    "type": "text"
                },
                "celebrities": {
                    "type": "nested",
                    "properties": {
                        "id": {
                            "type": "keyword"
                        },
                        "name": {
                            "type": "text"
                        }
                    }
                },
                "imdb_id": {
                    "type": "text"
                },
                "description": {
                    "type": "text"
                },
                "description_vector": {
                    "type": "dense_vector",
                    "dims": 512,
                    "index": "true",
                    "similarity": "l2_norm"
                }
            }
        }

        print(f"creating '{self.INDEX}' index...")
        self.es.indices.create(index=self.INDEX, settings=_settings, mappings=_mappings)

    def update_one(self, row):
        self.__check_index()
        embed = LoadModel().get_embed()
        vector = tf.constant([row["description"]])
        embeddings = embed(vector)
        vector = np.asanyarray(embeddings)
        vector = vector[0].tolist()

        data_dict = {
            "title": row["title"],
            "year": row["year"],
            "imdb_id": row["imdb_id"],
            "description": row["description"],
            "celebrities": row["celebrities"],
            "description_vector": vector,
        }

        result = self.es.update(index=self.INDEX, id=row["id"], body={"doc": data_dict})
        print(result)

    def insert_one(self, row):
        self.__check_index()
        embed = LoadModel().get_embed()
        vector = tf.constant([row["description"]])
        embeddings = embed(vector)
        vector = np.asanyarray(embeddings)
        vector = vector[0].tolist()

        data_dict = {
            "title": row["title"],
            "year": row["year"],
            "imdb_id": row["imdb_id"],
            "description": row["description"],
            "celebrities": row["celebrities"],
            "description_vector": vector,
        }

        result = self.es.index(index=self.INDEX, id=row["id"], document=data_dict)
        print(result)

    def __get_data_bulk(self, data):
        embed = LoadModel().get_embed()

        for index, row in data.iterrows():
            vector = tf.constant([row["description"]])
            embeddings = embed(vector)
            vector = np.asanyarray(embeddings)
            vector = vector[0].tolist()
            yield {
                "_index": self.INDEX,
                "_id": row["id"],
                "title": row["title"],
                "year": row["year"],
                "imdb_id": row["imdb_id"],
                "description": row["description"],
                "celebrities": row["celebrities"],
                "description_vector": vector
            }

    def insert_many(self, data):
        self.__check_index()
        res = helpers.bulk(self.es, self.__get_data_bulk(data))
        print(res)

    def delete_by_document_id(self, document_id):
        return self.es.delete(index=self.INDEX, id=document_id)

    def get_by_document_id(self, document_id):
        return self.es.get(index=self.INDEX, id=document_id)

    def check_by_document_id(self, document_id):
        return self.es.exists(index=self.INDEX, id=document_id)

    def query_movie(self, description, actors):
        self.__check_index()
        query = None
        script_query_knn = None

        if description:
            embed = LoadModel().get_embed()
            x = tf.constant([description])
            embeddings = embed(x)
            x = np.asanyarray(embeddings)
            vector = x[0].tolist()
            script_query_knn = {
                "field": "description_vector",
                "query_vector": vector,
                "k": 1,
                "num_candidates": 100
            }

        if actors:
            celebrities = [
                {
                    "nested": {
                        "path": "celebrities",
                        "query": {
                            "match_phrase": {
                                "celebrities.id": item["id"]
                            }
                        }
                    }
                }
                for item in actors
            ]
            query = {
                "bool": {
                    "should": celebrities
                }
            }

        response = self.es.search(
            index=self.INDEX,
            knn=script_query_knn,
            query=query,
            _source={"includes": ["title", "description", "year", "imdb_id"]}
        )
        return response
