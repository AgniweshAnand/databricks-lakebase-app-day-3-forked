"""
FastMCP Server for AI Movie Night Planner.
Exposes MCP tools to Agent Bricks for group recommendations and watchlist management.
"""

import os
import logging
from typing import List, Optional, Dict, Any
from fastmcp import FastMCP
from lakebase import run_query, run_write
import tmdb

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("movie-mcp-server")

# Initialize FastMCP Server
mcp = FastMCP("Movie Night Planner Server")


def initialize_database():
    """Initialize database schema on startup if tables don't exist."""
    try:
        from init_db import init_database
        logger.info("Checking database schema...")
        init_database()
        logger.info("✓ Database schema ready")
    except Exception as e:
        logger.warning(f"Database initialization skipped or failed: {e}")


def ensure_user_exists(email: str) -> None:
    """Create user if they don't exist."""
    try:
        sql = """
        INSERT INTO users (email, display_name)
        VALUES (%s, %s)
        ON CONFLICT (email) DO NOTHING;
        """
        # Extract display name from email (before @)
        display_name = email.split('@')[0]
        run_write(sql, (email, display_name))
    except Exception as e:
        logger.warning(f"Failed to ensure user exists: {e}")


def ensure_group_exists(group_id: int, created_by_email: str) -> None:
    """Create group if it doesn't exist."""
    try:
        # First ensure the user exists
        ensure_user_exists(created_by_email)
        
        # Check if group exists
        check_sql = "SELECT id FROM groups WHERE id = %s;"
        result = run_query(check_sql, (group_id,))
        
        if not result:
            # Create the group
            create_sql = """
            INSERT INTO groups (id, name, created_by)
            VALUES (%s, %s, %s)
            ON CONFLICT (id) DO NOTHING;
            """
            run_write(create_sql, (group_id, f"Group {group_id}", created_by_email))
            
            # Add creator as member
            member_sql = """
            INSERT INTO group_members (group_id, user_email)
            VALUES (%s, %s)
            ON CONFLICT (group_id, user_email) DO NOTHING;
            """
            run_write(member_sql, (group_id, created_by_email))
            logger.info(f"Created group {group_id} with member {created_by_email}")
    except Exception as e:
        logger.warning(f"Failed to ensure group exists: {e}")


@mcp.tool()
def search_movies_by_criteria(
    query: Optional[str] = None,
    year: Optional[int] = None,
    genre: Optional[str] = None,
    min_rating: float = 5.0,
    limit: int = 10
) -> Dict[str, Any]:
    """
    Search for movies using flexible criteria. Returns results even if exact criteria don't match.
    
    Args:
        query: Text keywords like "funny", "action", "romantic". Will search titles and descriptions.
        year: Preferred release year (e.g. 2024, 2025). Will also search nearby years if needed.
        genre: Genre like "comedy", "action", "thriller", "horror", "sci-fi", "drama", "romance".
        min_rating: Minimum TMDB rating (default: 5.0). Lower = more results.
        limit: Maximum results (default: 10).
    
    Returns:
        Dict with movies including title, year, rating, genres, cast, streaming, and overview.
    """
    try:
        # Map genre keywords to TMDB IDs
        genre_map = {
            "action": 28, "adventure": 12, "animation": 16, "comedy": 35,
            "crime": 80, "documentary": 99, "drama": 18, "family": 10751,
            "fantasy": 14, "history": 36, "horror": 27, "music": 10402,
            "mystery": 9648, "romance": 10749, "science fiction": 878,
            "sci-fi": 878, "thriller": 53, "war": 10752, "western": 37,
            "funny": 35, "romantic": 10749, "scary": 27, "suspense": 53
        }
        
        # Auto-detect genre from query
        detected_genre = None
        if not genre and query:
            query_lower = query.lower()
            for keyword, genre_id in genre_map.items():
                if keyword in query_lower:
                    genre = keyword
                    detected_genre = keyword
                    break
        
        # Get genre ID
        genre_id = None
        if genre:
            genre_lower = genre.lower()
            genre_id = genre_map.get(genre_lower)
        
        # Build search params - start with relaxed criteria
        params = {
            "sort_by": "popularity.desc",
            "include_adult": False,
            "vote_average.gte": min_rating,
            "page": 1
        }
        
        # For recent years, don't require many votes
        if year and year >= 2023:
            params["vote_count.gte"] = 5  # Very low threshold for new movies
        else:
            params["vote_count.gte"] = 20
        
        # Add genre filter if we have one
        if genre_id:
            params["with_genres"] = genre_id
        
        all_results = []
        
        # Strategy 1: Try exact year range if specified
        if year:
            year_range = [year, year-1, year-2, year+1]
            
            for try_year in year_range:
                if all_results:
                    break
                    
                params["primary_release_year"] = try_year
                
                try:
                    discover_data = tmdb._tmdb_get("/discover/movie", params)
                    candidates = discover_data.get("results", [])
                    logger.info(f"Year {try_year}: Found {len(candidates)} candidates")
                    
                    for item in candidates[:limit * 2]:
                        if len(all_results) >= limit:
                            break
                            
                        m_id = item.get("id")
                        if not m_id:
                            continue
                        
                        try:
                            details = tmdb.get_movie_full_details(m_id)
                            all_results.append({
                                "tmdb_id": details["tmdb_id"],
                                "title": details["title"],
                                "release_date": details.get("release_date", ""),
                                "year": details["release_date"][:4] if details.get("release_date") else "N/A",
                                "runtime": f"{details['runtime']} mins" if details.get("runtime") else "N/A",
                                "genres": details["genres"],
                                "vote_average": details.get("vote_average", 0),
                                "overview": details.get("overview", "")[:350] + "..." if len(details.get("overview", "")) > 350 else details.get("overview", ""),
                                "top_cast": details.get("cast", [])[:5],
                                "streaming_on": details.get("streaming_providers", [])
                            })
                        except Exception as e:
                            logger.warning(f"Error fetching movie {m_id}: {e}")
                            
                except Exception as e:
                    logger.warning(f"Error searching year {try_year}: {e}")
        
        # Strategy 2: If still no results, try broad genre search without year
        if not all_results and genre_id:
            logger.info("No results with year filter, trying broad genre search")
            params_broad = {
                "sort_by": "popularity.desc",
                "include_adult": False,
                "vote_count.gte": 50,
                "vote_average.gte": min_rating,
                "with_genres": genre_id,
                "primary_release_date.gte": "2020-01-01",  # Recent movies only
                "page": 1
            }
            
            try:
                discover_data = tmdb._tmdb_get("/discover/movie", params_broad)
                candidates = discover_data.get("results", [])
                logger.info(f"Broad search: Found {len(candidates)} candidates")
                
                for item in candidates[:limit]:
                    m_id = item.get("id")
                    if not m_id:
                        continue
                    
                    try:
                        details = tmdb.get_movie_full_details(m_id)
                        all_results.append({
                            "tmdb_id": details["tmdb_id"],
                            "title": details["title"],
                            "release_date": details.get("release_date", ""),
                            "year": details["release_date"][:4] if details.get("release_date") else "N/A",
                            "runtime": f"{details['runtime']} mins" if details.get("runtime") else "N/A",
                            "genres": details["genres"],
                            "vote_average": details.get("vote_average", 0),
                            "overview": details.get("overview", "")[:350] + "..." if len(details.get("overview", "")) > 350 else details.get("overview", ""),
                            "top_cast": details.get("cast", [])[:5],
                            "streaming_on": details.get("streaming_providers", [])
                        })
                    except Exception as e:
                        logger.warning(f"Error fetching movie {m_id}: {e}")
                        
            except Exception as e:
                logger.error(f"Broad search failed: {e}")
        
        # Strategy 3: If STILL no results, just search by query text
        if not all_results and query:
            logger.info(f"Trying text search for: {query}")
            try:
                search_results = tmdb.search_tmdb_movies(query)
                logger.info(f"Text search found {len(search_results)} results")
                
                for item in search_results[:limit]:
                    m_id = item.get("id")
                    if not m_id:
                        continue
                    
                    try:
                        details = tmdb.get_movie_full_details(m_id)
                        all_results.append({
                            "tmdb_id": details["tmdb_id"],
                            "title": details["title"],
                            "release_date": details.get("release_date", ""),
                            "year": details["release_date"][:4] if details.get("release_date") else "N/A",
                            "runtime": f"{details['runtime']} mins" if details.get("runtime") else "N/A",
                            "genres": details["genres"],
                            "vote_average": details.get("vote_average", 0),
                            "overview": details.get("overview", "")[:350] + "..." if len(details.get("overview", "")) > 350 else details.get("overview", ""),
                            "top_cast": details.get("cast", [])[:5],
                            "streaming_on": details.get("streaming_providers", [])
                        })
                    except Exception as e:
                        logger.warning(f"Error fetching movie {m_id}: {e}")
                        
            except Exception as e:
                logger.error(f"Text search failed: {e}")
        
        # Sort by rating and year
        all_results.sort(key=lambda x: (x.get("vote_average", 0), x.get("year", "")), reverse=True)
        
        return {
            "status": "success",
            "search_criteria": {
                "query": query,
                "year": year,
                "genre": genre,
                "detected_genre": detected_genre,
                "genre_id": genre_id,
                "min_rating": min_rating
            },
            "count": len(all_results),
            "movies": all_results[:limit]
        }
        
    except Exception as e:
        logger.exception("Search failed completely")
        return {
            "status": "error",
            "message": str(e),
            "count": 0,
            "movies": []
        }


@mcp.tool()
def search_and_explain_movies(query: str, limit: int = 5) -> Dict[str, Any]:
    """
    Simple text search for movies by title or keywords. Good for finding specific movies.
    
    Args:
        query: Search query (e.g. 'Galaxy Quest', 'Deadpool', 'funny movies').
        limit: Number of results (default: 5).
    """
    try:
        raw_results = tmdb.search_tmdb_movies(query=query)
        results = []
        
        for item in raw_results[:limit]:
            m_id = item.get("id")
            try:
                details = tmdb.get_movie_full_details(m_id)
                results.append({
                    "tmdb_id": details["tmdb_id"],
                    "title": details["title"],
                    "release_date": details.get("release_date", ""),
                    "year": details["release_date"][:4] if details.get("release_date") else "N/A",
                    "runtime": f"{details['runtime']} mins" if details.get("runtime") else "N/A",
                    "genres": details["genres"],
                    "vote_average": details.get("vote_average", 0),
                    "overview": details.get("overview", "")[:350] + "..." if len(details.get("overview", "")) > 350 else details.get("overview", ""),
                    "top_cast": details.get("cast", [])[:5],
                    "streaming_on": details.get("streaming_providers", [])
                })
            except Exception as e:
                logger.warning(f"Error resolving movie ID {m_id}: {e}")

        return {
            "status": "success",
            "query": query,
            "count": len(results),
            "movies": results
        }
    except Exception as e:
        logger.exception("Search failed")
        return {"status": "error", "message": str(e), "movies": []}


@mcp.tool()
def get_movie_details(tmdb_id: int) -> Dict[str, Any]:
    """Get full details for a specific movie by TMDB ID."""
    try:
        details = tmdb.get_movie_full_details(tmdb_id)
        return {"status": "success", "movie": details}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@mcp.tool()
def recommend_for_group(
    group_id: int,
    query_description: Optional[str] = None,
    max_runtime: Optional[int] = None,
    limit: int = 3
) -> Dict[str, Any]:
    """Recommend movies for a group based on their watch history and preferences."""
    try:
        members_sql = "SELECT user_email FROM group_members WHERE group_id = %s;"
        members = [row["user_email"] for row in run_query(members_sql, (group_id,))]
        excluded_ids = tmdb.get_group_excluded_movies(group_id)
        candidates = tmdb.discover_and_filter(
            genre_keyword=query_description,
            max_runtime=max_runtime,
            excluded_ids=excluded_ids,
            limit=limit
        )
        rec_ids = [c["tmdb_id"] for c in candidates]
        log_sql = """
        INSERT INTO recommendations (group_id, prompt_query, recommended_tmdb_ids, agent_reasoning)
        VALUES (%s, %s, %s, %s);
        """
        run_write(log_sql, (
            group_id,
            query_description or "General",
            rec_ids,
            f"Recommended {len(candidates)} titles."
        ))
        return {
            "status": "success",
            "group_id": group_id,
            "group_members": members,
            "excluded_movie_count": len(excluded_ids),
            "recommendations": candidates
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


@mcp.tool()
def add_to_group_watchlist(group_id: int, tmdb_id: int, added_by_email: str) -> Dict[str, Any]:
    """
    Add a movie to group watchlist. Automatically creates the group and user if they don't exist.
    
    Args:
        group_id: Target group ID (will be created if doesn't exist).
        tmdb_id: TMDB ID of the movie to add.
        added_by_email: Email of the user adding the movie (will be created if doesn't exist).
    
    Returns:
        Dict with status and confirmation message.
    """
    try:
        # Ensure group and user exist
        ensure_group_exists(group_id, added_by_email)
        
        # Get movie details first
        movie = tmdb.get_movie_full_details(tmdb_id)
        
        # Add to watchlist
        sql = """
        INSERT INTO watchlist_items (group_id, tmdb_id, added_by, status)
        VALUES (%s, %s, %s, 'queued')
        ON CONFLICT (group_id, tmdb_id) DO UPDATE SET status = 'queued';
        """
        run_write(sql, (group_id, tmdb_id, added_by_email))
        
        return {
            "status": "success",
            "message": f"✓ Added '{movie.get('title')}' to Group {group_id} watchlist",
            "movie": {
                "title": movie.get("title"),
                "year": movie.get("release_date", "")[:4] if movie.get("release_date") else "N/A",
                "genres": movie.get("genres", []),
                "rating": movie.get("vote_average")
            }
        }
    except Exception as e:
        logger.exception("Failed to add to watchlist")
        return {"status": "error", "message": str(e)}


@mcp.tool()
def record_movie_rating(user_email: str, tmdb_id: int, score: int, review: Optional[str] = None) -> Dict[str, Any]:
    """
    Record a user's rating for a movie. Auto-creates user if they don't exist.
    
    Args:
        user_email: User's email address.
        tmdb_id: TMDB ID of the movie.
        score: Rating from 1 (terrible) to 10 (masterpiece).
        review: Optional review text.
    """
    if score < 1 or score > 10:
        return {"status": "error", "message": "Score must be between 1 and 10"}
        
    try:
        # Ensure user exists
        ensure_user_exists(user_email)
        
        # Get movie details
        movie = tmdb.get_movie_full_details(tmdb_id)
        
        # Record rating
        sql = """
        INSERT INTO ratings (user_email, tmdb_id, score, review)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (user_email, tmdb_id) DO UPDATE SET
            score = EXCLUDED.score, review = EXCLUDED.review, rated_at = NOW();
        """
        run_write(sql, (user_email, tmdb_id, score, review))
        
        return {
            "status": "success",
            "message": f"✓ Rated '{movie.get('title')}' {score}/10"
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


@mcp.tool()
def compare_movies(tmdb_ids: List[int]) -> Dict[str, Any]:
    """Compare multiple movies side-by-side."""
    comparisons = []
    for m_id in tmdb_ids:
        try:
            details = tmdb.get_movie_full_details(m_id)
            comparisons.append({
                "tmdb_id": details["tmdb_id"],
                "title": details["title"],
                "runtime": f"{details.get('runtime')} mins",
                "vote_average": details.get("vote_average"),
                "genres": details.get("genres", []),
                "top_cast": details.get("cast", [])[:3],
                "streaming_providers": details.get("streaming_providers", [])
            })
        except Exception as e:
            logger.warning(f"Error fetching movie {m_id}: {e}")
    return {"status": "success", "comparison_count": len(comparisons), "movies": comparisons}


if __name__ == "__main__":
    # Initialize database on startup
    initialize_database()
    
    port = int(os.getenv("DATABRICKS_APP_PORT", os.getenv("PORT", 8000)))
    mcp.run(transport="http", host="0.0.0.0", port=port)
