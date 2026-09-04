"""
End-to-End Test Suite for AI Movie Night Planner.
Tests TMDB API client, Lakebase operations, and group recommendation filters.
"""

import sys
import logging
from lakebase import run_query, run_write
import tmdb
from movie_mcp_server import (
    search_and_explain_movies,
    get_movie_details,
    recommend_for_group,
    add_to_group_watchlist,
    record_movie_rating,
    compare_movies,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("test-movie")


def test_tmdb_search():
    logger.info("--- Testing TMDB Search & Details ---")
    results = search_and_explain_movies(query="Inception", limit=2)
    assert results["status"] == "success", "Search failed"
    assert len(results["movies"]) > 0, "No movies returned"
    
    first_movie = results["movies"][0]
    logger.info(f"✓ Found: {first_movie['title']} ({first_movie['runtime']})")
    logger.info(f"  Streaming on: {first_movie['streaming_on']}")
    return first_movie["tmdb_id"]


def test_lakebase_group_flow(tmdb_id: int):
    logger.info("\n--- Testing Group Flow & Exclusions ---")
    
    # 1. Setup mock user and group
    run_write("INSERT INTO users (email, display_name) VALUES (%s, %s) ON CONFLICT DO NOTHING;", 
              ("alex@example.com", "Alex"))
    run_write("INSERT INTO users (email, display_name) VALUES (%s, %s) ON CONFLICT DO NOTHING;", 
              ("sam@example.com", "Sam"))
    
    # Create or get group
    group_rows = run_query("SELECT id FROM groups WHERE name = %s LIMIT 1;", ("Friday Movie Night",))
    if not group_rows:
        run_write("INSERT INTO groups (name, created_by) VALUES (%s, %s);", 
                  ("Friday Movie Night", "alex@example.com"))
        group_rows = run_query("SELECT id FROM groups WHERE name = %s LIMIT 1;", ("Friday Movie Night",))
    group_id = group_rows[0]["id"]

    # Add members
    run_write("INSERT INTO group_members (group_id, user_email) VALUES (%s, %s) ON CONFLICT DO NOTHING;", 
              (group_id, "alex@example.com"))
    run_write("INSERT INTO group_members (group_id, user_email) VALUES (%s, %s) ON CONFLICT DO NOTHING;", 
              (group_id, "sam@example.com"))

    # 2. Add movie to watchlist
    add_res = add_to_group_watchlist(group_id=group_id, tmdb_id=tmdb_id, added_by_email="alex@example.com")
    assert add_res["status"] == "success", "Failed adding to watchlist"
    logger.info(f"✓ Added movie {tmdb_id} to group {group_id} watchlist")

    # 3. Test rating entry (Disliked movie: score 4/10)
    rate_res = record_movie_rating(user_email="sam@example.com", tmdb_id=tmdb_id, score=4, review="Too confusing.")
    assert rate_res["status"] == "success", "Failed recording rating"
    logger.info(f"✓ Recorded low rating (4/10) for movie {tmdb_id}")

    # 4. Verify exclusions filter
    excluded = tmdb.get_group_excluded_movies(group_id)
    assert tmdb_id in excluded, "Excluded list did not capture watched/disliked movie"
    logger.info(f"✓ Excluded list accurately contains ID {tmdb_id}")

    # 5. Test group recommendation
    rec_res = recommend_for_group(group_id=group_id, query_description="Sci-Fi", max_runtime=130, limit=2)
    assert rec_res["status"] == "success", "Group recommendation failed"
    rec_ids = [m["tmdb_id"] for m in rec_res["recommendations"]]
    assert tmdb_id not in rec_ids, "Recommendation returned an excluded movie!"
    logger.info(f"✓ Generated {len(rec_res['recommendations'])} clean recommendations respecting group filters.")


def test_movie_comparison(tmdb_id: int):
    logger.info("\n--- Testing Movie Comparison ---")
    comp_res = compare_movies(tmdb_ids=[tmdb_id, 27205]) # Inception + Inception-adjacent
    assert comp_res["status"] == "success"
    logger.info(f"✓ Successfully compared {len(comp_res['movies'])} movies side-by-side.")


if __name__ == "__main__":
    try:
        sample_id = test_tmdb_search()
        test_lakebase_group_flow(sample_id)
        test_movie_comparison(sample_id)
        print("\nAll integration and database tests passed successfully!")
    except Exception as e:
        logger.error(f"Test suite encountered an error: {e}", exc_info=True)
        sys.exit(1)