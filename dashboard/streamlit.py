import ast
import sys
from pathlib import Path

import altair as alt
import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns
import streamlit as st
from sklearn.feature_extraction.text import TfidfVectorizer

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from utils.postgres import get_postgres_connection

st.set_page_config(
    page_title="Analytics Dashboard",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="collapsed",
)


@st.cache_data
def preprocess_menu(menu_df: pd.DataFrame) -> pd.DataFrame:
    menu_df = menu_df.copy()
    menu_df["menu"] = menu_df["menu"].apply(lambda item: ast.literal_eval(item))
    menu_df = menu_df.explode("menu").dropna(subset=["menu"])

    menu_df["food_name"] = menu_df["menu"].apply(lambda item: item["name"])
    menu_df["food_name"] = menu_df["food_name"].str.strip().str.lower()
    menu_df["food_price"] = menu_df["menu"].apply(lambda item: item["price"])

    return menu_df.drop(columns="menu")


@st.cache_data
def process_tfidf(df: pd.DataFrame, ngram: int) -> pd.DataFrame:
    df = df.copy()
    df["food_name"] = df["food_name"].str.strip().str.lower()
    food_names = df["food_name"].values

    vectorizer = TfidfVectorizer(analyzer="word", ngram_range=(ngram, ngram))
    tfidf_matrix = vectorizer.fit_transform(food_names)
    feature_names = vectorizer.get_feature_names_out()
    tfidf_scores = tfidf_matrix.sum(axis=0).A1

    return pd.DataFrame({"keyword": feature_names, "score": tfidf_scores}).sort_values(
        by="score", ascending=False
    )


@st.cache_data
def get_data(query, _conn):
    return pd.read_sql(query, _conn)


@st.cache_resource
def get_connection():
    return get_postgres_connection()


conn = get_connection()

if conn is None:
    st.error("Unable to connect to PostgreSQL. Please check the connection settings.")
    st.stop()

restaurant_query = """
    SELECT *
    FROM restaurant
"""

menu_query = """
    SELECT restaurant_id, menu
    FROM menu
    WHERE is_current = TRUE;
"""

menu_df = get_data(menu_query, conn)
restaurant_df = get_data(restaurant_query, conn)

if menu_df.empty or restaurant_df.empty:
    st.warning("No data is available for the dashboard.")
    st.stop()

menu_df = preprocess_menu(menu_df)
df = restaurant_df.merge(menu_df, how="inner", on="restaurant_id")

if df.empty:
    st.warning("No merged data matches the current dataset.")
    st.stop()

district_options = sorted(df["district"].dropna().unique().tolist())
category_options = sorted(df["category"].dropna().unique().tolist())

filtered_df = df.copy()

with st.sidebar:
    st.title("🏙️ Dashboard")
    selected_districts = st.multiselect(
        "Filter by district",
        district_options,
        default=(
            ["Thành Phố Thủ Đức"]
            if "Thành Phố Thủ Đức" in district_options
            else district_options[:1]
        ),
    )
    if selected_districts:
        filtered_df = filtered_df[filtered_df["district"].isin(selected_districts)]

    selected_categories = st.multiselect(
        "Filter by restaurant type",
        category_options,
        default=(
            ["Ăn vặt/vỉa hè"]
            if "Ăn vặt/vỉa hè" in category_options
            else category_options[:1]
        ),
    )
    if selected_categories:
        filtered_df = filtered_df[filtered_df["category"].isin(selected_categories)]

    selected_ngram = st.slider("Select n-gram size", min_value=1, max_value=6, value=2)

if filtered_df.empty:
    st.warning("No data matches the selected filters.")
    st.stop()

col1, col2 = st.columns((3, 5), gap="medium")
top_keywords = None

with col1:
    tfidf_df = process_tfidf(filtered_df, selected_ngram)
    top_keywords = tfidf_df.head(10)

    if not top_keywords.empty:
        top_keywords_chart = (
            alt.Chart(top_keywords)
            .mark_bar()
            .encode(
                x=alt.X("score:Q", title="TF-IDF score"),
                y=alt.Y("keyword:N", title="Keyword", sort="-x"),
                color=alt.Color(
                    "score:Q",
                    scale=alt.Scale(range=["#2196F3", "#1976D2", "#0D47A1"]),
                    legend=None,
                ),
                tooltip=["keyword", "score"],
            )
            .properties(
                title="Top keywords in the menu",
                width=500,
                height=600,
            )
            .configure_title(fontSize=16, font="Arial", anchor="middle")
        )
        st.altair_chart(top_keywords_chart, use_container_width=True)

with col2:
    if top_keywords is not None and not top_keywords.empty:
        filtered_menus = []
        for keyword in top_keywords["keyword"]:
            keyword_menus = filtered_df[
                filtered_df["food_name"].str.contains(keyword, case=False, na=False)
            ].copy()
            keyword_menus["keyword"] = keyword
            filtered_menus.append(keyword_menus)

        if filtered_menus:
            keyword_price_df = pd.concat(filtered_menus, ignore_index=True)
        else:
            keyword_price_df = pd.DataFrame()

        if not keyword_price_df.empty:
            price_chart = (
                alt.Chart(keyword_price_df)
                .mark_boxplot()
                .encode(
                    x=alt.X("keyword:N", title="Keyword", sort="-x"),
                    y=alt.Y("food_price:Q", title="Price"),
                    tooltip=["keyword", "food_price"],
                    color=alt.Color(
                        "keyword:N",
                        scale=alt.Scale(range=["#2196F3", "#1976D2", "#0D47A1"]),
                        legend=None,
                    ),
                )
                .properties(
                    title="Price distribution of popular keywords",
                    width=800,
                    height=600,
                )
                .configure_title(fontSize=16, font="Arial", anchor="middle")
            )
            st.altair_chart(price_chart, use_container_width=True)
        else:
            st.warning("No dishes match the selected keywords.")

if top_keywords is not None and not top_keywords.empty:
    selected_keywords = st.multiselect(
        "Select keywords", top_keywords["keyword"].tolist()
    )

    if selected_keywords:
        keyword_pattern = "|".join(selected_keywords)
        filtered_menus = filtered_df[
            filtered_df["food_name"].str.contains(keyword_pattern, case=False, na=False)
        ]
        min_price = (
            int(filtered_menus["food_price"].min()) if not filtered_menus.empty else 0
        )
        max_price = (
            int(filtered_menus["food_price"].max())
            if not filtered_menus.empty
            else 500000
        )
    else:
        min_price = 0
        max_price = 500000

    min_price, max_price_slider = st.slider(
        "Select price range",
        min_value=min_price,
        max_value=max_price,
        value=(min_price, max_price),
        step=10000,
    )

    if selected_keywords:
        keyword_pattern = "|".join(selected_keywords)
        filtered_menus = filtered_df[
            filtered_df["food_name"].str.contains(keyword_pattern, case=False, na=False)
        ]
        filtered_menus = filtered_menus[
            (filtered_menus["food_price"] >= min_price)
            & (filtered_menus["food_price"] <= max_price_slider)
        ]

        if not filtered_menus.empty:
            filtered_menus_sorted = filtered_menus.sort_values(
                by="food_price", ascending=False
            ).reset_index(drop=True)
            st.write(
                f"Showing {len(filtered_menus_sorted)} dishes that match the filters:"
            )
            st.dataframe(filtered_menus_sorted[["food_name", "food_price"]])
        else:
            st.warning("No dishes match the filters.")
    else:
        st.warning("Please select at least one keyword and set a price range.")

    fig, ax = plt.subplots(figsize=(10, 6))
    sns.barplot(data=top_keywords, x="score", y="keyword", palette="Blues_r")
    ax.set_title("Top 10 keywords in the menu")
    ax.set_xlabel("TF-IDF score")
    ax.set_ylabel("Keyword")
    st.pyplot(fig)

    filtered_menus = []
    for keyword in top_keywords["keyword"]:
        keyword_menus = filtered_df[
            filtered_df["food_name"].str.contains(keyword, case=False, na=False)
        ].copy()
        keyword_menus["keyword"] = keyword
        filtered_menus.append(keyword_menus)

    if filtered_menus:
        keyword_price_df = pd.concat(filtered_menus, ignore_index=True)
        if not keyword_price_df.empty:
            fig, ax = plt.subplots(figsize=(14, 6))
            sns.boxplot(
                data=keyword_price_df,
                x="keyword",
                y="food_price",
                palette="Set3",
                showfliers=False,
                width=0.6,
            )
            ax.set_title("Price distribution of popular keywords")
            ax.set_xlabel("Keyword")
            ax.set_ylabel("Price (VND)")
            plt.xticks(rotation=45, ha="right")
            st.pyplot(fig)
        else:
            st.warning("No dishes match the selected keywords.")
    else:
        st.warning("No dishes match the selected keywords.")
else:
    st.warning("No data matches the current filters!")
