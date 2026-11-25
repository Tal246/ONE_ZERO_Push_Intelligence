
import streamlit as st
import pandas as pd
import plotly.express as px
import re
from pathlib import Path

# --------------------------------------------------
# 1. הגדרות ועיצוב
# --------------------------------------------------

st.set_page_config(
    page_title="Push Intelligence | ONE ZERO",
    page_icon="📊",
    layout="wide"
)

st.markdown("""
<style>
    .block-container {
        direction: rtl;
        text-align: right;
        padding-top: 1.8rem;
    }
    h1, h2, h3, p, label {
        text-align: right;
    }
    [data-testid="stMetric"] {
        direction: rtl;
        text-align: right;
    }
    [data-testid="stMetricValue"] {
        direction: ltr;
        text-align: right;
    }
</style>
""", unsafe_allow_html=True)

st.title("Push Intelligence")
st.subheader("מנתחים ביצועים. מזהים הזדמנויות. משפרים קמפיינים.")
st.caption(
    "מערכת תומכת החלטה למנהלי שיווק | "
    "ניתוח ביצועי Push Notifications"
)

# --------------------------------------------------
# 2. זיהוי והתאמת עמודות
# --------------------------------------------------

COLUMN_ALIASES = {
    "campaign": ["קמפיין", "campaign name", "campaign"],
    "audience": ["קהל יעד", "target audience", "audience"],
    "variant": ["גרסה", "variant", "וריאציה"],
    "push_text": ["נוסח הפוש", "push text", "notification text"],
    "goal": ["יעד הקמפיין", "campaign goal", "goal"],
    "sent": ["נשלחו", "sent count", "sent", "messages sent"],
    "clicked": [
        "הקליקו (24 שעות)", "הקליקו", "clicked (24 hours)",
        "clicked", "clicks", "הקלקות"
    ],
    "completed": [
        "השלימו יעד (7 ימים)", "השלימו יעד",
        "completed goal (7 days)", "completed goal",
        "conversions", "completed", "השלמת יעד"
    ]
}

REQUIRED_COLUMNS = [
    "campaign", "variant", "sent", "clicked", "completed"
]


def normalize_columns(df):
    normalized = {}

    for col in df.columns:
        clean = str(col).strip().lower()

        for standard_name, aliases in COLUMN_ALIASES.items():
            alias_list = [str(x).strip().lower() for x in aliases]

            if clean == standard_name or clean in alias_list:
                normalized[col] = standard_name
                break

    df = df.rename(columns=normalized)

    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]

    if missing:
        raise ValueError(
            "לא נמצאו העמודות הנדרשות: " + ", ".join(missing)
        )

    return df


def prepare_data(df):
    df = normalize_columns(df.copy())

    for col in ["sent", "clicked", "completed"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df = df.dropna(
        subset=["campaign", "variant", "sent", "clicked", "completed"]
    )

    if df.empty:
        raise ValueError("לא נמצאו שורות תקינות לניתוח.")

    if (df["sent"] <= 0).any():
        raise ValueError("נמצאו שורות עם כמות שליחות שאינה חיובית.")

    if (df["clicked"] < 0).any() or (df["completed"] < 0).any():
        raise ValueError("נמצאו ערכים שליליים.")

    if (df["clicked"] > df["sent"]).any():
        raise ValueError("נמצאו יותר הקלקות משליחות.")

    if (df["completed"] > df["sent"]).any():
        raise ValueError("נמצאו יותר השלמות יעד משליחות.")

    df["CTR"] = df["clicked"] / df["sent"]
    df["Goal Rate"] = df["completed"] / df["sent"]

    return df


# --------------------------------------------------
# 3. ניתוח מאפייני נוסח
# --------------------------------------------------

CTA_WORDS = [
    "לחצו", "לחץ", "לחצי", "להיכנס", "היכנסו",
    "להורדה", "להוריד", "בדקו", "בדוק", "בדקי",
    "עדכנו", "עדכן", "מלאו", "מלא", "צפו",
    "עברו", "הצטרפו", "התחילו", "הפיקו",
    "פתחו", "לצפייה", "להעביר", "לפרטים",
    "לבדיקה", "כאן"
]


def analyze_copy(text):
    if pd.isna(text):
        text = ""

    text = str(text).strip()
    words = re.findall(r"\b[\w]+\b", text, flags=re.UNICODE)

    has_question = "?" in text or "？" in text
    has_exclamation = "!" in text

    has_emoji = any(
        0x1F300 <= ord(char) <= 0x1FAFF
        or 0x2600 <= ord(char) <= 0x27BF
        or 0x1F1E6 <= ord(char) <= 0x1F1FF
        for char in text
    )

    lower_text = text.lower()

    has_cta = any(
        re.search(
            r"(?<!\w)" + re.escape(word) + r"(?!\w)",
            lower_text
        )
        for word in CTA_WORDS
    )

    return {
        "push_text": text,
        "char_count": len(text),
        "word_count": len(words),
        "has_question": has_question,
        "has_exclamation": has_exclamation,
        "has_emoji": has_emoji,
        "has_cta": has_cta
    }


def build_copy_analysis(df):
    if "push_text" not in df.columns:
        return pd.DataFrame()

    copy_rows = (
        df.groupby(["campaign", "variant"], as_index=False)
        .agg({
            "push_text": "first",
            "sent": "sum",
            "clicked": "sum",
            "completed": "sum"
        })
    )

    features = copy_rows["push_text"].apply(analyze_copy)
    feature_df = pd.DataFrame(features.tolist())

    result = pd.concat(
        [copy_rows.drop(columns=["push_text"]), feature_df],
        axis=1
    )

    result["CTR"] = result["clicked"] / result["sent"]
    result["Goal Rate"] = result["completed"] / result["sent"]

    return result


def feature_label(value):
    return "כן" if value else "לא"


# --------------------------------------------------
# 4. טעינת קובץ
# --------------------------------------------------

st.sidebar.header("ניהול נתונים")

uploaded_file = st.sidebar.file_uploader(
    "העלאת קובץ נתונים",
    type=["xlsx", "xls", "csv"]
)

default_file = Path("data/ONE_ZERO_Push_data_80_Rows.xlsx")

try:
    if uploaded_file is not None:
        if uploaded_file.name.lower().endswith(".csv"):
            raw_data = pd.read_csv(uploaded_file)
        else:
            raw_data = pd.read_excel(uploaded_file)

        data_source = uploaded_file.name

    elif default_file.exists():
        raw_data = pd.read_excel(default_file)
        data_source = default_file.name

    else:
        st.info("יש להעלות קובץ Excel או CSV כדי להתחיל.")
        st.stop()

    df = prepare_data(raw_data)
    copy_analysis = build_copy_analysis(df)

except Exception as error:
    st.error(f"לא ניתן לטעון את הנתונים: {error}")
    st.stop()

st.sidebar.success(f"הנתונים נטענו: {data_source}")
st.sidebar.caption(f"{len(df):,} רשומות תקינות")

# --------------------------------------------------
# 5. חישוב נתונים מרכזיים
# --------------------------------------------------

total_sent = df["sent"].sum()
total_clicked = df["clicked"].sum()
total_completed = df["completed"].sum()

overall_ctr = total_clicked / total_sent
overall_goal_rate = total_completed / total_sent

grouped = (
    df.groupby(["campaign", "variant"], as_index=False)
    .agg({
        "sent": "sum",
        "clicked": "sum",
        "completed": "sum"
    })
)

grouped["CTR"] = grouped["clicked"] / grouped["sent"]
grouped["Goal Rate"] = grouped["completed"] / grouped["sent"]

campaign_count = df["campaign"].nunique()

st.header("תמונת מצב כללית")

col1, col2, col3, col4 = st.columns(4)

col1.metric("הודעות שנשלחו", f"{total_sent:,.0f}")
col2.metric("הקלקות", f"{total_clicked:,.0f}")
col3.metric("שיעור הקלקה (CTR)", f"{overall_ctr:.1%}")
col4.metric("שיעור השלמת יעד", f"{overall_goal_rate:.1%}")

st.caption(
    f"הניתוח מבוסס על {len(df):,} רשומות, "
    f"{campaign_count} קמפיינים ו-{df['variant'].nunique()} וריאציות."
)

st.divider()

# --------------------------------------------------
# 6. סיכום מנהלים
# --------------------------------------------------

st.header("סיכום מנהלים")

leaders = (
    grouped.sort_values(
        ["campaign", "Goal Rate", "CTR"],
        ascending=[True, False, False]
    )
    .groupby("campaign", as_index=False)
    .first()
)

multi_variant_campaigns = grouped.groupby("campaign")["variant"].nunique()
comparable_count = int((multi_variant_campaigns >= 2).sum())

mismatch_count = 0

for campaign in grouped["campaign"].unique():
    subset = grouped[grouped["campaign"] == campaign]

    if len(subset) < 2:
        continue

    ctr_winner = subset.loc[subset["CTR"].idxmax(), "variant"]
    goal_winner = subset.loc[subset["Goal Rate"].idxmax(), "variant"]

    if ctr_winner != goal_winner:
        mismatch_count += 1

summary1, summary2, summary3 = st.columns(3)

summary1.metric("קמפיינים עם אפשרות להשוואה", f"{comparable_count}")
summary2.metric("פער בין מובילי המדדים", f"{mismatch_count}")
summary3.metric("שיעור השלמת יעד כולל", f"{overall_goal_rate:.1%}")

st.info(
    f"ב-{comparable_count} קמפיינים קיימות לפחות שתי וריאציות להשוואה. "
    f"ב-{mismatch_count} מהם מובילת ההקלקות שונה ממובילת השלמת היעד. "
    "מומלץ לבחון מקרים אלה לעומק ולא להסתמך על CTR בלבד."
)

st.divider()

# --------------------------------------------------
# 7. בחירת קמפיין
# --------------------------------------------------

st.header("ניתוח קמפיין")

campaigns = sorted(df["campaign"].astype(str).unique())

selected_campaign = st.selectbox(
    "בחירת קמפיין לניתוח",
    campaigns
)

campaign_data = df[
    df["campaign"].astype(str) == selected_campaign
].copy()

comparison = grouped[
    grouped["campaign"].astype(str) == selected_campaign
].copy()

if "goal" in campaign_data.columns:
    goals = campaign_data["goal"].dropna().astype(str).unique()
    if len(goals) > 0:
        st.markdown(f"**מטרת הקמפיין:** {goals[0]}")

if "audience" in campaign_data.columns:
    audiences = campaign_data["audience"].dropna().astype(str).unique()
    if len(audiences) > 0:
        st.markdown(f"**קהל יעד:** {audiences[0]}")

st.markdown("**ביצועי הווריאציות בקמפיין**")

display_comparison = comparison.rename(columns={
    "variant": "וריאציה",
    "sent": "נשלחו",
    "clicked": "הקליקו",
    "completed": "השלימו יעד",
    "CTR": "שיעור הקלקה",
    "Goal Rate": "שיעור השלמת יעד"
})

st.dataframe(
    display_comparison[
        ["וריאציה", "נשלחו", "הקליקו", "השלימו יעד",
         "שיעור הקלקה", "שיעור השלמת יעד"]
    ],
    use_container_width=True,
    hide_index=True,
    column_config={
        "שיעור הקלקה": st.column_config.NumberColumn(format="percent"),
        "שיעור השלמת יעד": st.column_config.NumberColumn(format="percent")
    }
)

# --------------------------------------------------
# 8. גרפים להשוואת וריאציות
# --------------------------------------------------

st.subheader("השוואה ויזואלית בין וריאציות")

if len(comparison) >= 2:

    chart_data = comparison.copy()
    chart_data["variant"] = chart_data["variant"].astype(str)

    chart_col1, chart_col2 = st.columns(2)

    with chart_col1:
        fig_ctr = px.bar(
            chart_data,
            x="variant",
            y="CTR",
            text=chart_data["CTR"].map(lambda x: f"{x:.1%}"),
            title="שיעור הקלקה (CTR)",
            labels={"variant": "וריאציה", "CTR": "שיעור הקלקה"},
            color="variant"
        )

        fig_ctr.update_traces(textposition="outside")
        fig_ctr.update_layout(
            showlegend=False,
            yaxis_tickformat=".0%",
            yaxis_rangemode="tozero",
            yaxis_title="שיעור הקלקה",
            xaxis_title="וריאציה"
        )
        st.plotly_chart(fig_ctr, use_container_width=True)

    with chart_col2:
        fig_goal = px.bar(
            chart_data,
            x="variant",
            y="Goal Rate",
            text=chart_data["Goal Rate"].map(lambda x: f"{x:.1%}"),
            title="שיעור השלמת יעד",
            labels={"variant": "וריאציה", "Goal Rate": "שיעור השלמת יעד"},
            color="variant"
        )

        fig_goal.update_traces(textposition="outside")
        fig_goal.update_layout(
            showlegend=False,
            yaxis_tickformat=".0%",
            yaxis_rangemode="tozero",
            yaxis_title="שיעור השלמת יעד",
            xaxis_title="וריאציה"
        )
        st.plotly_chart(fig_goal, use_container_width=True)

else:
    st.info("בקמפיין זה קיימת וריאציה אחת בלבד, ולכן אין אפשרות להשוואה.")

st.divider()

# --------------------------------------------------
# 9. תובנות והמלצות לקמפיין הנבחר
# --------------------------------------------------

st.header("תובנות והמלצות לפעולה")

if len(comparison) >= 2:

    best_goal = comparison.loc[comparison["Goal Rate"].idxmax()]
    best_ctr = comparison.loc[comparison["CTR"].idxmax()]

    goal_gap = (
        best_goal["Goal Rate"] -
        comparison["Goal Rate"].min()
    )

    st.markdown(
        f"**הווריאציה המובילה בהשלמת יעד: {best_goal['variant']}**"
    )

    st.write(
        f"שיעור השלמת היעד שלה הוא **{best_goal['Goal Rate']:.1%}**."
    )

    st.write(
        f"הווריאציה המובילה בהקלקות היא **{best_ctr['variant']}**, "
        f"עם CTR של **{best_ctr['CTR']:.1%}**."
    )

    if best_goal["variant"] != best_ctr["variant"]:

        st.warning(
            "זוהה פער בין הווריאציה שמייצרת יותר הקלקות "
            "לבין זו שמייצרת יותר השלמות יעד."
        )

        st.markdown("**המלצה:**")
        st.write(
            f"לבחון מה בווריאציה {best_goal['variant']} "
            "עשוי לתמוך בהשלמת היעד, גם אם היא אינה מייצרת "
            "את מספר ההקלקות הגבוה ביותר. "
            "כדאי לבדוק את התאמת המסר לצורך של הלקוח "
            "ואת המשך המסע לאחר ההקלקה."
        )

    else:

        st.success("אותה וריאציה מובילה גם בהקלקות וגם בהשלמת יעד.")

        st.markdown("**המלצה:**")
        st.write(
            f"לבחון את מאפייני וריאציה {best_goal['variant']} "
            "ולבדוק אם ניתן ליישם עקרונות דומים בקמפיינים אחרים."
        )

    st.caption(
        f"הפער בין שיעור השלמת היעד הגבוה לנמוך בקמפיין: "
        f"{goal_gap * 100:.1f} נקודות אחוז."
    )

    st.markdown("**הנוסחים שנבדקו:**")

    if "push_text" in campaign_data.columns:
        texts = campaign_data[["variant", "push_text"]].drop_duplicates()

        for _, row in texts.iterrows():
            st.write(f"**וריאציה {row['variant']}:** {row['push_text']}")

else:
    st.info("אין מספיק וריאציות בקמפיין כדי להפיק השוואה או המלצה.")

# --------------------------------------------------
# 10. ניתוח חכם של נוסחי הפוש
# --------------------------------------------------

st.divider()
st.header("ניתוח חכם של נוסחי הפוש")

if copy_analysis.empty:

    st.info(
        "בקובץ שהועלה לא נמצאה עמודת נוסח פוש. "
        "ניתוח ביצועים זמין, אך לא ניתן לנתח את מאפייני המסרים."
    )

else:

    st.write(
        "ניתוח מאפייני המסרים מאפשר לזהות הבדלים בין וריאציות "
        "ולגבש השערות לניסויים שיווקיים נוספים."
    )

    selected_copy = copy_analysis[
        copy_analysis["campaign"].astype(str) == selected_campaign
    ].copy()

    if not selected_copy.empty:

        st.subheader("מאפייני הנוסחים בקמפיין הנבחר")

        feature_display = selected_copy[[
            "variant", "char_count", "word_count",
            "has_question", "has_emoji",
            "has_exclamation", "has_cta"
        ]].copy()

        feature_display = feature_display.rename(columns={
            "variant": "וריאציה",
            "char_count": "מספר תווים",
            "word_count": "מספר מילים",
            "has_question": "סימן שאלה",
            "has_emoji": "אימוג'י",
            "has_exclamation": "סימן קריאה",
            "has_cta": "הנעה לפעולה"
        })

        for col in [
            "סימן שאלה", "אימוג'י",
            "סימן קריאה", "הנעה לפעולה"
        ]:
            feature_display[col] = feature_display[col].map(feature_label)

        st.dataframe(
            feature_display,
            use_container_width=True,
            hide_index=True
        )

        st.subheader("מאפייני המסר מול ביצועי הווריאציות")

        feature_columns = [
            ("has_cta", "הנעה לפעולה"),
            ("has_question", "שימוש בשאלה"),
            ("has_emoji", "שימוש באימוג'י"),
            ("has_exclamation", "שימוש בסימן קריאה")
        ]

        for feature, label in feature_columns:

            yes_rows = selected_copy[selected_copy[feature] == True]
            no_rows = selected_copy[selected_copy[feature] == False]

            if not yes_rows.empty and not no_rows.empty:

                yes_sent = yes_rows["sent"].sum()
                no_sent = no_rows["sent"].sum()

                yes_ctr = yes_rows["clicked"].sum() / yes_sent
                no_ctr = no_rows["clicked"].sum() / no_sent

                yes_goal = yes_rows["completed"].sum() / yes_sent
                no_goal = no_rows["completed"].sum() / no_sent

                st.markdown(f"**{label}**")

                st.write(
                    f"עם המאפיין: CTR של {yes_ctr:.1%}, "
                    f"שיעור השלמת יעד של {yes_goal:.1%}."
                )

                st.write(
                    f"ללא המאפיין: CTR של {no_ctr:.1%}, "
                    f"שיעור השלמת יעד של {no_goal:.1%}."
                )

            else:
                st.caption(
                    f"בקמפיין הנבחר אין מספיק שונות במאפיין '{label}' "
                    "כדי להשוות בין נוסחים עם המאפיין ובלעדיו."
                )

        # הצעות לניסוי לפי הבדלים בפועל בין הווריאציות

        st.subheader("הזדמנויות לניסוי הבא")

        if len(selected_copy) >= 2:

            goal_winner_copy = selected_copy.loc[
                selected_copy["Goal Rate"].idxmax()
            ]

            ctr_winner_copy = selected_copy.loc[
                selected_copy["CTR"].idxmax()
            ]

            differences = []

            if goal_winner_copy["has_cta"] != ctr_winner_copy["has_cta"]:
                differences.append("נוכחות של הנעה לפעולה")

            if goal_winner_copy["has_question"] != ctr_winner_copy["has_question"]:
                differences.append("שימוש בשאלה")

            if goal_winner_copy["has_emoji"] != ctr_winner_copy["has_emoji"]:
                differences.append("שימוש באימוג'י")

            if goal_winner_copy["has_exclamation"] != ctr_winner_copy["has_exclamation"]:
                differences.append("שימוש בסימן קריאה")

            if differences:
                st.write(
                    f"וריאציה {goal_winner_copy['variant']} מובילה בהשלמת יעד, "
                    f"ואילו וריאציה {ctr_winner_copy['variant']} מובילה בהקלקות."
                )

                st.write(
                    "בין הנוסחים קיים הבדל במאפיינים הבאים: "
                    + ", ".join(differences) + "."
                )

                st.info(
                    "כיוון לניסוי: לבודד אחד מהמאפיינים השונים "
                    "בגרסה חדשה ולבדוק אם שינויו משפר את השלמת היעד "
                    "מבלי לפגוע בהקלקות."
                )

            else:
                st.info(
                    "לא נמצאו הבדלים במאפייני המסר שנבדקו בין "
                    "מובילת ההקלקות למובילת השלמת היעד. "
                    "אפשר להמשיך ולבדוק הבדלים בתוכן, בהבטחה השיווקית "
                    "ובבהירות המסר."
                )

        else:
            st.info("נדרשות לפחות שתי וריאציות כדי להציע ניסוי השוואתי.")

    # --------------------------------------------------
    # השוואה רוחבית בין מאפייני מסרים
    # --------------------------------------------------

    st.divider()
    st.subheader("מגמות רוחביות: מאפייני מסר וביצועים")

    feature_columns = [
        ("has_cta", "הנעה לפעולה"),
        ("has_question", "שימוש בשאלה"),
        ("has_emoji", "שימוש באימוג'י"),
        ("has_exclamation", "שימוש בסימן קריאה")
    ]

    trend_rows = []

    for feature, label in feature_columns:

        for value, group_label in [
            (True, "עם המאפיין"),
            (False, "ללא המאפיין")
        ]:

            subset = copy_analysis[copy_analysis[feature] == value]

            if subset.empty:
                continue

            sent_sum = subset["sent"].sum()

            trend_rows.append({
                "מאפיין": label,
                "קבוצה": group_label,
                "מספר וריאציות": len(subset),
                "מספר קמפיינים": subset["campaign"].nunique(),
                "CTR": subset["clicked"].sum() / sent_sum,
                "Goal Rate": subset["completed"].sum() / sent_sum
            })

    trend_df = pd.DataFrame(trend_rows)

    trend_display = trend_df.rename(columns={
        "מאפיין": "מאפיין מסר",
        "קבוצה": "סוג נוסח",
        "מספר וריאציות": "מספר וריאציות",
        "מספר קמפיינים": "מספר קמפיינים",
        "CTR": "שיעור הקלקה",
        "Goal Rate": "שיעור השלמת יעד"
    })

    # תיקון תצוגת האחוזים בטבלה הרוחבית

    st.dataframe(
        trend_display,
        use_container_width=True,
        hide_index=True,
        column_config={
            "שיעור הקלקה": st.column_config.NumberColumn(
                "שיעור הקלקה",
                format="percent"
            ),
            "שיעור השלמת יעד": st.column_config.NumberColumn(
                "שיעור השלמת יעד",
                format="percent"
            )
        }
    )

    st.caption(
        "המדדים מחושבים לפי סך השליחות בכל קבוצת נוסחים. "
        "הם מציגים קשר תיאורי בלבד: ייתכנו הבדלים בקהלים, "
        "במטרות הקמפיינים ובמאפיינים נוספים."
    )

# --------------------------------------------------
# 11. מבט רוחבי על כלל הקמפיינים
# --------------------------------------------------

st.divider()
st.header("מבט רוחבי: ביצועי הקמפיינים")

leaders_display = leaders.rename(columns={
    "campaign": "קמפיין",
    "variant": "וריאציה מובילה",
    "sent": "נשלחו",
    "completed": "השלימו יעד",
    "CTR": "שיעור הקלקה",
    "Goal Rate": "שיעור השלמת יעד"
})

st.dataframe(
    leaders_display[
        ["קמפיין", "וריאציה מובילה", "נשלחו",
         "השלימו יעד", "שיעור הקלקה", "שיעור השלמת יעד"]
    ].sort_values("שיעור השלמת יעד", ascending=False),
    use_container_width=True,
    hide_index=True,
    column_config={
        "שיעור הקלקה": st.column_config.NumberColumn(format="percent"),
        "שיעור השלמת יעד": st.column_config.NumberColumn(format="percent")
    }
)

# --------------------------------------------------
# 12. נתונים מקוריים ומגבלות
# --------------------------------------------------

st.divider()
st.header("נתונים, שקיפות ומגבלות")

with st.expander("צפייה בנתונים המקוריים"):
    st.dataframe(df, use_container_width=True, hide_index=True)

with st.expander("הנחות ומגבלות הניתוח"):
    st.markdown("""
    - CTR מחושב כמספר ההקלקות חלקי מספר ההודעות שנשלחו.
    - שיעור השלמת יעד מחושב כמספר השלמות היעד חלקי מספר ההודעות שנשלחו.
    - אורך המסר, מספר המילים, סימני שאלה, סימני קריאה, אימוג'י והנעה לפעולה מזוהים אוטומטית.
    - זיהוי הנעה לפעולה מבוסס על רשימת ביטויים מוגדרת מראש ואינו מבין בהכרח את ההקשר המלא של המשפט.
    - ההשוואה בין מאפייני מסרים לביצועים היא תיאורית ואינה מוכיחה סיבתיות.
    - ייתכנו הבדלים בין הקמפיינים בקהל, במטרה ובתנאי השליחה.
    - אין בקובץ מידע על הקצאה אקראית לקבוצות או מובהקות סטטיסטית.
    - הקלקות נמדדות בתוך 24 שעות והשלמות יעד בתוך 7 ימים.
    - אין להסיק מהנתונים לבדם שהקלקה מסוימת הובילה להשלמת יעד.
    - מומלץ לאמת מגמות בניסויים נוספים לפני קבלת החלטות רחבות.
    """)

st.caption(
    "Push Intelligence | Prototype | "
    "Rule-based analysis based on uploaded campaign data"
)
