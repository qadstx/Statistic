import streamlit as st
import pandas as pd
import numpy as np
from scipy import stats
from scipy.special import gammaln
import plotly.graph_objects as go
import re
from io import BytesIO
import zipfile

# --- ปรับหัวแอปให้คลีนแบบ Minimal ---
st.set_page_config(page_title="Minitab DIY", layout="wide")
st.title("Minitab DIY")

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

def fmt6(v):
    """แสดง 6 significant digits แบบ Minitab (ตัดศูนย์ท้ายทิ้ง)"""
    return np.format_float_positional(float(v), precision=6, unique=False, fractional=False, trim='-')

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
st.sidebar.header("📁 ข้อมูล (Data Input)")
uploaded_file = st.sidebar.file_uploader("อัปโหลดไฟล์ Excel/CSV", type=["xlsx", "csv"], label_visibility="collapsed")

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

if "editor_ver" not in st.session_state:
    st.session_state.editor_ver = 0

btn_col1, btn_col2 = st.sidebar.columns(2)
with btn_col1:
    if st.button("📥 โหลดข้อมูล", use_container_width=True):
        if uploaded_file is not None:
            if uploaded_file.name.endswith(".csv"):
                temp_df = pd.read_csv(uploaded_file)
            else:
                temp_df = pd.read_excel(uploaded_file)
            temp_df.index = np.arange(1, len(temp_df) + 1)
            temp_df.index.name = "Row"
            st.session_state.df = temp_df
            st.session_state.editor_ver += 1
with btn_col2:
    if st.button("🧹 ล้างตาราง", use_container_width=True):
        empty_df = pd.DataFrame({"B1_0.328 ± 0.0015": [np.nan]*10, "Cavity": [1]*10})
        empty_df.index = np.arange(1, len(empty_df) + 1)
        empty_df.index.name = "Row"
        st.session_state.df = empty_df
        st.session_state.editor_ver += 1

st.session_state.df.index = np.arange(1, len(st.session_state.df) + 1)
st.session_state.df.index.name = "Row"

with st.expander("📝 ตารางข้อมูล (คลิกแก้ตัวเลข / ก๊อปวางจาก Excel ได้ทันที)", expanded=True):
    _cfg = {"_index": st.column_config.NumberColumn("Row #", help="ลำดับแถวข้อมูล", format="%d")}
    for _c in st.session_state.df.columns:
        if str(_c).lower() != "cavity" and pd.api.types.is_numeric_dtype(st.session_state.df[_c]):
            _cfg[_c] = st.column_config.NumberColumn(format="%.5f", step=0.00001)
    edited_df = st.data_editor(
        st.session_state.df,
        num_rows="dynamic",
        use_container_width=True,
        hide_index=False,
        column_config=_cfg,
        key=f"data_editor_{st.session_state.editor_ver}"
    )
    edited_df.index = np.arange(1, len(edited_df) + 1)
    edited_df.index.name = "Row"

def to_excel(df):
    output = BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=True, sheet_name='Adjusted_Data')
    return output.getvalue()

st.sidebar.download_button(
    label="💾 เซฟข้อมูลที่แก้แล้ว (.xlsx)",
    data=to_excel(edited_df),
    file_name="adjusted_data.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    use_container_width=True
)

st.sidebar.divider()

# --- 2. ตั้งค่า (Settings) ---
st.sidebar.header("⚙️ ตั้งค่า (Settings)")
view_mode = st.sidebar.radio(
    "รูปแบบการแสดงผล:",
    ["🔍 Show ทีละกราฟ", "📜 Show ทั้งหมดทีเดียว"],
    horizontal=True,
    label_visibility="collapsed"
)

all_cols = edited_df.columns.tolist()
num_cols = [c for c in all_cols if str(c).lower() != "cavity"]

group_col = st.sidebar.selectbox(
    "แบ่งกลุ่มตาม (Group by):",
    ["ไม่แยกกลุ่ม"] + all_cols,
    index=all_cols.index("Cavity") + 1 if "Cavity" in all_cols else 0
)

cavity_filter = "ทั้งหมด (Combined)"
if group_col != "ไม่แยกกลุ่ม" and group_col in edited_df.columns:
    unique_cavities = ["ทั้งหมด (Combined)"] + list(edited_df[group_col].dropna().unique())
    cavity_filter = st.sidebar.selectbox("เลือกดูเฉพาะกลุ่ม:", unique_cavities)

subgroup_size = st.sidebar.number_input(
    "Subgroup size", min_value=1, value=32, step=1,
    help="1 = ใช้ Moving Range, > 1 = ใช้ Pooled StDev (แบบ Minitab)"
)

if "Show ทีละกราฟ" in view_mode:
    selected_col = st.sidebar.selectbox("เลือกพอยต์ที่ต้องการวิเคราะห์:", num_cols)
    auto_lsl, auto_target, auto_usl = parse_spec_from_col(selected_col)
    c1_sp, c2_sp, c3_sp = st.sidebar.columns(3)
    lsl_input = c1_sp.number_input("LSL", value=auto_lsl, format="%.5f", step=0.0001)
    target_input = c2_sp.number_input("Target", value=auto_target, format="%.5f", step=0.0001)
    usl_input = c3_sp.number_input("USL", value=auto_usl, format="%.5f", step=0.0001)
    cols_to_plot = [selected_col]
else:
    cols_to_plot = st.sidebar.multiselect("เลือกพอยต์ที่จะแสดงทั้งหมด:", num_cols, default=num_cols)
    st.sidebar.caption("💡 ดึงค่า Spec จากชื่อหัวคอลัมน์ให้อัตโนมัติ")

# --- 3. ตกแต่งกราฟ (ซ่อนใน Expander แบบคลีนๆ) ---
with st.sidebar.expander("🎨 ตกแต่งกราฟ (เปลี่ยนสี/ขนาด)"):
    col_c1, col_c2 = st.columns(2)
    with col_c1:
        box_fill_hex = st.color_picker("สีพื้น Boxplot", "#72A0E5")
    with col_c2:
        box_line_hex = st.color_picker("สีเส้นขอบ", "#333333")
    box_width_val = st.slider("ความอ้วนของกล่อง", 0.15, 0.70, 0.35, 0.05)
    box_gap_val = st.slider("ระยะห่างระหว่างกล่อง", 0.3, 2.5, 1.0, 0.1)
    chart_height = st.slider("ความสูงของกราฟ (px)", 380, 700, 480, 20)

# ฟังก์ชันกรองข้อมูล
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
    tick_pos, tick_txt = [], []
    n_g = valid_df[grp_col].nunique() if grp_col != "ไม่แยกกลุ่ม" else 1
    bw = min(box_width_val, box_gap_val * 0.95) if n_g > 1 else box_width_val

    if grp_col != "ไม่แยกกลุ่ม":
        for gi, (grp, grp_df) in enumerate(valid_df.groupby(grp_col)):
            pos = gi * box_gap_val
            tick_pos.append(pos)
            tick_txt.append(str(grp))
            fig.add_trace(go.Box(
                x=[pos] * len(grp_df),
                y=grp_df[col_name],
                name=f"{grp_col} {grp}",
                width=bw,
                boxpoints='outliers',
                customdata=grp_df["Row_ID"],
                hovertemplate="<b>Row #: %{customdata}</b><br>Value: %{y:.5f}<extra></extra>",
                fillcolor=fill_rgba,
                line=dict(color=box_line_hex, width=1.5),
                marker=dict(color="red", size=7, symbol="asterisk")
            ))
    else:
        tick_pos, tick_txt = [0], [col_name]
        fig.add_trace(go.Box(
            x=[0] * len(valid_df),
            y=valid_df[col_name],
            name=col_name,
            width=bw,
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

    n_b = len(tick_pos)
    x_span = max((n_b - 1) * box_gap_val + 1.0, 2.0) if n_b > 1 else 1.0
    x_mid = (tick_pos[0] + tick_pos[-1]) / 2 if n_b > 0 else 0

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
        xaxis=dict(tickmode='array', tickvals=tick_pos, ticktext=tick_txt,
                   range=[x_mid - x_span / 2, x_mid + x_span / 2], gridcolor="#EAEAEA"),
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
# ฟังก์ชันสร้าง Capability 
# ==============================================================================
def create_capability(df_in, col_name, grp_col, cav_val, lsl, target, usl, subgroup_size=1):
    valid_df = get_filtered_data(df_in, col_name, grp_col, cav_val)
    data = valid_df[col_name]
    n = len(data)
    if n == 0:
        return None, {}

    mean = data.mean()
    std_overall = data.std(ddof=1) if n > 1 else 0.0001

    std_within = calc_within(data.values, subgroup_size)
    if not np.isfinite(std_within) or std_within <= 0:
        std_within = std_overall

    pp = (usl - lsl) / (6 * std_overall) if std_overall > 0 else 0
    ppl = (mean - lsl) / (3 * std_overall) if std_overall > 0 else 0
    ppu = (usl - mean) / (3 * std_overall) if std_overall > 0 else 0
    ppk = min(ppl, ppu)

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

    d_min, d_max = float(data.min()), float(data.max())
    ax_lo, ax_hi = min(lsl, d_min), max(usl, d_max)
    span = ax_hi - ax_lo if ax_hi > ax_lo else 0.003
    raw = span / 8
    mag = 10 ** np.floor(np.log10(raw))
    step = next((k * mag for k in (1, 2, 4, 5, 10) if k * mag >= raw * 0.999), 10 * mag)
    dec = max(0, int(np.ceil(-np.log10(step) - 1e-9)))
    t0 = np.ceil(ax_lo / step - 1e-9) * step
    ticks = np.arange(t0, ax_hi + step * 1e-6, step)

    BIN_DIV = 8  
    bin_w = step / BIN_DIV
    b_start = t0 - bin_w / 2
    b_start += np.floor((d_min - b_start) / bin_w) * bin_w
    b_end = b_start + bin_w * (np.floor((d_max - b_start) / bin_w) + 1)
    x_grid = np.linspace(ax_lo, ax_hi, 400)

    RED, GREEN, GRAY = "#8B1A1A", "#0B6623", "#555555"
    FONT = "Segoe UI, Arial, sans-serif"

    fig = go.Figure()
    fig.add_trace(go.Histogram(
        x=data, histnorm='probability density', showlegend=False,
        xbins=dict(start=b_start, end=b_end, size=bin_w),
        marker_color="#7DA6D9", marker_line=dict(color="#1F3E7A", width=0.8)
    ))
    if std_overall > 0:
        fig.add_trace(go.Scatter(x=x_grid, y=stats.norm.pdf(x_grid, mean, std_overall),
                                 mode='lines', showlegend=False, line=dict(color=RED, width=1.8)))
    if std_within > 0:
        fig.add_trace(go.Scatter(x=x_grid, y=stats.norm.pdf(x_grid, mean, std_within),
                                 mode='lines', showlegend=False, line=dict(color=GRAY, width=1.8, dash='dash')))

    PLOT_TOP = 0.865
    for xv, colr, lbl in [(lsl, RED, "LSL"), (target, GREEN, "Target"), (usl, RED, "USL")]:
        fig.add_vline(x=xv, line_dash="dash", line_color=colr, line_width=1.2)
        fig.add_annotation(x=xv, xref="x", y=PLOT_TOP, yref="paper", text=lbl, showarrow=False,
                           yanchor="bottom", yshift=3, font=dict(color=colr, size=15, family=FONT))

    def _t(x, y, text, anchor="left", size=14, italic=False, bold=False):
        txt = f"<b>{text}</b>" if bold else text
        txt = f"<i>{txt}</i>" if italic else txt
        fig.add_annotation(x=x, y=y, xref="paper", yref="paper", text=txt, showarrow=False,
                           xanchor=anchor, yanchor="middle", font=dict(size=size, color="#222222", family=FONT))

    _t(0.5, 0.955, f"Process Capability Report for {col_name}", "center", 24)

    _t(0.155, 0.838, "Process Data", "center")
    for yy, (lb, vv) in zip(
        [0.812, 0.784, 0.758, 0.730, 0.702, 0.673, 0.646],
        [("LSL", fmt6(lsl)), ("Target", fmt6(target)), ("USL", fmt6(usl)), ("Sample Mean", fmt6(mean)),
         ("Sample N", f"{n}"), ("StDev(Overall)", fmt6(std_overall)), ("StDev(Within)", fmt6(std_within))]):
        _t(0.03, yy, lb)
        _t(0.152, yy, vv)

    fig.add_shape(type="line", xref="paper", yref="paper", x0=0.748, x1=0.800, y0=0.840, y1=0.840,
                  line=dict(color=RED, width=2))
    fig.add_shape(type="line", xref="paper", yref="paper", x0=0.748, x1=0.800, y0=0.812, y1=0.812,
                  line=dict(color=GRAY, width=2, dash="dash"))
    _t(0.809, 0.840, "Overall")
    _t(0.809, 0.812, "Within")

    _t(0.863, 0.759, "Overall Capability", "center")
    for yy, (lb, vv) in zip([0.731, 0.705, 0.677, 0.649, 0.621],
                            [("Pp", pp), ("PPL", ppl), ("PPU", ppu), ("Ppk", ppk), ("Cpm", cpm)]):
        _t(0.815, yy, lb)
        _t(0.878, yy, f"{vv:.2f}")
    _t(0.862, 0.586, "Potential (Within) Capability", "center")
    for yy, (lb, vv) in zip([0.552, 0.524, 0.496, 0.468],
                            [("Cp", cp), ("CPL", cpl), ("CPU", cpu), ("Cpk", cpk)]):
        _t(0.815, yy, lb)
        _t(0.878, yy, f"{vv:.2f}")

    col_x = [0.2227, 0.381, 0.5346]
    _t(0.284, 0.216, "Performance", "center")
    for cx, hd in zip(col_x, ["Observed", "Expected Overall", "Expected Within"]):
        _t(cx, 0.189, hd, "right")
    perf_rows = [
        ("PPM < LSL", [obs_below, exp_below_ovr, exp_below_wit], 0.162),
        ("PPM > USL", [obs_above, exp_above_ovr, exp_above_wit], 0.134),
        ("PPM Total", [obs_total, exp_total_ovr, exp_total_wit], 0.107),
    ]
    for lb, vals, yy in perf_rows:
        _t(0.036, yy, lb)
        for cx, vv in zip(col_x, vals):
            _t(cx, yy, f"{vv:.2f}", "right")

    _t(0.02, 0.025, "The actual process spread is represented by 6 sigma.", "left", 17, italic=True)

    fig.update_layout(
        xaxis=dict(domain=[0.306, 0.721], range=[ax_lo - span*0.12, ax_hi + span*0.12], tickmode='array', tickvals=ticks,
                   ticktext=[f"{t:.{dec}f}" for t in ticks], tickangle=-45, tickfont=dict(size=14, family=FONT),
                   showgrid=True, gridcolor="#E6E6E6", showline=True, linecolor="#888888", mirror=True),
        yaxis=dict(domain=[0.359, PLOT_TOP], showticklabels=False, showgrid=True, gridcolor="#E6E6E6",
                   zeroline=False, showline=True, linecolor="#888888", mirror=True, nticks=6),
        bargap=0, showlegend=False,
        plot_bgcolor="white", paper_bgcolor="#DDDDDD",
        height=720, margin=dict(l=0, r=0, t=0, b=0)
    )

    metrics = {
        "N": n, "Mean": mean, "StDev(Overall)": std_overall, "StDev(Within)": std_within,
        "Cp": cp, "Cpk": cpk, "Pp": pp, "Ppk": ppk, "Cpm": cpm,
        "PPL": ppl, "PPU": ppu, "CPL": cpl, "CPU": cpu,
        "Obs_Below": obs_below, "Obs_Above": obs_above, "Obs_Total": obs_total,
        "Exp_Ovr_Below": exp_below_ovr, "Exp_Ovr_Above": exp_above_ovr, "Exp_Ovr_Total": exp_total_ovr,
        "Exp_Wit_Below": exp_below_wit, "Exp_Wit_Above": exp_above_wit, "Exp_Wit_Total": exp_total_wit
    }
    return fig, metrics

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
# ฟังก์ชันสร้าง Probability Plot
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

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=sorted_df[col_name], y=z_scores, mode='markers', name='Data',
        marker=dict(size=9, color=box_fill_hex, line=dict(width=1.2, color=box_line_hex)),
        customdata=np.stack((sorted_df["Row_ID"], probs, sorted_df[grp_col] if grp_col != "ไม่แยกกลุ่ม" else ["-"]*n), axis=-1),
        hovertemplate="<b>⚠️ Row #: %{customdata[0]}</b> (Cavity: %{customdata[2]})<br>Value: %{x:.5f}<br>Percent: %{customdata[1]:.1f}%<extra></extra>"
    ))
    fig.add_trace(go.Scatter(x=line_x, y=z_scores, mode='lines', name='Fit Line', line=dict(color='darkred', width=1.8)))

    fig.update_layout(
        title=dict(text=f"<b>Probability Plot of {col_name}</b><br><sup>AD = {ad_stat:.3f}, P-Value = {ad_pval:.4f}</sup>", x=0.5, xanchor='center'),
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
    "📦 1. Boxplot",
    "📈 2. Process Capability",
    "🎯 3. Probability Plot"
])

# ----------------- TAB 1: BOXPLOT -----------------
with tab1:
    if "Show ทีละกราฟ" in view_mode:
        c_left, c_center, c_right = st.columns([1, 2.2, 1])
        with c_center:
            fig_b = create_boxplot(edited_df, selected_col, group_col, lsl_input, target_input, usl_input)
            st.plotly_chart(fig_b, use_container_width=True)
    else:
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
            st.plotly_chart(fig_c, use_container_width=True)

            with st.expander("🔬 วินิจฉัย: เทียบกับค่าใน Minitab", expanded=False):
                _d = get_filtered_data(edited_df, selected_col, group_col, cavity_filter)[selected_col]
                _w_df, _cpm_df = diagnose_capability(_d.values, lsl_input, target_input, usl_input, subgroup_size)
                st.caption(f"N = {len(_d)} | Mean = {_d.mean():.7f} | LSL/T/USL = {lsl_input} / {target_input} / {usl_input}")
                st.dataframe(_w_df.set_index("วิธีประมาณ σ"), use_container_width=True)
                st.dataframe(_cpm_df.set_index("สูตร Cpm"), use_container_width=True)
        else:
            st.warning("ข้อมูลไม่เพียงพอสำหรับการคำนวณในกลุ่มที่เลือก")
    else:
        grid_cols = st.columns(1)
        for idx, col_name in enumerate(cols_to_plot):
            c_lsl, c_target, c_usl = parse_spec_from_col(col_name)
            fig_c, m = create_capability(edited_df, col_name, group_col, cavity_filter,
                                         c_lsl, c_target, c_usl, subgroup_size)
            if m:
                with grid_cols[0]:
                    st.plotly_chart(fig_c, use_container_width=True)
                    st.divider()

# ----------------- TAB 3: PROBABILITY PLOT -----------------
with tab3:
    if "Show ทีละกราฟ" in view_mode:
        fig_p, ad_stat, ad_pval, mean, std, n = create_prob_plot(edited_df, selected_col, group_col, cavity_filter)
        if n >= 3:
            c1, c2 = st.columns([2.5, 1])
            with c1:
                event = st.plotly_chart(fig_p, use_container_width=True, on_select="rerun",
                                        selection_mode="points",
                                        key=f"prob_plot_single_{st.session_state.editor_ver}")
            with c2:
                st.markdown("##### 🎯 Normality Test")
                if ad_pval >= 0.05:
                    st.success(f"✅ **Normal Distribution**\n\n(P-Value = {ad_pval:.4f} ≥ 0.05)")
                else:
                    st.error(f"❌ **Non-Normal**\n\n(P-Value = {ad_pval:.4f} < 0.05)")
                st.metric("P-Value (Anderson-Darling)", f"{ad_pval:.4f}")
                st.metric("AD Statistic", f"{ad_stat:.3f}")
                st.metric("Mean / StDev", f"{mean:.5f} / {std:.6f}")
                st.info("💡 **ทริค:** คลิกจุดบนกราฟ (กด Shift ค้างเพื่อเลือกหลายจุด) แล้วใส่ค่าใหม่ในช่องด้านล่าง กดอัปเดต ค่าจะไปแก้ในตารางด้านบนให้ทันที")

            # --- คลิกจุด -> แก้ค่า -> อัปเดตตาราง ---
            try:
                _pts = event["selection"]["points"]
            except Exception:
                _pts = []
            _sd = get_filtered_data(edited_df, selected_col, group_col, cavity_filter)
            _sd = _sd.sort_values(by=selected_col).reset_index(drop=True)
            _sel_ids = []
            for _p in _pts:
                if _p.get("curve_number", 0) != 0:
                    continue
                _i = _p.get("point_index", _p.get("point_number"))
                if _i is not None and 0 <= int(_i) < len(_sd):
                    _rid = int(_sd.loc[int(_i), "Row_ID"])
                    if _rid not in _sel_ids:
                        _sel_ids.append(_rid)

            if _sel_ids:
                st.markdown("##### ✏️ แก้ค่าจุดที่เลือก")
                _new_vals = {}
                _ecols = st.columns(min(len(_sel_ids), 4))
                for _k, _rid in enumerate(_sel_ids[:8]):
                    _cur = float(edited_df.loc[_rid, selected_col])
                    with _ecols[_k % len(_ecols)]:
                        _new_vals[_rid] = st.number_input(
                            f"Row #{_rid}", value=_cur, format="%.5f", step=0.00001,
                            key=f"newval_{selected_col}_{_rid}_{st.session_state.editor_ver}"
                        )
                if st.button("✅ อัปเดตค่าลงตาราง", type="primary"):
                    _new_df = edited_df.copy()
                    for _rid, _v in _new_vals.items():
                        _new_df.loc[_rid, selected_col] = _v
                    st.session_state.df = _new_df
                    st.session_state.editor_ver += 1
                    st.rerun()
        else:
            st.warning("ข้อมูลน้อยเกินไปสำหรับการรัน Probability Plot (ต้องการอย่างน้อย 3 แถว)")
    else:
        grid_cols = st.columns(2)
        for idx, col_name in enumerate(cols_to_plot):
            fig_p, ad_stat, ad_pval, mean, std, n = create_prob_plot(edited_df, col_name, group_col, cavity_filter)
            if n >= 3:
                with grid_cols[idx % 2]:
                    st.plotly_chart(fig_p, use_container_width=True)

# ==============================================================================
# Export กราฟเป็นรูปภาพ (จัดเรียงอยู่ Sidebar ด้านล่างสุด)
# ==============================================================================
EXPORT_TYPES = ["Boxplot", "Process Capability", "Probability Plot"]
EXPORT_FILE = {"Boxplot": "boxplot", "Process Capability": "process_capability", "Probability Plot": "probability_plot"}

def build_export_zips(points, types, img_w, img_h):
    cav_tag = "" if cavity_filter == "ทั้งหมด (Combined)" else f"_Cavity{cavity_filter}"
    files = {t: [] for t in types}
    for i, col_name in enumerate(points, 1):
        if "Show ทีละกราฟ" in view_mode and col_name == selected_col:
            c_lsl, c_target, c_usl = lsl_input, target_input, usl_input
        else:
            c_lsl, c_target, c_usl = parse_spec_from_col(col_name)
        safe = re.sub(r"[^0-9A-Za-z._-]+", "_", str(col_name)).strip("_")
        base = f"{i:02d}_{safe}{cav_tag}"

        if "Boxplot" in types:
            f = create_boxplot(edited_df, col_name, group_col, c_lsl, c_target, c_usl)
            files["Boxplot"].append((f"{base}_boxplot.png",
                                     f.to_image(format="png", width=img_w, height=img_h, scale=2)))
        if "Process Capability" in types:
            f, _m = create_capability(edited_df, col_name, group_col, cavity_filter,
                                      c_lsl, c_target, c_usl, subgroup_size)
            if f is not None:
                files["Process Capability"].append((f"{base}_capability.png",
                                                    f.to_image(format="png", width=1000, height=720, scale=2)))
        if "Probability Plot" in types:
            f = create_prob_plot(edited_df, col_name, group_col, cavity_filter)[0]
            if f is not None:
                files["Probability Plot"].append((f"{base}_probplot.png",
                                                  f.to_image(format="png", width=img_w, height=img_h, scale=2)))

    zips = {}
    for t, items in files.items():
        buf = BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for name, b in items:
                zf.writestr(name, b)
        zips[t] = buf.getvalue()
    if len(types) > 1:
        buf = BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for t, items in files.items():
                for name, b in items:
                    zf.writestr(f"{EXPORT_FILE[t]}/{name}", b)
        zips["ทั้งหมด"] = buf.getvalue()
    return zips

with st.sidebar:
    st.header("🖼️ ดาวน์โหลดรูปภาพ")
    export_cols = st.multiselect("พอยต์ที่จะ export:", num_cols, default=num_cols)
    export_types = st.multiselect("ชนิดกราฟ:", EXPORT_TYPES, default=EXPORT_TYPES)
    ec1, ec2 = st.columns(2)
    with ec1:
        export_w = st.number_input("กว้าง (px)", min_value=300, max_value=1600, value=600, step=50)
    with ec2:
        export_h = st.number_input("สูง (px)", min_value=300, max_value=1200, value=480, step=20)
    st.caption("ขนาดใช้กับ Boxplot และ Prob Plot ส่วน Capability ใช้ 1000×720 คงที่")
    if st.button("🖼️ สร้างไฟล์ ZIP", use_container_width=True):
        if not export_cols or not export_types:
            st.warning("เลือกพอยต์และชนิดกราฟอย่างน้อยอย่างละ 1")
        else:
            try:
                with st.spinner(f"กำลังสร้างรูป {len(export_cols)} พอยต์..."):
                    st.session_state.export_zips = build_export_zips(
                        export_cols, export_types, int(export_w), int(export_h))
            except Exception as e:
                st.session_state.pop("export_zips", None)
                st.error(f"สร้างรูปไม่สำเร็จ: {e}\n\nลอง: pip install kaleido==0.2.1 plotly==5.24.1")
    if "export_zips" in st.session_state:
        for _t_name, _bytes in st.session_state.export_zips.items():
            _fname = "all_charts.zip" if _t_name == "ทั้งหมด" else f"{EXPORT_FILE[_t_name]}.zip"
            st.download_button(f"⬇️ {_t_name} (.zip)", data=_bytes, file_name=_fname,
                               mime="application/zip", use_container_width=True, key=f"dl_{_t_name}")
