"""
TMDB Broker & Context Engineering Module.
Fetches movie details from TMDB API and applies group-aware recommendation filtering.
"""

import os
import base64
import logging
import requests
from typing import Optional, List, Dict, Any
from databricks.sdk import WorkspaceClient
from lakebase import run_query, run_write

logger = logging.getLogger("tmdb-broker")
TMDB_BASE_URL = "https://api.themoviedb.org/3"

# Lazy initialization - don't create client at module import time
_tmdb_token_cache = None


def get_tmdb_token() -> str:
    """Retrieve TMDB API Read Access Token from environment or Databricks Secrets."""
    global _tmdb_token_cache
    
    # Return cached token if available
    if _tmdb_token_cache:
        return _tmdb_token_cache
    
    # 1. Direct environment variable (local/dev fallback)
    if os.getenv("TMDB_TOKEN"):
        _tmdb_token_cache = os.getenv("TMDB_TOKEN")
        return _tmdb_token_cache

    # 2. Databricks Secrets Scope
    try:
        scope = os.getenv("TMDB_SECRET_SCOPE", "database")
        key = os.getenv("TMDB_SECRET_KEY", "tmdb-token")
        w = WorkspaceClient()
        secret_resp = w.secrets.get_secret(scope=scope, key=key)
        if secret_resp.value:
            _tmdb_token_cache = base64.b64decode(secret_resp.value).decode("utf-8")
            return _tmdb_token_cache
    except Exception as e:
        logger.warning(f"Could not load TMDB token from Databricks Secrets: {e}")

    return ""


def _tmdb_get(endpoint: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Execute authenticated GET request to TMDB API."""
    token = get_tmdb_token()
    if not token:
        raise ValueError("TMDB API token not configured in Databricks Secrets or environment.")

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json;charset=utf-8"
    }

    url = f"{TMDB_BASE_URL}{endpoint}"
    resp = requests.get(url, headers=headers, params=params or {}, timeout=10)
    resp.raise_for_status()
    return resp.json()


def search_tmdb_movies(query: str, page: int = 1) -> List[Dict[str, Any]]:
    """Search for movies matching a text query."""
    data = _tmdb_get("/search/movie", {"query": query, "page": page, "include_adult": False})
    return data.get("results", [])


def get_movie_full_details(tmdb_id: int) -> Dict[str, Any]:
    """Fetch movie details, credits, keywords, and watch providers."""
    data = _tmdb_get(f"/movie/{tmdb_id}", {"append_to_response": "credits,keywords,watch/providers"})
    
    # Extract streaming providers (US default)
    providers_data = data.get("watch/providers", {}).get("results", {}).get("US", {}).get("flatrate", [])
    streaming_providers = [p.get("provider_name") for p in providers_data if p.get("provider_name")]

    # Extract genres
    genres = [g.get("name") for g in data.get("genres", []) if g.get("name")]

    # Extract keywords
    keywords_data = data.get("keywords", {}).get("keywords", [])
    keywords = [k.get("name") for k in keywords_data if k.get("name")]

    # Extract top 5 cast members
    cast_data = data.get("credits", {}).get("cast", [])[:5]
    top_cast = [c.get("name") for c in cast_data if c.get("name")]

    movie_info = {
        "tmdb_id": data.get("id"),
        "title": data.get("title"),
        "overview": data.get("overview"),
        "genres": genres,
        "runtime": data.get("runtime"),
        "vote_average": data.get("vote_average"),
        "poster_path": f"https://image.tmdb.org/t/p/w500{data.get('poster_path')}" if data.get("poster_path") else None,
        "release_date": data.get("release_date"),
        "keywords": keywords,
        "cast": top_cast,
        "streaming_providers": streaming_providers
    }

    # Try to cache but don't fail if database isn't set up
    try:
        cache_movie(movie_info)
    except Exception as e:
        logger.warning(f"Failed to cache movie {tmdb_id} (database may not be initialized): {e}")
    
    return movie_info


def cache_movie(movie: Dict[str, Any]) -> None:
    """Store or update movie metadata in the Lakebase PostgreSQL cache."""
    sql = """
    INSERT INTO movies (tmdb_id, title, overview, genres, runtime, vote_average, poster_path, release_date, keywords, streaming_providers)
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    ON CONFLICT (tmdb_id) DO UPDATE SET
        title = EXCLUDED.title,
        overview = EXCLUDED.overview,
        genres = EXCLUDED.genres,
        runtime = EXCLUDED.runtime,
        vote_average = EXCLUDED.vote_average,
        poster_path = EXCLUDED.poster_path,
        release_date = EXCLUDED.release_date,
        keywords = EXCLUDED.keywords,
        streaming_providers = EXCLUDED.streaming_providers;
    """
    run_write(sql, (
        movie["tmdb_id"],
        movie["title"],
        movie["overview"],
        movie["genres"],
        movie["runtime"],
        movie["vote_average"],
        movie["poster_path"],
        movie["release_date"],
        movie["keywords"],
        movie["streaming_providers"]
    ))


def get_group_excluded_movies(group_id: int) -> List[int]:
    """Retrieve tmdb_ids already watched, queued, or disliked (score < 6) by any group member."""
    try:
        # 1. Movies already on group watchlist
        watchlist_sql = "SELECT tmdb_id FROM watchlist_items WHERE group_id = %s;"
        watchlist_rows = run_query(watchlist_sql, (group_id,))
        excluded_ids = {row["tmdb_id"] for row in watchlist_rows}

        # 2. Movies rated low (< 6/10) by members in this group
        ratings_sql = """
        SELECT r.tmdb_id 
        FROM ratings r
        JOIN group_members gm ON r.user_email = gm.user_email
        WHERE gm.group_id = %s AND r.score < 6;
        """
        low_rated_rows = run_query(ratings_sql, (group_id,))
        for row in low_rated_rows:
            excluded_ids.add(row["tmdb_id"])

        return list(excluded_ids)
    except Exception as e:
        logger.warning(f"Failed to get excluded movies (database may not be initialized): {e}")
        return []


def discover_and_filter(
    genre_keyword: Optional[str] = None,
    max_runtime: Optional[int] = None,
    excluded_ids: Optional[List[int]] = None,
    limit: int = 5
) -> List[Dict[str, Any]]:
    """Discover candidates matching criteria and filter out excluded titles."""
    excluded_set = set(excluded_ids or [])
    
    # Query popular / discover movies
    params: Dict[str, Any] = {
        "sort_by": "popularity.desc",
        "vote_count.gte": 150,
        "include_adult": False,
        "page": 1
    }
    if max_runtime:
        params["with_runtime.lte"] = max_runtime

    candidates_raw = _tmdb_get("/discover/movie", params).get("results", [])
    
    recommendations = []
    for item in candidates_raw:
        m_id = item.get("id")
        if m_id in excluded_set:
            continue

        details = get_movie_full_details(m_id)
        
        # Apply genre/keyword textual filter if provided
        if genre_keyword:
            text_corpus = (
                f"{details.get('title', '')} "
                f"{' '.join(details.get('genres', []))} "
                f"{' '.join(details.get('keywords', []))} "
                f"{details.get('overview', '')}"
            ).lower()
            if genre_keyword.lower() not in text_corpus:
                continue

        recommendations.append(details)
        if len(recommendations) >= limit:
            break

    return recommendations
