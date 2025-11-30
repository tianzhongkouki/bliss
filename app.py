import streamlit as st
import pandas as pd
import altair as alt
from pathlib import Path

# ---------------------------
# Streamlit 設定
# ---------------------------
st.set_page_config(
    page_title="Tumor Volume Viewer",
    page_icon="combination study",
    layout="wide"
)

st.title("マウス腫瘍体積データ可視化アプリ")
st.write("CSV（mouse_id / day / group / volume）を読み込み、可視化します。")

# ---------------------------
# CSV アップロード
# ---------------------------
uploaded_file = st.file_uploader("CSVファイルをアップロードしてください", type=["csv"])

if uploaded_file is not None:
    df = pd.read_csv(uploaded_file)
else:
    st.info("アップロードがないため、data/simulation.csv を読み込みます。")
    default_path = Path("data") / "simulation.csv"
    if default_path.exists():
        df = pd.read_csv(default_path)
    else:
        st.error("data/simulation.csv が見つかりません。CSV をアップロードしてください。")
        st.stop()

# 必須カラムチェック
required_cols = {"mouse_id", "day", "group", "volume"}
if not required_cols.issubset(df.columns):
    st.error("CSV に必要なカラム（mouse_id, day, group, volume）が含まれていません。")
    st.stop()

df["day"] = pd.to_numeric(df["day"], errors="coerce")
df["volume"] = pd.to_numeric(df["volume"], errors="coerce")
df = df.dropna(subset=["day", "volume"])

# ---------------------------
# サイドバー：フィルター & 閾値 & 群指定
# ---------------------------
st.sidebar.header("フィルター & 設定")

groups = sorted(df["group"].unique().tolist())
selected_groups = st.sidebar.multiselect("Group を選択（解析対象の群）", groups, default=groups)

filtered_df = df[df["group"].isin(selected_groups)]

mouse_ids = filtered_df["mouse_id"].unique().tolist()
selected_mouse = st.sidebar.multiselect("Mouse ID を選択（任意）", mouse_ids)

if selected_mouse:
    filtered_df = filtered_df[filtered_df["mouse_id"].isin(selected_mouse)]

# コントロール群 / DrugA / DrugB の指定
if groups:
    # コントロール群（Vehicle など）を選択
    default_ctrl_idx = groups.index("Vehicle") if "Vehicle" in groups else 0
    control_group = st.sidebar.selectbox("コントロール群（Vehicleなど）", groups, index=default_ctrl_idx)

    # Drug 群の候補（コントロール以外）
    drug_candidates = [g for g in groups if g != control_group] or groups

    drugA_group = st.sidebar.selectbox("Drug A 群", drug_candidates, index=0)
    # Drug B は Drug A と別の群をデフォルトに
    drugB_default_idx = 1 if len(drug_candidates) > 1 else 0
    drugB_group = st.sidebar.selectbox("Drug B 群", drug_candidates, index=drugB_default_idx)
else:
    control_group = None
    drugA_group = None
    drugB_group = None

# 人道的エンドポイントの閾値
endpoint_threshold = st.sidebar.number_input(
    "人道的エンドポイントとなる腫瘍体積",
    min_value=0.0,
    value=500.0,
    step=50.0,
    help="この腫瘍体積に初めて到達した個体について、その直前 day のデータを基準に TGI を算出します。"
)

# ---------------------------
# グループ別の平均腫瘍体積
# ---------------------------
st.subheader("グループ別の腫瘍体積推移（平均）")

if filtered_df.empty:
    st.warning("選択された条件に該当するデータがありません。")
else:
    group_mean = (
        filtered_df.groupby(["group", "day"])["volume"]
        .mean()
        .reset_index()
    )
    chart_group = (
        alt.Chart(group_mean)
        .mark_line(point=True)
        .encode(
            x="day:Q",
            y="volume:Q",
            color="group:N",
            tooltip=["group", "day", "volume"]
        )
        .properties(height=400)
    )
    st.altair_chart(chart_group, use_container_width=True)

# ---------------------------
# 群ごとの個体別腫瘍体積推移（2×2 レイアウト）
# ---------------------------
st.subheader("群ごとの個体別腫瘍体積推移（2×2レイアウト）")

if not filtered_df.empty:
    grp_list = sorted(filtered_df["group"].unique())

    # 2列ずつ表示
    for i in range(0, len(grp_list), 2):
        cols = st.columns(2)
        for j in range(2):
            idx = i + j
            if idx >= len(grp_list):
                break
            grp = grp_list[idx]
            with cols[j]:
                st.markdown(f"#### Group: {grp}")
                df_grp = filtered_df[filtered_df["group"] == grp]

                chart_mouse = (
                    alt.Chart(df_grp)
                    .mark_line(point=True)
                    .encode(
                        x="day:Q",
                        y="volume:Q",
                        color="mouse_id:N",
                        tooltip=["mouse_id", "day", "volume"]
                    )
                    .properties(height=300)
                )
                st.altair_chart(chart_mouse, use_container_width=True)

# ---------------------------
# 人道的エンドポイント到達個体の「最も早い直前 day」の全個体データ + TGI
# ---------------------------
st.subheader("人道的エンドポイント到達個体に対する **最も早い直前 day** の全個体データ + TGI")

tgi_by_group = {}
bliss_value = None

if filtered_df.empty:
    st.info("データがないため判定できません。")
else:
    grouped_mouse = filtered_df.sort_values(["mouse_id", "day"]).groupby("mouse_id")

    target_days = []

    # 各個体ごとに、threshold 到達前の day を求めてリストに格納
    for mouse_id, g in grouped_mouse:
        g_sorted = g.sort_values("day")
        reached = g_sorted["volume"] >= endpoint_threshold

        if reached.any():
            first_idx = reached.idxmax()
            pos = g_sorted.index.get_loc(first_idx)

            if isinstance(pos, int) and pos > 0:
                prev_day = g_sorted.iloc[pos - 1]["day"]
                target_days.append(prev_day)

    if target_days:
        # 一番早い day のみを採用
        earliest_day = min(target_days)

        st.markdown(
            f"人道的エンドポイント（腫瘍体積 >= **{endpoint_threshold}**）に"
            f" 初めて到達した個体のうち、**最も早く到達した個体の直前 day = {earliest_day}** における"
            " 全個体のデータです（TGI はコントロール群平均を基準）。"
        )
        day_df = filtered_df[filtered_df["day"] == earliest_day].copy()

        # --- TGI 計算 ---
        if control_group not in day_df["group"].unique():
            st.error(f"day = {earliest_day} にコントロール群（{control_group}）のデータがないため、TGI を計算できません。")
            st.dataframe(day_df, use_container_width=True)
        else:
            mean_by_group = day_df.groupby("group")["volume"].mean()
            mean_control = mean_by_group.get(control_group, None)

            if mean_control is None or mean_control <= 0:
                st.error("コントロール群の平均腫瘍体積が 0 以下のため、TGI を計算できません。")
                st.dataframe(day_df, use_container_width=True)
            else:
                # TGI(%) = (1 - treated / control) * 100
                tgi_by_group = {
                    grp: (1.0 - m / mean_control) * 100.0
                    for grp, m in mean_by_group.items()
                }

                day_df["TGI(%)"] = day_df["group"].map(tgi_by_group)
                st.dataframe(day_df, use_container_width=True)

                # ---------------------------
                # Bliss independence model
                # ---------------------------
                st.subheader("Bliss independence model による期待 TGI")

                if (drugA_group in tgi_by_group) and (drugB_group in tgi_by_group):
                    tgiA = tgi_by_group[drugA_group]
                    tgiB = tgi_by_group[drugB_group]

                    # TGI を 0–1 にスケールして効果 E とみなす
                    EA = tgiA / 100.0
                    EB = tgiB / 100.0

                    # Bliss independence: E_AB = EA + EB - EA * EB
                    E_bliss = EA + EB - EA * EB
                    bliss_value = E_bliss * 100.0  # % に戻す

                    st.markdown(
                        f"- コントロール群: **{control_group}**  (day = {earliest_day})  \n"
                        f"- Drug A 群: **{drugA_group}** → TGI = **{tgiA:.1f}%**  \n"
                        f"- Drug B 群: **{drugB_group}** → TGI = **{tgiB:.1f}%**  \n\n"
                        f"Bliss independence model による期待 TGI（Drug A + Drug B の理論値）は："
                        f" **{bliss_value:.1f}%** です。"
                    )
                else:
                    st.info(
                        "指定された Drug A / Drug B 群に対する TGI が計算できませんでした。\n"
                        f"（day = {earliest_day} に {drugA_group} または {drugB_group} のデータがない可能性があります）"
                    )

    else:
        st.info(f"腫瘍体積が {endpoint_threshold} に到達する個体はいませんでした。")


# ---------------------------
# Combination Index（CI） + Bootstrap 95%CI
# ---------------------------
st.subheader("Combination Index（CI） と 95%CI（Bootstrap）")

if ("Combo" not in day_df["group"].unique()) and ("A+B" not in day_df["group"].unique()):
    st.info("Combo 群（A+B）がデータに存在しないため、CI は計算できません。")
else:
    # Combo 群名の自動検出
    combo_group = None
    for cand in ["Combo", "A+B", "DrugAB", "AB"]:
        if cand in day_df["group"].unique():
            combo_group = cand
            break

    if combo_group is None:
        st.error("Combo（併用）群が見つかりません。group 名に Combo/A+B/DrugAB を使用してください。")
    else:
        # --- mean volume ---
        mean_by_group = day_df.groupby("group")["volume"].mean()

        if control_group not in mean_by_group:
            st.error("コントロール群が存在しないため CI を計算できません。")
        else:
            mean_ctrl = mean_by_group[control_group]
            mean_A    = mean_by_group.get(drugA_group, None)
            mean_B    = mean_by_group.get(drugB_group, None)
            mean_combo = mean_by_group.get(combo_group, None)

            if None in [mean_A, mean_B, mean_combo]:
                st.error("DrugA / DrugB / Combo のいずれかが day に存在しません。")
            else:
                # --- TGI ---
                TGI_A = (1 - mean_A / mean_ctrl)
                TGI_B = (1 - mean_B / mean_ctrl)
                TGI_combo = (1 - mean_combo / mean_ctrl)

                # --- Bliss expected ----
                E_bliss = TGI_A + TGI_B - TGI_A * TGI_B

                # --- Combination Index ---
                CI = E_bliss / TGI_combo

                st.markdown(f"""
                **Combination Index (CI)**  
                - Drug A TGI: **{TGI_A*100:.1f}%**  
                - Drug B TGI: **{TGI_B*100:.1f}%**  
                - Combo TGI: **{TGI_combo*100:.1f}%**  
                - Bliss expected TGI: **{E_bliss*100:.1f}%**  

                ▶ **Combination Index CI = {CI:.3f}**
                """)

                # ---------------------------
                # Bootstrap 95%CI
                # ---------------------------
                n_boot = st.sidebar.number_input(
                    "ブートストラップ回数（CI 95%CI 用）",
                    min_value=200,
                    max_value=100000,
                    step=200,
                    value=2000
                )

                import numpy as np

                # データを群ごとに分割
                df_ctrl  = day_df[day_df["group"] == control_group]["volume"].values
                df_A     = day_df[day_df["group"] == drugA_group]["volume"].values
                df_B     = day_df[day_df["group"] == drugB_group]["volume"].values
                df_combo = day_df[day_df["group"] == combo_group]["volume"].values

                CI_list = []

                for _ in range(int(n_boot)):
                    # ブートストラップ標本
                    boot_ctrl  = np.random.choice(df_ctrl,  size=len(df_ctrl),  replace=True)
                    boot_A     = np.random.choice(df_A,     size=len(df_A),     replace=True)
                    boot_B     = np.random.choice(df_B,     size=len(df_B),     replace=True)
                    boot_combo = np.random.choice(df_combo, size=len(df_combo), replace=True)

                    # 平均
                    m_ctrl  = boot_ctrl.mean()
                    m_A     = boot_A.mean()
                    m_B     = boot_B.mean()
                    m_combo = boot_combo.mean()

                    # TGI
                    tA = 1 - m_A / m_ctrl
                    tB = 1 - m_B / m_ctrl
                    tC = 1 - m_combo / m_ctrl

                    # Bliss effect
                    e_bliss = tA + tB - tA * tB

                    if tC > 0:
                        CI_list.append(e_bliss / tC)

                if len(CI_list) > 10:
                    CI_low  = np.percentile(CI_list, 2.5)
                    CI_high = np.percentile(CI_list, 97.5)

                    st.markdown(f"""
                    ### **Combination Index 95% CI（Bootstrap）**
                    - CI = **{CI:.3f}**
                    - 95% CI = **[{CI_low:.3f}, {CI_high:.3f}]**
                    """)
                else:
                    st.info("データ数が少ないため、ブートストラップ CI を計算できませんでした。")
