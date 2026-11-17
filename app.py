import streamlit as st
import pandas as pd
import numpy as np
from scipy import stats
from scipy.special import gammaln
import plotly.graph_objects as go
import re
from io import BytesIO

st.set_page_config(page_title="Mini-QAD Statistical Tool", layout="wide")
st.title("📊 Minitab Alternative: Boxplot, Capability & Probability Plot")

# --- ฟังก์ชันแปลงรหัสสี Hex เป็น RGBA ---
def hex_to_rgba(hex_color, opacity=0.85):
    hex_color = hex_color.lstrip('#')
    r, g, b = tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
    return f"rgba({r}, {g}, {b}, {opacity})"

# --- ฟังก์ชันดึงค่า Target / Tol จากชื่อคอลัมน์ เช่น B1_0.328 ± 0.0015 ---
def parse_spec_from_col(col_name):
    match = re.search(r"(\d+\.\d+)\s*[±\+\-]\s*(\d+\.\d+)", str(col_name))
    if match:
        target = float(match.group(1))
        tol = float(match.group(2))
        return round(target - tol, 6), target, round(target + tol, 6)
    return 0.3265, 0.3280, 0.3295

# --- ค่าคงที่ unbiasing ตาม Minitab ---
def c4(n):
    return np.sqrt(2.0 / (n - 1)) * np.exp(gammaln(n / 2.0) - gammaln((n - 1) / 2.0))

def calc_within(values, subgroup_size=1):
    """StDev(Within) แบบ Minitab
    - subgroup_size = 1 : Moving Range (MRbar / 1.128)
    - subgroup_size > 1 : Pooled StDev หารด้วย c4(d+1) (unbiasing constant)
    """
    x = np.asarray(values, dtype=float)
    if subgroup_size <= 1:
        mr = np.abs(np.diff(x))
        return mr.mean() / 1.128 if len(mr) > 0 else np.nan
    groups = [x[i:i + subgroup_size] for i in range(0, len(x), subgroup_size)]
    groups = [g for g in groups if len(g) > 1]
    if not groups:
        return np.nan
    ss = sum(((g - g.mean()) ** 2).sum() for g in groups)
    d = sum(len(g) - 1 for g in groups)
    return np.sqrt(ss / d) / c4(d + 1)

# --- 1. ส่วนจัดการข้อมูล (Upload หรือ ตารางเปล่าให้กรอก) ---
st.sidebar.header("📁 1. จัดการข้อมูล (Data Input)")
uploaded_file = st.sidebar.file_uploader("อัปโหลดไฟล์ Excel หรือ CSV", type=["xlsx", "csv"])

if "df" not in st.session_state:
    np.random.seed(42)
    df_init = pd.DataFrame({
        "B1_0.328 ± 0.0015": np.round(np.random.normal(0.3283, 0.00012, 32), 4),
        "B2_0.2845 ± 0.0015": np.round(np.random.normal(0.2843, 0.00012, 32), 4),
        "B3_0.2443 ± 0.0015": np.round(np.random.normal(0.2446, 0.00010, 32), 4),
        "B4_0.2008 ± 0.0015": np.round(np.random.normal(0.2010, 0.00011, 32), 4),
        "Cavity": [1]*16 + [2]*16
    })
    df_init.index = np.arange(1, len(df_init) + 1)
    df_init.index.name = "Row"
    st.session_state.df = df_init

if uploaded_file is not None:
    if st.sidebar.button("📥 โหลดข้อมูลจากไฟล์", use_container_width=True):
        if uploaded_file.name.endswith(".csv"):
            temp_df = pd.read_csv(uploaded_file)
        else:
            temp_df = pd.read_excel(uploaded_file)
        temp_df.index = np.arange(1, len(temp_df) + 1)
        temp_df.index.name = "Row"
        st.session_state.df = temp_df

if st.sidebar.button("🧹 ล้างตาราง (สร้างตารางเปล่า)", use_container_width=True):
    empty_df = pd.DataFrame({"B1_0.328 ± 0.0015": [np.nan]*10, "Cavity": [1]*10})
    empty_df.index = np.arange(1, len(empty_df) + 1)
    empty_df.index.name = "Row"
    st.session_state.df = empty_df

st.session_state.df.index = np.arange(1, len(st.session_state.df) + 1)
st.session_state.df.index.name = "Row"

with st.expander("📝 ตารางข้อมูล (มีเลขแถว Row ชัดเจน / ดับเบิลคลิกแก้ไขตัวเลข / ก๊อปวางจาก Excel ได้ทันที)", expanded=True):
    edited_df = st.data_editor(
        st.session_state.df,
        num_rows="dynamic",
        use_container_width=True,
        hide_index=False,
        column_config={
            "_index": st.column_config.NumberColumn("Row #", help="ลำดับแถวข้อมูล", format="%d")
        },
        key="data_editor"
    )
    edited_df.index = np.arange(1, len(edited_df) + 1)
    edited_df.index.name = "Row"

def to_excel(df):
    output = BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=True, sheet_name='Adjusted_Data')
    return output.getvalue()

st.sidebar.download_button(
    label="💾 เซฟตารางข้อมูลที่แก้แล้ว (.xlsx)",
    data=to_excel(edited_df),
    file_name="adjusted_data.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    use_container_width=True
)

# --- 2. ตั้งค่าการแสดงผล สี และ Spec Limits ---
st.sidebar.header("🎨 2. รูปแบบกราฟ & การแสดงผล")
view_mode = st.sidebar.radio(
    "โหมดการแสดงผลกราฟ:",
    ["🔍 Show ทีละกราฟ (ปรับ Spec ละเอียด)", "📜 Show ทั้งหมดทีเดียว (เลื่อนดูยาวๆ)"],
    index=0
)

col_c1, col_c2 = st.sidebar.columns(2)
with col_c1:
    box_fill_hex = st.color_picker("สีพื้น Boxplot", "#72A0E5")
with col_c2:
    box_line_hex = st.color_picker("สีเส้นขอบ", "#333333")

box_width_val = st.sidebar.slider("ความอ้วนของกล่อง Boxplot", 0.15, 0.70, 0.35, 0.05)
chart_height = st.sidebar.slider("ความสูงของกราฟ (px)", 380, 700, 480, 20)

st.sidebar.header("⚙️ 3. ตั้งค่าตัวแปรและ Spec")
all_cols = edited_df.columns.tolist()
num_cols = [c for c in all_cols if str(c).lower() != "cavity"]

group_col = st.sidebar.selectbox(
    "คอลัมน์แยกกลุ่ม (เช่น Cavity):",
    ["ไม่แยกกลุ่ม"] + all_cols,
    index=all_cols.index("Cavity") + 1 if "Cavity" in all_cols else 0
)

# ตัวเลือกกรองเฉพาะ Cavity สำหรับหน้า Capability & Probability Plot
cavity_filter = "ทั้งหมด (Combined)"
if group_col != "ไม่แยกกลุ่ม" and group_col in edited_df.columns:
    unique_cavities = ["ทั้งหมด (Combined)"] + list(edited_df[group_col].dropna().unique())
    cavity_filter = st.sidebar.selectbox("🎯 เลือก Cavity ที่ต้องการวิเคราะห์เดี่ยวๆ:", unique_cavities)

# Subgroup size (ตั้งให้เหมือนที่ใช้ใน Minitab > Capability Analysis)
subgroup_size = st.sidebar.number_input(
    "Subgroup size (เหมือนใน Minitab)", min_value=1, value=32, step=1,
    help="1 = ใช้ Moving Range, มากกว่า 1 = ใช้ Pooled StDev (หารด้วย c4)"
)

if "Show ทีละกราฟ" in view_mode:
    selected_col = st.sidebar.selectbox("เลือกพอยต์ที่ต้องการวิเคราะห์:", num_cols)
    auto_lsl, auto_target, auto_usl = parse_spec_from_col(selected_col)
    lsl_input = st.sidebar.number_input("LSL (Lower Spec)", value=auto_lsl, format="%.5f", step=0.0001)
    target_input = st.sidebar.number_input("Target (Nominal)", value=auto_target, format="%.5f", step=0.0001)
    usl_input = st.sidebar.number_input("USL (Upper Spec)", value=auto_usl, format="%.5f", step=0.0001)
    cols_to_plot = [selected_col]
else:
    cols_to_plot = st.sidebar.multiselect("เลือกพอยต์ที่จะแสดงทั้งหมด:", num_cols, default=num_cols)
    st.sidebar.caption("💡 ในโหมดแสดงทั้งหมด ระบบจะดึงค่า USL / Target / LSL จากชื่อหัวคอลัมน์ให้อัตโนมัติ")

# ฟังก์ชันกรองข้อมูลตาม Cavity ที่เลือก
def get_filtered_data(df_in, col_name, grp_col, cav_val):
    temp_df = df_in[[col_name] + ([grp_col] if grp_col != "ไม่แยกกลุ่ม" else [])].copy()
    temp_df["Row_ID"] = temp_df.index
    temp_df[col_name] = pd.to_numeric(temp_df[col_name], errors='coerce')
    temp_df = temp_df.dropna(subset=[col_name])

    if grp_col != "ไม่แยกกลุ่ม" and cav_val != "ทั้งหมด (Combined)":
        temp_df = temp_df[temp_df[grp_col].astype(str) == str(cav_val)]
    return temp_df

# ==============================================================================
# ฟังก์ชันสร้างกราฟ Boxplot
# ==============================================================================
def create_boxplot(df_in, col_name, grp_col, lsl, target, usl):
    valid_df = df_in[[col_name] + ([grp_col] if grp_col != "ไม่แยกกลุ่ม" else [])].dropna(subset=[col_name]).copy()
    valid_df["Row_ID"] = valid_df.index
    valid_df[col_name] = pd.to_numeric(valid_df[col_name], errors='coerce')
    valid_df = valid_df.dropna(subset=[col_name])

    fig = go.Figure()
    fill_rgba = hex_to_rgba(box_fill_hex, 0.85)

    if grp_col != "ไม่แยกกลุ่ม":
        for grp, grp_df in valid_df.groupby(grp_col):
            fig.add_trace(go.Box(
                x=[str(grp)] * len(grp_df),
                y=grp_df[col_name],
                name=f"{grp_col} {grp}",
                width=box_width_val,
                boxpoints='outliers',
                customdata=grp_df["Row_ID"],
                hovertemplate="<b>Row #: %{customdata}</b><br>Value: %{y:.5f}<extra></extra>",
                fillcolor=fill_rgba,
                line=dict(color=box_line_hex, width=1.5),
                marker=dict(color="red", size=7, symbol="asterisk")
            ))
    else:
        fig.add_trace(go.Box(
            x=[col_name] * len(valid_df),
            y=valid_df[col_name],
            name=col_name,
            width=box_width_val,
            boxpoints='outliers',
            customdata=valid_df["Row_ID"],
            hovertemplate="<b>Row #: %{customdata}</b><br>Value: %{y:.5f}<extra></extra>",
            fillcolor=fill_rgba,
            line=dict(color=box_line_hex, width=1.5),
            marker=dict(color="red", size=7, symbol="asterisk")
        ))

    fig.add_hline(y=usl, line_dash="dash", line_color="red", line_width=1.5,
                  annotation_text=f" {usl}", annotation_position="right", annotation_font_color="black")
    fig.add_hline(y=target, line_dash="dash", line_color="limegreen", line_width=1.5,
                  annotation_text=f" {target}", annotation_position="right", annotation_font_color="black")
    fig.add_hline(y=lsl, line_dash="dash", line_color="red", line_width=1.5,
                  annotation_text=f" {lsl}", annotation_position="right", annotation_font_color="black")

    y_min = min(lsl, valid_df[col_name].min()) if len(valid_df) > 0 else lsl
    y_max = max(usl, valid_df[col_name].max()) if len(valid_df) > 0 else usl
    span = y_max - y_min if y_max > y_min else 0.003

    fig.update_layout(
        title=dict(text=f"<b>Boxplot of {col_name}</b>", x=0.5, xanchor='center'),
        xaxis_title=grp_col if grp_col != "ไม่แยกกลุ่ม" else "",
        yaxis_title=col_name,
        yaxis=dict(
            range=[y_min - span * 0.12, y_max + span * 0.12],
            tickformat=".4f",
            gridcolor="#EAEAEA",
            zeroline=False
        ),
        xaxis=dict(type='category', gridcolor="#EAEAEA"),
        plot_bgcolor="white",
        paper_bgcolor="#E8E8E8",
        height=chart_height,
        margin=dict(l=70, r=70, t=55, b=50),
        showlegend=False
    )
    fig.update_xaxes(showline=True, linewidth=1, linecolor='#999999', mirror=True)
    fig.update_yaxes(showline=True, linewidth=1, linecolor='#999999', mirror=True)
    return fig

# ==============================================================================
# ฟังก์ชันสร้าง Capability (StDev Within / Cpm ปรับให้ตรง Minitab)
# ==============================================================================
def create_capability(df_in, col_name, grp_col, cav_val, lsl, target, usl, subgroup_size=1):
    valid_df = get_filtered_data(df_in, col_name, grp_col, cav_val)
    data = valid_df[col_name]
    n = len(data)
    if n == 0:
        return None, {}

    mean = data.mean()
    std_overall = data.std(ddof=1) if n > 1 else 0.0001

    # StDev(Within): ตามลำดับแถวของข้อมูลที่กรองแล้ว + Subgroup size ที่ผู้ใช้ตั้ง
    std_within = calc_within(data.values, subgroup_size)
    if not np.isfinite(std_within) or std_within <= 0:
        std_within = std_overall

    pp = (usl - lsl) / (6 * std_overall) if std_overall > 0 else 0
    ppl = (mean - lsl) / (3 * std_overall) if std_overall > 0 else 0
    ppu = (usl - mean) / (3 * std_overall) if std_overall > 0 else 0
    ppk = min(ppl, ppu)

    # Cpm ตามสูตร Minitab
    s_t = np.sqrt(((data - target) ** 2).sum() / n) if n > 0 else 0
    cpm = min(usl - target, target - lsl) / (3 * s_t) if s_t > 0 else 0

    cp = (usl - lsl) / (6 * std_within) if std_within > 0 else 0
    cpl = (mean - lsl) / (3 * std_within) if std_within > 0 else 0
    cpu = (usl - mean) / (3 * std_within) if std_within > 0 else 0
    cpk = min(cpl, cpu)

    obs_below = (data < lsl).sum() / n * 1000000 if n > 0 else 0
    obs_above = (data > usl).sum() / n * 1000000 if n > 0 else 0
    obs_total = obs_below + obs_above

    exp_below_ovr = stats.norm.cdf(lsl, mean, std_overall) * 1000000 if std_overall > 0 else 0
    exp_above_ovr = (1 - stats.norm.cdf(usl, mean, std_overall)) * 1000000 if std_overall > 0 else 0
    exp_total_ovr = exp_below_ovr + exp_above_ovr

    exp_below_wit = stats.norm.cdf(lsl, mean, std_within) * 1000000 if std_within > 0 else 0
    exp_above_wit = (1 - stats.norm.cdf(usl, mean, std_within)) * 1000000 if std_within > 0 else 0
    exp_total_wit = exp_below_wit + exp_above_wit

    # --- แกน X / Bin / Tick ให้หน้าตาเหมือน Minitab ---
    d_min, d_max = float(data.min()), float(data.max())
    ax_lo, ax_hi = min(lsl, d_min), max(usl, d_max)
    span = ax_hi - ax_lo if ax_hi > ax_lo else 0.003
    raw = span / 8
    mag = 10 ** np.floor(np.log10(raw))
    step = next((k * mag for k in (1, 2, 4, 5, 10) if k * mag >= raw * 0.999), 10 * mag)
    dec = max(0, int(np.ceil(-np.log10(step) - 1e-9)))
    t0 = np.ceil(ax_lo / step - 1e-9) * step
    ticks = np.arange(t0, ax_hi + step * 1e-6, step)

    # Bin กว้าง = ครึ่งหนึ่งของระยะ tick โดยให้จุดกึ่งกลาง bin ตรงกับ tick
    bin_w = step / 2
    b_start = t0 - bin_w / 2
    b_start += np.floor((d_min - b_start) / bin_w) * bin_w
    b_end = b_start + bin_w * (np.floor((d_max - b_start) / bin_w) + 1)

    x_grid = np.linspace(ax_lo, ax_hi, 400)

    fig = go.Figure()
    fig.add_trace(go.Histogram(
        x=data, histnorm='probability density', name='Data', showlegend=False,
        xbins=dict(start=b_start, end=b_end, size=bin_w),
        marker_color="#6C9BD2",
        marker_line=dict(color="#1F3E7A", width=0.8)
    ))
    if std_overall > 0:
        fig.add_trace(go.Scatter(x=x_grid, y=stats.norm.pdf(x_grid, mean, std_overall),
                                 mode='lines', name='Overall', line=dict(color='#8B1A1A', width=1.6)))
    if std_within > 0:
        fig.add_trace(go.Scatter(x=x_grid, y=stats.norm.pdf(x_grid, mean, std_within),
                                 mode='lines', name='Within', line=dict(color='#555555', width=1.6, dash='dash')))

    for xv, colr, lbl in [(lsl, "red", "LSL"), (target, "#333333", "Target"), (usl, "red", "USL")]:
        fig.add_vline(x=xv, line_dash="dot", line_color=colr, line_width=1.3)
        fig.add_annotation(x=xv, y=1, yref="paper", text=f"<b>{lbl}</b>", showarrow=False,
                           yanchor="bottom", font=dict(color=colr, size=12))

    title_suffix = f" (Cavity: {cav_val})" if cav_val != "ทั้งหมด (Combined)" else ""
    fig.update_layout(
        title=dict(text=f"<b>Process Capability Report for {col_name}{title_suffix}</b>", x=0.5, xanchor='center'),
        xaxis=dict(range=[ax_lo, ax_hi], tickmode='array', tickvals=ticks,
                   ticktext=[f"{t:.{dec}f}" for t in ticks], tickangle=-60, showgrid=False),
        yaxis=dict(showgrid=False, showticklabels=False, zeroline=False),
        bargap=0,
        legend=dict(x=1.01, y=1, xanchor='left', yanchor='top'),
        plot_bgcolor="white",
        paper_bgcolor="#E8E8E8",
        height=chart_height,
        margin=dict(l=40, r=90, t=75, b=70)
    )
    fig.update_xaxes(showline=True, linewidth=1, linecolor='#999999', mirror=True)
    fig.update_yaxes(showline=True, linewidth=1, linecolor='#999999', mirror=True)

    metrics = {
        "N": n, "Mean": mean, "StDev(Overall)": std_overall, "StDev(Within)": std_within,
        "Cp": cp, "Cpk": cpk, "Pp": pp, "Ppk": ppk, "Cpm": cpm,
        "Obs_Below": obs_below, "Obs_Above": obs_above, "Obs_Total": obs_total,
        "Exp_Ovr_Below": exp_below_ovr, "Exp_Ovr_Above": exp_above_ovr, "Exp_Ovr_Total": exp_total_ovr,
        "Exp_Wit_Below": exp_below_wit, "Exp_Wit_Above": exp_above_wit, "Exp_Wit_Total": exp_total_wit
    }
    return fig, metrics


# ==============================================================================
# ตารางวินิจฉัย: เทียบทุกวิธีที่เป็นไปได้กับค่า StDev(Within) / Cpm ใน Minitab
# ==============================================================================
def diagnose_capability(data, lsl, target, usl, subgroup_size=1):
    x = np.asarray(data, dtype=float)
    n = len(x)
    mean = x.mean()
    s = x.std(ddof=1)
    dx = np.diff(x)
    mr = np.abs(dx)

    cands = {
        "Average MR: MRbar/1.128 (w=2)": mr.mean() / 1.128,
        "Median MR: MR-median/0.954 (w=2)": np.median(mr) / 0.954,
        "Sqrt of MSSD: sqrt(Σ(Δx)²/(2(n-1)))": np.sqrt((dx ** 2).sum() / (2 * (n - 1))),
        "StDev Overall (s)": s,
    }
    if subgroup_size > 1:
        groups = [x[i:i + subgroup_size] for i in range(0, n, subgroup_size)]
        groups = [g for g in groups if len(g) > 1]
        if groups:
            ss = sum(((g - g.mean()) ** 2).sum() for g in groups)
            d = sum(len(g) - 1 for g in groups)
            sp = np.sqrt(ss / d)
            cands[f"Pooled StDev (size={subgroup_size}) ไม่หาร c4"] = sp
            cands[f"Pooled StDev (size={subgroup_size}) หาร c4(d+1)"] = sp / c4(d + 1)

    rows = []
    for name, sg in cands.items():
        if not np.isfinite(sg) or sg <= 0:
            continue
        cpl = (mean - lsl) / (3 * sg)
        cpu = (usl - mean) / (3 * sg)
        rows.append({
            "วิธีประมาณ σ": name, "StDev(Within)": f"{sg:.7f}",
            "Cp": f"{(usl - lsl) / (6 * sg):.4f}", "CPL": f"{cpl:.4f}",
            "CPU": f"{cpu:.4f}", "Cpk": f"{min(cpl, cpu):.4f}"
        })

    half = min(usl - target, target - lsl)
    ss_t = ((x - target) ** 2).sum()
    cpm_rows = []
    for name, val in {
        "min(USL-T, T-LSL) / (3·sqrt(Σ(x-T)²/(n-1)))": half / (3 * np.sqrt(ss_t / (n - 1))),
        "(USL-LSL) / (6·sqrt(s² + (mean-T)²))": (usl - lsl) / (6 * np.sqrt(s ** 2 + (mean - target) ** 2)),
        "(USL-LSL) / (6·sqrt(Σ(x-T)²/n))": (usl - lsl) / (6 * np.sqrt(ss_t / n)),
    }.items():
        cpm_rows.append({"สูตร Cpm": name, "Cpm": f"{val:.4f}"})
    return pd.DataFrame(rows), pd.DataFrame(cpm_rows)

# ==============================================================================
# ฟังก์ชันสร้าง Probability Plot (รองรับการกรอง Cavity แยกเดี่ยวๆ เช่นกัน)
# ==============================================================================
def create_prob_plot(df_in, col_name, grp_col, cav_val):
    valid_df = get_filtered_data(df_in, col_name, grp_col, cav_val)
    data = valid_df[col_name]
    n = len(data)
    if n < 3:
        return None, 1.0, 1.0, 0, 0, n

    mean = data.mean()
    std_overall = data.std(ddof=1) if n > 1 else 0.0001

    ad_res = stats.anderson(data, dist='norm')
    ad_stat = ad_res.statistic
    ad_star = ad_stat * (1 + 0.75/n + 2.25/(n**2))
    if ad_star >= 0.6:
        ad_pval = np.exp(1.2937 - 5.709*ad_star + 0.0186*(ad_star**2))
    elif ad_star >= 0.34:
        ad_pval = np.exp(0.9177 - 4.279*ad_star - 1.38*(ad_star**2))
    elif ad_star > 0.2:
        ad_pval = 1 - np.exp(-8.318 + 42.796*ad_star - 59.938*(ad_star**2))
    else:
        ad_pval = 1 - np.exp(-13.436 + 101.14*ad_star - 223.73*(ad_star**2))
    ad_pval = float(np.clip(ad_pval, 0.0001, 0.9999))

    sorted_df = valid_df.sort_values(by=col_name).reset_index(drop=True)
    probs = (np.arange(1, n + 1) - 0.3) / (n + 0.4) * 100
    z_scores = stats.norm.ppf(probs / 100.0)
    line_x = mean + z_scores * std_overall

    tick_probs = [0.1, 1, 5, 10, 20, 30, 40, 50, 60, 70, 80, 90, 95, 99, 99.9]
    tick_z = stats.norm.ppf(np.array(tick_probs) / 100.0)

    title_suffix = f" (Cavity: {cav_val})" if cav_val != "ทั้งหมด (Combined)" else ""
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=sorted_df[col_name], y=z_scores, mode='markers', name='Data',
        marker=dict(size=9, color=box_fill_hex, line=dict(width=1.2, color=box_line_hex)),
        customdata=np.stack((sorted_df["Row_ID"], probs, sorted_df[grp_col] if grp_col != "ไม่แยกกลุ่ม" else ["-"]*n), axis=-1),
        hovertemplate="<b>⚠️ Row #: %{customdata[0]}</b> (Cavity: %{customdata[2]})<br>Value: %{x:.5f}<br>Percent: %{customdata[1]:.1f}%<extra></extra>"
    ))
    fig.add_trace(go.Scatter(x=line_x, y=z_scores, mode='lines', name='Fit Line', line=dict(color='darkred', width=1.8)))

    fig.update_layout(
        title=dict(text=f"<b>Probability Plot of {col_name}{title_suffix}</b><br><sup>AD = {ad_stat:.3f}, P-Value = {ad_pval:.4f}</sup>", x=0.5, xanchor='center'),
        xaxis=dict(title="Measurement", tickformat=".4f", gridcolor="#EAEAEA"),
        yaxis=dict(title="Percent", tickmode='array', tickvals=tick_z, ticktext=[str(p) for p in tick_probs], gridcolor="#EAEAEA"),
        plot_bgcolor="white",
        paper_bgcolor="#E8E8E8",
        height=chart_height,
        margin=dict(l=60, r=40, t=65, b=50),
        showlegend=False
    )
    return fig, ad_stat, ad_pval, mean, std_overall, n

# ==============================================================================
# ส่วนแสดงผลหน้าเว็บ
# ==============================================================================
tab1, tab2, tab3 = st.tabs([
    "📦 1. Boxplot (พร้อมเส้น Spec)",
    "📈 2. Process Capability (Histogram & Cpk/Ppk)",
    "🎯 3. Probability Plot (เช็ก P-value & ชี้ดู Row ที่หลุด)"
])

# ----------------- TAB 1: BOXPLOT -----------------
with tab1:
    if "Show ทีละกราฟ" in view_mode:
        c_left, c_center, c_right = st.columns([1, 2.2, 1])
        with c_center:
            fig_b = create_boxplot(edited_df, selected_col, group_col, lsl_input, target_input, usl_input)
            st.plotly_chart(fig_b, use_container_width=True)
    else:
        st.subheader(f"📦 แสดง Boxplot ทั้งหมด ({len(cols_to_plot)} พอยต์)")
        grid_cols = st.columns(2)
        for idx, col_name in enumerate(cols_to_plot):
            c_lsl, c_target, c_usl = parse_spec_from_col(col_name)
            with grid_cols[idx % 2]:
                fig_b = create_boxplot(edited_df, col_name, group_col, c_lsl, c_target, c_usl)
                st.plotly_chart(fig_b, use_container_width=True)

# ----------------- TAB 2: PROCESS CAPABILITY -----------------
with tab2:
    if "Show ทีละกราฟ" in view_mode:
        fig_c, m = create_capability(edited_df, selected_col, group_col, cavity_filter,
                                     lsl_input, target_input, usl_input, subgroup_size)
        if m:
            col_l, col_m, col_r = st.columns([1.1, 2.5, 1.1])
            with col_l:
                st.markdown("##### 📋 Process Data")
                st.dataframe(pd.DataFrame({
                    "Metric": ["LSL", "Target", "USL", "Sample Mean", "Sample N", "StDev(Overall)", "StDev(Within)"],
                    "Value": [f"{lsl_input:.4f}", f"{target_input:.4f}", f"{usl_input:.4f}", f"{m['Mean']:.6f}", f"{m['N']}", f"{m['StDev(Overall)']:.7f}", f"{m['StDev(Within)']:.7f}"]
                }).set_index("Metric"), use_container_width=True)
            with col_m:
                st.plotly_chart(fig_c, use_container_width=True)

                st.markdown("##### 📊 Performance (PPM)")
                perf_df = pd.DataFrame({
                    "Performance": ["PPM < LSL", "PPM > USL", "PPM Total"],
                    "Observed": [f"{m['Obs_Below']:.2f}", f"{m['Obs_Above']:.2f}", f"{m['Obs_Total']:.2f}"],
                    "Expected Overall": [f"{m['Exp_Ovr_Below']:.2f}", f"{m['Exp_Ovr_Above']:.2f}", f"{m['Exp_Ovr_Total']:.2f}"],
                    "Expected Within": [f"{m['Exp_Wit_Below']:.2f}", f"{m['Exp_Wit_Above']:.2f}", f"{m['Exp_Wit_Total']:.2f}"]
                }).set_index("Performance")
                st.dataframe(perf_df, use_container_width=True)

            with col_r:
                st.markdown("##### 🏆 Capability Indices")
                st.dataframe(pd.DataFrame({
                    "Index": ["Pp", "PPL", "PPU", "Ppk", "Cpm", "Cp", "CPL", "CPU", "Cpk"],
                    "Value": [
                        f"{m['Pp']:.2f}",
                        f"{(m['Mean']-lsl_input)/(3*m['StDev(Overall)'] if m['StDev(Overall)'] > 0 else 1):.2f}",
                        f"{(usl_input-m['Mean'])/(3*m['StDev(Overall)'] if m['StDev(Overall)'] > 0 else 1):.2f}",
                        f"{m['Ppk']:.2f}",
                        f"{m['Cpm']:.2f}",
                        f"{m['Cp']:.2f}",
                        f"{(m['Mean']-lsl_input)/(3*m['StDev(Within)'] if m['StDev(Within)'] > 0 else 1):.2f}",
                        f"{(usl_input-m['Mean'])/(3*m['StDev(Within)'] if m['StDev(Within)'] > 0 else 1):.2f}",
                        f"{m['Cpk']:.2f}"
                    ]
                }).set_index("Index"), use_container_width=True)

            with st.expander("🔬 วินิจฉัย: เทียบกับค่าใน Minitab (เปิดดูว่าวิธีไหนตรง)", expanded=False):
                _d = get_filtered_data(edited_df, selected_col, group_col, cavity_filter)[selected_col]
                _w_df, _cpm_df = diagnose_capability(_d.values, lsl_input, target_input, usl_input, subgroup_size)
                st.caption(f"N = {len(_d)} | Mean = {_d.mean():.7f} | LSL/T/USL = {lsl_input} / {target_input} / {usl_input}")
                st.dataframe(_w_df.set_index("วิธีประมาณ σ"), use_container_width=True)
                st.dataframe(_cpm_df.set_index("สูตร Cpm"), use_container_width=True)
        else:
            st.warning("ข้อมูลไม่เพียงพอสำหรับการคำนวณในกลุ่มที่เลือก")
    else:
        st.subheader(f"📈 แสดง Process Capability ทั้งหมด ({len(cols_to_plot)} พอยต์ - {cavity_filter})")
        grid_cols = st.columns(2)
        for idx, col_name in enumerate(cols_to_plot):
            c_lsl, c_target, c_usl = parse_spec_from_col(col_name)
            fig_c, m = create_capability(edited_df, col_name, group_col, cavity_filter,
                                         c_lsl, c_target, c_usl, subgroup_size)
            if m:
                with grid_cols[idx % 2]:
                    st.plotly_chart(fig_c, use_container_width=True)
                    st.caption(f"**{col_name}** | N: {m['N']} | Mean: `{m['Mean']:.5f}` | **Cp:** `{m['Cp']:.2f}` | **Cpk:** `{m['Cpk']:.2f}` | **Ppk:** `{m['Ppk']:.2f}`")
                    st.divider()

# ----------------- TAB 3: PROBABILITY PLOT -----------------
with tab3:
    if "Show ทีละกราฟ" in view_mode:
        fig_p, ad_stat, ad_pval, mean, std, n = create_prob_plot(edited_df, selected_col, group_col, cavity_filter)
        if n >= 3:
            c1, c2 = st.columns([2.5, 1])
            with c1:
                st.plotly_chart(fig_p, use_container_width=True)
            with c2:
                st.markdown("##### 🎯 Normality Test")
                if ad_pval >= 0.05:
                    st.success(f"✅ **Normal Distribution**\n\n(P-Value = {ad_pval:.4f} ≥ 0.05)")
                else:
                    st.error(f"❌ **Non-Normal**\n\n(P-Value = {ad_pval:.4f} < 0.05)")
                st.metric("P-Value (Anderson-Darling)", f"{ad_pval:.4f}")
                st.metric("AD Statistic", f"{ad_stat:.3f}")
                st.metric("Mean / StDev", f"{mean:.5f} / {std:.6f}")
                st.info("💡 **ทริค:** เอาเมาส์ชี้จุดที่กระโดดออกจากเส้นเพื่อดูเลข **Row #** แล้วเลื่อนขึ้นไปแก้ตัวเลขที่แถวนั้นในตารางด้านบน กราฟจะอัปเดตทันที!")
        else:
            st.warning("ข้อมูลน้อยเกินไปสำหรับการรัน Probability Plot (ต้องการอย่างน้อย 3 แถว)")
    else:
        st.subheader(f"🎯 แสดง Probability Plot ทั้งหมด ({len(cols_to_plot)} พอยต์ - {cavity_filter})")
        grid_cols = st.columns(2)
        for idx, col_name in enumerate(cols_to_plot):
            fig_p, ad_stat, ad_pval, mean, std, n = create_prob_plot(edited_df, col_name, group_col, cavity_filter)
            if n >= 3:
                with grid_cols[idx % 2]:
                    st.plotly_chart(fig_p, use_container_width=True)
