"""
Streamlit Web UI for AI Movie Night Planner.
Displays real-time group watchlists, member ratings, posters, and streaming availability.
"""

import streamlit as st
import pandas as pd
from lakebase import run_query

st.set_page_config(
    page_title="AI Movie Night Planner",
    page_icon="🎬",
    layout="wide"
)

st.title("🎬 AI Movie Night Planner Dashboard")
st.markdown("Live view of group watchlists, member ratings, and streaming availability synced with Lakebase.")

# --- Sidebar: Group Selector ---
try:
    groups = run_query("SELECT id, name FROM groups ORDER BY id ASC;")
except Exception as e:
    st.error(f"Failed to connect to Lakebase: {e}")
    groups = []

if not groups:
    st.info("No groups found. Run `python mcp_server/init_db.py` and `python mcp_server/test_movie.py` to initialize and seed data.")
    st.stop()

group_dict = {f"{g['name']} (ID: {g['id']})": g['id'] for g in groups}
selected_group_label = st.sidebar.selectbox("Select Movie Night Group", list(group_dict.keys()))
selected_group_id = group_dict[selected_group_label]

# --- Sidebar: Group Members Section ---
members = run_query(
    "SELECT user_email, joined_at FROM group_members WHERE group_id = %s ORDER BY joined_at ASC;",
    (selected_group_id,)
)
member_emails = [m['user_email'] for m in members]

st.sidebar.markdown("### 👥 Group Members")
if member_emails:
    for m in member_emails:
        st.sidebar.markdown(f"- **{m}**")
else:
    st.sidebar.write("No members in this group.")

# --- Main Content Tabs ---
tab_watchlist, tab_ratings, tab_recommendations = st.tabs([
    "📋 Group Watchlist", 
    "⭐ Member Ratings", 
    "🤖 Agent Recommendations"
])

# Tab 1: Group Watchlist
with tab_watchlist:
    st.subheader("Current Watchlist Queue")
    watchlist_sql = """
    SELECT w.status, w.added_by, w.added_at,
           m.tmdb_id, m.title, m.overview, m.genres, m.runtime,
           m.vote_average, m.poster_path, m.streaming_providers
    FROM watchlist_items w
    JOIN movies m ON w.tmdb_id = m.tmdb_id
    WHERE w.group_id = %s
    ORDER BY w.added_at DESC;
    """
    watchlist = run_query(watchlist_sql, (selected_group_id,))

    if not watchlist:
        st.write("No movies currently in the watchlist queue for this group.")
    else:
        for item in watchlist:
            col1, col2 = st.columns([1, 4])
            with col1:
                if item.get("poster_path"):
                    st.image(item["poster_path"], use_container_width=True)
                else:
                    st.write("*(No Poster Available)*")
            with col2:
                runtime_str = f"{item['runtime']} mins" if item.get('runtime') else "N/A"
                st.markdown(f"### {item['title']} ({runtime_str})")
                st.markdown(f"**TMDB Rating:** ⭐ {item.get('vote_average', 'N/A')}/10 | **Status:** `{item.get('status', 'queued')}`")
                
                genres = item.get("genres") or []
                st.markdown(f"**Genres:** {', '.join(genres) if genres else 'N/A'}")
                
                providers = item.get("streaming_providers") or []
                if providers:
                    st.markdown(f"**Streaming On:** {', '.join(providers)}")
                else:
                    st.markdown("**Streaming On:** *Not currently available on tracked subscription platforms*")
                
                st.write(item.get("overview", ""))
                st.caption(f"Added by: {item.get('added_by')} on {item.get('added_at')}")
            st.divider()

# Tab 2: Member Ratings
with tab_ratings:
    st.subheader("Group Member Ratings History")
    ratings_sql = """
    SELECT r.user_email, r.score, r.review, r.rated_at,
           m.title, m.poster_path
    FROM ratings r
    JOIN movies m ON r.tmdb_id = m.tmdb_id
    JOIN group_members gm ON r.user_email = gm.user_email
    WHERE gm.group_id = %s
    ORDER BY r.rated_at DESC;
    """
    ratings = run_query(ratings_sql, (selected_group_id,))

    if not ratings:
        st.write("No ratings recorded yet by members of this group.")
    else:
        df_ratings = pd.DataFrame(ratings)
        st.dataframe(
            df_ratings[["title", "user_email", "score", "review", "rated_at"]],
            use_container_width=True
        )

# Tab 3: Agent Recommendations
with tab_recommendations:
    st.subheader("Recent Agent Recommendation Logs")
    recs_sql = """
    SELECT prompt_query, agent_reasoning, created_at
    FROM recommendations
    WHERE group_id = %s
    ORDER BY created_at DESC
    LIMIT 10;
    """
    recs = run_query(recs_sql, (selected_group_id,))

    if not recs:
        st.write("No agent recommendations logged yet.")
    else:
        for r in recs:
            st.markdown(f"**Query:** *\"{r['prompt_query']}\"*")
            st.markdown(f"**Agent Reasoning:** {r['agent_reasoning']}")
            st.caption(f"Logged at: {r['created_at']}")
            st.divider()